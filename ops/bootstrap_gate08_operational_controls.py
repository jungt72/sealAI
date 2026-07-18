#!/usr/bin/python3 -I
"""Hash-bound GATE-08 bootstrap for fixed operational control paths."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from typing import Any, NoReturn, Sequence


APPROVAL_PATH = Path("/etc/sealai/approvals/gate-08-operational-controls.json")
SELF_ARTIFACT = "ops/bootstrap_gate08_operational_controls.py"
GATE_ARTIFACT = "ops/production_release_gate.py"
STATE_ARTIFACT = "ops/production-release-state.json"
LIVE_PRODUCTION_REPO = Path("/home/thorsten/sealai")
ROLLBACK_ROOT = Path("/var/lib/sealai-operational-controls/rollbacks")
RECEIPT_ROOT = Path("/var/lib/sealai-operational-controls/receipts")
ARTIFACTS = frozenset(
    {
        "docs/ops/operational-control-install.md",
        "docs/ops/p0-operational-gate-unblock.md",
        "docs/ops/production-release-freeze.md",
        SELF_ARTIFACT,
        "ops/credential_cutover.py",
        "ops/install-operational-controls.sh",
        "ops/permission_manifest.py",
        STATE_ARTIFACT,
        GATE_ARTIFACT,
        "ops/schemas/credential-cutover-approval.schema.json",
        "ops/schemas/gate08-operational-controls.schema.json",
        "ops/schemas/permission-manifest.schema.json",
    }
)


@dataclass(frozen=True)
class TargetSpec:
    source: str
    target: Path
    mode: int


TARGET_SPECS = (
    TargetSpec(
        "ops/credential_cutover.py",
        Path("/usr/local/libexec/sealai/credential-cutover.py"),
        0o755,
    ),
    TargetSpec(
        "ops/permission_manifest.py",
        Path("/usr/local/libexec/sealai/permission-manifest.py"),
        0o755,
    ),
    TargetSpec(
        "ops/schemas/credential-cutover-approval.schema.json",
        Path("/usr/local/share/sealai/schemas/credential-cutover-approval.schema.json"),
        0o644,
    ),
    TargetSpec(
        "ops/schemas/permission-manifest.schema.json",
        Path("/usr/local/share/sealai/schemas/permission-manifest.schema.json"),
        0o644,
    ),
)
INSTALL_TARGETS = {spec.source: str(spec.target) for spec in TARGET_SPECS}
TARGET_MODES = {str(spec.target): f"0{spec.mode:03o}" for spec in TARGET_SPECS}
APPROVAL_KEYS = {
    "schema_version",
    "gate_id",
    "operation",
    "decision",
    "scope",
    "approval_id",
    "owner",
    "approved_at",
    "expires_at",
    "source_git_sha",
    "artifact_sha256",
    "install_targets",
    "target_preconditions",
}
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CHILD_ENV = {
    "HOME": "/root",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}
GIT_ENV = {
    **CHILD_ENV,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ALLOW_PROTOCOL": "file",
    "GIT_PROTOCOL_FROM_USER": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}


class BootstrapDenied(RuntimeError):
    """The install cannot prove its authorization or rollback safety."""


def _deny(message: str) -> NoReturn:
    raise BootstrapDenied(message)


def _timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        _deny("private approval timestamp is invalid")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _deny("private approval timestamp is invalid")


def _safe_components(
    path: Path,
    *,
    leaf_directory: bool,
    allowed_uids: set[int],
    exact_leaf_mode: int | None = None,
) -> os.stat_result:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    leaf: os.stat_result | None = None
    for index, part in enumerate((absolute.anchor, *absolute.parts[1:])):
        if index:
            current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _deny("trusted path is unavailable")
        is_leaf = current == absolute
        expected_directory = leaf_directory if is_leaf else True
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in allowed_uids
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (expected_directory and not stat.S_ISDIR(metadata.st_mode))
            or (not expected_directory and not stat.S_ISREG(metadata.st_mode))
            or (
                is_leaf
                and exact_leaf_mode is not None
                and stat.S_IMODE(metadata.st_mode) != exact_leaf_mode
            )
        ):
            _deny("trusted path owner, mode, or topology is unsafe")
        leaf = metadata
    if leaf is None:
        _deny("trusted path is unavailable")
    return leaf


def _existing_ancestors_are_safe(path: Path, *, required_uid: int) -> None:
    current = Path(os.path.abspath(path))
    missing: list[Path] = []
    while True:
        try:
            current.lstat()
            break
        except FileNotFoundError:
            missing.append(current)
            if current == Path(current.anchor):
                _deny("target path has no trusted ancestor")
            current = current.parent
    _safe_components(current, leaf_directory=True, allowed_uids={0, required_uid})
    if any(candidate.is_symlink() for candidate in missing):
        _deny("target path contains a symlink")


def _open_regular(
    path: Path, *, flags: int, required_uid: int
) -> tuple[int, os.stat_result]:
    _safe_components(path, leaf_directory=False, allowed_uids={0, required_uid})
    open_flags = flags | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, open_flags)
    except OSError:
        _deny("trusted file cannot be opened safely")
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != required_uid:
        os.close(descriptor)
        _deny("opened trusted file is unsafe")
    return descriptor, metadata


def _digest_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _safe_digest(path: Path, *, required_uid: int) -> str:
    descriptor, _ = _open_regular(path, flags=os.O_RDONLY, required_uid=required_uid)
    try:
        return _digest_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _read_approval(path: Path = APPROVAL_PATH) -> tuple[dict[str, Any], bytes]:
    _safe_components(
        path,
        leaf_directory=False,
        allowed_uids={0},
        exact_leaf_mode=0o600,
    )
    descriptor, metadata = _open_regular(path, flags=os.O_RDONLY, required_uid=0)
    try:
        if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 64 * 1024:
            _deny("private approval is unsafe")
        raw = os.read(descriptor, 64 * 1024 + 1)
    finally:
        os.close(descriptor)
    if len(raw) > 64 * 1024:
        _deny("private approval is oversized")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _deny("private approval is invalid")
    if not isinstance(value, dict) or set(value) != APPROVAL_KEYS:
        _deny("private approval schema is not exact")
    return value, raw


def _validate_preconditions(value: Any) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict) or set(value) != set(TARGET_MODES):
        _deny("target precondition set is not exact")
    normalized: dict[str, dict[str, object]] = {}
    for target, expected_mode in TARGET_MODES.items():
        item = value.get(target)
        if not isinstance(item, dict):
            _deny("target precondition is invalid")
        if item.get("state") == "ABSENT":
            if set(item) != {"state"}:
                _deny("absent target precondition is not exact")
        elif item.get("state") == "PRESENT":
            if set(item) != {"state", "type", "sha256", "uid", "gid", "mode"}:
                _deny("present target precondition is not exact")
            if (
                item.get("type") != "file"
                or item.get("uid") != 0
                or item.get("gid") != 0
                or item.get("mode") != expected_mode
                or not isinstance(item.get("sha256"), str)
                or not SHA256_RE.fullmatch(str(item["sha256"]))
            ):
                _deny("present target precondition is unsafe")
        else:
            _deny("target precondition state is invalid")
        normalized[target] = dict(item)
    return normalized


def _validate_approval(
    value: dict[str, Any],
) -> tuple[str, dict[str, str], dict[str, dict[str, object]]]:
    if (
        value.get("schema_version") != 1
        or value.get("gate_id") != "GATE-08"
        or value.get("operation") != "operational-control-install"
        or value.get("decision") != "APPROVED"
        or value.get("scope") != "p0-operational-control-install"
        or not isinstance(value.get("approval_id"), str)
        or not value["approval_id"].strip()
        or not isinstance(value.get("owner"), str)
        or not value["owner"].strip()
    ):
        _deny("private approval does not authorize this bootstrap")
    approved_at = _timestamp(value.get("approved_at"))
    expires_at = _timestamp(value.get("expires_at"))
    now = dt.datetime.now(dt.timezone.utc)
    if (
        approved_at > now + dt.timedelta(minutes=5)
        or expires_at <= now
        or expires_at > approved_at + dt.timedelta(hours=4)
    ):
        _deny("private approval is expired or over-broad")
    source_sha = value.get("source_git_sha")
    if not isinstance(source_sha, str) or not GIT_SHA_RE.fullmatch(source_sha):
        _deny("approved source commit is invalid")
    hashes = value.get("artifact_sha256")
    if (
        not isinstance(hashes, dict)
        or set(hashes) != ARTIFACTS
        or any(
            not isinstance(digest, str) or not SHA256_RE.fullmatch(digest)
            for digest in hashes.values()
        )
    ):
        _deny("approved artifact set is not exact")
    if value.get("install_targets") != INSTALL_TARGETS:
        _deny("approved install target set is not exact")
    return (
        source_sha,
        dict(hashes),
        _validate_preconditions(value.get("target_preconditions")),
    )


def _git(
    hooks: Path, arguments: Sequence[str], *, checkout: Path | None = None
) -> subprocess.CompletedProcess[str]:
    command = [
        "/usr/bin/git",
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "core.alternateRefsCommand=/bin/false",
        "-c",
        "protocol.file.allow=always",
    ]
    if checkout is not None:
        command.extend(("-C", str(checkout)))
    result = subprocess.run(
        [*command, *arguments],
        env=GIT_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _deny("isolated Git operation failed")
    return result


def _verify_source_repository(source: Path) -> None:
    owner = source.lstat().st_uid
    _safe_components(source, leaf_directory=True, allowed_uids={0, owner})
    _safe_components(source / ".git", leaf_directory=True, allowed_uids={0, owner})


def _prepare_checkout(
    source: Path, checkout: Path, hooks: Path, source_sha: str
) -> None:
    _verify_source_repository(source)
    _git(
        hooks,
        (
            "clone",
            "--no-local",
            "--no-checkout",
            "--no-recurse-submodules",
            "--depth=1",
            "--single-branch",
            "--no-tags",
            "--",
            str(source),
            str(checkout),
        ),
    )
    if (
        _git(hooks, ("rev-parse", "HEAD"), checkout=checkout).stdout.strip()
        != source_sha
    ):
        _deny("candidate HEAD does not match approval")
    tree = _git(hooks, ("ls-tree", "-r", source_sha), checkout=checkout).stdout
    if any(line.startswith("160000 ") for line in tree.splitlines()):
        _deny("approved commit contains a submodule")
    if any(line.startswith("120000 ") for line in tree.splitlines()):
        _deny("approved commit contains a symlink")
    _git(
        hooks, ("checkout", "--detach", "--force", source_sha, "--"), checkout=checkout
    )
    if _git(
        hooks, ("status", "--porcelain=v1", "--untracked-files=all"), checkout=checkout
    ).stdout:
        _deny("root checkout is not clean")
    if (checkout / ".git/objects/info/alternates").exists():
        _deny("object alternates are forbidden")
    _safe_components(checkout, leaf_directory=True, allowed_uids={0})
    _safe_components(checkout / ".git", leaf_directory=True, allowed_uids={0})


def _copy_verified(
    source: Path, destination: Path, expected: str, *, required_uid: int
) -> None:
    descriptor, _ = _open_regular(source, flags=os.O_RDONLY, required_uid=required_uid)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    output = os.open(destination, flags, 0o600)
    digest = hashlib.sha256()
    try:
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            os.write(output, chunk)
        os.fsync(output)
    finally:
        os.close(descriptor)
        os.close(output)
    if digest.hexdigest() != expected:
        _deny("artifact hash does not match approval")
    if _safe_digest(destination, required_uid=required_uid) != expected:
        _deny("staged artifact re-hash failed")


def _stage_artifacts(checkout: Path, stage: Path, hashes: dict[str, str]) -> None:
    stage.mkdir(mode=0o700)
    for relative in sorted(ARTIFACTS):
        _copy_verified(
            checkout / relative, stage / relative, hashes[relative], required_uid=0
        )
    actual = {
        str(path.relative_to(stage)) for path in stage.rglob("*") if path.is_file()
    }
    if actual != ARTIFACTS:
        _deny("staged artifact set is not exact")


def _run_gate(
    checkout: Path,
    source_sha: str,
    hashes: dict[str, str],
    preconditions: dict[str, dict[str, object]],
) -> None:
    result = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            str(checkout / GATE_ARTIFACT),
            "check",
            "operational-control-install",
        ],
        env=CHILD_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _deny("verified operational release gate denied")
    try:
        decision = json.loads(result.stdout)
    except json.JSONDecodeError:
        _deny("verified operational release gate output is invalid")
    expected_keys = {
        "allowed",
        "operation",
        "reason",
        "state_id",
        "required_gate",
        "source_git_sha",
        "approval_id",
        "artifact_sha256",
        "install_targets",
        "target_preconditions",
    }
    if (
        not isinstance(decision, dict)
        or set(decision) != expected_keys
        or decision.get("allowed") is not True
        or decision.get("operation") != "operational-control-install"
        or decision.get("reason") != "gate08_hash_bound_operational_control_install"
        or decision.get("required_gate") != "GATE-08"
        or decision.get("source_git_sha") != source_sha
        or decision.get("artifact_sha256") != hashes
        or decision.get("install_targets") != INSTALL_TARGETS
        or decision.get("target_preconditions") != preconditions
    ):
        _deny("verified operational release gate decision is not exact")


def _target_fingerprint(path: Path, *, required_uid: int) -> dict[str, object]:
    descriptor, metadata = _open_regular(
        path, flags=os.O_RDONLY, required_uid=required_uid
    )
    try:
        return {
            "state": "PRESENT",
            "type": "file",
            "sha256": _digest_descriptor(descriptor),
            "uid": metadata.st_uid,
            "gid": metadata.st_gid,
            "mode": f"0{stat.S_IMODE(metadata.st_mode):03o}",
        }
    finally:
        os.close(descriptor)


def _current_target_fingerprint(path: Path, *, required_uid: int) -> dict[str, object]:
    try:
        path.lstat()
    except FileNotFoundError:
        return {"state": "ABSENT"}
    return _target_fingerprint(path, required_uid=required_uid)


def _preflight_targets(
    specs: Sequence[TargetSpec],
    preconditions: dict[str, dict[str, object]],
    *,
    required_uid: int,
) -> dict[str, dict[str, object]]:
    actual: dict[str, dict[str, object]] = {}
    for spec in specs:
        _existing_ancestors_are_safe(spec.target.parent, required_uid=required_uid)
        fingerprint = _current_target_fingerprint(
            spec.target, required_uid=required_uid
        )
        if fingerprint != preconditions[str(spec.target)]:
            _deny("existing operational target fingerprint drift")
        actual[str(spec.target)] = fingerprint
    return actual


def _ensure_private_directory(
    path: Path, *, required_uid: int, required_gid: int
) -> None:
    if path.exists():
        _safe_components(
            path,
            leaf_directory=True,
            allowed_uids={0, required_uid},
            exact_leaf_mode=0o700,
        )
        return
    _existing_ancestors_are_safe(path.parent, required_uid=required_uid)
    path.mkdir(mode=0o700)
    os.chown(path, required_uid, required_gid)
    path.chmod(0o700)


def _ensure_target_directories(
    specs: Sequence[TargetSpec], *, required_uid: int, required_gid: int
) -> list[Path]:
    created: list[Path] = []
    directories = sorted(
        {spec.target.parent for spec in specs}, key=lambda item: len(item.parts)
    )
    for directory in directories:
        chain: list[Path] = []
        current = directory
        while not current.exists():
            chain.append(current)
            current = current.parent
        _safe_components(current, leaf_directory=True, allowed_uids={0, required_uid})
        for candidate in reversed(chain):
            candidate.mkdir(mode=0o755)
            os.chown(candidate, required_uid, required_gid)
            candidate.chmod(0o755)
            created.append(candidate)
        _safe_components(
            directory,
            leaf_directory=True,
            allowed_uids={0, required_uid},
            exact_leaf_mode=0o755,
        )
    return created


def _atomic_copy(
    source: Path,
    target: Path,
    *,
    mode: int,
    uid: int,
    gid: int,
) -> None:
    source_fd, _ = _open_regular(source, flags=os.O_RDONLY, required_uid=uid)
    temporary = target.parent / f".{target.name}.install-{os.getpid()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    output = os.open(temporary, flags, 0o600)
    try:
        while chunk := os.read(source_fd, 1024 * 1024):
            os.write(output, chunk)
        os.fchown(output, uid, gid)
        os.fchmod(output, mode)
        os.fsync(output)
    finally:
        os.close(source_fd)
        os.close(output)
    try:
        os.replace(temporary, target)
        parent_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_private_json(
    path: Path,
    value: dict[str, object],
    *,
    required_uid: int,
    required_gid: int,
) -> None:
    if path.exists() or path.is_symlink():
        _deny("private evidence path already exists")
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.write(descriptor, raw)
        os.fchown(descriptor, required_uid, required_gid)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _rollback_targets(
    specs: Sequence[TargetSpec],
    before: dict[str, dict[str, object]],
    backups: dict[str, Path],
    stage: Path,
    *,
    required_uid: int,
) -> None:
    for spec in reversed(tuple(specs)):
        expected_before = before[str(spec.target)]
        if expected_before["state"] == "PRESENT":
            _atomic_copy(
                backups[str(spec.target)],
                spec.target,
                mode=int(str(expected_before["mode"]), 8),
                uid=int(expected_before["uid"]),
                gid=int(expected_before["gid"]),
            )
        else:
            try:
                current = _target_fingerprint(spec.target, required_uid=required_uid)
            except BootstrapDenied:
                continue
            installed_hash = _safe_digest(
                stage / spec.source, required_uid=required_uid
            )
            if current.get("sha256") != installed_hash:
                _deny("rollback cannot remove a drifted target")
            spec.target.unlink()
    for spec in specs:
        actual = _current_target_fingerprint(spec.target, required_uid=required_uid)
        if actual != before[str(spec.target)]:
            _deny("operational target rollback verification failed")


def _disable_installed_controls(
    specs: Sequence[TargetSpec], stage: Path, *, required_uid: int
) -> None:
    for spec in specs:
        try:
            current = _target_fingerprint(spec.target, required_uid=required_uid)
            installed_hash = _safe_digest(
                stage / spec.source, required_uid=required_uid
            )
            if current.get("sha256") == installed_hash:
                descriptor = os.open(
                    spec.target,
                    os.O_WRONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    os.fchmod(descriptor, 0)
                finally:
                    os.close(descriptor)
        except (BootstrapDenied, OSError):
            continue


def install_from_stage(
    stage: Path,
    specs: Sequence[TargetSpec],
    preconditions: dict[str, dict[str, object]],
    *,
    approval_id: str,
    owner: str,
    source_sha: str,
    rollback_root: Path,
    receipt_root: Path,
    required_uid: int = 0,
    required_gid: int | None = None,
    fault_after: int | None = None,
) -> dict[str, object]:
    if required_gid is None:
        required_gid = required_uid
    before = _preflight_targets(specs, preconditions, required_uid=required_uid)
    _ensure_private_directory(
        rollback_root.parent, required_uid=required_uid, required_gid=required_gid
    )
    _ensure_private_directory(
        rollback_root, required_uid=required_uid, required_gid=required_gid
    )
    _ensure_private_directory(
        receipt_root, required_uid=required_uid, required_gid=required_gid
    )
    evidence_id = hashlib.sha256(
        f"{approval_id}\0{source_sha}".encode("utf-8")
    ).hexdigest()
    rollback_dir = rollback_root / evidence_id
    if rollback_dir.exists() or rollback_dir.is_symlink():
        _deny("rollback evidence already exists")
    rollback_dir.mkdir(mode=0o700)
    os.chown(rollback_dir, required_uid, required_gid)
    backups: dict[str, Path] = {}
    for index, spec in enumerate(specs):
        if before[str(spec.target)]["state"] == "PRESENT":
            backup = rollback_dir / f"target-{index}.previous"
            _copy_verified(
                spec.target,
                backup,
                str(before[str(spec.target)]["sha256"]),
                required_uid=required_uid,
            )
            backups[str(spec.target)] = backup
    _write_private_json(
        rollback_dir / "manifest.json",
        {
            "schema_version": 1,
            "approval_id": approval_id,
            "source_git_sha": source_sha,
            "targets": before,
        },
        required_uid=required_uid,
        required_gid=required_gid,
    )
    created_directories: list[Path] = []
    installed: list[TargetSpec] = []
    try:
        created_directories = _ensure_target_directories(
            specs, required_uid=required_uid, required_gid=required_gid
        )
        for index, spec in enumerate(specs, start=1):
            current = _current_target_fingerprint(
                spec.target, required_uid=required_uid
            )
            if current != before[str(spec.target)]:
                _deny("operational target changed after preflight")
            installed.append(spec)
            _atomic_copy(
                stage / spec.source,
                spec.target,
                mode=spec.mode,
                uid=required_uid,
                gid=required_gid,
            )
            if fault_after == index:
                raise OSError("injected partial installation failure")
        installed_fingerprints: dict[str, dict[str, object]] = {}
        for spec in specs:
            fingerprint = _target_fingerprint(spec.target, required_uid=required_uid)
            expected_hash = _safe_digest(stage / spec.source, required_uid=required_uid)
            if (
                fingerprint.get("sha256") != expected_hash
                or fingerprint.get("uid") != required_uid
                or fingerprint.get("gid") != required_gid
                or fingerprint.get("mode") != f"0{spec.mode:03o}"
            ):
                _deny("installed operational control postcondition failed")
            installed_fingerprints[str(spec.target)] = fingerprint
        receipt = {
            "schema_version": 1,
            "operation": "operational-control-install",
            "required_gate": "GATE-08",
            "approval_id": approval_id,
            "owner": owner,
            "source_git_sha": source_sha,
            "installed_at": dt.datetime.now(dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "rollback_evidence_id": evidence_id,
            "targets": installed_fingerprints,
        }
        _write_private_json(
            receipt_root / f"{evidence_id}.json",
            receipt,
            required_uid=required_uid,
            required_gid=required_gid,
        )
        return receipt
    except BaseException as install_error:
        try:
            _rollback_targets(
                specs,
                before,
                backups,
                stage,
                required_uid=required_uid,
            )
            for directory in reversed(created_directories):
                try:
                    directory.rmdir()
                except OSError:
                    pass
        except BaseException:
            _disable_installed_controls(installed, stage, required_uid=required_uid)
            raise BootstrapDenied(
                "rollback failed; affected controls disabled; owner incident review required"
            ) from install_error
        raise BootstrapDenied(
            "installation failed and was rolled back"
        ) from install_error


def _arguments(argv: Sequence[str]) -> Path:
    if list(argv) == ["--help"]:
        print(
            "Usage: bootstrap_gate08_operational_controls.py "
            "--source-repository ABSOLUTE_LOCAL_PATH --apply"
        )
        raise SystemExit(0)
    if len(argv) != 3 or argv[0] != "--source-repository" or argv[2] != "--apply":
        _deny("invalid bootstrap arguments")
    if not argv[1].startswith("/") or "\n" in argv[1] or "\r" in argv[1]:
        _deny("source repository must be one absolute local path")
    source = Path(os.path.abspath(argv[1]))
    if source == LIVE_PRODUCTION_REPO:
        _deny("live production checkout is not an execution path")
    return source


def main(argv: Sequence[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if list(arguments) == ["--help"]:
        _arguments(arguments)
    if os.geteuid() != 0:
        _deny("root is required")
    os.umask(0o077)
    source = _arguments(arguments)
    approval, approval_raw = _read_approval()
    source_sha, hashes, preconditions = _validate_approval(approval)
    if _safe_digest(Path(__file__), required_uid=0) != hashes[SELF_ARTIFACT]:
        _deny("executing bootstrap hash does not match approval")

    root_stage = Path(
        tempfile.mkdtemp(prefix="sealai-operational-controls.", dir="/run")
    )
    os.chown(root_stage, 0, 0)
    root_stage.chmod(0o700)
    try:
        hooks = root_stage / "empty-hooks"
        hooks.mkdir(mode=0o700)
        checkout = root_stage / "checkout"
        _prepare_checkout(source, checkout, hooks, source_sha)
        stage = root_stage / "verified-artifacts"
        _stage_artifacts(checkout, stage, hashes)
        approval_after, approval_raw_after = _read_approval()
        source_after, hashes_after, preconditions_after = _validate_approval(
            approval_after
        )
        if (
            approval_raw_after != approval_raw
            or source_after != source_sha
            or hashes_after != hashes
            or preconditions_after != preconditions
        ):
            _deny("private approval changed during bootstrap")
        _run_gate(checkout, source_sha, hashes, preconditions)
        install_from_stage(
            stage,
            TARGET_SPECS,
            preconditions,
            approval_id=str(approval["approval_id"]),
            owner=str(approval["owner"]),
            source_sha=source_sha,
            rollback_root=ROLLBACK_ROOT,
            receipt_root=RECEIPT_ROOT,
        )
    finally:
        shutil.rmtree(root_stage, ignore_errors=True)
    print(
        json.dumps(
            {
                "allowed": True,
                "operation": "operational-control-install",
                "required_gate": "GATE-08",
                "targets": len(TARGET_SPECS),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def _terminate(_signal: int, _frame: object) -> NoReturn:
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, _terminate)
    signal.signal(signal.SIGTERM, _terminate)
    try:
        raise SystemExit(main())
    except BootstrapDenied as exc:
        print(f"operational controls bootstrap: {exc}", file=sys.stderr)
        raise SystemExit(78) from None
