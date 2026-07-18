#!/usr/bin/python3 -I
"""Execute one approved Python bootstrap only after descriptor-bound hashing."""

from __future__ import annotations

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


INSTALLED_LOADER = Path("/usr/local/libexec/sealai/hash-verified-python-loader.py")
APPROVAL_PATH = Path("/etc/sealai/approvals/gate-08-operational-controls.json")
BOOTSTRAP_ARTIFACT = "ops/bootstrap_gate08_operational_controls.py"
RUN_ROOT = Path("/run")
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
APPROVED_ARTIFACTS = frozenset(
    {
        "docs/ops/operational-control-install.md",
        "docs/ops/p0-operational-gate-unblock.md",
        "docs/ops/production-release-freeze.md",
        BOOTSTRAP_ARTIFACT,
        "ops/credential_cutover.py",
        "ops/install-operational-controls.sh",
        "ops/permission_manifest.py",
        "ops/production-release-state.json",
        "ops/production_release_gate.py",
        "ops/schemas/credential-cutover-approval.schema.json",
        "ops/schemas/gate08-operational-controls.schema.json",
        "ops/schemas/permission-manifest.schema.json",
    }
)
INSTALL_TARGETS = {
    "ops/credential_cutover.py": "/usr/local/libexec/sealai/credential-cutover.py",
    "ops/permission_manifest.py": "/usr/local/libexec/sealai/permission-manifest.py",
    "ops/schemas/credential-cutover-approval.schema.json": (
        "/usr/local/share/sealai/schemas/credential-cutover-approval.schema.json"
    ),
    "ops/schemas/permission-manifest.schema.json": (
        "/usr/local/share/sealai/schemas/permission-manifest.schema.json"
    ),
}
TARGET_MODES = {
    "/usr/local/libexec/sealai/credential-cutover.py": "0755",
    "/usr/local/libexec/sealai/permission-manifest.py": "0755",
    "/usr/local/share/sealai/schemas/credential-cutover-approval.schema.json": "0644",
    "/usr/local/share/sealai/schemas/permission-manifest.schema.json": "0644",
}
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CHILD_ENV = {
    "HOME": "/root",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "PYTHONNOUSERSITE": "1",
}


class LoaderDenied(RuntimeError):
    """The candidate cannot be proven to be the approved bootstrap."""


def _deny(message: str) -> NoReturn:
    raise LoaderDenied(message)


def _safe_components(
    path: Path,
    *,
    leaf_directory: bool,
    required_uid: int = 0,
    required_gid: int = 0,
    exact_leaf_mode: int | None = None,
) -> os.stat_result:
    if not path.is_absolute() or ".." in path.parts:
        _deny("trusted path is invalid")
    current = Path(path.anchor)
    leaf: os.stat_result | None = None
    for index, part in enumerate((path.anchor, *path.parts[1:])):
        if index:
            current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _deny("trusted path is unavailable")
        is_leaf = current == path
        expect_directory = leaf_directory if is_leaf else True
        owner = (metadata.st_uid, metadata.st_gid)
        owner_is_safe = owner == (required_uid, required_gid) or (
            not is_leaf and owner == (0, 0)
        )
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not owner_is_safe
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (expect_directory and not stat.S_ISDIR(metadata.st_mode))
            or (not expect_directory and not stat.S_ISREG(metadata.st_mode))
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


def _verify_loader(
    invoked: Path,
    *,
    installed_path: Path = INSTALLED_LOADER,
    required_uid: int = 0,
    required_gid: int = 0,
) -> None:
    if invoked != installed_path:
        _deny("loader must run from its fixed installed path")
    _safe_components(
        invoked,
        leaf_directory=False,
        required_uid=required_uid,
        required_gid=required_gid,
        exact_leaf_mode=0o755,
    )


def _open_regular(
    path: Path,
    *,
    required_uid: int = 0,
    required_gid: int = 0,
    exact_mode: int | None = None,
) -> tuple[int, os.stat_result]:
    _safe_components(
        path,
        leaf_directory=False,
        required_uid=required_uid,
        required_gid=required_gid,
        exact_leaf_mode=exact_mode,
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _deny("trusted file cannot be opened safely")
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != required_uid
        or metadata.st_gid != required_gid
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (exact_mode is not None and stat.S_IMODE(metadata.st_mode) != exact_mode)
    ):
        os.close(descriptor)
        _deny("opened trusted file is unsafe")
    return descriptor, metadata


def _read_approval(
    path: Path = APPROVAL_PATH, *, required_uid: int = 0, required_gid: int = 0
) -> tuple[dict[str, Any], bytes]:
    descriptor, metadata = _open_regular(
        path,
        required_uid=required_uid,
        required_gid=required_gid,
        exact_mode=0o600,
    )
    try:
        if metadata.st_size > 64 * 1024:
            _deny("private approval is oversized")
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


def _timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        _deny("private approval timestamp is invalid")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _deny("private approval timestamp is invalid")


def _validate_preconditions(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != set(TARGET_MODES):
        _deny("target precondition set is not exact")
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
                or type(item.get("uid")) is not int
                or type(item.get("gid")) is not int
                or item.get("uid") != 0
                or item.get("gid") != 0
                or item.get("mode") != expected_mode
                or not isinstance(item.get("sha256"), str)
                or not SHA256_RE.fullmatch(str(item["sha256"]))
            ):
                _deny("present target precondition is unsafe")
        else:
            _deny("target precondition state is invalid")


def _validate_approval(value: dict[str, Any]) -> str:
    if set(value) != APPROVAL_KEYS or (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
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
        or set(hashes) != APPROVED_ARTIFACTS
        or any(
            not isinstance(digest, str) or not SHA256_RE.fullmatch(digest)
            for digest in hashes.values()
        )
    ):
        _deny("approved artifact set is not exact")
    if value.get("install_targets") != INSTALL_TARGETS:
        _deny("approved install target set is not exact")
    _validate_preconditions(value.get("target_preconditions"))
    return str(hashes[BOOTSTRAP_ARTIFACT])


def _open_candidate(path: Path, *, required_uid: int = 0, required_gid: int = 0) -> int:
    descriptor, _ = _open_regular(
        path,
        required_uid=required_uid,
        required_gid=required_gid,
    )
    return descriptor


def _read_verified_descriptor(descriptor: int, expected_hash: str) -> bytes:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 1024 * 1024):
        chunks.append(chunk)
        digest.update(chunk)
    if digest.hexdigest() != expected_hash:
        _deny("approved bootstrap hash mismatch")
    return b"".join(chunks)


def _stage_and_execute(
    approved_bytes: bytes,
    expected_hash: str,
    bootstrap_arguments: Sequence[str],
    *,
    run_root: Path = RUN_ROOT,
    required_uid: int = 0,
    required_gid: int = 0,
) -> int:
    _safe_components(
        run_root,
        leaf_directory=True,
        required_uid=required_uid,
        required_gid=required_gid,
    )
    stage = Path(tempfile.mkdtemp(prefix="sealai-operational-loader.", dir=run_root))
    if (stage.stat().st_uid, stage.stat().st_gid) != (required_uid, required_gid):
        os.chown(stage, required_uid, required_gid)
    stage.chmod(0o700)
    candidate = stage / "bootstrap.py"
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(candidate, flags, 0o600)
        try:
            metadata = os.fstat(descriptor)
            if (metadata.st_uid, metadata.st_gid) != (required_uid, required_gid):
                os.fchown(descriptor, required_uid, required_gid)
            view = memoryview(approved_bytes)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    _deny("root-private bootstrap stage write failed")
                view = view[written:]
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o500)
        finally:
            os.close(descriptor)
        staged, _ = _open_regular(
            candidate,
            required_uid=required_uid,
            required_gid=required_gid,
            exact_mode=0o500,
        )
        try:
            if (
                hashlib.sha256(
                    _read_verified_descriptor(staged, expected_hash)
                ).hexdigest()
                != expected_hash
            ):
                _deny("root-private bootstrap stage hash mismatch")
        finally:
            os.close(staged)
        result = subprocess.run(
            ["/usr/bin/python3", "-I", str(candidate), *bootstrap_arguments],
            env=CHILD_ENV,
            check=False,
        )
        return result.returncode
    finally:
        try:
            shutil.rmtree(stage)
        except OSError:
            _deny("root-private bootstrap stage cleanup failed")
        if stage.exists():
            _deny("root-private bootstrap stage cleanup failed")


def _verify_and_execute(
    candidate: Path,
    expected_hash: str,
    bootstrap_arguments: Sequence[str],
    *,
    run_root: Path = RUN_ROOT,
    required_uid: int = 0,
    required_gid: int = 0,
) -> int:
    descriptor = _open_candidate(
        candidate,
        required_uid=required_uid,
        required_gid=required_gid,
    )
    try:
        approved_bytes = _read_verified_descriptor(descriptor, expected_hash)
    finally:
        os.close(descriptor)
    return _stage_and_execute(
        approved_bytes,
        expected_hash,
        bootstrap_arguments,
        run_root=run_root,
        required_uid=required_uid,
        required_gid=required_gid,
    )


def _parse_arguments(argv: Sequence[str]) -> tuple[Path, tuple[str, ...]]:
    arguments = list(argv)
    if len(arguments) != 10 or arguments[:6:2] != [
        "--approval",
        "--artifact-key",
        "--candidate",
    ]:
        _deny("loader arguments do not match the fixed contract")
    if (
        arguments[1] != str(APPROVAL_PATH)
        or arguments[3] != BOOTSTRAP_ARTIFACT
        or arguments[6] != "--"
        or arguments[7] != "--source-repository"
        or arguments[9] != "--apply"
    ):
        _deny("loader arguments do not match the fixed contract")
    candidate_text = arguments[5]
    source_text = arguments[8]
    if any("\n" in value or "\r" in value for value in (candidate_text, source_text)):
        _deny("loader path argument is invalid")
    candidate = Path(candidate_text)
    source = Path(source_text)
    if (
        not candidate.is_absolute()
        or ".." in candidate.parts
        or not source.is_absolute()
        or ".." in source.parts
    ):
        _deny("loader path argument is invalid")
    return candidate, ("--source-repository", str(source), "--apply")


def main(argv: Sequence[str] | None = None) -> int:
    if os.geteuid() != 0:
        _deny("root is required")
    os.umask(0o077)
    candidate, bootstrap_arguments = _parse_arguments(
        sys.argv[1:] if argv is None else argv
    )
    _verify_loader(Path(os.path.abspath(__file__)))
    approval, approval_raw = _read_approval()
    expected_hash = _validate_approval(approval)
    descriptor = _open_candidate(candidate)
    try:
        approved_bytes = _read_verified_descriptor(descriptor, expected_hash)
    finally:
        os.close(descriptor)
    approval_after, approval_raw_after = _read_approval()
    if approval_raw_after != approval_raw:
        _deny("private approval changed during verification")
    if _validate_approval(approval_after) != expected_hash:
        _deny("private approval changed during verification")
    return _stage_and_execute(
        approved_bytes,
        expected_hash,
        bootstrap_arguments,
    )


def _terminate(signal_number: int, _frame: object) -> NoReturn:
    raise SystemExit(128 + signal_number)


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, _terminate)
    signal.signal(signal.SIGINT, _terminate)
    signal.signal(signal.SIGTERM, _terminate)
    try:
        raise SystemExit(main())
    except LoaderDenied as exc:
        print(f"operational bootstrap loader: {exc}", file=sys.stderr)
        raise SystemExit(78) from None
