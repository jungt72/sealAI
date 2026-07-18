#!/usr/bin/env python3
"""Object-exact, fail-closed permission change engine for GATE-02."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any


BATCHES = frozenset({"GATE-02A", "GATE-02B", "GATE-02C", "GATE-02D", "GATE-02E"})
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MODE_RE = re.compile(r"^0[0-7]{3}$")
GLOB_CHARACTERS = frozenset("*?[")
INSTALLED_CONTROL = Path("/usr/local/libexec/sealai/permission-manifest.py")
GATE02E_KINDS = frozenset(
    {
        "public_certificate",
        "private_key",
        "renewal_config",
        "acme_account_metadata",
        "directory",
    }
)
GATE02E_FIELDS = {
    "material_kind",
    "lineage",
    "certbot_managed",
    "nginx_referenced",
    "renewal_config_path",
    "public_certificate_fingerprint",
}
SAFE_CHILD_ENV = {
    "HOME": "/nonexistent",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}


class PermissionManifestError(RuntimeError):
    """The requested batch cannot be proven safe."""


def _fail(message: str) -> None:
    raise PermissionManifestError(message)


def _read_json_nofollow(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PermissionManifestError("manifest is unavailable or unsafe") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024 * 1024:
            _fail("manifest must be a bounded regular file")
        raw = b""
        while len(raw) <= 1024 * 1024:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PermissionManifestError("manifest is invalid JSON") from exc
    if not isinstance(value, dict):
        _fail("manifest root must be an object")
    return value


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _control_sha256() -> str:
    digest = hashlib.sha256()
    with Path(__file__).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_installed_control(path: Path = Path(__file__)) -> None:
    invoked = Path(os.path.abspath(path))
    if invoked != INSTALLED_CONTROL:
        _fail("apply requires the fixed installed control")
    current = Path(invoked.anchor)
    for part in invoked.parts[1:]:
        current /= part
        metadata = current.lstat()
        is_leaf = current == invoked
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (is_leaf and not stat.S_ISREG(metadata.st_mode))
            or (not is_leaf and not stat.S_ISDIR(metadata.st_mode))
        ):
            _fail("installed control path is unsafe")


def _object_type(metadata: os.stat_result) -> str:
    if stat.S_ISREG(metadata.st_mode):
        return "file"
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    _fail("only regular files and directories are supported")


def _assert_no_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise PermissionManifestError("path component is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            _fail("symlink path components are forbidden")


def _open_object(
    path: Path, *, read_content: bool = True
) -> tuple[int, os.stat_result]:
    if not path.is_absolute() or any(
        character in str(path) for character in GLOB_CHARACTERS
    ):
        _fail("paths must be absolute and may not contain glob syntax")
    _assert_no_symlink_components(path)
    access = os.O_RDONLY if read_content else os.O_WRONLY
    flags = access | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        lexical = path.lstat()
        if stat.S_ISLNK(lexical.st_mode):
            _fail("symlink objects are forbidden")
        if stat.S_ISDIR(lexical.st_mode):
            flags = (
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_DIRECTORY", 0)
            )
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PermissionManifestError("object is unavailable or unsafe") from exc
    opened = os.fstat(descriptor)
    if (lexical.st_dev, lexical.st_ino) != (opened.st_dev, opened.st_ino):
        os.close(descriptor)
        _fail("object identity changed while opening")
    _object_type(opened)
    return descriptor, opened


def _fingerprint(
    path: str,
    descriptor: int,
    metadata: os.stat_result,
    *,
    include_hash: bool = True,
) -> dict[str, Any]:
    object_type = _object_type(metadata)
    value: dict[str, Any] = {
        "path": path,
        "type": object_type,
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "mode": f"0{stat.S_IMODE(metadata.st_mode):03o}",
    }
    if object_type == "file" and include_hash:
        value["sha256"] = _sha256_descriptor(descriptor)
    return value


def _certificate_fingerprint(descriptor: int) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = b""
    while chunk := os.read(descriptor, 1024 * 1024):
        raw += chunk
        if len(raw) > 4 * 1024 * 1024:
            _fail("public certificate is oversized")
    os.lseek(descriptor, 0, os.SEEK_SET)
    result = subprocess.run(
        ["/usr/bin/openssl", "x509", "-outform", "DER"],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=SAFE_CHILD_ENV,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        _fail("public certificate is invalid")
    return hashlib.sha256(result.stdout).hexdigest()


def _validate_consumers(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        _fail("runtime_consumers must contain unique non-empty names")
    return list(value)


def _validate_target(value: dict[str, Any]) -> None:
    if not isinstance(value["target_uid"], int) or value["target_uid"] < 0:
        _fail("target_uid is invalid")
    if not isinstance(value["target_gid"], int) or value["target_gid"] < 0:
        _fail("target_gid is invalid")
    if not isinstance(value["target_mode"], str) or not MODE_RE.fullmatch(
        value["target_mode"]
    ):
        _fail("target_mode is invalid")


def _validate_gate02e_fields(value: dict[str, Any]) -> None:
    kind = value.get("material_kind")
    lineage = value.get("lineage")
    renewal_path = value.get("renewal_config_path")
    fingerprint = value.get("public_certificate_fingerprint")
    if kind not in GATE02E_KINDS:
        _fail("GATE-02E material_kind is invalid")
    if (
        not isinstance(lineage, str)
        or not lineage.strip()
        or "/" in lineage
        or "\\" in lineage
    ):
        _fail("GATE-02E lineage is invalid")
    if value.get("certbot_managed") is not True:
        _fail("GATE-02E objects must be Certbot managed")
    if not isinstance(value.get("nginx_referenced"), bool):
        _fail("GATE-02E nginx reference flag is invalid")
    if (
        not isinstance(renewal_path, str)
        or not Path(renewal_path).is_absolute()
        or any(character in renewal_path for character in GLOB_CHARACTERS)
    ):
        _fail("GATE-02E renewal configuration path is invalid")
    if not isinstance(fingerprint, str) or not re.fullmatch(
        r"[0-9a-f]{64}", fingerprint
    ):
        _fail("GATE-02E public certificate fingerprint is invalid")
    consumers = _validate_consumers(value.get("runtime_consumers"))
    if "certbot" not in consumers:
        _fail("GATE-02E requires the Certbot runtime consumer")
    if value["nginx_referenced"] != ("nginx" in consumers):
        _fail("GATE-02E Nginx consumer mapping is inconsistent")
    target_mode = value.get("target_mode")
    if kind in {"private_key", "renewal_config", "acme_account_metadata"}:
        if target_mode != "0600":
            _fail("GATE-02E private material target mode is invalid")
    elif kind == "public_certificate":
        if target_mode != "0644":
            _fail("GATE-02E public certificate target mode is invalid")
    elif target_mode not in {"0700", "0750", "0755"}:
        _fail("GATE-02E directory target mode is invalid")


def _validate_gate02e_relationships(objects: list[dict[str, Any]]) -> None:
    lineages: dict[str, list[dict[str, Any]]] = {}
    for item in objects:
        lineages.setdefault(str(item["lineage"]), []).append(item)
    for lineage, members in lineages.items():
        kinds = {str(item["material_kind"]) for item in members}
        required = {"public_certificate", "private_key", "renewal_config"}
        if not required.issubset(kinds):
            _fail(f"GATE-02E lineage is incomplete: {lineage}")
        renewal_paths = {str(item["renewal_config_path"]) for item in members}
        fingerprints = {str(item["public_certificate_fingerprint"]) for item in members}
        if len(renewal_paths) != 1 or len(fingerprints) != 1:
            _fail("GATE-02E lineage bindings are inconsistent")
        renewal_path = next(iter(renewal_paths))
        if not any(
            item["material_kind"] == "renewal_config" and item["path"] == renewal_path
            for item in members
        ):
            _fail("GATE-02E renewal configuration object is missing")
        for item in members:
            if item["material_kind"] in {"public_certificate", "private_key"} and (
                item["nginx_referenced"] is not True
                or "nginx" not in item["runtime_consumers"]
            ):
                _fail("GATE-02E live TLS objects require the Nginx consumer")


def generate_manifest(request_path: Path) -> dict[str, Any]:
    request = _read_json_nofollow(request_path)
    if set(request) != {"batch", "objects"} or request.get("batch") not in BATCHES:
        _fail("generation request is not an exact GATE-02 batch")
    objects = request.get("objects")
    if not isinstance(objects, list) or not objects:
        _fail("generation request must contain objects")
    paths: set[str] = set()
    identities: set[tuple[int, int]] = set()
    generated: list[dict[str, Any]] = []
    descriptors: list[int] = []
    gate02e = request["batch"] == "GATE-02E"
    try:
        for candidate in objects:
            expected_fields = {
                "path",
                "runtime_consumers",
                "target_uid",
                "target_gid",
                "target_mode",
            } | (GATE02E_FIELDS if gate02e else set())
            if not isinstance(candidate, dict) or set(candidate) != expected_fields:
                _fail("generation object fields are not exact")
            path_value = candidate.get("path")
            if not isinstance(path_value, str) or path_value in paths:
                _fail("generation paths must be unique strings")
            paths.add(path_value)
            consumers = _validate_consumers(candidate.get("runtime_consumers"))
            _validate_target(candidate)
            if gate02e:
                _validate_gate02e_fields(candidate)
            private_key = gate02e and candidate["material_kind"] == "private_key"
            descriptor, metadata = _open_object(
                Path(path_value), read_content=not private_key
            )
            descriptors.append(descriptor)
            identity = (metadata.st_dev, metadata.st_ino)
            if identity in identities:
                _fail("generation objects must have unique identities")
            identities.add(identity)
            generated_item = _fingerprint(
                path_value,
                descriptor,
                metadata,
                include_hash=not private_key,
            ) | {
                "runtime_consumers": consumers,
                "target_uid": candidate["target_uid"],
                "target_gid": candidate["target_gid"],
                "target_mode": candidate["target_mode"],
            }
            if gate02e:
                generated_item |= {
                    field: candidate[field] for field in sorted(GATE02E_FIELDS)
                }
                if candidate["material_kind"] == "public_certificate":
                    actual_fingerprint = _certificate_fingerprint(descriptor)
                    if (
                        actual_fingerprint
                        != candidate["public_certificate_fingerprint"]
                    ):
                        _fail("GATE-02E public certificate fingerprint drift")
                    generated_item["public_certificate_fingerprint"] = (
                        actual_fingerprint
                    )
            generated.append(generated_item)
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
    if gate02e:
        _validate_gate02e_relationships(generated)
    return {
        "schema_version": 1,
        "gate_id": request["batch"],
        "created_at": dt.datetime.now(dt.timezone.utc).strftime(UTC_FORMAT),
        "control_sha256": _control_sha256(),
        "objects": generated,
    }


def _validate_manifest_shape(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if set(manifest) != {
        "schema_version",
        "gate_id",
        "created_at",
        "control_sha256",
        "objects",
    }:
        _fail("permission manifest fields are not exact")
    if manifest.get("schema_version") != 1 or manifest.get("gate_id") not in BATCHES:
        _fail("permission manifest gate is invalid")
    try:
        dt.datetime.strptime(str(manifest.get("created_at")), UTC_FORMAT)
    except ValueError as exc:
        raise PermissionManifestError("created_at is invalid") from exc
    if manifest.get("control_sha256") != _control_sha256():
        _fail("permission control fingerprint drift")
    objects = manifest.get("objects")
    if not isinstance(objects, list) or not objects:
        _fail("permission manifest must contain objects")
    expected_base = {
        "path",
        "type",
        "device",
        "inode",
        "uid",
        "gid",
        "mode",
        "runtime_consumers",
        "target_uid",
        "target_gid",
        "target_mode",
    }
    paths: set[str] = set()
    gate02e = manifest["gate_id"] == "GATE-02E"
    for item in objects:
        if not isinstance(item, dict):
            _fail("permission object must be an object")
        include_hash = item.get("type") == "file" and not (
            gate02e and item.get("material_kind") == "private_key"
        )
        expected = (
            expected_base
            | (GATE02E_FIELDS if gate02e else set())
            | ({"sha256"} if include_hash else set())
        )
        if set(item) != expected or item.get("type") not in {"file", "directory"}:
            _fail("permission object fields are not exact")
        path_value = item.get("path")
        if not isinstance(path_value, str) or path_value in paths:
            _fail("permission object paths must be unique strings")
        paths.add(path_value)
        if any(
            not isinstance(item.get(name), int) or item[name] < 0
            for name in ("device", "inode", "uid", "gid")
        ):
            _fail("permission object identity is invalid")
        if not isinstance(item.get("mode"), str) or not MODE_RE.fullmatch(item["mode"]):
            _fail("permission object mode is invalid")
        if include_hash and (
            not isinstance(item.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        ):
            _fail("permission object hash is invalid")
        _validate_consumers(item.get("runtime_consumers"))
        _validate_target(item)
        if gate02e:
            _validate_gate02e_fields(item)
            if (item["material_kind"] == "directory") != (item["type"] == "directory"):
                _fail("GATE-02E material kind and object type disagree")
    if gate02e:
        _validate_gate02e_relationships(objects)
    return objects


def validate_manifest(
    manifest: dict[str, Any],
) -> list[tuple[int, dict[str, Any], os.stat_result]]:
    objects = _validate_manifest_shape(manifest)
    gate02e = manifest["gate_id"] == "GATE-02E"
    opened: list[tuple[int, dict[str, Any], os.stat_result]] = []
    identities: set[tuple[int, int]] = set()
    try:
        for item in objects:
            private_key = gate02e and item.get("material_kind") == "private_key"
            descriptor, metadata = _open_object(
                Path(item["path"]), read_content=not private_key
            )
            opened.append((descriptor, item, metadata))
            identity = (metadata.st_dev, metadata.st_ino)
            if identity in identities:
                _fail("permission object identity is duplicated")
            identities.add(identity)
            actual = _fingerprint(
                item["path"],
                descriptor,
                metadata,
                include_hash=not private_key,
            )
            expected = {name: item[name] for name in actual}
            if actual != expected:
                _fail("permission object drift detected")
            if gate02e and item.get("material_kind") == "public_certificate":
                if (
                    _certificate_fingerprint(descriptor)
                    != item["public_certificate_fingerprint"]
                ):
                    _fail("GATE-02E public certificate fingerprint drift")
        for descriptor, item, metadata in opened:
            lexical = Path(item["path"]).lstat()
            if (lexical.st_dev, lexical.st_ino) != (metadata.st_dev, metadata.st_ino):
                _fail("permission object identity changed before mutation")
        return opened
    except Exception:
        for descriptor, _, _ in opened:
            os.close(descriptor)
        raise


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        _fail("output path already exists")
    if not path.is_absolute():
        _fail("output path must be absolute")
    _assert_no_symlink_components(path.parent)
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) & 0o022
    ):
        _fail("output directory is unsafe")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def apply_manifest(
    manifest: dict[str, Any], rollback_path: Path, *, require_root: bool = True
) -> dict[str, Any]:
    if require_root and os.geteuid() != 0:
        _fail("permission apply requires root")
    if require_root:
        _assert_installed_control()
    opened = validate_manifest(manifest)
    try:
        rollback_objects: list[dict[str, Any]] = []
        for descriptor, item, metadata in opened:
            expected_after = dict(item)
            expected_after["uid"] = item["target_uid"]
            expected_after["gid"] = item["target_gid"]
            expected_after["mode"] = item["target_mode"]
            expected_after["target_uid"] = metadata.st_uid
            expected_after["target_gid"] = metadata.st_gid
            expected_after["target_mode"] = f"0{stat.S_IMODE(metadata.st_mode):03o}"
            rollback_objects.append(expected_after)
        rollback = {
            "schema_version": 1,
            "gate_id": manifest["gate_id"],
            "created_at": dt.datetime.now(dt.timezone.utc).strftime(UTC_FORMAT),
            "control_sha256": manifest["control_sha256"],
            "objects": rollback_objects,
        }
        _write_private_json(rollback_path, rollback)

        mutation_started = False
        try:
            for descriptor, item, _ in opened:
                mutation_started = True
                os.fchown(descriptor, item["target_uid"], item["target_gid"])
                os.fchmod(descriptor, int(item["target_mode"], 8))
            for descriptor, item, _ in opened:
                metadata = os.fstat(descriptor)
                if (
                    metadata.st_uid != item["target_uid"]
                    or metadata.st_gid != item["target_gid"]
                    or stat.S_IMODE(metadata.st_mode) != int(item["target_mode"], 8)
                ):
                    _fail("permission postcondition failed")
        except BaseException as apply_error:
            if mutation_started:
                try:
                    for descriptor, _, original in reversed(opened):
                        os.fchown(descriptor, original.st_uid, original.st_gid)
                        os.fchmod(descriptor, stat.S_IMODE(original.st_mode))
                    for descriptor, _, original in opened:
                        restored = os.fstat(descriptor)
                        if (
                            restored.st_uid != original.st_uid
                            or restored.st_gid != original.st_gid
                            or stat.S_IMODE(restored.st_mode)
                            != stat.S_IMODE(original.st_mode)
                        ):
                            _fail("permission rollback verification failed")
                except BaseException as rollback_error:
                    raise PermissionManifestError(
                        "permission rollback failed; owner incident review required"
                    ) from rollback_error
            raise PermissionManifestError(
                "permission apply failed and was rolled back"
            ) from apply_error
        return rollback
    finally:
        for descriptor, _, _ in opened:
            os.close(descriptor)


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--request", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    for name in ("validate", "dry-run"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--manifest", type=Path, required=True)
    apply.add_argument("--rollback-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_manifest(args.request)
            _write_private_json(args.output, manifest)
            _print(
                {
                    "allowed": True,
                    "operation": "generate",
                    "objects": len(manifest["objects"]),
                }
            )
            return 0
        manifest = _read_json_nofollow(args.manifest)
        if args.command in {"validate", "dry-run"}:
            opened = validate_manifest(manifest)
            for descriptor, _, _ in opened:
                os.close(descriptor)
            _print(
                {
                    "allowed": True,
                    "operation": args.command,
                    "objects": len(manifest["objects"]),
                    "mutation": False,
                }
            )
            return 0
        apply_manifest(manifest, args.rollback_manifest)
        _print(
            {
                "allowed": True,
                "operation": "apply",
                "objects": len(manifest["objects"]),
                "rollback_manifest_written": True,
            }
        )
        return 0
    except (PermissionManifestError, OSError) as exc:
        _print({"allowed": False, "reason": str(exc)})
        return 78


if __name__ == "__main__":
    sys.exit(main())
