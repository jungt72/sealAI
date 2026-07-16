#!/usr/bin/env python3
"""Validate the exact fail-closed Stage-A partial state and staged controls."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, NoReturn, Sequence


EVIDENCE_ID = "legacy-stage-a-c905780b-20260716T062603Z"
EVIDENCE_DIRECTORY = (
    Path("/var/lib/sealai-disk-guard/legacy-unit-evidence") / EVIDENCE_ID
)
APPROVAL_PATH = Path("/etc/sealai/approvals/gate-08-remediation-resume.json")
PRODUCTION_REPOSITORY = Path("/home/thorsten/sealai")
PRODUCTION_SHA = "b5fea96e387772547722bdbcaecde1e125d9100b"
LEGACY_CRON_USER = "thorsten"
LEGACY_CRON_LINE = "0 * * * * /home/thorsten/sealai/ops/disk_safeguard.sh"
LEGACY_TIMER = "sealai-docker-disk-guard.timer"
LEGACY_SERVICE = "sealai-docker-disk-guard.service"
LEGACY_FRAGMENTS = {
    LEGACY_TIMER: Path("/etc/systemd/system/sealai-docker-disk-guard.timer"),
    LEGACY_SERVICE: Path("/etc/systemd/system/sealai-docker-disk-guard.service"),
}
EVIDENCE_FILES = frozenset(
    {
        "sealai-docker-disk-guard.service",
        "sealai-docker-disk-guard.timer",
        "status-before.json",
        "status-after.json",
    }
)


class TargetSpec:
    __slots__ = ("source", "path", "mode")

    def __init__(self, source: str, path: str, mode: str) -> None:
        self.source = source
        self.path = path
        self.mode = mode


TARGET_SPECS = (
    TargetSpec(
        "docs/ops/docker-disk-guard.md",
        "/usr/local/share/doc/sealai/docker-disk-guard.md",
        "0644",
    ),
    TargetSpec("ops/disk-guard.example.json", "/etc/sealai/disk-guard.json", "0600"),
    TargetSpec(
        "ops/docker-disk-guard.sh",
        "/usr/local/libexec/sealai/docker-disk-guard.sh",
        "0755",
    ),
    TargetSpec(
        "ops/docker_disk_guard.py",
        "/usr/local/libexec/sealai/docker_disk_guard.py",
        "0755",
    ),
    TargetSpec(
        "ops/hash_verified_python_loader.py",
        "/usr/local/libexec/sealai/hash-verified-python-loader.py",
        "0755",
    ),
    TargetSpec(
        "ops/production-deploy-remote-entrypoint.sh",
        "/usr/local/libexec/sealai/production-deploy-remote-entrypoint.sh",
        "0755",
    ),
    TargetSpec(
        "ops/production-release-gate-check.sh",
        "/usr/local/libexec/sealai/production-release-gate-check.sh",
        "0755",
    ),
    TargetSpec(
        "ops/production-storage-lease.sh",
        "/usr/local/libexec/sealai/production-storage-lease.sh",
        "0644",
    ),
    TargetSpec(
        "ops/sudoers/sealai-storage-preflight",
        "/etc/sudoers.d/sealai-storage-preflight",
        "0440",
    ),
    TargetSpec(
        "ops/systemd/sealai-disk-guard.service",
        "/etc/systemd/system/sealai-disk-guard.service",
        "0644",
    ),
    TargetSpec(
        "ops/systemd/sealai-disk-guard.timer",
        "/etc/systemd/system/sealai-disk-guard.timer",
        "0644",
    ),
    TargetSpec(
        "ops/tmpfiles/sealai-storage-mutation.conf",
        "/etc/tmpfiles.d/sealai-storage-mutation.conf",
        "0644",
    ),
)
if len(TARGET_SPECS) != len({spec.source for spec in TARGET_SPECS}) or len(
    TARGET_SPECS
) != len({spec.path for spec in TARGET_SPECS}):
    raise RuntimeError("canonical recovery target specification is not unique")
TARGETS_BY_SOURCE = {spec.source: spec for spec in TARGET_SPECS}
TARGETS_BY_PATH = {spec.path: spec for spec in TARGET_SPECS}
RUNTIME_TARGETS = frozenset(
    {
        "/run/lock/sealai-storage-mutation.lock",
        "/var/lib/sealai-disk-guard/state.json",
    }
)
ALL_TARGETS = frozenset({spec.path for spec in TARGET_SPECS} | RUNTIME_TARGETS)
SYNTHETIC_REQUIRED_TARGETS = frozenset(
    {
        "/etc/systemd/system/sealai-disk-guard.service",
        "/etc/systemd/system/sealai-disk-guard.timer",
        "/usr/local/libexec/sealai/docker-disk-guard.sh",
        "/usr/local/libexec/sealai/docker_disk_guard.py",
        "/usr/local/libexec/sealai/production-storage-lease.sh",
        "/usr/local/libexec/sealai/production-release-gate-check.sh",
        "/usr/local/libexec/sealai/production-deploy-remote-entrypoint.sh",
        "/usr/local/libexec/sealai/hash-verified-python-loader.py",
    }
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
APPROVAL_KEYS = frozenset(
    {
        "schema_version",
        "gate_id",
        "operation",
        "decision",
        "scope",
        "approval_id",
        "approved_by",
        "approved_at",
        "expires_at",
        "source_git_sha",
        "artifact_sha256",
        "incident",
        "legacy_evidence",
        "evidence_status_before_sha256",
        "evidence_status_after_sha256",
        "legacy_timer_fragment_sha256",
        "legacy_service_fragment_sha256",
        "production",
        "current_partial_state",
        "new_targets",
        "storage_policy",
    }
)
CHILD_ENV = {
    "HOME": "/root",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}
PRODUCTION_GIT_ENV = {
    "HOME": "/root",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
}
STORAGE_PATH_GROUPS = {
    "/": "rootfs",
    "/etc": "rootfs",
    "/usr/local": "rootfs",
    "/var/lib/sealai-disk-guard": "rootfs",
    "/run": "runfs",
    "/mnt/sealai-volume/docker-data": "dockerfs",
}
STORAGE_GROUPS = frozenset(STORAGE_PATH_GROUPS.values())
COMMON_UNIT_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "UnitFileState",
    "FragmentPath",
)
SERVICE_PID_PROPERTIES = ("MainPID", "ControlPID")


class RecoveryError(RuntimeError):
    """The exact partial state or staged control set could not be proven."""


def _fail(message: str) -> NoReturn:
    raise RecoveryError(message)


def _exact_mapping(
    value: Any, keys: set[str] | frozenset[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail(f"{label} fields are not exact")
    return value


def _timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        _fail(f"{label} is invalid")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RecoveryError(f"{label} is invalid") from exc


def _digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_regular(
    path: Path,
    *,
    required_uid: int | None = None,
    required_gid: int | None = None,
    required_mode: int | None = None,
    maximum: int = 1024 * 1024,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RecoveryError(f"required file is unavailable: {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (required_uid is not None and metadata.st_uid != required_uid)
            or (required_gid is not None and metadata.st_gid != required_gid)
            or (
                required_mode is not None
                and stat.S_IMODE(metadata.st_mode) != required_mode
            )
            or metadata.st_size > maximum
        ):
            _fail(f"required file metadata is unsafe: {path}")
        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(descriptor, 65536):
            size += len(chunk)
            if size > maximum:
                _fail(f"required file is oversized: {path}")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _json_bytes(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"{label} is invalid JSON") from exc


def load_private_approval(path: Path = APPROVAL_PATH) -> dict[str, Any]:
    raw = _read_regular(
        path,
        required_uid=0,
        required_gid=0,
        required_mode=0o600,
        maximum=65536,
    )
    value = _json_bytes(raw, "recovery approval")
    if not isinstance(value, dict):
        _fail("recovery approval root is invalid")
    return value


def _validate_unit_statuses(value: Any, *, before: bool) -> None:
    if not isinstance(value, list) or len(value) != 2:
        _fail("legacy status evidence set is not exact")
    by_name: dict[str, dict[str, Any]] = {}
    keys = {
        "unit_name",
        "load_state",
        "active_state",
        "unit_file_state",
        "fragment_path",
    }
    for item in value:
        item = _exact_mapping(item, keys, "legacy status evidence")
        name = item.get("unit_name")
        if name not in LEGACY_FRAGMENTS or name in by_name:
            _fail("legacy status evidence unit set is not exact")
        if item.get("fragment_path") != str(LEGACY_FRAGMENTS[str(name)]):
            _fail("legacy status evidence fragment path drift")
        by_name[str(name)] = item
    if set(by_name) != set(LEGACY_FRAGMENTS):
        _fail("legacy status evidence unit set is not exact")
    timer = by_name[LEGACY_TIMER]
    service = by_name[LEGACY_SERVICE]
    expected_timer = (
        ("loaded", "active", "enabled")
        if before
        else ("loaded", "inactive", "disabled")
    )
    if (
        timer.get("load_state"),
        timer.get("active_state"),
        timer.get("unit_file_state"),
    ) != expected_timer:
        _fail("legacy timer evidence does not prove the bound transition")
    if (
        service.get("load_state"),
        service.get("active_state"),
        service.get("unit_file_state"),
    ) != ("loaded", "failed", "static"):
        _fail("legacy service evidence does not prove the bound state")


def validate_approval_contract(
    approval: dict[str, Any],
    *,
    now: dt.datetime | None = None,
    require_approved: bool = True,
) -> dict[str, Any]:
    _exact_mapping(approval, APPROVAL_KEYS, "recovery approval")
    if (
        approval.get("schema_version") != 1
        or approval.get("gate_id") != "GATE-08"
        or approval.get("operation") != "remediation-control-resume"
        or approval.get("scope") != "p0-stage-a-partial-recovery"
        or approval.get("decision")
        != ("APPROVED" if require_approved else "PENDING_OWNER_APPROVAL")
    ):
        _fail("recovery approval does not authorize this operation")
    for key in ("approval_id", "approved_by"):
        if not isinstance(approval.get(key), str) or not approval[key].strip():
            _fail(f"{key} is invalid")
    approved_at = _timestamp(approval.get("approved_at"), "approved_at")
    expires_at = _timestamp(approval.get("expires_at"), "expires_at")
    if require_approved:
        current = now or dt.datetime.now(dt.timezone.utc)
        if (
            approved_at > current + dt.timedelta(minutes=5)
            or expires_at <= current
            or expires_at > approved_at + dt.timedelta(hours=4)
        ):
            _fail("recovery approval is expired or over-broad")
    elif expires_at > approved_at + dt.timedelta(hours=4):
        _fail("pending recovery approval lifetime is over-broad")
    if not isinstance(approval.get("source_git_sha"), str) or not GIT_SHA_RE.fullmatch(
        approval["source_git_sha"]
    ):
        _fail("recovery source commit is invalid")
    artifacts = approval.get("artifact_sha256")
    if not isinstance(artifacts, dict) or not artifacts:
        _fail("recovery artifact set is invalid")
    if any(
        not isinstance(path, str)
        or not path
        or not isinstance(digest, str)
        or not SHA256_RE.fullmatch(digest)
        for path, digest in artifacts.items()
    ):
        _fail("recovery artifact hash is invalid")

    incident = _exact_mapping(
        approval.get("incident"),
        {
            "failed_source_git_sha",
            "failed_operation",
            "failure_class",
            "failed_at_phase",
        },
        "incident binding",
    )
    if incident != {
        "failed_source_git_sha": "c905780b54c1f5d27c6c6cea46d12fabdd69ddf8",
        "failed_operation": "remediation-control-install",
        "failure_class": "SYSTEMD_VERIFY_BEFORE_DEPENDENCY_INSTALL",
        "failed_at_phase": "AFTER_LEGACY_UNIT_RETIREMENT_BEFORE_CRON_RETIREMENT",
    }:
        _fail("incident binding drift")

    evidence = _exact_mapping(
        approval.get("legacy_evidence"),
        {"evidence_id", "evidence_directory", "expected_files"},
        "legacy evidence binding",
    )
    if (
        evidence.get("evidence_id") != EVIDENCE_ID
        or evidence.get("evidence_directory") != str(EVIDENCE_DIRECTORY)
        or not isinstance(evidence.get("expected_files"), list)
        or len(evidence["expected_files"]) != 4
    ):
        _fail("legacy evidence identity drift")
    evidence_by_path: dict[str, dict[str, Any]] = {}
    for item in evidence["expected_files"]:
        item = _exact_mapping(
            item, {"path", "sha256", "mode", "uid", "gid"}, "evidence file"
        )
        path = item.get("path")
        if path not in EVIDENCE_FILES or path in evidence_by_path:
            _fail("legacy evidence file set is not exact")
        if (
            not SHA256_RE.fullmatch(str(item.get("sha256", "")))
            or item.get("mode") != "0600"
            or item.get("uid") != 0
            or item.get("gid") != 0
        ):
            _fail("legacy evidence file binding is unsafe")
        evidence_by_path[str(path)] = item
    if set(evidence_by_path) != EVIDENCE_FILES:
        _fail("legacy evidence file set is not exact")
    digest_bindings = {
        "status-before.json": "evidence_status_before_sha256",
        "status-after.json": "evidence_status_after_sha256",
        "sealai-docker-disk-guard.timer": "legacy_timer_fragment_sha256",
        "sealai-docker-disk-guard.service": "legacy_service_fragment_sha256",
    }
    for filename, field in digest_bindings.items():
        if approval.get(field) != evidence_by_path[filename]["sha256"]:
            _fail("legacy evidence duplicate hash binding drift")

    production = _exact_mapping(
        approval.get("production"),
        {
            "repository",
            "commit",
            "worktree_state",
            "docker_root_dir",
            "backend_container_id",
            "worker_container_id",
            "backend_image_digest",
            "worker_image_digest",
            "release_freeze_active",
            "required_release_gate",
            "gate10_lift_implemented",
        },
        "production binding",
    )
    if (
        production.get("repository") != str(PRODUCTION_REPOSITORY)
        or production.get("commit") != PRODUCTION_SHA
        or production.get("worktree_state") != "CLEAN"
        or production.get("docker_root_dir") != "/mnt/sealai-volume/docker-data"
        or production.get("release_freeze_active") is not True
        or production.get("required_release_gate") != "GATE-10"
        or production.get("gate10_lift_implemented") is not False
    ):
        _fail("production binding drift")
    for field in ("backend_container_id", "worker_container_id"):
        if not isinstance(production.get(field), str) or not re.fullmatch(
            r"[0-9a-f]{64}", production[field]
        ):
            _fail("production container binding is invalid")
    for field in ("backend_image_digest", "worker_image_digest"):
        if not isinstance(production.get(field), str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", production[field]
        ):
            _fail("production image binding is invalid")

    storage_policy_value = approval.get("storage_policy")
    if (
        not isinstance(storage_policy_value, dict)
        or not {
            "path_groups",
            "minimum_available_bytes",
            "minimum_free_inodes",
            "fixed_safety_reserve_bytes",
        }
        <= set(storage_policy_value)
        or set(storage_policy_value)
        - {
            "path_groups",
            "minimum_available_bytes",
            "minimum_free_inodes",
            "maximum_usage_percent",
            "fixed_safety_reserve_bytes",
        }
    ):
        _fail("storage policy keys are not exact")
    storage_policy = storage_policy_value
    if storage_policy.get("path_groups") != STORAGE_PATH_GROUPS:
        _fail("storage mount policy drift")
    for field in (
        "minimum_available_bytes",
        "minimum_free_inodes",
        "fixed_safety_reserve_bytes",
    ):
        values = storage_policy.get(field)
        if not isinstance(values, dict) or set(values) != STORAGE_GROUPS:
            _fail("storage threshold set is not exact")
        for value in values.values():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                _fail("storage threshold is invalid")
    if "maximum_usage_percent" in storage_policy:
        values = storage_policy["maximum_usage_percent"]
        if (
            not isinstance(values, dict)
            or set(values) != STORAGE_GROUPS
            or any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
                or value > 99
                for value in values.values()
            )
        ):
            _fail("storage usage threshold is invalid")

    partial = _exact_mapping(
        approval.get("current_partial_state"),
        {"legacy_timer", "legacy_service", "legacy_cron_exact_count"},
        "partial state",
    )
    timer = _exact_mapping(
        partial.get("legacy_timer"),
        {
            "load_state",
            "active_state",
            "unit_file_state",
            "fragment_path",
            "fragment_sha256",
        },
        "partial timer state",
    )
    service = _exact_mapping(
        partial.get("legacy_service"),
        {
            "load_state",
            "active_state",
            "unit_file_state",
            "main_pid",
            "control_pid",
            "fragment_path",
            "fragment_sha256",
        },
        "partial service state",
    )
    if timer != {
        "load_state": "loaded",
        "active_state": "inactive",
        "unit_file_state": "disabled",
        "fragment_path": str(LEGACY_FRAGMENTS[LEGACY_TIMER]),
        "fragment_sha256": approval["legacy_timer_fragment_sha256"],
    }:
        _fail("partial legacy timer binding drift")
    if service != {
        "load_state": "loaded",
        "active_state": "failed",
        "unit_file_state": "static",
        "main_pid": 0,
        "control_pid": 0,
        "fragment_path": str(LEGACY_FRAGMENTS[LEGACY_SERVICE]),
        "fragment_sha256": approval["legacy_service_fragment_sha256"],
    }:
        _fail("partial legacy service binding drift")
    if partial.get("legacy_cron_exact_count") != 1:
        _fail("partial legacy cron binding drift")
    targets = approval.get("new_targets")
    if not isinstance(targets, dict) or set(targets) != ALL_TARGETS:
        _fail("recovery target precondition set is not exact")
    if any(value != "ABSENT" for value in targets.values()):
        _fail("recovery target precondition is not ABSENT")
    return approval


def validate_evidence(
    approval: dict[str, Any],
    *,
    evidence_directory: Path | None = None,
    required_uid: int = 0,
    required_gid: int = 0,
) -> dict[str, str]:
    evidence = approval["legacy_evidence"]
    directory = evidence_directory or Path(evidence["evidence_directory"])
    metadata = directory.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != required_uid
        or metadata.st_gid != required_gid
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail("legacy evidence directory is unsafe")
    actual_names = {entry.name for entry in directory.iterdir()}
    if actual_names != EVIDENCE_FILES:
        _fail("legacy evidence file set drift")
    expected = {item["path"]: item for item in evidence["expected_files"]}
    raws: dict[str, bytes] = {}
    digests: dict[str, str] = {}
    for filename in sorted(EVIDENCE_FILES):
        raw = _read_regular(
            directory / filename,
            required_uid=required_uid,
            required_gid=required_gid,
            required_mode=0o600,
            maximum=65536,
        )
        digest = _digest_bytes(raw)
        if digest != expected[filename]["sha256"]:
            _fail("legacy evidence hash drift")
        raws[filename] = raw
        digests[filename] = digest
    _validate_unit_statuses(
        _json_bytes(raws["status-before.json"], "status-before"), before=True
    )
    _validate_unit_statuses(
        _json_bytes(raws["status-after.json"], "status-after"), before=False
    )
    return digests


def validate_target_preconditions(
    targets: dict[str, str], *, path_factory: Callable[[str], Path] = Path
) -> None:
    if set(targets) != ALL_TARGETS or any(
        value != "ABSENT" for value in targets.values()
    ):
        _fail("recovery target precondition set is not exact")
    for target in sorted(ALL_TARGETS):
        path = path_factory(target)
        if path.exists() or path.is_symlink():
            _fail("RECOVERY_TARGET_PRECONDITION_DRIFT")


def _verify_ancestor_chain(
    path: Path,
    *,
    root: Path,
    required_uid: int,
    required_gid: int,
) -> None:
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise RecoveryError("installed target root is unavailable") from exc
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != required_uid
        or root_metadata.st_gid != required_gid
        or stat.S_IMODE(root_metadata.st_mode) & 0o022
    ):
        _fail("installed target ancestor is unsafe")
    root = root.resolve(strict=True)
    parent = path.parent
    try:
        relative = parent.relative_to(root)
    except ValueError:
        _fail("target path escapes the fixed root")
    current = root
    for part in relative.parts:
        current /= part
        metadata = current.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != required_uid
            or metadata.st_gid != required_gid
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            _fail("installed target ancestor is unsafe")


def _validate_target_metadata(
    metadata: os.stat_result,
    spec: TargetSpec,
    *,
    required_uid: int,
    required_gid: int,
    label: str,
) -> None:
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != required_uid
        or metadata.st_gid != required_gid
        or stat.S_IMODE(metadata.st_mode) != int(spec.mode, 8)
    ):
        _fail(f"{label} metadata drift")


def verify_installed_targets(
    stage: Path,
    *,
    specs: Sequence[TargetSpec] = TARGET_SPECS,
    root: Path = Path("/"),
    required_uid: int = 0,
    required_gid: int = 0,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for spec in sorted(specs, key=lambda item: item.path):
        source = stage / spec.source
        expected = _digest_bytes(_read_regular(source))
        target = root / spec.path.lstrip("/")
        _verify_ancestor_chain(
            target,
            root=root,
            required_uid=required_uid,
            required_gid=required_gid,
        )
        try:
            metadata = target.lstat()
        except OSError as exc:
            raise RecoveryError("installed target is unavailable") from exc
        _validate_target_metadata(
            metadata,
            spec,
            required_uid=required_uid,
            required_gid=required_gid,
            label="installed target",
        )
        actual = _digest_bytes(
            _read_regular(
                target,
                required_uid=required_uid,
                required_gid=required_gid,
                required_mode=int(spec.mode, 8),
            )
        )
        if actual != expected:
            _fail("installed target hash drift")
        results.append(
            {
                "path": spec.path,
                "sha256": actual,
                "uid": required_uid,
                "gid": required_gid,
                "mode": spec.mode,
            }
        )
    return results


FailureHook = Callable[[str, TargetSpec, Path | None, Path], None]


def _write_all(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            _fail("atomic target write failed")
        offset += written


def install_target_atomic(
    spec: TargetSpec,
    stage: Path,
    *,
    root: Path = Path("/"),
    required_uid: int = 0,
    required_gid: int = 0,
    failure_hook: FailureHook | None = None,
) -> dict[str, Any]:
    target = root / spec.path.lstrip("/")
    _verify_ancestor_chain(
        target,
        root=root,
        required_uid=required_uid,
        required_gid=required_gid,
    )
    if target.exists() or target.is_symlink():
        _fail("RECOVERY_TARGET_PRECONDITION_DRIFT")
    source_raw = _read_regular(stage / spec.source)
    expected = _digest_bytes(source_raw)
    temporary: Path | None = None
    descriptor: int | None = None
    renamed = False

    def inject(step: str) -> None:
        if failure_hook is not None:
            failure_hook(step, spec, temporary, target)

    try:
        inject("temp_create")
        descriptor, raw_name = tempfile.mkstemp(
            prefix=f".{target.name}.recovery.", dir=target.parent
        )
        temporary = Path(raw_name)
        inject("install")
        _write_all(descriptor, source_raw)
        os.fchown(descriptor, required_uid, required_gid)
        os.fchmod(descriptor, int(spec.mode, 8))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None

        inject("hash")
        if _digest_bytes(_read_regular(temporary)) != expected:
            _fail("temporary target hash drift")
        inject("metadata")
        _validate_target_metadata(
            temporary.lstat(),
            spec,
            required_uid=required_uid,
            required_gid=required_gid,
            label="temporary target",
        )
        inject("rename")
        os.replace(temporary, target)
        renamed = True
        temporary = None
        inject("fsync")
        parent = os.open(
            target.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        return verify_installed_target(
            spec,
            stage,
            root=root,
            required_uid=required_uid,
            required_gid=required_gid,
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if not renamed and temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def verify_installed_target(
    spec: TargetSpec,
    stage: Path,
    *,
    root: Path = Path("/"),
    required_uid: int = 0,
    required_gid: int = 0,
) -> dict[str, Any]:
    results = verify_installed_targets(
        stage,
        specs=(spec,),
        root=root,
        required_uid=required_uid,
        required_gid=required_gid,
    )
    return results[0]


def install_targets_atomic(
    stage: Path,
    *,
    root: Path = Path("/"),
    required_uid: int = 0,
    required_gid: int = 0,
    failure_hook: FailureHook | None = None,
) -> list[dict[str, Any]]:
    results = []
    for spec in sorted(TARGET_SPECS, key=lambda item: item.path):
        results.append(
            install_target_atomic(
                spec,
                stage,
                root=root,
                required_uid=required_uid,
                required_gid=required_gid,
                failure_hook=failure_hook,
            )
        )
    return results


def _mount_identity(path: str) -> dict[str, Any]:
    resolved = str(Path(path).resolve(strict=True))
    best: tuple[int, dict[str, Any]] | None = None
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RecoveryError("RECOVERY_STORAGE_PREFLIGHT_FAILED") from exc
    for line in lines:
        fields = line.split()
        if len(fields) < 10 or "-" not in fields:
            continue
        mount_point = fields[4].replace("\\040", " ")
        if resolved != mount_point and not resolved.startswith(
            mount_point.rstrip("/") + "/"
        ):
            continue
        candidate = {
            "mount_id": int(fields[0]),
            "device_major_minor": fields[2],
            "mount_point": mount_point,
        }
        length = len(mount_point)
        if best is None or length > best[0]:
            best = (length, candidate)
    if best is None:
        _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
    return best[1]


def collect_filesystem_snapshots(
    paths: Sequence[str],
    *,
    stat_fn: Callable[[str], os.stat_result] = os.stat,
    statvfs_fn: Callable[[str], os.statvfs_result] = os.statvfs,
    mount_resolver: Callable[[str], dict[str, Any]] = _mount_identity,
) -> list[dict[str, Any]]:
    snapshots: dict[tuple[int, int, int], dict[str, Any]] = {}
    for path in paths:
        try:
            metadata = stat_fn(path)
            filesystem = statvfs_fn(path)
            mount = mount_resolver(path)
            filesystem_id = int(getattr(filesystem, "f_fsid", metadata.st_dev))
            mount_id = int(mount["mount_id"])
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise RecoveryError("RECOVERY_STORAGE_PREFLIGHT_FAILED") from exc
        identity = (int(metadata.st_dev), filesystem_id, mount_id)
        block_size = int(filesystem.f_frsize or filesystem.f_bsize)
        total_bytes = int(filesystem.f_blocks) * block_size
        free_bytes = int(filesystem.f_bfree) * block_size
        available_bytes = int(filesystem.f_bavail) * block_size
        used_bytes = max(total_bytes - free_bytes, 0)
        usage_percent = (used_bytes * 100 + max(total_bytes, 1) - 1) // max(
            total_bytes, 1
        )
        value = {
            "device_id": int(metadata.st_dev),
            "filesystem_id": filesystem_id,
            "mount_id": mount_id,
            "device_major_minor": str(mount["device_major_minor"]),
            "mount_point": str(mount["mount_point"]),
            "paths": [],
            "total_bytes": total_bytes,
            "free_bytes": free_bytes,
            "available_bytes": available_bytes,
            "total_inodes": int(filesystem.f_files),
            "free_inodes": int(filesystem.f_ffree),
            "usage_percent": usage_percent,
        }
        existing = snapshots.setdefault(identity, value)
        metric_keys = {
            "device_id",
            "filesystem_id",
            "mount_id",
            "device_major_minor",
            "mount_point",
            "total_bytes",
            "free_bytes",
            "available_bytes",
            "total_inodes",
            "free_inodes",
            "usage_percent",
        }
        if any(existing[key] != value[key] for key in metric_keys):
            _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
        existing["paths"].append(path)
    for snapshot in snapshots.values():
        snapshot["paths"].sort()
    return sorted(
        snapshots.values(), key=lambda item: (item["mount_id"], item["paths"])
    )


def calculate_storage_requirements(
    source_root: Path,
    approval: dict[str, Any],
    *,
    cron_evidence_bytes: int = 65536,
) -> dict[str, dict[str, int]]:
    artifact_bytes = sum(
        (source_root / relative).stat().st_size
        for relative in approval["artifact_sha256"]
    )
    target_bytes = sum(
        (source_root / spec.source).stat().st_size for spec in TARGET_SPECS
    )
    evidence_bytes = 1024 * 1024 + cron_evidence_bytes * 2
    components = {
        "rootfs": {
            "target_installation_bytes": target_bytes,
            "rollback_bytes": target_bytes,
            "transaction_and_cron_evidence_bytes": evidence_bytes,
            "private_stage_bytes": 0,
            "synthetic_validation_root_bytes": 0,
        },
        "runfs": {
            "target_installation_bytes": 0,
            "rollback_bytes": 0,
            "transaction_and_cron_evidence_bytes": 0,
            "private_stage_bytes": artifact_bytes,
            "synthetic_validation_root_bytes": target_bytes + 1024 * 1024,
        },
        "dockerfs": {
            "target_installation_bytes": 0,
            "rollback_bytes": 0,
            "transaction_and_cron_evidence_bytes": 0,
            "private_stage_bytes": 0,
            "synthetic_validation_root_bytes": 0,
        },
    }
    result: dict[str, dict[str, int]] = {}
    reserve = approval["storage_policy"]["fixed_safety_reserve_bytes"]
    for group, values in components.items():
        subtotal = sum(values.values())
        result[group] = {
            **values,
            "fixed_safety_reserve_bytes": int(reserve[group]),
            "calculated_required_bytes": subtotal + int(reserve[group]),
        }
    return result


def validate_storage_snapshots(
    approval: dict[str, Any],
    snapshots: Sequence[dict[str, Any]],
    requirements: dict[str, dict[str, int]],
) -> dict[str, Any]:
    policy = approval["storage_policy"]
    by_path: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        expected_keys = {
            "device_id",
            "filesystem_id",
            "mount_id",
            "device_major_minor",
            "mount_point",
            "paths",
            "total_bytes",
            "free_bytes",
            "available_bytes",
            "total_inodes",
            "free_inodes",
            "usage_percent",
        }
        if not isinstance(snapshot, dict) or set(snapshot) != expected_keys:
            _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
        integer_fields = (
            "device_id",
            "filesystem_id",
            "mount_id",
            "total_bytes",
            "free_bytes",
            "available_bytes",
            "total_inodes",
            "free_inodes",
            "usage_percent",
        )
        if any(
            not isinstance(snapshot[field], int)
            or isinstance(snapshot[field], bool)
            or snapshot[field] < 0
            for field in integer_fields
        ):
            _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
        if (
            not isinstance(snapshot["device_major_minor"], str)
            or not snapshot["device_major_minor"]
            or not isinstance(snapshot["mount_point"], str)
            or not snapshot["mount_point"].startswith("/")
            or not isinstance(snapshot["paths"], list)
            or not snapshot["paths"]
            or snapshot["total_bytes"] <= 0
            or snapshot["available_bytes"] > snapshot["free_bytes"]
            or snapshot["free_bytes"] > snapshot["total_bytes"]
            or snapshot["total_inodes"] <= 0
            or snapshot["free_inodes"] > snapshot["total_inodes"]
            or snapshot["usage_percent"] > 100
        ):
            _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
        for path in snapshot["paths"]:
            if not isinstance(path, str):
                _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
            if path in by_path:
                _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
            by_path[path] = snapshot
    if set(by_path) != set(STORAGE_PATH_GROUPS):
        _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
    if set(requirements) != STORAGE_GROUPS or any(
        not isinstance(requirements[group], dict)
        or not isinstance(requirements[group].get("calculated_required_bytes"), int)
        or isinstance(requirements[group].get("calculated_required_bytes"), bool)
        or requirements[group]["calculated_required_bytes"] < 0
        for group in STORAGE_GROUPS
    ):
        _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
    group_identity: dict[str, tuple[int, int, int]] = {}
    for path, group in policy["path_groups"].items():
        snapshot = by_path[path]
        identity = (
            snapshot["device_id"],
            snapshot["filesystem_id"],
            snapshot["mount_id"],
        )
        if group in group_identity and group_identity[group] != identity:
            _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
        group_identity[group] = identity
    if set(group_identity) != STORAGE_GROUPS or len(
        set(group_identity.values())
    ) != len(STORAGE_GROUPS):
        _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
    validated = []
    for group in sorted(STORAGE_GROUPS):
        identity = group_identity[group]
        snapshot = next(
            item
            for item in snapshots
            if (
                item["device_id"],
                item["filesystem_id"],
                item["mount_id"],
            )
            == identity
        )
        required = max(
            policy["minimum_available_bytes"][group],
            requirements[group]["calculated_required_bytes"],
        )
        maximum_usage = policy.get("maximum_usage_percent", {}).get(group)
        if (
            snapshot["available_bytes"] < required
            or snapshot["total_inodes"] <= 0
            or snapshot["free_inodes"] < policy["minimum_free_inodes"][group]
            or (maximum_usage is not None and snapshot["usage_percent"] > maximum_usage)
        ):
            _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
        validated.append(
            {
                "group": group,
                **snapshot,
                "minimum_available_bytes": policy["minimum_available_bytes"][group],
                "minimum_free_inodes": policy["minimum_free_inodes"][group],
                "maximum_usage_percent": maximum_usage,
                "calculated_required_bytes": requirements[group][
                    "calculated_required_bytes"
                ],
            }
        )
    return {"filesystems": validated, "requirements": requirements}


def run_storage_preflight(
    approval: dict[str, Any],
    source_root: Path,
    *,
    actual_docker_root: str,
    stat_fn: Callable[[str], os.stat_result] = os.stat,
    statvfs_fn: Callable[[str], os.statvfs_result] = os.statvfs,
    mount_resolver: Callable[[str], dict[str, Any]] = _mount_identity,
) -> dict[str, Any]:
    if actual_docker_root != approval["production"]["docker_root_dir"]:
        _fail("RECOVERY_STORAGE_PREFLIGHT_FAILED")
    try:
        requirements = calculate_storage_requirements(source_root, approval)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise RecoveryError("RECOVERY_STORAGE_PREFLIGHT_FAILED") from exc
    snapshots = collect_filesystem_snapshots(
        tuple(STORAGE_PATH_GROUPS),
        stat_fn=stat_fn,
        statvfs_fn=statvfs_fn,
        mount_resolver=mount_resolver,
    )
    return validate_storage_snapshots(approval, snapshots, requirements)


def _copy_exact(source: Path, target: Path, mode: int) -> str:
    raw = _read_regular(source)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    if target.exists() or target.is_symlink():
        _fail("synthetic verification target already exists")
    descriptor = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        mode,
    )
    try:
        os.write(descriptor, raw)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if _read_regular(target) != raw:
        _fail("synthetic verification byte mismatch")
    return _digest_bytes(raw)


def build_synthetic_root(stage: Path, root: Path) -> dict[str, str]:
    if root.exists() or root.is_symlink():
        _fail("synthetic verification root must be absent")
    root.mkdir(mode=0o700, parents=False)
    (root / "etc").mkdir(mode=0o755)
    (root / "etc/passwd").write_text(
        "root:x:0:0:root:/root:/bin/bash\n"
        "thorsten:x:1000:1000:thorsten:/home/thorsten:/bin/bash\n",
        encoding="utf-8",
    )
    (root / "etc/group").write_text("root:x:0:\nthorsten:x:1000:\n", encoding="utf-8")
    system_units = root / "usr/lib/systemd/system"
    system_units.mkdir(mode=0o755, parents=True)
    for name in (
        "basic.target",
        "local-fs.target",
        "shutdown.target",
        "sysinit.target",
        "timers.target",
    ):
        (system_units / name).write_text("[Unit]\n", encoding="utf-8")
    hashes: dict[str, str] = {}
    for spec in sorted(TARGET_SPECS, key=lambda item: item.path):
        hashes[spec.path] = _copy_exact(
            stage / spec.source,
            root / spec.path.lstrip("/"),
            int(spec.mode, 8),
        )
    if not SYNTHETIC_REQUIRED_TARGETS <= set(hashes):
        _fail("synthetic verification root is incomplete")
    return hashes


def _run_checked(arguments: Sequence[str]) -> None:
    result = subprocess.run(
        list(arguments), env=CHILD_ENV, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        detail = (
            result.stderr.strip().splitlines()[-1:]
            or result.stdout.strip().splitlines()[-1:]
        )
        suffix = f": {detail[0]}" if detail else ""
        _fail(f"staged validation command failed{suffix}")


def _assert_gate10_disabled(source: Path) -> None:
    tree = ast.parse(_read_regular(source), filename=str(source))
    matches = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "GATE10_LIFT_IMPLEMENTED"
            for target in node.targets
        )
    ]
    if (
        len(matches) != 1
        or not isinstance(matches[0], ast.Constant)
        or matches[0].value is not False
    ):
        _fail("GATE10_LIFT_IMPLEMENTED is not exactly False")


def validate_stage(
    stage: Path,
    validation_root: Path,
    *,
    actual_docker_root: str,
) -> dict[str, Any]:
    hashes = build_synthetic_root(stage, validation_root)
    shell_sources = sorted(stage.glob("ops/*.sh"))
    for source in shell_sources:
        _run_checked(("/bin/bash", "-n", str(source)))
    for source in sorted(stage.glob("ops/*.py")):
        compile(_read_regular(source), str(source), "exec")
    for source in (
        stage / "ops/disk-guard.example.json",
        stage / "ops/production-release-state.json",
        stage / "ops/schemas/gate08-remediation-resume.schema.json",
    ):
        _json_bytes(_read_regular(source), str(source))
    config = _json_bytes(
        _read_regular(stage / "ops/disk-guard.example.json"), "disk guard config"
    )
    if (
        not isinstance(config, dict)
        or config.get("docker_root_dir") != actual_docker_root
    ):
        _fail("Docker root/config mismatch")
    _assert_gate10_disabled(stage / "ops/production_release_gate.py")
    _run_checked(
        (
            "/usr/sbin/visudo",
            "-cf",
            str(stage / "ops/sudoers/sealai-storage-preflight"),
        )
    )
    _run_checked(
        (
            "/usr/bin/systemd-tmpfiles",
            "--create",
            f"--root={validation_root}",
        )
    )
    _run_checked(
        (
            "/usr/bin/systemd-analyze",
            f"--root={validation_root}",
            "verify",
            "sealai-disk-guard.service",
            "sealai-disk-guard.timer",
        )
    )
    return {"validated_targets": hashes}


def _command(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        list(arguments), env=CHILD_ENV, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        _fail("recovery preflight command failed")
    return result.stdout.strip()


def _production_git(
    *arguments: str, command_runner: Callable[..., Any] | None = None
) -> str:
    if arguments not in {("rev-parse", "HEAD"), ("status", "--porcelain=v1")}:
        _fail("unsupported production Git operation")
    runner = subprocess.run if command_runner is None else command_runner
    result = runner(
        [
            "/usr/bin/git",
            "-c",
            f"safe.directory={PRODUCTION_REPOSITORY}",
            "-C",
            str(PRODUCTION_REPOSITORY),
            *arguments,
        ],
        env=PRODUCTION_GIT_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("production Git check failed")
    return result.stdout.rstrip("\n")


def _validate_production_git_state() -> None:
    if _production_git("rev-parse", "HEAD") != PRODUCTION_SHA:
        _fail("production commit drift")
    if _production_git("status", "--porcelain=v1"):
        _fail("production worktree drift")


def _unit_state(
    unit: str, *, command_runner: Callable[[Sequence[str]], str] | None = None
) -> dict[str, Any]:
    if unit == LEGACY_TIMER:
        properties = COMMON_UNIT_PROPERTIES
    elif unit == LEGACY_SERVICE:
        properties = COMMON_UNIT_PROPERTIES + SERVICE_PID_PROPERTIES
    else:
        _fail("unsupported legacy unit")
    runner = _command if command_runner is None else command_runner
    raw = runner(
        (
            "/usr/bin/systemctl",
            "show",
            "--no-pager",
            *(f"--property={name}" for name in properties),
            unit,
        )
    )
    values = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    if set(values) != set(properties):
        _fail("legacy unit state query is incomplete")
    state: dict[str, Any] = {
        "load_state": values["LoadState"],
        "active_state": values["ActiveState"],
        "unit_file_state": values["UnitFileState"],
        "fragment_path": values["FragmentPath"],
    }
    if unit == LEGACY_SERVICE:
        try:
            state["main_pid"] = int(values["MainPID"])
            state["control_pid"] = int(values["ControlPID"])
        except ValueError as exc:
            raise RecoveryError("legacy service PID is invalid") from exc
    return state


def _ancestor_pids() -> set[int]:
    ancestors = {os.getpid()}
    current = os.getppid()
    while current > 1 and current not in ancestors:
        ancestors.add(current)
        try:
            fields = Path(f"/proc/{current}/stat").read_text(encoding="utf-8").split()
            current = int(fields[3])
        except (OSError, ValueError, IndexError):
            break
    return ancestors


def validate_live_partial_state(approval: dict[str, Any]) -> dict[str, Any]:
    production = approval["production"]
    _validate_production_git_state()
    if any((PRODUCTION_REPOSITORY / ".git").rglob("*.lock")):
        _fail("production Git lock is present")
    if (
        _command(("/usr/bin/docker", "info", "--format", "{{.DockerRootDir}}"))
        != production["docker_root_dir"]
    ):
        _fail("Docker root drift")
    for name, id_field, image_field in (
        ("backend-v2", "backend_container_id", "backend_image_digest"),
        ("backend-v2-worker", "worker_container_id", "worker_image_digest"),
    ):
        value = _command(
            ("/usr/bin/docker", "inspect", "--format", "{{.Id}}|{{.Image}}", name)
        )
        if value != f"{production[id_field]}|{production[image_field]}":
            _fail("production container drift")
    expected_partial = approval["current_partial_state"]
    for unit, key in (
        (LEGACY_TIMER, "legacy_timer"),
        (LEGACY_SERVICE, "legacy_service"),
    ):
        actual = _unit_state(unit)
        expected = expected_partial[key]
        for field in ("load_state", "active_state", "unit_file_state", "fragment_path"):
            if actual[field] != expected[field]:
                _fail("legacy unit state drift")
        if key == "legacy_service" and (
            actual["main_pid"] != expected["main_pid"]
            or actual["control_pid"] != expected["control_pid"]
        ):
            _fail("legacy service PID drift")
        raw = _read_regular(
            Path(expected["fragment_path"]), required_uid=0, required_gid=0
        )
        if _digest_bytes(raw) != expected["fragment_sha256"]:
            _fail("legacy fragment hash drift")
    cron = subprocess.run(
        ("/usr/bin/crontab", "-u", LEGACY_CRON_USER, "-l"),
        env=CHILD_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if (
        cron.returncode != 0
        or sum(line == LEGACY_CRON_LINE for line in cron.stdout.splitlines()) != 1
    ):
        _fail("legacy cron fingerprint drift")
    validate_target_preconditions(approval["new_targets"])
    process = subprocess.run(
        (
            "/usr/bin/pgrep",
            "-f",
            "[b]ootstrap_gate08|[i]nstall-disk-guard|[r]esume-disk-guard|"
            "[p]roduction-deploy-remote-entrypoint|[/]home/thorsten/sealai/ops/disk_safeguard|"
            "[d]ocker (build|buildx)",
        ),
        env=CHILD_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode == 0:
        allowed = _ancestor_pids()
        matches = {
            int(value) for value in process.stdout.splitlines() if value.isdigit()
        }
        if matches - allowed:
            _fail("parallel production mutation detected")
    if process.returncode not in {0, 1}:
        _fail("parallel process check failed")
    validate_evidence(approval)
    return {"legacy_cron": cron.stdout, "targets": sorted(ALL_TARGETS)}


def write_transaction_evidence(
    approval: dict[str, Any],
    *,
    root: Path,
    staged_hashes: dict[str, str],
) -> Path:
    transaction_id = "stage-a-recovery-" + dt.datetime.now(dt.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    transaction = root / transaction_id
    transaction.mkdir(mode=0o700, parents=False)
    manifest = {
        "schema_version": 1,
        "operation": "remediation-control-resume",
        "approval_id": approval["approval_id"],
        "incident_evidence_id": EVIDENCE_ID,
        "recovery_transaction_id": transaction_id,
        "target_preconditions": approval["new_targets"],
        "staged_target_sha256": staged_hashes,
        "legacy_reactivation_allowed": False,
        "cron_reactivation_allowed": False,
    }
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    path = transaction / "rollback-manifest.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(transaction, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return transaction


def _arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-stage")
    validate.add_argument("--stage-dir", required=True, type=Path)
    validate.add_argument("--validation-root", required=True, type=Path)
    validate.add_argument("--actual-docker-root", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--approval", type=Path, default=APPROVAL_PATH)
    storage = subparsers.add_parser("storage-preflight")
    storage.add_argument("--approval", type=Path, default=APPROVAL_PATH)
    storage.add_argument("--source-root", required=True, type=Path)
    prepare = subparsers.add_parser("prepare-transaction")
    prepare.add_argument("--approval", type=Path, default=APPROVAL_PATH)
    prepare.add_argument("--evidence-root", required=True, type=Path)
    prepare.add_argument("--staged-hashes", required=True, type=Path)
    install = subparsers.add_parser("install-targets")
    install.add_argument("--stage-dir", required=True, type=Path)
    verify = subparsers.add_parser("verify-targets")
    verify.add_argument("--stage-dir", required=True, type=Path)
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(sys.argv[1:] if argv is None else argv)
    if args.command == "validate-stage":
        result = validate_stage(
            args.stage_dir,
            args.validation_root,
            actual_docker_root=args.actual_docker_root,
        )
    elif args.command == "preflight":
        approval = validate_approval_contract(load_private_approval(args.approval))
        result = validate_live_partial_state(approval)
    elif args.command == "storage-preflight":
        approval = validate_approval_contract(load_private_approval(args.approval))
        actual_docker_root = _command(
            ("/usr/bin/docker", "info", "--format", "{{.DockerRootDir}}")
        )
        result = run_storage_preflight(
            approval,
            args.source_root,
            actual_docker_root=actual_docker_root,
        )
    elif args.command == "prepare-transaction":
        approval = validate_approval_contract(load_private_approval(args.approval))
        hashes = _json_bytes(_read_regular(args.staged_hashes), "staged hashes")
        if not isinstance(hashes, dict):
            _fail("staged hashes are invalid")
        transaction = write_transaction_evidence(
            approval,
            root=args.evidence_root,
            staged_hashes={str(key): str(value) for key, value in hashes.items()},
        )
        result = {"transaction_directory": str(transaction)}
    elif args.command == "install-targets":
        if os.geteuid() != 0:
            _fail("install-targets requires root")
        result = {"targets": install_targets_atomic(args.stage_dir)}
    else:
        result = {"targets": verify_installed_targets(args.stage_dir)}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RecoveryError, OSError) as exc:
        print(
            json.dumps(
                {"allowed": False, "reason": str(exc)},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(78) from None
