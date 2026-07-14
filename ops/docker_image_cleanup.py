#!/usr/bin/env python3
"""Object-specific Docker image cleanup for one approved GATE-03 batch."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import errno
import fcntl
import grp
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence


IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DIGEST_REF_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
TAG_REF_RE = re.compile(r"^[^\s@]+:[^\s@:]+$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
DEVICE_RE = re.compile(r"^\d+:\d+$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MAX_BATCH_SIZE = 10
MAX_DOCUMENT_BYTES = 1024 * 1024
APPROVAL_GATE = "GATE-03"
SCHEMA_VERSION = 2
GLOBAL_STORAGE_LOCK = Path("/run/lock/sealai-storage-mutation.lock")
PRODUCTION_CHECKOUT = Path("/home/thorsten/sealai")
MINIMUM_FREE_BYTES = 3 * 1024**3
TARGET_MAX_USED_PERCENT = 80
MAX_APPROVAL_LIFETIME = dt.timedelta(hours=4)
MAX_RECOVERY_EVIDENCE_LIFETIME = dt.timedelta(hours=24)
DOCKER_BINARY = "/usr/bin/docker"
GIT_BINARY = "/usr/bin/git"
LOCAL_DOCKER_HOST = "unix:///var/run/docker.sock"
GIT_SAFE_CONFIG_ARGS = (
    "--no-optional-locks",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.fsmonitor=false",
)
REMOVE_COMMAND_PREFIX = (DOCKER_BINARY, "image", "rm", "--no-prune")
CORE_CONTAINERS = (
    "backend-v2",
    "backend-v2-worker",
    "sealai-frontend-1",
    "nginx",
    "keycloak",
    "postgres",
    "redis",
    "qdrant",
)
APPROVED_CLEANUP_REPOSITORIES = frozenset({"ghcr.io/jungt72/sealai-backend-v2"})
PROTECTION_ROLES = frozenset(
    {
        "production_desired",
        "staging",
        "rollback_primary",
        "rollback_secondary",
        "legacy_v1",
        "foreign_workloads",
    }
)
MANDATORY_PRESENT_ROLES = frozenset(
    {"production_desired", "rollback_primary", "rollback_secondary"}
)
PROTECTED_TAG_MARKERS = (
    ":latest",
    ":local",
    ":rollback-hold-",
    ":rollback-pre-",
    ":rollback-reconstructed-",
    "sealai-staging-",
    "sealai-keycloak:rollback-hold-",
)


class CleanupError(RuntimeError):
    """Expected fail-closed validation or runtime error."""


class RemovalInterrupted(BaseException):
    """A process signal interrupted an image removal with unknown outcome."""

    def __init__(self, signum: int) -> None:
        super().__init__(f"signal {signum} interrupted image removal")
        self.signum = signum


@dataclass(frozen=True)
class ImageCandidate:
    image_id: str
    expected_repo_digests: tuple[str, ...]
    expected_repo_tags: tuple[str, ...]
    expected_labels_sha256: str
    estimated_reclaim_bytes: int


@dataclass(frozen=True)
class RoleAttestation:
    role: str
    status: str
    image_ids: tuple[str, ...]


@dataclass(frozen=True)
class HostBinding:
    hostname: str
    machine_id_sha256: str


@dataclass(frozen=True)
class CheckoutBinding:
    path: Path
    branch: str
    commit: str
    tree: str
    clean: bool
    fingerprint_sha256: str


@dataclass(frozen=True)
class StorageBinding:
    docker_root_dir: Path
    target_filesystem: Path
    device_major_minor: str
    minimum_free_bytes: int
    target_max_used_percent: int


@dataclass(frozen=True)
class RecoveryEvidence:
    evidence_id: str
    kind: str
    status: str
    evidence_sha256: str
    verified_at: dt.datetime
    valid_until: dt.datetime


@dataclass(frozen=True)
class CoreContainerBinding:
    name: str
    image_id: str


@dataclass(frozen=True)
class OperationBinding:
    operation_id: str
    host: HostBinding
    checkout: CheckoutBinding
    storage: StorageBinding
    core_containers: tuple[CoreContainerBinding, ...]
    production_fingerprint_sha256: str
    command_sha256: str


@dataclass(frozen=True)
class FilesystemSnapshot:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    device_major_minor: str

    @property
    def target_reached(self) -> bool:
        user_visible_bytes = self.used_bytes + self.free_bytes
        return (
            user_visible_bytes > 0
            and self.used_bytes * 100 <= user_visible_bytes * TARGET_MAX_USED_PERCENT
        )


@dataclass(frozen=True)
class ExecutionCheckpoint:
    filesystem: FilesystemSnapshot
    protected_image_ids: set[str]


@dataclass(frozen=True)
class BatchOutcome:
    removed_count: int
    remaining_count: int
    target_reached: bool
    initial_free_bytes: int
    final_free_bytes: int


@dataclass(frozen=True)
class CleanupManifest:
    digest: str
    minimum_reclaim_bytes: int
    images: tuple[ImageCandidate, ...]
    roles: tuple[RoleAttestation, ...]
    operation: OperationBinding
    backup_evidence: RecoveryEvidence
    rollback_evidence: RecoveryEvidence
    protection_sha256: str

    @property
    def protected_image_ids(self) -> set[str]:
        return {image_id for role in self.roles for image_id in role.image_ids}


@dataclass(frozen=True)
class CleanupApproval:
    approval_id: str
    approved_at: dt.datetime
    expires_at: dt.datetime


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
HostProbe = Callable[[], HostBinding]
FilesystemProbe = Callable[[Path, Path], FilesystemSnapshot]
NowProvider = Callable[[], dt.datetime]


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment["PATH"] = "/usr/sbin:/usr/bin:/sbin:/bin"
    environment["DOCKER_HOST"] = LOCAL_DOCKER_HOST
    environment.pop("DOCKER_CONTEXT", None)
    environment.pop("DOCKER_TLS_VERIFY", None)
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
    )


def emit(event: str, status_value: str, **fields: object) -> None:
    payload = {
        "event": event,
        "status": status_value,
        "timestamp": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        **fields,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _read_private_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CleanupError("private document unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > MAX_DOCUMENT_BYTES
        ):
            raise CleanupError("private document is unsafe")
        chunks: list[bytes] = []
        remaining = MAX_DOCUMENT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise CleanupError("private document is too large")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CleanupError("private document is invalid") from exc
    if not isinstance(value, dict):
        raise CleanupError("private document root must be an object")
    return raw, value


def _repository(reference: str) -> str:
    without_digest = reference.split("@", 1)[0]
    slash = without_digest.rfind("/")
    colon = without_digest.rfind(":")
    return without_digest[:colon] if colon > slash else without_digest


def _validate_candidate(item: Any, index: int) -> ImageCandidate:
    expected_fields = {
        "type",
        "id",
        "expected_repo_digests",
        "expected_repo_tags",
        "expected_labels_sha256",
        "estimated_reclaim_bytes",
        "active_dependency",
        "safe_to_remove",
        "backup_required",
        "recovery",
    }
    if not isinstance(item, dict) or set(item) != expected_fields:
        raise CleanupError(f"object {index} has missing or unexpected fields")
    image_id = item["id"]
    if (
        item["type"] != "docker_image"
        or not isinstance(image_id, str)
        or not IMAGE_ID_RE.fullmatch(image_id)
    ):
        raise CleanupError(f"object {index} is not an exact Docker image id")
    if item["active_dependency"] is not False or item["safe_to_remove"] is not True:
        raise CleanupError(f"object {index} is not safely classified")
    if item["backup_required"] is not False:
        raise CleanupError(f"object {index} requires a backup")

    estimated = item["estimated_reclaim_bytes"]
    if not isinstance(estimated, int) or isinstance(estimated, bool) or estimated <= 0:
        raise CleanupError(f"object {index} has invalid reclaim bytes")
    digests = item["expected_repo_digests"]
    tags = item["expected_repo_tags"]
    labels_sha256 = item["expected_labels_sha256"]
    if (
        not isinstance(digests, list)
        or not digests
        or any(
            not isinstance(value, str) or not DIGEST_REF_RE.fullmatch(value)
            for value in digests
        )
        or len(digests) != len(set(digests))
    ):
        raise CleanupError(f"object {index} needs immutable recovery digests")
    if (
        not isinstance(tags, list)
        or any(
            not isinstance(value, str) or not TAG_REF_RE.fullmatch(value)
            for value in tags
        )
        or len(tags) != len(set(tags))
    ):
        raise CleanupError(f"object {index} has invalid expected tags")
    if not isinstance(labels_sha256, str) or not SHA256_RE.fullmatch(labels_sha256):
        raise CleanupError(f"object {index} has invalid expected labels digest")
    repositories = {_repository(value) for value in [*digests, *tags]}
    if repositories != APPROVED_CLEANUP_REPOSITORIES:
        raise CleanupError(
            f"object {index} is outside the cleanup repository allowlist"
        )

    recovery = item["recovery"]
    if (
        not isinstance(recovery, dict)
        or set(recovery) != {"kind", "reference"}
        or recovery.get("kind") != "registry_digest"
        or recovery.get("reference") not in digests
    ):
        raise CleanupError(f"object {index} has no immutable recovery reference")
    return ImageCandidate(
        image_id=image_id,
        expected_repo_digests=tuple(sorted(digests)),
        expected_repo_tags=tuple(sorted(tags)),
        expected_labels_sha256=labels_sha256,
        estimated_reclaim_bytes=estimated,
    )


def _validate_protection(value: Any) -> tuple[RoleAttestation, ...]:
    if not isinstance(value, dict) or set(value) != {"role_attestations"}:
        raise CleanupError("protection has missing or unexpected fields")
    raw_roles = value["role_attestations"]
    if not isinstance(raw_roles, dict) or set(raw_roles) != PROTECTION_ROLES:
        raise CleanupError("protection roles are incomplete or unexpected")
    roles: list[RoleAttestation] = []
    seen_ids: set[str] = set()
    for role in sorted(PROTECTION_ROLES):
        record = raw_roles[role]
        if not isinstance(record, dict) or set(record) != {"status", "image_ids"}:
            raise CleanupError("protection role schema is invalid")
        status_value = record["status"]
        image_ids = record["image_ids"]
        if status_value not in {"PRESENT", "NONE_APPROVED"} or not isinstance(
            image_ids, list
        ):
            raise CleanupError("protection role status is invalid")
        if any(
            not isinstance(value, str) or not IMAGE_ID_RE.fullmatch(value)
            for value in image_ids
        ):
            raise CleanupError("protected image id is invalid")
        if len(image_ids) != len(set(image_ids)):
            raise CleanupError("protected role contains duplicate ids")
        if status_value == "PRESENT" and not image_ids:
            raise CleanupError("present protection role is empty")
        if status_value == "NONE_APPROVED" and image_ids:
            raise CleanupError("none-approved protection role has ids")
        if role in MANDATORY_PRESENT_ROLES and status_value != "PRESENT":
            raise CleanupError("mandatory protection role is not present")
        overlap = seen_ids.intersection(image_ids)
        if overlap and role in {"rollback_primary", "rollback_secondary"}:
            raise CleanupError("rollback protection ids must be distinct")
        seen_ids.update(image_ids)
        roles.append(RoleAttestation(role, status_value, tuple(sorted(image_ids))))
    primary = next(role for role in roles if role.role == "rollback_primary")
    secondary = next(role for role in roles if role.role == "rollback_secondary")
    if len(primary.image_ids) != 1 or len(secondary.image_ids) != 1:
        raise CleanupError("exactly two distinct rollback images are required")
    return tuple(roles)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _expected_command_sha256(images: Sequence[ImageCandidate]) -> str:
    commands = [[*REMOVE_COMMAND_PREFIX, image.image_id] for image in images]
    return _canonical_sha256(commands)


def _expected_protection_sha256(roles: Sequence[RoleAttestation]) -> str:
    value = {
        role.role: {"status": role.status, "image_ids": list(role.image_ids)}
        for role in roles
    }
    return _canonical_sha256(value)


def _repository_fingerprint(host: HostBinding, checkout: CheckoutBinding) -> str:
    return _canonical_sha256(
        {
            "hostname": host.hostname,
            "machine_id_sha256": host.machine_id_sha256,
            "checkout_path": str(checkout.path),
            "branch": checkout.branch,
            "commit": checkout.commit,
            "tree": checkout.tree,
            "clean": checkout.clean,
        }
    )


def _production_fingerprint(
    host: HostBinding,
    checkout: CheckoutBinding,
    storage: StorageBinding,
    core_containers: Sequence[CoreContainerBinding],
    protection_sha256: str,
) -> str:
    return _canonical_sha256(
        {
            "host": {
                "hostname": host.hostname,
                "machine_id_sha256": host.machine_id_sha256,
            },
            "repository_fingerprint_sha256": checkout.fingerprint_sha256,
            "docker_storage": {
                "docker_root_dir": str(storage.docker_root_dir),
                "target_filesystem": str(storage.target_filesystem),
                "device_major_minor": storage.device_major_minor,
            },
            "core_container_image_ids": {
                container.name: container.image_id for container in core_containers
            },
            "protection_sha256": protection_sha256,
        }
    )


def _validate_absolute_normalized_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.startswith("/"):
        raise CleanupError(f"{field} must be an absolute path")
    path = Path(value)
    if str(path) != value or any(part in {".", ".."} for part in path.parts):
        raise CleanupError(f"{field} must be lexically normalized")
    return path


def _validate_recovery_evidence(
    value: Any, *, expected_kind: str, expected_status: str, field: str
) -> RecoveryEvidence:
    expected_fields = {
        "kind",
        "status",
        "evidence_id",
        "evidence_sha256",
        "verified_at",
        "valid_until",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise CleanupError(f"{field} evidence schema is invalid")
    if value["kind"] != expected_kind:
        raise CleanupError(f"{field} evidence kind is invalid")
    if value["status"] != expected_status:
        raise CleanupError(f"{field} evidence is not verified")
    if not isinstance(value["evidence_id"], str) or not TOKEN_RE.fullmatch(
        value["evidence_id"]
    ):
        raise CleanupError(f"{field} evidence id is invalid")
    if not isinstance(value["evidence_sha256"], str) or not SHA256_RE.fullmatch(
        value["evidence_sha256"]
    ):
        raise CleanupError(f"{field} evidence digest is invalid")
    verified_at = _parse_utc(value["verified_at"], f"{field} verified_at")
    valid_until = _parse_utc(value["valid_until"], f"{field} valid_until")
    if (
        valid_until <= verified_at
        or valid_until > verified_at + MAX_RECOVERY_EVIDENCE_LIFETIME
    ):
        raise CleanupError(f"{field} evidence lifetime is invalid")
    return RecoveryEvidence(
        evidence_id=value["evidence_id"],
        kind=value["kind"],
        status=value["status"],
        evidence_sha256=value["evidence_sha256"],
        verified_at=verified_at,
        valid_until=valid_until,
    )


def _validate_operation(
    value: Any,
    images: Sequence[ImageCandidate],
    protection_sha256: str,
) -> OperationBinding:
    if not isinstance(value, dict) or set(value) != {
        "operation_id",
        "host",
        "checkout",
        "docker_storage",
        "core_containers",
        "production_fingerprint_sha256",
        "command",
    }:
        raise CleanupError("operation has missing or unexpected fields")
    operation_id = value["operation_id"]
    if not isinstance(operation_id, str) or not TOKEN_RE.fullmatch(operation_id):
        raise CleanupError("operation id is invalid")

    host = value["host"]
    if not isinstance(host, dict) or set(host) != {
        "hostname",
        "machine_id_sha256",
    }:
        raise CleanupError("host binding schema is invalid")
    if not isinstance(host["hostname"], str) or not HOSTNAME_RE.fullmatch(
        host["hostname"]
    ):
        raise CleanupError("approved hostname is invalid")
    if not isinstance(host["machine_id_sha256"], str) or not SHA256_RE.fullmatch(
        host["machine_id_sha256"]
    ):
        raise CleanupError("approved machine identity is invalid")
    host_binding = HostBinding(host["hostname"], host["machine_id_sha256"])

    checkout = value["checkout"]
    if not isinstance(checkout, dict) or set(checkout) != {
        "path",
        "branch",
        "commit",
        "tree",
        "clean",
        "fingerprint_sha256",
    }:
        raise CleanupError("checkout binding schema is invalid")
    checkout_path = _validate_absolute_normalized_path(
        checkout["path"], "checkout path"
    )
    if checkout_path != PRODUCTION_CHECKOUT:
        raise CleanupError("checkout is not the fixed production checkout")
    if (
        checkout["branch"] != "main"
        or not isinstance(checkout["commit"], str)
        or not GIT_OID_RE.fullmatch(checkout["commit"])
        or not isinstance(checkout["tree"], str)
        or not GIT_OID_RE.fullmatch(checkout["tree"])
        or checkout["clean"] is not True
        or not isinstance(checkout["fingerprint_sha256"], str)
        or not SHA256_RE.fullmatch(checkout["fingerprint_sha256"])
    ):
        raise CleanupError("checkout binding is invalid")
    checkout_binding = CheckoutBinding(
        path=checkout_path,
        branch=checkout["branch"],
        commit=checkout["commit"],
        tree=checkout["tree"],
        clean=True,
        fingerprint_sha256=checkout["fingerprint_sha256"],
    )
    if (
        _repository_fingerprint(host_binding, checkout_binding)
        != checkout_binding.fingerprint_sha256
    ):
        raise CleanupError("checkout fingerprint does not match its bound identity")

    storage = value["docker_storage"]
    if not isinstance(storage, dict) or set(storage) != {
        "docker_root_dir",
        "target_filesystem",
        "device_major_minor",
        "minimum_free_bytes",
        "target_max_used_percent",
    }:
        raise CleanupError("Docker storage binding schema is invalid")
    docker_root_dir = _validate_absolute_normalized_path(
        storage["docker_root_dir"], "Docker root"
    )
    target_filesystem = _validate_absolute_normalized_path(
        storage["target_filesystem"], "target filesystem"
    )
    try:
        docker_root_dir.relative_to(target_filesystem)
    except ValueError as exc:
        raise CleanupError("Docker root is outside the target filesystem") from exc
    if (
        not isinstance(storage["device_major_minor"], str)
        or not DEVICE_RE.fullmatch(storage["device_major_minor"])
        or storage["minimum_free_bytes"] != MINIMUM_FREE_BYTES
        or storage["target_max_used_percent"] != TARGET_MAX_USED_PERCENT
    ):
        raise CleanupError("Docker storage safety boundary is invalid")
    storage_binding = StorageBinding(
        docker_root_dir=docker_root_dir,
        target_filesystem=target_filesystem,
        device_major_minor=storage["device_major_minor"],
        minimum_free_bytes=MINIMUM_FREE_BYTES,
        target_max_used_percent=TARGET_MAX_USED_PERCENT,
    )

    raw_core_containers = value["core_containers"]
    if not isinstance(raw_core_containers, dict) or set(raw_core_containers) != set(
        CORE_CONTAINERS
    ):
        raise CleanupError("core container set is invalid")
    core_containers: list[CoreContainerBinding] = []
    for name in CORE_CONTAINERS:
        record = raw_core_containers[name]
        if (
            not isinstance(record, dict)
            or set(record) != {"image_id"}
            or not isinstance(record["image_id"], str)
            or not IMAGE_ID_RE.fullmatch(record["image_id"])
        ):
            raise CleanupError("core container image binding is invalid")
        core_containers.append(CoreContainerBinding(name, record["image_id"]))

    production_fingerprint_sha256 = value["production_fingerprint_sha256"]
    if (
        not isinstance(production_fingerprint_sha256, str)
        or not SHA256_RE.fullmatch(production_fingerprint_sha256)
        or production_fingerprint_sha256
        != _production_fingerprint(
            host_binding,
            checkout_binding,
            storage_binding,
            core_containers,
            protection_sha256,
        )
    ):
        raise CleanupError("production fingerprint binding is invalid")

    command = value["command"]
    if not isinstance(command, dict) or set(command) != {
        "argv_prefix",
        "ordered_image_ids",
        "commands_sha256",
    }:
        raise CleanupError("command binding schema is invalid")
    expected_ids = [image.image_id for image in images]
    expected_command_sha256 = _expected_command_sha256(images)
    if (
        command["argv_prefix"] != list(REMOVE_COMMAND_PREFIX)
        or command["ordered_image_ids"] != expected_ids
        or command["commands_sha256"] != expected_command_sha256
    ):
        raise CleanupError("command binding does not match the exact batch")

    return OperationBinding(
        operation_id=operation_id,
        host=host_binding,
        checkout=checkout_binding,
        storage=storage_binding,
        core_containers=tuple(core_containers),
        production_fingerprint_sha256=production_fingerprint_sha256,
        command_sha256=expected_command_sha256,
    )


def load_manifest(path: Path) -> CleanupManifest:
    raw, data = _read_private_json(path)
    if set(data) != {
        "schema_version",
        "gate_id",
        "purpose",
        "minimum_reclaim_bytes",
        "operation",
        "recovery_evidence",
        "protection",
        "objects",
    }:
        raise CleanupError("manifest has missing or unexpected root fields")
    if data["schema_version"] != SCHEMA_VERSION or data["gate_id"] != APPROVAL_GATE:
        raise CleanupError("manifest schema or gate is invalid")
    if not isinstance(data["purpose"], str) or not data["purpose"].strip():
        raise CleanupError("manifest purpose is required")
    minimum_reclaim = data["minimum_reclaim_bytes"]
    if (
        not isinstance(minimum_reclaim, int)
        or isinstance(minimum_reclaim, bool)
        or minimum_reclaim <= 0
    ):
        raise CleanupError("minimum reclaim must be positive")
    objects = data["objects"]
    if not isinstance(objects, list) or not 1 <= len(objects) <= MAX_BATCH_SIZE:
        raise CleanupError("one manifest must contain one batch of one to ten images")
    candidates = tuple(
        _validate_candidate(item, index) for index, item in enumerate(objects)
    )
    if len({candidate.image_id for candidate in candidates}) != len(candidates):
        raise CleanupError("manifest contains duplicate image ids")
    if (
        sum(candidate.estimated_reclaim_bytes for candidate in candidates)
        < minimum_reclaim
    ):
        raise CleanupError("manifest estimate is below its reclaim target")
    roles = _validate_protection(data["protection"])
    protected = {image_id for role in roles for image_id in role.image_ids}
    if protected.intersection(candidate.image_id for candidate in candidates):
        raise CleanupError("cleanup candidate intersects a protected role")
    protection_sha256 = _expected_protection_sha256(roles)
    operation = _validate_operation(data["operation"], candidates, protection_sha256)
    recovery = data["recovery_evidence"]
    if not isinstance(recovery, dict) or set(recovery) != {"backup", "rollback"}:
        raise CleanupError("recovery evidence schema is invalid")
    backup_evidence = _validate_recovery_evidence(
        recovery["backup"],
        expected_kind="encrypted_offsite_restore_verified",
        expected_status="VERIFIED",
        field="backup",
    )
    rollback_evidence = _validate_recovery_evidence(
        recovery["rollback"],
        expected_kind="registry_digest_pull_verified",
        expected_status="EXECUTABLE_VERIFIED",
        field="rollback",
    )
    return CleanupManifest(
        digest=hashlib.sha256(raw).hexdigest(),
        minimum_reclaim_bytes=minimum_reclaim,
        images=candidates,
        roles=roles,
        operation=operation,
        backup_evidence=backup_evidence,
        rollback_evidence=rollback_evidence,
        protection_sha256=protection_sha256,
    )


def _docker_json(command: Sequence[str], runner: Runner) -> Any:
    result = runner(command)
    if result.returncode != 0:
        raise CleanupError("Docker inspection failed")
    try:
        return json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CleanupError("Docker inspection returned invalid JSON") from exc


def _inspect_one(reference: str, runner: Runner) -> dict[str, Any]:
    inspected = _docker_json([DOCKER_BINARY, "image", "inspect", reference], runner)
    if (
        not isinstance(inspected, list)
        or len(inspected) != 1
        or not isinstance(inspected[0], dict)
    ):
        raise CleanupError("image inspection did not return exactly one image")
    return inspected[0]


def referenced_image_ids(runner: Runner = _run) -> set[str]:
    result = runner([DOCKER_BINARY, "container", "ls", "--all", "--quiet"])
    if result.returncode != 0:
        raise CleanupError("cannot enumerate all containers")
    container_ids = [
        line.strip() for line in result.stdout.splitlines() if line.strip()
    ]
    if not container_ids:
        return set()
    inspected = _docker_json(
        [DOCKER_BINARY, "container", "inspect", *container_ids], runner
    )
    if not isinstance(inspected, list):
        raise CleanupError("container inspection did not return a list")
    referenced: set[str] = set()
    for item in inspected:
        image_id = item.get("Image") if isinstance(item, dict) else None
        if not isinstance(image_id, str) or not IMAGE_ID_RE.fullmatch(image_id):
            raise CleanupError("container inspection omitted an exact image id")
        referenced.add(image_id)
    return referenced


def compose_desired_image_ids(runner: Runner = _run) -> set[str]:
    command = [
        DOCKER_BINARY,
        "compose",
        "--project-directory",
        str(PRODUCTION_CHECKOUT),
        "--env-file",
        str(PRODUCTION_CHECKOUT / ".env.prod"),
        "-f",
        str(PRODUCTION_CHECKOUT / "docker-compose.yml"),
        "-f",
        str(PRODUCTION_CHECKOUT / "docker-compose.deploy.yml"),
        "--profile",
        "v2",
        "--profile",
        "frontend-container",
        "config",
        "--images",
    ]
    result = runner(command)
    if result.returncode != 0:
        raise CleanupError("cannot resolve desired production images")
    references = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if not references:
        raise CleanupError("desired production image set is empty")
    desired: set[str] = set()
    for reference in sorted(references):
        image_id = _inspect_one(reference, runner).get("Id")
        if not isinstance(image_id, str) or not IMAGE_ID_RE.fullmatch(image_id):
            raise CleanupError("desired production image id is invalid")
        desired.add(image_id)
    return desired


def _role_ids(manifest: CleanupManifest, role_name: str) -> set[str]:
    return {
        image_id
        for role in manifest.roles
        if role.role == role_name
        for image_id in role.image_ids
    }


def validate_protection(manifest: CleanupManifest, runner: Runner = _run) -> set[str]:
    rollback_markers = (
        ":rollback-hold-",
        ":rollback-pre-",
        ":rollback-reconstructed-",
    )
    for role in manifest.roles:
        for image_id in role.image_ids:
            item = _inspect_one(image_id, runner)
            if item.get("Id") != image_id:
                raise CleanupError("protected image identity changed")
            tags = item.get("RepoTags") or []
            config = item.get("Config")
            labels = config.get("Labels") or {} if isinstance(config, dict) else {}
            if role.role in {"rollback_primary", "rollback_secondary"} and not any(
                marker in tag for marker in rollback_markers for tag in tags
            ):
                raise CleanupError("rollback role lacks runtime rollback evidence")
            if role.role == "staging" and not (
                labels.get("com.docker.compose.project") == "sealai-staging"
                or any("sealai-staging-" in tag for tag in tags)
            ):
                raise CleanupError("staging role lacks runtime staging evidence")
            if role.role == "legacy_v1" and not any(
                _repository(tag) == "ghcr.io/jungt72/sealai-backend" for tag in tags
            ):
                raise CleanupError("legacy role lacks V1 repository evidence")
            if role.role == "foreign_workloads" and not any(
                _repository(tag) not in APPROVED_CLEANUP_REPOSITORIES for tag in tags
            ):
                raise CleanupError("foreign role lacks foreign repository evidence")
    desired = compose_desired_image_ids(runner)
    if desired != _role_ids(manifest, "production_desired"):
        raise CleanupError("production desired images changed since approval")
    return desired | manifest.protected_image_ids | referenced_image_ids(runner)


def _validate_registry_recovery(candidate: ImageCandidate, runner: Runner) -> None:
    for reference in candidate.expected_repo_digests:
        result = runner([DOCKER_BINARY, "manifest", "inspect", reference])
        if result.returncode != 0:
            raise CleanupError("immutable registry recovery is unavailable")


def inspect_candidate(
    candidate: ImageCandidate, protected: set[str], runner: Runner = _run
) -> None:
    if candidate.image_id in protected:
        raise CleanupError("planned image is operationally protected")
    item = _inspect_one(candidate.image_id, runner)
    actual_id = item.get("Id")
    actual_digests = item.get("RepoDigests") or []
    actual_tags = item.get("RepoTags") or []
    config = item.get("Config")
    actual_labels = config.get("Labels") or {} if isinstance(config, dict) else {}
    if actual_id != candidate.image_id:
        raise CleanupError("image id changed since approval")
    if sorted(actual_digests) != list(candidate.expected_repo_digests):
        raise CleanupError("image registry digests changed since approval")
    if sorted(actual_tags) != list(candidate.expected_repo_tags):
        raise CleanupError("image tags changed since approval")
    if not isinstance(actual_labels, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in actual_labels.items()
    ):
        raise CleanupError("image labels are invalid")
    if _canonical_sha256(actual_labels) != candidate.expected_labels_sha256:
        raise CleanupError("image labels changed since approval")
    if any(marker in tag for marker in PROTECTED_TAG_MARKERS for tag in actual_tags):
        raise CleanupError("image has a protected operational tag")
    if any(
        _repository(reference) not in APPROVED_CLEANUP_REPOSITORIES
        for reference in [*actual_digests, *actual_tags]
    ):
        raise CleanupError("image repository is not cleanup-approved")
    if actual_labels.get("com.docker.compose.project") == "sealai-staging":
        raise CleanupError("staging image is protected")
    _validate_registry_recovery(candidate, runner)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _default_host_probe() -> HostBinding:
    hostname = socket.gethostname()
    if not HOSTNAME_RE.fullmatch(hostname):
        raise CleanupError("runtime hostname is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open("/etc/machine-id", flags)
    except OSError as exc:
        raise CleanupError("machine identity is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 256:
            raise CleanupError("machine identity source is unsafe")
        raw = os.read(descriptor, 257)
    finally:
        os.close(descriptor)
    normalized = raw.strip()
    if not re.fullmatch(rb"[0-9a-f]{32}", normalized):
        raise CleanupError("machine identity source is invalid")
    return HostBinding(hostname, hashlib.sha256(normalized).hexdigest())


def _default_filesystem_probe(
    docker_root_dir: Path, target_filesystem: Path
) -> FilesystemSnapshot:
    try:
        resolved_root = docker_root_dir.resolve(strict=True)
        resolved_target = target_filesystem.resolve(strict=True)
        root_metadata = resolved_root.stat()
        target_metadata = resolved_target.stat()
        usage = shutil.disk_usage(resolved_target)
    except OSError as exc:
        raise CleanupError("Docker storage filesystem is unavailable") from exc
    if resolved_root != docker_root_dir or resolved_target != target_filesystem:
        raise CleanupError("Docker storage path identity changed")
    if not resolved_root.is_dir() or not resolved_target.is_dir():
        raise CleanupError("Docker storage path is not a directory")
    if not os.path.ismount(resolved_target):
        raise CleanupError("approved Docker target is not a mount point")
    if root_metadata.st_dev != target_metadata.st_dev:
        raise CleanupError("Docker root moved off the approved filesystem")
    if usage.total <= 0 or usage.free < 0 or usage.used < 0:
        raise CleanupError("Docker storage capacity is invalid")
    return FilesystemSnapshot(
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        device_major_minor=f"{os.major(root_metadata.st_dev)}:{os.minor(root_metadata.st_dev)}",
    )


def _command_stdout(command: Sequence[str], runner: Runner, failure: str) -> str:
    result = runner(command)
    if result.returncode != 0 or not isinstance(result.stdout, str):
        raise CleanupError(failure)
    return result.stdout.rstrip("\n")


def _validate_host_and_checkout(
    manifest: CleanupManifest,
    runner: Runner,
    host_probe: HostProbe,
) -> None:
    actual_host = host_probe()
    if actual_host != manifest.operation.host:
        raise CleanupError("approved host identity changed")
    checkout = manifest.operation.checkout
    command_prefix = [
        GIT_BINARY,
        *GIT_SAFE_CONFIG_ARGS,
        "-C",
        str(checkout.path),
    ]
    actual_root = _command_stdout(
        [*command_prefix, "rev-parse", "--show-toplevel"],
        runner,
        "production checkout is unavailable",
    )
    actual_branch = _command_stdout(
        [*command_prefix, "symbolic-ref", "--short", "HEAD"],
        runner,
        "production checkout branch is unavailable",
    )
    actual_commit = _command_stdout(
        [*command_prefix, "rev-parse", "HEAD"],
        runner,
        "production checkout commit is unavailable",
    )
    actual_tree = _command_stdout(
        [*command_prefix, "rev-parse", "HEAD^{tree}"],
        runner,
        "production checkout tree is unavailable",
    )
    status_output = _command_stdout(
        [*command_prefix, "status", "--porcelain=v1", "--untracked-files=all"],
        runner,
        "production checkout status is unavailable",
    )
    if status_output:
        raise CleanupError("production checkout fingerprint drifted")
    if (
        actual_root != str(checkout.path)
        or actual_branch != checkout.branch
        or actual_commit != checkout.commit
        or actual_tree != checkout.tree
    ):
        raise CleanupError("production checkout fingerprint drifted")
    actual_checkout = CheckoutBinding(
        path=checkout.path,
        branch=actual_branch,
        commit=actual_commit,
        tree=actual_tree,
        clean=True,
        fingerprint_sha256=checkout.fingerprint_sha256,
    )
    if (
        _repository_fingerprint(actual_host, actual_checkout)
        != checkout.fingerprint_sha256
    ):
        raise CleanupError("production checkout fingerprint drifted")


def _validate_storage_identity(
    manifest: CleanupManifest,
    runner: Runner,
    filesystem_probe: FilesystemProbe,
) -> FilesystemSnapshot:
    storage = manifest.operation.storage
    raw_docker_root = _command_stdout(
        [DOCKER_BINARY, "info", "--format", "{{json .DockerRootDir}}"],
        runner,
        "Docker root identity is unavailable",
    )
    try:
        docker_root_value = json.loads(raw_docker_root)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CleanupError("Docker root identity is invalid") from exc
    if docker_root_value != str(storage.docker_root_dir):
        raise CleanupError("Docker root identity changed")
    snapshot = filesystem_probe(storage.docker_root_dir, storage.target_filesystem)
    if snapshot.device_major_minor != storage.device_major_minor:
        raise CleanupError("Docker storage device identity changed")
    if (
        snapshot.total_bytes <= 0
        or snapshot.used_bytes < 0
        or snapshot.free_bytes < 0
        or snapshot.used_bytes + snapshot.free_bytes > snapshot.total_bytes
    ):
        raise CleanupError("Docker storage capacity is invalid")
    if snapshot.free_bytes < storage.minimum_free_bytes:
        raise CleanupError("free Docker storage is below 3 GiB")
    return snapshot


def _validate_core_container_health(manifest: CleanupManifest, runner: Runner) -> None:
    expected_images = {
        container.name: container.image_id
        for container in manifest.operation.core_containers
    }
    inspected = _docker_json(
        [
            DOCKER_BINARY,
            "container",
            "inspect",
            *expected_images,
        ],
        runner,
    )
    if not isinstance(inspected, list) or len(inspected) != len(CORE_CONTAINERS):
        raise CleanupError("core container inspection is incomplete")
    observed: set[str] = set()
    for item in inspected:
        if not isinstance(item, dict):
            raise CleanupError("core container inspection is invalid")
        name = item.get("Name")
        image_id = item.get("Image")
        state = item.get("State")
        normalized_name = (
            name[1:] if isinstance(name, str) and name.startswith("/") else None
        )
        if (
            normalized_name not in CORE_CONTAINERS
            or image_id != expected_images.get(normalized_name)
            or not isinstance(state, dict)
            or state.get("Running") is not True
            or state.get("Status") != "running"
            or not isinstance(state.get("Health"), dict)
            or state["Health"].get("Status") != "healthy"
        ):
            raise CleanupError("a fixed core container is not running and healthy")
        observed.add(normalized_name)
    if observed != set(CORE_CONTAINERS):
        raise CleanupError("core container identity set changed")


def _ensure_recovery_evidence_current(
    manifest: CleanupManifest, now: dt.datetime
) -> None:
    for field, evidence in (
        ("backup", manifest.backup_evidence),
        ("rollback", manifest.rollback_evidence),
    ):
        if evidence.verified_at > now + dt.timedelta(minutes=5):
            raise CleanupError(f"{field} evidence is future-dated")
        if evidence.valid_until <= now:
            raise CleanupError(f"{field} evidence expired during cleanup")


def validate_execution_checkpoint(
    manifest: CleanupManifest,
    approval: CleanupApproval | None,
    *,
    runner: Runner = _run,
    host_probe: HostProbe = _default_host_probe,
    filesystem_probe: FilesystemProbe = _default_filesystem_probe,
    now: dt.datetime | None = None,
) -> ExecutionCheckpoint:
    current = now or _utc_now()
    if approval is not None:
        ensure_approval_current(approval, current)
    _ensure_recovery_evidence_current(manifest, current)
    _validate_host_and_checkout(manifest, runner, host_probe)
    filesystem = _validate_storage_identity(manifest, runner, filesystem_probe)
    _validate_core_container_health(manifest, runner)
    protected = validate_protection(manifest, runner)
    return ExecutionCheckpoint(filesystem, protected)


def validate_runtime(
    manifest: CleanupManifest,
    runner: Runner = _run,
    *,
    host_probe: HostProbe = _default_host_probe,
    filesystem_probe: FilesystemProbe = _default_filesystem_probe,
    now: dt.datetime | None = None,
) -> None:
    checkpoint = validate_execution_checkpoint(
        manifest,
        None,
        runner=runner,
        host_probe=host_probe,
        filesystem_probe=filesystem_probe,
        now=now,
    )
    for candidate in manifest.images:
        inspect_candidate(candidate, checkpoint.protected_image_ids, runner)


def _parse_utc(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise CleanupError(f"{field} timestamp is invalid")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CleanupError(f"{field} timestamp is invalid") from exc


def validate_approval(
    path: Path, manifest: CleanupManifest, now: dt.datetime | None = None
) -> CleanupApproval:
    _, data = _read_private_json(path)
    if set(data) != {
        "schema_version",
        "gate_id",
        "decision",
        "approval_id",
        "approved_by",
        "approved_at",
        "manifest_sha256",
        "expires_at",
        "operation_id",
        "approved_hostname",
        "approved_machine_id_sha256",
        "repository_fingerprint_sha256",
        "production_fingerprint_sha256",
        "commands_sha256",
        "protection_sha256",
        "backup_evidence_sha256",
        "rollback_evidence_sha256",
    }:
        raise CleanupError("approval has missing or unexpected fields")
    if (
        data["schema_version"] != SCHEMA_VERSION
        or data["gate_id"] != APPROVAL_GATE
        or data["decision"] != "APPROVED"
    ):
        raise CleanupError("approval does not authorize GATE-03")
    if not isinstance(data["approval_id"], str) or not TOKEN_RE.fullmatch(
        data["approval_id"]
    ):
        raise CleanupError("approval id is invalid")
    if not isinstance(data["approved_by"], str) or not TOKEN_RE.fullmatch(
        data["approved_by"]
    ):
        raise CleanupError("approval identity is invalid")
    if data["manifest_sha256"] != manifest.digest:
        raise CleanupError("approval is not bound to this manifest")
    expected_bindings = {
        "operation_id": manifest.operation.operation_id,
        "approved_hostname": manifest.operation.host.hostname,
        "approved_machine_id_sha256": manifest.operation.host.machine_id_sha256,
        "repository_fingerprint_sha256": manifest.operation.checkout.fingerprint_sha256,
        "production_fingerprint_sha256": manifest.operation.production_fingerprint_sha256,
        "commands_sha256": manifest.operation.command_sha256,
        "protection_sha256": manifest.protection_sha256,
        "backup_evidence_sha256": manifest.backup_evidence.evidence_sha256,
        "rollback_evidence_sha256": manifest.rollback_evidence.evidence_sha256,
    }
    if any(data[field] != expected for field, expected in expected_bindings.items()):
        raise CleanupError("approval scope is not bound to the exact operation")
    approved_at = _parse_utc(data["approved_at"], "approval time")
    expires_at = _parse_utc(data["expires_at"], "approval expiry")
    current = now or dt.datetime.now(dt.timezone.utc)
    if approved_at > current + dt.timedelta(minutes=5):
        raise CleanupError("approval is future-dated")
    if (
        expires_at <= current
        or expires_at <= approved_at
        or expires_at > approved_at + MAX_APPROVAL_LIFETIME
    ):
        raise CleanupError("approval is expired or over-broad")
    return CleanupApproval(data["approval_id"], approved_at, expires_at)


def ensure_approval_current(
    approval: CleanupApproval, now: dt.datetime | None = None
) -> None:
    if approval.expires_at <= (now or dt.datetime.now(dt.timezone.utc)):
        raise CleanupError("approval expired during cleanup")


@contextlib.contextmanager
def storage_mutation_lock(
    path: Path = GLOBAL_STORAGE_LOCK,
    *,
    expected_uid: int = 0,
    expected_gid: int | None = None,
    expected_mode: int = 0o660,
) -> Iterator[None]:
    flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CleanupError("storage mutation lock unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        required_gid = (
            grp.getgrnam("thorsten").gr_gid if expected_gid is None else expected_gid
        )
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or metadata.st_gid != required_gid
            or stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise CleanupError("storage mutation lock is unsafe")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise CleanupError("storage mutation lock is busy") from None
            raise CleanupError("storage mutation lock unavailable") from exc
        yield
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def removal_signal_boundary() -> Iterator[None]:
    """Turn termination during `docker image rm` into an auditable unknown result."""

    watched = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous: dict[signal.Signals, Any] = {}

    def interrupted(signum: int, _frame: Any) -> None:
        raise RemovalInterrupted(signum)

    try:
        for watched_signal in watched:
            previous[watched_signal] = signal.getsignal(watched_signal)
            signal.signal(watched_signal, interrupted)
        yield
    finally:
        for watched_signal, handler in previous.items():
            signal.signal(watched_signal, handler)


def execute_batch(
    manifest: CleanupManifest,
    approval: CleanupApproval,
    runner: Runner = _run,
    *,
    host_probe: HostProbe = _default_host_probe,
    filesystem_probe: FilesystemProbe = _default_filesystem_probe,
    now_provider: NowProvider = _utc_now,
) -> BatchOutcome:
    removed = 0
    removal_in_flight = False
    initial_free_bytes: int | None = None
    final_free_bytes: int | None = None
    current_candidate: str | None = manifest.images[0].image_id
    try:
        checkpoint = validate_execution_checkpoint(
            manifest,
            approval,
            runner=runner,
            host_probe=host_probe,
            filesystem_probe=filesystem_probe,
            now=now_provider(),
        )
        initial_free_bytes = checkpoint.filesystem.free_bytes
        final_free_bytes = initial_free_bytes
        if checkpoint.filesystem.target_reached:
            return BatchOutcome(
                removed_count=0,
                remaining_count=len(manifest.images),
                target_reached=True,
                initial_free_bytes=initial_free_bytes,
                final_free_bytes=final_free_bytes,
            )

        for index, candidate in enumerate(manifest.images):
            current_candidate = candidate.image_id
            checkpoint = validate_execution_checkpoint(
                manifest,
                approval,
                runner=runner,
                host_probe=host_probe,
                filesystem_probe=filesystem_probe,
                now=now_provider(),
            )
            final_free_bytes = checkpoint.filesystem.free_bytes
            if checkpoint.filesystem.target_reached:
                break
            inspect_candidate(candidate, checkpoint.protected_image_ids, runner)

            # Re-sample every global invariant after the candidate inspection so
            # the command is immediately preceded by the approved host,
            # checkout, storage, health, TTL and protection boundary.
            checkpoint = validate_execution_checkpoint(
                manifest,
                approval,
                runner=runner,
                host_probe=host_probe,
                filesystem_probe=filesystem_probe,
                now=now_provider(),
            )
            final_free_bytes = checkpoint.filesystem.free_bytes
            if checkpoint.filesystem.target_reached:
                break
            inspect_candidate(candidate, checkpoint.protected_image_ids, runner)
            ensure_approval_current(approval, now_provider())
            removal_in_flight = True
            with removal_signal_boundary():
                result = runner([*REMOVE_COMMAND_PREFIX, candidate.image_id])
                if result.returncode != 0:
                    raise CleanupError("exact image removal failed")
                removed += 1
                current_candidate = (
                    manifest.images[index + 1].image_id
                    if index + 1 < len(manifest.images)
                    else None
                )
                # Keep this last: a signal before the complete success state is
                # booked must remain an unknown in-flight mutation.
                removal_in_flight = False
            emit("docker_image_removed", "ok", image_id=candidate.image_id)

            checkpoint = validate_execution_checkpoint(
                manifest,
                approval,
                runner=runner,
                host_probe=host_probe,
                filesystem_probe=filesystem_probe,
                now=now_provider(),
            )
            final_free_bytes = checkpoint.filesystem.free_bytes
            if checkpoint.filesystem.target_reached:
                return BatchOutcome(
                    removed_count=removed,
                    remaining_count=len(manifest.images) - removed,
                    target_reached=True,
                    initial_free_bytes=initial_free_bytes,
                    final_free_bytes=final_free_bytes,
                )

        return BatchOutcome(
            removed_count=removed,
            remaining_count=len(manifest.images) - removed,
            target_reached=checkpoint.filesystem.target_reached,
            initial_free_bytes=initial_free_bytes,
            final_free_bytes=final_free_bytes,
        )
    except BaseException as exc:
        if removed or removal_in_flight:
            reason = (
                str(exc)
                if isinstance(exc, CleanupError)
                else "process interrupted or failed after a removal attempt"
            )
            emit(
                "storage_cleanup_batch",
                "indeterminate" if removal_in_flight else "partial",
                removed_count=removed,
                remaining_count=len(manifest.images) - removed,
                stopped_before_image_id=current_candidate,
                removal_outcome_unknown=removal_in_flight,
                reason=reason,
            )
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="validate one batch without mutation")
    plan.add_argument("manifest", type=Path)
    execute = subparsers.add_parser("execute", help="remove exactly one approved batch")
    execute.add_argument("manifest", type=Path)
    execute.add_argument("--approval", required=True, type=Path)
    return parser


def classify_batch_outcome(
    manifest: CleanupManifest, outcome: BatchOutcome
) -> tuple[str, int, int]:
    observed_reclaim = max(0, outcome.final_free_bytes - outcome.initial_free_bytes)
    initial_target_was_already_met = (
        outcome.target_reached and outcome.removed_count == 0
    )
    minimum_observed = observed_reclaim >= manifest.minimum_reclaim_bytes
    if outcome.target_reached and (initial_target_was_already_met or minimum_observed):
        return "target_reached", 0, observed_reclaim
    if outcome.target_reached:
        return "minimum_reclaim_not_observed", 3, observed_reclaim
    return "insufficient_reclaim", 3, observed_reclaim


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        manifest = load_manifest(args.manifest)
        if args.command == "plan":
            validate_runtime(manifest)
            emit(
                "storage_cleanup_plan",
                "validated",
                manifest_sha256=manifest.digest,
                object_count=len(manifest.images),
                estimated_reclaim_bytes=sum(
                    item.estimated_reclaim_bytes for item in manifest.images
                ),
            )
            return 0
        approval = validate_approval(args.approval, manifest)
        with storage_mutation_lock():
            validate_runtime(manifest)
            ensure_approval_current(approval)
            outcome = execute_batch(manifest, approval)
        status_value, exit_code, observed_reclaim = classify_batch_outcome(
            manifest, outcome
        )
        emit(
            "storage_cleanup_batch",
            status_value,
            approval_id=approval.approval_id,
            removed_count=outcome.removed_count,
            remaining_count=outcome.remaining_count,
            initial_free_bytes=outcome.initial_free_bytes,
            final_free_bytes=outcome.final_free_bytes,
            observed_reclaim_bytes=observed_reclaim,
            approved_minimum_reclaim_bytes=manifest.minimum_reclaim_bytes,
            target_max_used_percent=TARGET_MAX_USED_PERCENT,
            health_verification_required=True,
        )
        return exit_code
    except RemovalInterrupted as exc:
        return 128 + exc.signum
    except CleanupError as exc:
        emit("storage_cleanup", "denied", reason=str(exc))
        return 2
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError, TypeError):
        emit("storage_cleanup", "denied", reason="unexpected local runtime failure")
        return 2
    except Exception:
        emit("storage_cleanup", "denied", reason="internal fail-closed boundary")
        return 2


if __name__ == "__main__":
    sys.exit(main())
