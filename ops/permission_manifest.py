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
import sys
from typing import Any


BATCHES = frozenset({"GATE-02A", "GATE-02B", "GATE-02C", "GATE-02D"})
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MODE_RE = re.compile(r"^0[0-7]{3}$")
GLOB_CHARACTERS = frozenset("*?[")
INSTALLED_CONTROL = Path("/usr/local/libexec/sealai/permission-manifest.py")


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


def _open_object(path: Path) -> tuple[int, os.stat_result]:
    if not path.is_absolute() or any(
        character in str(path) for character in GLOB_CHARACTERS
    ):
        _fail("paths must be absolute and may not contain glob syntax")
    _assert_no_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        lexical = path.lstat()
        if stat.S_ISLNK(lexical.st_mode):
            _fail("symlink objects are forbidden")
        if stat.S_ISDIR(lexical.st_mode):
            flags |= getattr(os, "O_DIRECTORY", 0)
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
    path: str, descriptor: int, metadata: os.stat_result
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
    if object_type == "file":
        value["sha256"] = _sha256_descriptor(descriptor)
    return value


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
    try:
        for candidate in objects:
            if not isinstance(candidate, dict) or set(candidate) != {
                "path",
                "runtime_consumers",
                "target_uid",
                "target_gid",
                "target_mode",
            }:
                _fail("generation object fields are not exact")
            path_value = candidate.get("path")
            if not isinstance(path_value, str) or path_value in paths:
                _fail("generation paths must be unique strings")
            paths.add(path_value)
            consumers = _validate_consumers(candidate.get("runtime_consumers"))
            _validate_target(candidate)
            descriptor, metadata = _open_object(Path(path_value))
            descriptors.append(descriptor)
            identity = (metadata.st_dev, metadata.st_ino)
            if identity in identities:
                _fail("generation objects must have unique identities")
            identities.add(identity)
            generated.append(
                _fingerprint(path_value, descriptor, metadata)
                | {
                    "runtime_consumers": consumers,
                    "target_uid": candidate["target_uid"],
                    "target_gid": candidate["target_gid"],
                    "target_mode": candidate["target_mode"],
                }
            )
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
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
    for item in objects:
        if not isinstance(item, dict):
            _fail("permission object must be an object")
        expected = expected_base | ({"sha256"} if item.get("type") == "file" else set())
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
        if item["type"] == "file" and (
            not isinstance(item.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        ):
            _fail("permission object hash is invalid")
        _validate_consumers(item.get("runtime_consumers"))
        _validate_target(item)
    return objects


def validate_manifest(
    manifest: dict[str, Any],
) -> list[tuple[int, dict[str, Any], os.stat_result]]:
    objects = _validate_manifest_shape(manifest)
    opened: list[tuple[int, dict[str, Any], os.stat_result]] = []
    identities: set[tuple[int, int]] = set()
    try:
        for item in objects:
            descriptor, metadata = _open_object(Path(item["path"]))
            opened.append((descriptor, item, metadata))
            identity = (metadata.st_dev, metadata.st_ino)
            if identity in identities:
                _fail("permission object identity is duplicated")
            identities.add(identity)
            actual = _fingerprint(item["path"], descriptor, metadata)
            expected = {name: item[name] for name in actual}
            if actual != expected:
                _fail("permission object drift detected")
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

        for descriptor, item, _ in opened:
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
