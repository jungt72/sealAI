#!/usr/bin/python3 -I
"""Fail-closed manifest, receipt, and metrics contracts for disaster recovery."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn


SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 2
MAX_JSON_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 128 * 1024 * 1024
MAX_FILES = 250_000
MAX_FILE_BYTES = 256 * 1024 * 1024 * 1024
MAX_SET_BYTES = 2 * 1024 * 1024 * 1024 * 1024
MAX_QDRANT_POINTS = 5_000_000
MAX_CLOCK_SKEW_SECONDS = 300
MAX_RECEIPT_AGE_SECONDS = 24 * 60 * 60
MAX_DRILL_AGE_SECONDS = 35 * 24 * 60 * 60
MAX_GATE_VALIDITY_SECONDS = 15 * 60
NANOSECONDS_PER_SECOND = 1_000_000_000
TOKEN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})  ([^/\r\n]+)\n$")
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REQUIRED_COMPONENTS = (
    "postgres",
    "qdrant",
    "uploads",
    "documents",
    "configuration",
)
REQUIRED_RECOVERY_FILES = {
    "recovery/recovery-point.json",
    "recovery/qdrant-rebuild.json",
    "recovery/secret-recovery.json",
}
REQUIRED_CONFIGURATION_IDS = {
    "compose_base",
    "compose_deploy",
    "identity",
    "monitoring",
    "nginx",
    "release_control",
}
ALLOWED_SECRET_CUSTODY = {
    "offline_escrow",
    "managed_secret_store",
    "manual_rotation",
}
ALLOWED_RECOVERY_TESTS = {"procedure_only", "nonproduction_key_verified"}
ALLOWED_QDRANT_MODES = {"snapshot_and_rebuild", "postgres_rebuild"}
ALLOWED_GATE_ACTIONS = {
    "dr_offsite_backup",
    "dr_retention_prune",
    "dr_restore_drill",
}
FORBIDDEN_CONFIGURATION_NAMES = {
    ".env",
    ".env.prod",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "secrets",
    "secrets.json",
}
STATUS_KEYS = {
    "backup_last_success_timestamp_seconds",
    "backup_last_failure_timestamp_seconds",
    "offsite_backup_last_success_timestamp_seconds",
    "restore_drill_last_success_timestamp_seconds",
    "backup_receipt_valid",
}
STATUS_COMPONENTS = {*REQUIRED_COMPONENTS, "redis"}
RESTORE_IMAGE_KEYS = {"DR_POSTGRES_IMAGE", "DR_QDRANT_IMAGE", "DR_VERIFIER_IMAGE"}
IMAGE_DIGEST_RE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:[/:][a-z0-9]+(?:[._-][a-z0-9]+)*)*"
    r"@sha256:[0-9a-f]{64}$"
)
METRIC_NAMES = {
    "backup_last_success_timestamp_seconds": (
        "sealai_backup_last_success_timestamp_seconds"
    ),
    "backup_last_failure_timestamp_seconds": (
        "sealai_backup_last_failure_timestamp_seconds"
    ),
    "offsite_backup_last_success_timestamp_seconds": (
        "sealai_offsite_backup_last_success_timestamp_seconds"
    ),
    "restore_drill_last_success_timestamp_seconds": (
        "sealai_restore_drill_last_success_timestamp_seconds"
    ),
    "backup_receipt_valid": "sealai_backup_receipt_valid",
}


class DrError(RuntimeError):
    """An expected fail-closed result containing a non-sensitive reason token."""

    def __init__(self, reason: str) -> None:
        safe_reason = reason if TOKEN_RE.fullmatch(reason) else "dr_error"
        super().__init__(safe_reason)
        self.reason = safe_reason


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _fail(reason: str) -> NoReturn:
    raise DrError(reason)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key")
        result[key] = value
    return result


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _normalized_absolute(path: Path) -> Path:
    raw = str(path)
    if (
        not path.is_absolute()
        or "//" in raw
        or raw != os.path.normpath(raw)
        or any(part in {".", "..", "~"} or part.startswith("~") for part in path.parts)
    ):
        _fail("path_not_normalized_absolute")
    return path


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _fail("invalid_relative_path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail("invalid_relative_path")
    return path


def _validate_file_metadata(
    metadata: os.stat_result, *, private: bool, reason: str
) -> os.stat_result:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.geteuid()
    ):
        _fail(reason)
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & 0o022:
        _fail(reason)
    if private and mode not in {0o400, 0o600}:
        _fail(reason)
    return metadata


def _regular_file(path: Path, *, private: bool, reason: str) -> os.stat_result:
    _normalized_absolute(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise DrError(reason) from exc
    return _validate_file_metadata(metadata, private=private, reason=reason)


def _private_directory(path: Path) -> os.stat_result:
    _normalized_absolute(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise DrError("unsafe_stage_root") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail("unsafe_stage_root")
    return metadata


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_nlink,
        left.st_uid,
        left.st_gid,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_nlink,
        right.st_uid,
        right.st_gid,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _read_file_bound(
    path: Path, *, private: bool, maximum_bytes: int, reason: str
) -> bytes:
    _normalized_absolute(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DrError(reason) from exc
    try:
        before = _validate_file_metadata(
            os.fstat(descriptor), private=private, reason=reason
        )
        if before.st_size <= 0 or before.st_size > maximum_bytes:
            _fail(reason)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                _fail(reason)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(reason)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        path_state = path.lstat()
    except OSError as exc:
        raise DrError(reason) from exc
    if not _same_file_state(before, after) or not _same_file_state(path_state, after):
        _fail(reason)
    return b"".join(chunks)


def _read_json(
    path: Path, *, private: bool = True, maximum_bytes: int = MAX_JSON_BYTES
) -> Any:
    raw = _read_file_bound(
        path,
        private=private,
        maximum_bytes=maximum_bytes,
        reason="invalid_json_size",
    )
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DrError("invalid_json") from exc


def _require_object(value: Any, keys: set[str], *, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(reason)
    return value


def _require_token(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or not TOKEN_RE.fullmatch(value):
        _fail(reason)
    return value


def _require_sha256(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail(reason)
    return value


def _parse_timestamp(value: Any, *, reason: str) -> dt.datetime:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        _fail(reason)
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError as exc:
        raise DrError(reason) from exc


def _positive_int(value: Any, *, reason: str, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        or value > maximum
    ):
        _fail(reason)
    return value


def validate_secret_recovery(value: Any) -> dict[str, Any]:
    document = _require_object(
        value, {"schema_version", "entries"}, reason="invalid_secret_recovery_schema"
    )
    if document["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_secret_recovery_version")
    entries = document["entries"]
    if not isinstance(entries, list) or not entries or len(entries) > 128:
        _fail("invalid_secret_recovery_entries")
    seen: set[str] = set()
    for item in entries:
        entry = _require_object(
            item,
            {
                "secret_id",
                "purpose",
                "custody",
                "key_id_sha256",
                "recovery_test",
                "rotate_after_restore",
            },
            reason="invalid_secret_recovery_entry",
        )
        secret_id = _require_token(entry["secret_id"], reason="invalid_secret_id")
        _require_token(entry["purpose"], reason="invalid_secret_purpose")
        if secret_id in seen:
            _fail("duplicate_secret_id")
        seen.add(secret_id)
        if entry["custody"] not in ALLOWED_SECRET_CUSTODY:
            _fail("invalid_secret_custody")
        _require_sha256(entry["key_id_sha256"], reason="invalid_secret_key_id")
        if entry["recovery_test"] not in ALLOWED_RECOVERY_TESTS:
            _fail("invalid_secret_recovery_test")
        if not isinstance(entry["rotate_after_restore"], bool):
            _fail("invalid_secret_rotation_policy")
    return document


def validate_qdrant_rebuild(value: Any) -> dict[str, Any]:
    document = _require_object(
        value,
        {
            "schema_version",
            "mode",
            "canonical_source",
            "require_empty_target",
            "verify_no_orphans",
            "verify_tenant_counts",
            "collections",
        },
        reason="invalid_qdrant_rebuild_schema",
    )
    if document["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_qdrant_rebuild_version")
    if document["mode"] not in ALLOWED_QDRANT_MODES:
        _fail("invalid_qdrant_rebuild_mode")
    if document["canonical_source"] != "postgres":
        _fail("invalid_qdrant_canonical_source")
    for key in ("require_empty_target", "verify_no_orphans", "verify_tenant_counts"):
        if document[key] is not True:
            _fail("unsafe_qdrant_rebuild_policy")
    collections = document["collections"]
    if not isinstance(collections, list) or not collections or len(collections) > 128:
        _fail("invalid_qdrant_collections")
    seen: set[str] = set()
    for item in collections:
        collection = _require_object(
            item,
            {
                "logical_id",
                "collection_name",
                "ledger_database",
                "tenant_scope",
                "authority_epoch_sha256",
                "rebuild_command_id",
                "snapshot_path",
                "snapshot_sha256",
                "expected_points_count",
                "tenant_payload_key",
                "tenant_counts_sha256",
            },
            reason="invalid_qdrant_collection",
        )
        logical_id = _require_token(
            collection["logical_id"], reason="invalid_qdrant_logical_id"
        )
        if logical_id in seen:
            _fail("duplicate_qdrant_logical_id")
        seen.add(logical_id)
        collection_name = collection["collection_name"]
        if not isinstance(collection_name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", collection_name
        ):
            _fail("invalid_qdrant_collection_name")
        if collection["ledger_database"] != "sealai_v2":
            _fail("invalid_qdrant_ledger_database")
        if collection["tenant_scope"] not in {"tenant_bound", "shared_reviewed"}:
            _fail("invalid_qdrant_tenant_scope")
        _require_sha256(
            collection["authority_epoch_sha256"],
            reason="invalid_qdrant_authority_epoch",
        )
        _require_token(
            collection["rebuild_command_id"], reason="invalid_qdrant_rebuild_command"
        )
        if (
            not isinstance(collection["expected_points_count"], int)
            or isinstance(collection["expected_points_count"], bool)
            or collection["expected_points_count"] < 0
            or collection["expected_points_count"] > MAX_QDRANT_POINTS
        ):
            _fail("invalid_qdrant_expected_points")
        _require_token(
            collection["tenant_payload_key"], reason="invalid_qdrant_tenant_payload_key"
        )
        _require_sha256(
            collection["tenant_counts_sha256"],
            reason="invalid_qdrant_tenant_counts_sha256",
        )
        if document["mode"] == "snapshot_and_rebuild":
            snapshot_path = _safe_relative(collection["snapshot_path"])
            if (
                snapshot_path.parts[0] != "qdrant"
                or not str(snapshot_path).endswith(".snapshot")
                or not re.fullmatch(
                    r"qdrant/[A-Za-z0-9_.-]+\.snapshot", str(snapshot_path)
                )
            ):
                _fail("invalid_qdrant_snapshot_path")
            _require_sha256(
                collection["snapshot_sha256"], reason="invalid_qdrant_snapshot_sha256"
            )
        elif (
            collection["snapshot_path"] is not None
            or collection["snapshot_sha256"] is not None
        ):
            _fail("unexpected_qdrant_snapshot")
    return document


def validate_recovery_point(
    value: Any, *, now: dt.datetime | None = None, require_fresh: bool = False
) -> dict[str, Any]:
    document = _require_object(
        value,
        {
            "schema_version",
            "recovery_point_id",
            "created_at",
            "source_git_commit",
            "authority_epoch_sha256",
            "components",
        },
        reason="invalid_recovery_point_schema",
    )
    if document["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_recovery_point_version")
    _require_token(document["recovery_point_id"], reason="invalid_recovery_point_id")
    created_at = _parse_timestamp(document["created_at"], reason="invalid_created_at")
    observed_now = _utc_now() if now is None else now
    if created_at > observed_now + dt.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        _fail("recovery_point_from_future")
    if (
        require_fresh
        and (observed_now - created_at).total_seconds() > MAX_CLOCK_SKEW_SECONDS
    ):
        _fail("recovery_point_stale")
    if not isinstance(document["source_git_commit"], str) or not GIT_SHA_RE.fullmatch(
        document["source_git_commit"]
    ):
        _fail("invalid_source_git_commit")
    _require_sha256(
        document["authority_epoch_sha256"], reason="invalid_authority_epoch"
    )
    components = document["components"]
    if not isinstance(components, dict) or set(components) != set(REQUIRED_COMPONENTS):
        _fail("invalid_recovery_point_components")
    for name in REQUIRED_COMPONENTS:
        component = _require_object(
            components[name],
            {
                "captured_at",
                "source_id_sha256",
                "rpo_target_seconds",
                "rto_target_seconds",
            },
            reason="invalid_recovery_component",
        )
        captured_at = _parse_timestamp(
            component["captured_at"], reason="invalid_component_capture_time"
        )
        if captured_at > created_at + dt.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
            _fail("component_capture_from_future")
        rpo = _positive_int(
            component["rpo_target_seconds"],
            reason="invalid_rpo_target",
            maximum=7 * 24 * 60 * 60,
        )
        _positive_int(
            component["rto_target_seconds"],
            reason="invalid_rto_target",
            maximum=7 * 24 * 60 * 60,
        )
        if (created_at - captured_at).total_seconds() > rpo:
            _fail("rpo_target_missed")
        _require_sha256(component["source_id_sha256"], reason="invalid_source_id")
    return document


def require_recovery_point_within_rpo(
    recovery_point: dict[str, Any], *, now: dt.datetime | None = None
) -> None:
    """Reject a receipt for a recovery point that is stale at verification time."""
    observed_now = _utc_now() if now is None else now
    for component in recovery_point["components"].values():
        captured_at = _parse_timestamp(
            component["captured_at"], reason="invalid_component_capture_time"
        )
        age = (observed_now - captured_at).total_seconds()
        if age < -MAX_CLOCK_SKEW_SECONDS or age > component["rpo_target_seconds"]:
            _fail("rpo_target_missed")


def validate_configuration_inventory(value: Any) -> dict[str, Any]:
    document = _require_object(
        value,
        {"schema_version", "source_git_commit", "artifacts"},
        reason="invalid_configuration_inventory_schema",
    )
    if document["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_configuration_inventory_version")
    if not isinstance(document["source_git_commit"], str) or not GIT_SHA_RE.fullmatch(
        document["source_git_commit"]
    ):
        _fail("invalid_configuration_source_commit")
    artifacts = document["artifacts"]
    if not isinstance(artifacts, list) or not artifacts or len(artifacts) > 256:
        _fail("invalid_configuration_artifacts")
    identifiers: set[str] = set()
    paths: set[str] = set()
    for item in artifacts:
        artifact = _require_object(
            item,
            {"logical_id", "path", "sha256"},
            reason="invalid_configuration_artifact",
        )
        logical_id = _require_token(
            artifact["logical_id"], reason="invalid_configuration_logical_id"
        )
        path = _safe_relative(artifact["path"])
        if (
            path.parts[0] != "configuration"
            or str(path) == "configuration/inventory.json"
        ):
            _fail("invalid_configuration_path")
        if logical_id in identifiers or str(path) in paths:
            _fail("duplicate_configuration_artifact")
        identifiers.add(logical_id)
        paths.add(str(path))
        _require_sha256(artifact["sha256"], reason="invalid_configuration_sha256")
    if not REQUIRED_CONFIGURATION_IDS.issubset(identifiers):
        _fail("required_configuration_artifact_missing")
    return document


def validate_data_inventory(value: Any, *, component: str) -> dict[str, Any]:
    if component not in {"uploads", "documents"}:
        _fail("invalid_data_inventory_component")
    document = _require_object(
        value,
        {
            "schema_version",
            "component",
            "source_id_sha256",
            "file_count",
            "total_bytes",
            "empty_source_confirmed",
        },
        reason="invalid_data_inventory_schema",
    )
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["component"] != component
    ):
        _fail("invalid_data_inventory_component")
    _require_sha256(document["source_id_sha256"], reason="invalid_data_source_id")
    for key in ("file_count", "total_bytes"):
        if (
            not isinstance(document[key], int)
            or isinstance(document[key], bool)
            or document[key] < 0
        ):
            _fail("invalid_data_inventory_count")
    if not isinstance(document["empty_source_confirmed"], bool):
        _fail("invalid_empty_source_confirmation")
    return document


def _sha256(path: Path) -> str:
    _normalized_absolute(path)
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DrError("stage_file_changed") from exc
    try:
        before = _validate_file_metadata(
            os.fstat(descriptor), private=True, reason="unsafe_stage_file"
        )
        if before.st_size > MAX_FILE_BYTES:
            _fail("stage_file_too_large")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        path_state = path.lstat()
    except OSError as exc:
        raise DrError("stage_file_changed") from exc
    if not _same_file_state(before, after) or not _same_file_state(path_state, after):
        _fail("stage_file_changed")
    return digest.hexdigest()


def _validate_checksum_sidecar(payload: Path, digest: str) -> None:
    sidecar = payload.with_name(f"{payload.name}.sha256")
    try:
        text = _read_file_bound(
            sidecar,
            private=True,
            maximum_bytes=256,
            reason="invalid_p0_checksum",
        ).decode("ascii")
    except UnicodeDecodeError as exc:
        raise DrError("invalid_p0_checksum") from exc
    match = CHECKSUM_RE.fullmatch(text)
    if not match or match.group(1) != digest or match.group(2) != payload.name:
        _fail("invalid_p0_checksum")


def _walk_stage(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    inode_ids: set[tuple[int, int]] = set()
    for current, directories, filenames in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        current_meta = current_path.lstat()
        if (
            not stat.S_ISDIR(current_meta.st_mode)
            or current_meta.st_uid != os.geteuid()
            or stat.S_IMODE(current_meta.st_mode) != 0o700
        ):
            _fail("unsafe_stage_directory")
        directories.sort()
        filenames.sort()
        for directory in directories:
            child = current_path / directory
            if child.is_symlink():
                _fail("stage_symlink_forbidden")
        for filename in filenames:
            path = current_path / filename
            relative = path.relative_to(root).as_posix()
            _safe_relative(relative)
            if relative == "dr-manifest.json":
                continue
            metadata = _regular_file(path, private=True, reason="unsafe_stage_file")
            inode_id = (metadata.st_dev, metadata.st_ino)
            if inode_id in inode_ids:
                _fail("stage_hardlink_forbidden")
            inode_ids.add(inode_id)
            if metadata.st_size > MAX_FILE_BYTES:
                _fail("stage_file_too_large")
            total_bytes += metadata.st_size
            if total_bytes > MAX_SET_BYTES or len(entries) >= MAX_FILES:
                _fail("stage_set_too_large")
            if relative.startswith("configuration/"):
                lowered = {part.lower() for part in PurePosixPath(relative).parts}
                if lowered & FORBIDDEN_CONFIGURATION_NAMES or any(
                    part.startswith(".env")
                    or "credential" in part
                    or "secret" in part
                    or part.endswith((".key", ".pem", ".p12", ".pfx"))
                    for part in lowered
                ):
                    _fail("configuration_secret_file_forbidden")
            digest = _sha256(path)
            observed_metadata = _regular_file(
                path, private=True, reason="unsafe_stage_file"
            )
            if not _same_file_state(metadata, observed_metadata):
                _fail("stage_file_changed")
            if relative.startswith("postgres/") and path.name.endswith(
                (".sql.gz", ".dump")
            ):
                _validate_checksum_sidecar(path, digest)
            if relative.startswith("qdrant/") and path.name.endswith(".snapshot"):
                _validate_checksum_sidecar(path, digest)
            entries.append(
                {
                    "path": relative,
                    "size": metadata.st_size,
                    "sha256": digest,
                    "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                    "mtime_ns": metadata.st_mtime_ns,
                }
            )
    if not entries:
        _fail("empty_recovery_set")
    return entries


def _validate_payload_metadata(
    entries: list[dict[str, Any]],
    recovery_point: dict[str, Any],
    *,
    now: dt.datetime | None,
    require_fresh: bool,
) -> None:
    """Bind declared capture times to observed payload metadata.

    A recovery-point timestamp is not freshness evidence by itself.  Every
    component therefore binds the real nanosecond mtime of every staged file,
    and the newest component file must agree with the declared capture time.
    Freshness checks additionally reject any individual payload older than the
    component RPO.  Restored sets retain the bound mtimes and can be checked
    without pretending that the restore time is a new capture time.
    """

    observed_now = _utc_now() if now is None else now
    observed_now_ns = int(observed_now.timestamp() * NANOSECONDS_PER_SECOND)
    maximum_skew_ns = MAX_CLOCK_SKEW_SECONDS * NANOSECONDS_PER_SECOND
    for component in REQUIRED_COMPONENTS:
        component_entries = [
            entry
            for entry in entries
            if PurePosixPath(entry["path"]).parts[0] == component
        ]
        if not component_entries:
            _fail("required_component_missing")
        mtimes: list[int] = []
        for entry in component_entries:
            mtime_ns = entry.get("mtime_ns")
            if (
                not isinstance(mtime_ns, int)
                or isinstance(mtime_ns, bool)
                or mtime_ns <= 0
            ):
                _fail("invalid_payload_mtime")
            if mtime_ns > observed_now_ns + maximum_skew_ns:
                _fail("payload_mtime_from_future")
            mtimes.append(mtime_ns)

        capture = recovery_point["components"][component]
        captured_at = _parse_timestamp(
            capture["captured_at"], reason="invalid_component_capture_time"
        )
        captured_at_seconds = int(captured_at.timestamp())
        latest_mtime_seconds = max(mtimes) // NANOSECONDS_PER_SECOND
        if abs(latest_mtime_seconds - captured_at_seconds) > MAX_CLOCK_SKEW_SECONDS:
            _fail("payload_capture_mismatch")
        if require_fresh:
            maximum_age_ns = capture["rpo_target_seconds"] * NANOSECONDS_PER_SECOND
            if any(observed_now_ns - mtime_ns > maximum_age_ns for mtime_ns in mtimes):
                _fail("payload_mtime_stale")


def _validate_set_contract(
    root: Path,
    entries: list[dict[str, Any]],
    *,
    require_fresh: bool,
    now: dt.datetime | None = None,
) -> None:
    paths = {entry["path"] for entry in entries}
    if not REQUIRED_RECOVERY_FILES.issubset(paths):
        _fail("required_recovery_file_missing")
    if "configuration/inventory.json" not in paths:
        _fail("configuration_inventory_missing")
    for component in ("uploads", "documents"):
        if f"{component}/inventory.json" not in paths:
            _fail("data_inventory_missing")
    for component in REQUIRED_COMPONENTS:
        if not any(path.startswith(f"{component}/") for path in paths):
            _fail("required_component_missing")
    if not any(
        path.startswith("postgres/") and path.endswith((".sql.gz", ".dump"))
        for path in paths
    ):
        _fail("postgres_backup_missing")

    qdrant_plan = validate_qdrant_rebuild(
        _read_json(root / "recovery" / "qdrant-rebuild.json")
    )
    snapshots = [
        path
        for path in paths
        if path.startswith("qdrant/") and path.endswith(".snapshot")
    ]
    if qdrant_plan["mode"] == "snapshot_and_rebuild" and not snapshots:
        _fail("qdrant_snapshot_missing")
    entry_by_path = {entry["path"]: entry for entry in entries}
    if qdrant_plan["mode"] == "snapshot_and_rebuild":
        for collection in qdrant_plan["collections"]:
            snapshot_entry = entry_by_path.get(collection["snapshot_path"])
            if (
                snapshot_entry is None
                or snapshot_entry["sha256"] != collection["snapshot_sha256"]
            ):
                _fail("qdrant_snapshot_binding_mismatch")
    validate_secret_recovery(_read_json(root / "recovery" / "secret-recovery.json"))
    recovery_point = validate_recovery_point(
        _read_json(root / "recovery" / "recovery-point.json"),
        now=now,
        require_fresh=require_fresh,
    )
    _validate_payload_metadata(
        entries, recovery_point, now=now, require_fresh=require_fresh
    )
    if qdrant_plan["collections"] and any(
        item["authority_epoch_sha256"] != recovery_point["authority_epoch_sha256"]
        for item in qdrant_plan["collections"]
    ):
        _fail("qdrant_authority_epoch_mismatch")
    configuration = validate_configuration_inventory(
        _read_json(root / "configuration" / "inventory.json")
    )
    if configuration["source_git_commit"] != recovery_point["source_git_commit"]:
        _fail("configuration_source_commit_mismatch")
    for artifact in configuration["artifacts"]:
        entry = entry_by_path.get(artifact["path"])
        if entry is None or entry["sha256"] != artifact["sha256"]:
            _fail("configuration_artifact_mismatch")
    for component in ("uploads", "documents"):
        inventory = validate_data_inventory(
            _read_json(root / component / "inventory.json"), component=component
        )
        data_entries = [
            entry
            for entry in entries
            if entry["path"].startswith(f"{component}/")
            and entry["path"] != f"{component}/inventory.json"
        ]
        if (
            inventory["source_id_sha256"]
            != recovery_point["components"][component]["source_id_sha256"]
            or inventory["file_count"] != len(data_entries)
            or inventory["total_bytes"] != sum(entry["size"] for entry in data_entries)
            or inventory["empty_source_confirmed"] is not (not data_entries)
        ):
            _fail("data_inventory_mismatch")


def _atomic_write(path: Path, payload: bytes, *, replace: bool = False) -> None:
    parent = path.parent
    _private_directory(parent)
    if path.exists() or path.is_symlink():
        if not replace:
            _fail("output_already_exists")
        _regular_file(path, private=True, reason="unsafe_existing_output")
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        temporary = Path(raw_path)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            descriptor = None
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if replace:
            os.replace(temporary, path)
            temporary = None
        else:
            os.link(temporary, path)
            temporary.unlink()
            temporary = None
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        raise DrError("output_already_exists") from exc
    except OSError as exc:
        raise DrError("output_write_failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def create_manifest(root: Path, *, now: dt.datetime | None = None) -> dict[str, Any]:
    _private_directory(root)
    manifest_path = root / "dr-manifest.json"
    if manifest_path.exists() or manifest_path.is_symlink():
        _fail("manifest_already_exists")
    entries = _walk_stage(root)
    observed_now = _utc_now() if now is None else now
    _validate_set_contract(root, entries, require_fresh=True, now=observed_now)
    recovery_point = validate_recovery_point(
        _read_json(root / "recovery" / "recovery-point.json"),
        now=observed_now,
        require_fresh=True,
    )
    core = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": recovery_point["created_at"],
        "recovery_point_id": recovery_point["recovery_point_id"],
        "source_git_commit": recovery_point["source_git_commit"],
        "authority_epoch_sha256": recovery_point["authority_epoch_sha256"],
        "files": entries,
    }
    manifest = dict(core)
    manifest["set_id_sha256"] = hashlib.sha256(_canonical_json(core)).hexdigest()
    _atomic_write(manifest_path, _canonical_json(manifest))
    return manifest


def verify_manifest(root: Path) -> dict[str, Any]:
    _private_directory(root)
    manifest = _require_object(
        _read_json(root / "dr-manifest.json", maximum_bytes=MAX_MANIFEST_BYTES),
        {
            "schema_version",
            "created_at",
            "recovery_point_id",
            "source_git_commit",
            "authority_epoch_sha256",
            "files",
            "set_id_sha256",
        },
        reason="invalid_manifest_schema",
    )
    if manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        _fail("invalid_manifest_version")
    _require_sha256(manifest["set_id_sha256"], reason="invalid_set_id")
    observed_entries = _walk_stage(root)
    if manifest["files"] != observed_entries:
        _fail("manifest_file_mismatch")
    _validate_set_contract(root, observed_entries, require_fresh=False)
    core = {key: value for key, value in manifest.items() if key != "set_id_sha256"}
    if hashlib.sha256(_canonical_json(core)).hexdigest() != manifest["set_id_sha256"]:
        _fail("set_id_mismatch")
    recovery_point = validate_recovery_point(
        _read_json(root / "recovery" / "recovery-point.json")
    )
    for key in (
        "created_at",
        "recovery_point_id",
        "source_git_commit",
        "authority_epoch_sha256",
    ):
        if manifest[key] != recovery_point[key]:
            _fail("manifest_recovery_point_mismatch")
    return manifest


def postgres_backup_path(root: Path) -> Path:
    manifest = verify_manifest(root)
    candidates = [
        entry["path"]
        for entry in manifest["files"]
        if entry["path"].startswith("postgres/") and entry["path"].endswith(".sql.gz")
    ]
    if len(candidates) != 1 or not re.fullmatch(
        r"postgres/postgres-all-[A-Za-z0-9_.-]+\.sql\.gz", candidates[0]
    ):
        _fail("postgres_backup_ambiguous")
    return root / candidates[0]


def _manifest_digest(root: Path) -> str:
    manifest_path = root / "dr-manifest.json"
    _regular_file(manifest_path, private=True, reason="unsafe_manifest_file")
    return _sha256(manifest_path)


def _local_gate_provenance(
    root: Path,
    gate_receipt_path: Path,
    *,
    snapshot_id: str,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> dict[str, str]:
    manifest = verify_manifest(root)
    _require_sha256(snapshot_id, reason="invalid_snapshot_id")
    gate = verify_gate08_receipt(
        root,
        gate_receipt_path,
        "dr_restore_drill",
        snapshot_id=snapshot_id,
        now=now,
        required_uid=required_uid,
    )
    return {
        "kind": "LOCAL_UNATTESTED",
        "gate_id": "GATE-08",
        "gate_action": "dr_restore_drill",
        "gate_receipt_sha256": _sha256(gate_receipt_path),
        "gate_approval_id_sha256": gate["approval_id_sha256"],
        "snapshot_id_sha256": gate["snapshot_id_sha256"],
        "manifest_sha256": _manifest_digest(root),
        "set_id_sha256": manifest["set_id_sha256"],
    }


def _validate_local_evidence_common(
    root: Path,
    evidence_path: Path,
    gate_receipt_path: Path,
    *,
    scope: str,
    extra_keys: set[str],
    maximum_age_seconds: int,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> dict[str, Any]:
    manifest = verify_manifest(root)
    common = {
        "schema_version",
        "status",
        "evidence_scope",
        "authoritative",
        "manifest_sha256",
        "set_id_sha256",
        "observed_at",
        "provenance",
    }
    evidence = _require_object(
        _read_json(evidence_path),
        common | extra_keys,
        reason="invalid_local_evidence_schema",
    )
    if (
        evidence["schema_version"] != SCHEMA_VERSION
        or evidence["status"] != "LOCAL_EVIDENCE_ONLY"
        or evidence["evidence_scope"] != scope
        or evidence["authoritative"] is not False
    ):
        _fail("invalid_local_evidence_status")
    if evidence["manifest_sha256"] != _manifest_digest(root):
        _fail("local_evidence_manifest_mismatch")
    if evidence["set_id_sha256"] != manifest["set_id_sha256"]:
        _fail("local_evidence_set_mismatch")
    observed_at = _parse_timestamp(
        evidence["observed_at"], reason="invalid_observed_at"
    )
    observed_now = _utc_now() if now is None else now
    age = (observed_now - observed_at).total_seconds()
    if age < -MAX_CLOCK_SKEW_SECONDS or age > maximum_age_seconds:
        _fail("local_evidence_stale")

    provenance = _require_object(
        evidence["provenance"],
        {
            "kind",
            "gate_id",
            "gate_action",
            "gate_receipt_sha256",
            "gate_approval_id_sha256",
            "snapshot_id_sha256",
            "manifest_sha256",
            "set_id_sha256",
        },
        reason="invalid_local_evidence_provenance",
    )
    if (
        provenance["kind"] != "LOCAL_UNATTESTED"
        or provenance["gate_id"] != "GATE-08"
        or provenance["gate_action"] != "dr_restore_drill"
    ):
        _fail("invalid_local_evidence_provenance")
    for key in (
        "gate_receipt_sha256",
        "gate_approval_id_sha256",
        "snapshot_id_sha256",
        "manifest_sha256",
        "set_id_sha256",
    ):
        _require_sha256(provenance[key], reason="invalid_local_evidence_provenance")
    gate = _read_gate08_receipt(
        gate_receipt_path,
        "dr_restore_drill",
        now=observed_at,
        required_uid=required_uid,
    )
    if (
        provenance["gate_receipt_sha256"] != _sha256(gate_receipt_path)
        or provenance["gate_approval_id_sha256"] != gate["approval_id_sha256"]
        or provenance["snapshot_id_sha256"] != gate["snapshot_id_sha256"]
        or provenance["manifest_sha256"] != evidence["manifest_sha256"]
        or provenance["set_id_sha256"] != evidence["set_id_sha256"]
        or gate["manifest_sha256"] != evidence["manifest_sha256"]
        or gate["set_id_sha256"] != evidence["set_id_sha256"]
    ):
        _fail("local_evidence_provenance_mismatch")
    return evidence


def verify_offsite_receipt(
    root: Path,
    receipt_path: Path,
    gate_receipt_path: Path,
    *,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> NoReturn:
    """Validate local observations, then block without an external importer."""

    evidence = _validate_local_evidence_common(
        root,
        receipt_path,
        gate_receipt_path,
        scope="offsite",
        extra_keys={
            "repository_id_sha256",
            "snapshot_id_sha256",
            "encryption_key_id_sha256",
            "full_download_observed",
            "authenticated_decryption_observed",
            "restic_read_data_observed",
        },
        maximum_age_seconds=MAX_RECEIPT_AGE_SECONDS,
        now=now,
        required_uid=required_uid,
    )
    for key in (
        "repository_id_sha256",
        "snapshot_id_sha256",
        "encryption_key_id_sha256",
    ):
        _require_sha256(evidence[key], reason="invalid_offsite_identifier")
    if evidence["snapshot_id_sha256"] != evidence["provenance"]["snapshot_id_sha256"]:
        _fail("local_evidence_provenance_mismatch")
    for key in (
        "full_download_observed",
        "authenticated_decryption_observed",
        "restic_read_data_observed",
    ):
        if evidence[key] is not True:
            _fail("offsite_observation_incomplete")
    _fail("external_receipt_required")


def verify_drill_receipt(
    root: Path,
    receipt_path: Path,
    gate_receipt_path: Path,
    *,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> NoReturn:
    """Validate local observations, then block without an external importer."""

    evidence = _validate_local_evidence_common(
        root,
        receipt_path,
        gate_receipt_path,
        scope="restore_drill",
        extra_keys={
            "isolated_runner_observed",
            "production_endpoint_access_observed",
            "postgres_restore_observed",
            "qdrant_recovery_observed",
            "uploads_check_observed",
            "documents_check_observed",
            "configuration_check_observed",
            "secret_procedure_check_observed",
            "rpo_observed",
            "rto_observed",
            "elapsed_seconds",
        },
        maximum_age_seconds=MAX_DRILL_AGE_SECONDS,
        now=now,
        required_uid=required_uid,
    )
    if (
        evidence["isolated_runner_observed"] is not True
        or evidence["production_endpoint_access_observed"] is not False
    ):
        _fail("restore_not_isolated")
    for key in (
        "postgres_restore_observed",
        "qdrant_recovery_observed",
        "uploads_check_observed",
        "documents_check_observed",
        "configuration_check_observed",
        "secret_procedure_check_observed",
        "rpo_observed",
        "rto_observed",
    ):
        if evidence[key] is not True:
            _fail("restore_verification_incomplete")
    _positive_int(
        evidence["elapsed_seconds"],
        reason="invalid_restore_elapsed",
        maximum=7 * 86400,
    )
    _fail("external_receipt_required")


def write_offsite_receipt(
    root: Path,
    output: Path,
    *,
    repository_id: str,
    snapshot_id: str,
    encryption_key_id_sha256: str,
    gate_receipt_path: Path,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> dict[str, Any]:
    """Write non-authoritative local observations, never a verified receipt."""

    manifest = verify_manifest(root)
    observed_now = _utc_now() if now is None else now
    recovery_point = validate_recovery_point(
        _read_json(root / "recovery" / "recovery-point.json"), now=observed_now
    )
    require_recovery_point_within_rpo(recovery_point, now=observed_now)
    _validate_payload_metadata(
        manifest["files"], recovery_point, now=observed_now, require_fresh=True
    )
    if not SHA256_RE.fullmatch(repository_id) or not SHA256_RE.fullmatch(snapshot_id):
        _fail("invalid_offsite_source_identifier")
    _require_sha256(encryption_key_id_sha256, reason="invalid_offsite_key_id")
    provenance = _local_gate_provenance(
        root,
        gate_receipt_path,
        snapshot_id=snapshot_id,
        now=observed_now,
        required_uid=required_uid,
    )
    observed_at = observed_now.strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": "LOCAL_EVIDENCE_ONLY",
        "evidence_scope": "offsite",
        "authoritative": False,
        "manifest_sha256": _manifest_digest(root),
        "set_id_sha256": manifest["set_id_sha256"],
        "observed_at": observed_at,
        "provenance": provenance,
        "repository_id_sha256": hashlib.sha256(
            repository_id.encode("ascii")
        ).hexdigest(),
        "snapshot_id_sha256": hashlib.sha256(snapshot_id.encode("ascii")).hexdigest(),
        "encryption_key_id_sha256": encryption_key_id_sha256,
        "full_download_observed": True,
        "authenticated_decryption_observed": True,
        "restic_read_data_observed": True,
    }
    _atomic_write(output, _canonical_json(evidence))
    return evidence


def write_drill_receipt(
    root: Path,
    output: Path,
    *,
    elapsed_seconds: int,
    snapshot_id: str,
    gate_receipt_path: Path,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> dict[str, Any]:
    """Write non-authoritative local observations, never a verified receipt."""

    manifest = verify_manifest(root)
    elapsed = _positive_int(
        elapsed_seconds, reason="invalid_restore_elapsed", maximum=7 * 86400
    )
    observed_now = _utc_now() if now is None else now
    recovery_point = validate_recovery_point(
        _read_json(root / "recovery" / "recovery-point.json"), now=observed_now
    )
    require_recovery_point_within_rpo(recovery_point, now=observed_now)
    _validate_payload_metadata(
        manifest["files"], recovery_point, now=observed_now, require_fresh=True
    )
    full_restore_rto = max(
        component["rto_target_seconds"]
        for component in recovery_point["components"].values()
    )
    if elapsed > full_restore_rto:
        _fail("rto_target_missed")
    provenance = _local_gate_provenance(
        root,
        gate_receipt_path,
        snapshot_id=snapshot_id,
        now=observed_now,
        required_uid=required_uid,
    )
    observed_at = observed_now.strftime("%Y-%m-%dT%H:%M:%SZ")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": "LOCAL_EVIDENCE_ONLY",
        "evidence_scope": "restore_drill",
        "authoritative": False,
        "manifest_sha256": _manifest_digest(root),
        "set_id_sha256": manifest["set_id_sha256"],
        "observed_at": observed_at,
        "provenance": provenance,
        "isolated_runner_observed": True,
        "production_endpoint_access_observed": False,
        "postgres_restore_observed": True,
        "qdrant_recovery_observed": True,
        "uploads_check_observed": True,
        "documents_check_observed": True,
        "configuration_check_observed": True,
        "secret_procedure_check_observed": True,
        "rpo_observed": True,
        "rto_observed": True,
        "elapsed_seconds": elapsed,
    }
    _atomic_write(output, _canonical_json(evidence))
    return evidence


def _read_gate08_receipt(
    receipt_path: Path,
    action: str,
    *,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> dict[str, Any]:
    if action not in ALLOWED_GATE_ACTIONS:
        _fail("invalid_gate_action")
    metadata = _regular_file(receipt_path, private=True, reason="unsafe_gate_receipt")
    if metadata.st_uid != required_uid:
        _fail("unsafe_gate_receipt")
    keys = {
        "schema_version",
        "gate_id",
        "action",
        "manifest_sha256",
        "set_id_sha256",
        "approval_id_sha256",
        "issued_at",
        "expires_at",
    }
    if action == "dr_restore_drill":
        keys.add("snapshot_id_sha256")
    raw_receipt = _read_json(receipt_path)
    if (
        not isinstance(raw_receipt, dict)
        or raw_receipt.get("schema_version") != SCHEMA_VERSION
        or raw_receipt.get("gate_id") != "GATE-08"
        or raw_receipt.get("action") != action
    ):
        _fail("gate_receipt_scope_mismatch")
    receipt = _require_object(raw_receipt, keys, reason="invalid_gate_receipt_schema")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["gate_id"] != "GATE-08"
        or receipt["action"] != action
    ):
        _fail("gate_receipt_scope_mismatch")
    _require_sha256(receipt["manifest_sha256"], reason="invalid_gate_manifest")
    _require_sha256(receipt["set_id_sha256"], reason="invalid_gate_set")
    _require_sha256(receipt["approval_id_sha256"], reason="invalid_gate_approval_id")
    if action == "dr_restore_drill":
        _require_sha256(receipt["snapshot_id_sha256"], reason="invalid_gate_snapshot")
    issued_at = _parse_timestamp(receipt["issued_at"], reason="invalid_gate_issued_at")
    expires_at = _parse_timestamp(
        receipt["expires_at"], reason="invalid_gate_expires_at"
    )
    observed_now = _utc_now() if now is None else now
    if (
        expires_at <= issued_at
        or (expires_at - issued_at).total_seconds() > MAX_GATE_VALIDITY_SECONDS
        or observed_now < issued_at - dt.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS)
        or observed_now > expires_at
    ):
        _fail("gate_receipt_expired")
    return receipt


def verify_gate08_selection(
    receipt_path: Path,
    action: str,
    *,
    set_id: str,
    snapshot_id: str,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> dict[str, Any]:
    """Authorize the exact offsite object before any full-data read begins."""
    if action != "dr_restore_drill":
        _fail("invalid_gate_action")
    _require_sha256(set_id, reason="invalid_set_id")
    _require_sha256(snapshot_id, reason="invalid_snapshot_id")
    receipt = _read_gate08_receipt(
        receipt_path, action, now=now, required_uid=required_uid
    )
    if receipt["set_id_sha256"] != set_id:
        _fail("gate_set_mismatch")
    if (
        receipt["snapshot_id_sha256"]
        != hashlib.sha256(snapshot_id.encode("ascii")).hexdigest()
    ):
        _fail("gate_snapshot_mismatch")
    return receipt


def verify_gate08_receipt(
    root: Path,
    receipt_path: Path,
    action: str,
    *,
    snapshot_id: str | None = None,
    now: dt.datetime | None = None,
    required_uid: int = 0,
) -> dict[str, Any]:
    receipt = _read_gate08_receipt(
        receipt_path, action, now=now, required_uid=required_uid
    )
    manifest = verify_manifest(root)
    if receipt["manifest_sha256"] != _manifest_digest(root):
        _fail("gate_manifest_mismatch")
    if receipt["set_id_sha256"] != manifest["set_id_sha256"]:
        _fail("gate_set_mismatch")
    if action == "dr_restore_drill":
        if snapshot_id is None:
            _fail("gate_snapshot_required")
        verify_gate08_selection(
            receipt_path,
            action,
            set_id=manifest["set_id_sha256"],
            snapshot_id=snapshot_id,
            now=now,
            required_uid=required_uid,
        )
    elif snapshot_id is not None:
        _fail("unexpected_gate_snapshot")
    return receipt


def render_metrics(status_path: Path) -> str:
    value = _require_object(
        _read_json(status_path),
        {"schema_version", "components"},
        reason="invalid_status_schema",
    )
    if value["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_status_version")
    components = value["components"]
    if not isinstance(components, dict) or not set(REQUIRED_COMPONENTS).issubset(
        components
    ):
        _fail("invalid_status_components")
    lines: list[str] = []
    for component in sorted(components):
        _require_token(component, reason="invalid_status_component")
        if component not in STATUS_COMPONENTS:
            _fail("invalid_status_component")
        fields = components[component]
        if not isinstance(fields, dict) or set(fields) != STATUS_KEYS:
            _fail("invalid_status_fields")
        for key in sorted(STATUS_KEYS):
            raw = fields[key]
            if key == "backup_receipt_valid":
                if raw not in {0, 1} or isinstance(raw, bool):
                    _fail("invalid_receipt_metric")
            elif (
                not isinstance(raw, int)
                or isinstance(raw, bool)
                or raw < 0
                or raw > 4_102_444_800
            ):
                _fail("invalid_timestamp_metric")
            lines.append(f'{METRIC_NAMES[key]}{{component="{component}"}} {raw}')
    return "\n".join(lines) + "\n"


def validate_restore_images(path: Path) -> dict[str, str]:
    try:
        lines = (
            _read_file_bound(
                path,
                private=True,
                maximum_bytes=4096,
                reason="invalid_restore_images",
            )
            .decode("ascii")
            .splitlines()
        )
    except UnicodeDecodeError as exc:
        raise DrError("invalid_restore_images") from exc
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            _fail("invalid_restore_images")
        key, value = line.split("=", 1)
        if (
            key not in RESTORE_IMAGE_KEYS
            or key in values
            or not IMAGE_DIGEST_RE.fullmatch(value)
        ):
            _fail("invalid_restore_image_reference")
        values[key] = value
    if set(values) != RESTORE_IMAGE_KEYS:
        _fail("restore_image_missing")
    return values


def _emit(status_value: str, reason: str, **metrics: int) -> None:
    payload: dict[str, Any] = {
        "component": "dr_recovery",
        "event": "dr_contract",
        "status": status_value,
        "reason": reason,
        "timestamp": _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if metrics:
        payload["metrics"] = metrics
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _path(value: str) -> Path:
    return _normalized_absolute(Path(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    for name in (
        "create-manifest",
        "verify-manifest",
        "show-set-id",
        "show-postgres-backup",
    ):
        command = commands.add_parser(name)
        command.add_argument("--root", required=True, type=_path)

    secret = commands.add_parser("validate-secret-recovery")
    secret.add_argument("--file", required=True, type=_path)

    qdrant = commands.add_parser("validate-qdrant-rebuild")
    qdrant.add_argument("--file", required=True, type=_path)

    configuration = commands.add_parser("validate-configuration-inventory")
    configuration.add_argument("--file", required=True, type=_path)

    data_inventory = commands.add_parser("validate-data-inventory")
    data_inventory.add_argument("--file", required=True, type=_path)
    data_inventory.add_argument(
        "--component", required=True, choices=("uploads", "documents")
    )

    offsite = commands.add_parser("verify-offsite-receipt")
    offsite.add_argument("--root", required=True, type=_path)
    offsite.add_argument("--receipt", required=True, type=_path)
    offsite.add_argument("--gate-receipt", required=True, type=_path)

    drill = commands.add_parser("verify-drill-receipt")
    drill.add_argument("--root", required=True, type=_path)
    drill.add_argument("--receipt", required=True, type=_path)
    drill.add_argument("--gate-receipt", required=True, type=_path)

    write_offsite = commands.add_parser("write-offsite-receipt")
    write_offsite.add_argument("--root", required=True, type=_path)
    write_offsite.add_argument("--output", required=True, type=_path)
    write_offsite.add_argument("--repository-id", required=True)
    write_offsite.add_argument("--snapshot-id", required=True)
    write_offsite.add_argument("--encryption-key-id-sha256", required=True)
    write_offsite.add_argument("--gate-receipt", required=True, type=_path)

    write_drill = commands.add_parser("write-drill-receipt")
    write_drill.add_argument("--root", required=True, type=_path)
    write_drill.add_argument("--output", required=True, type=_path)
    write_drill.add_argument("--elapsed-seconds", required=True, type=int)
    write_drill.add_argument("--snapshot-id", required=True)
    write_drill.add_argument("--gate-receipt", required=True, type=_path)

    gate = commands.add_parser("verify-gate-08")
    gate.add_argument("--root", required=True, type=_path)
    gate.add_argument("--receipt", required=True, type=_path)
    gate.add_argument("--action", required=True, choices=sorted(ALLOWED_GATE_ACTIONS))
    gate.add_argument("--snapshot-id")

    selection = commands.add_parser("verify-gate-08-selection")
    selection.add_argument("--receipt", required=True, type=_path)
    selection.add_argument("--action", required=True, choices=("dr_restore_drill",))
    selection.add_argument("--set-id", required=True)
    selection.add_argument("--snapshot-id", required=True)

    metrics = commands.add_parser("render-metrics")
    metrics.add_argument("--status", required=True, type=_path)
    metrics.add_argument("--output", required=True, type=_path)

    images = commands.add_parser("validate-restore-images")
    images.add_argument("--file", required=True, type=_path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create-manifest":
            manifest = create_manifest(args.root)
            _emit("ok", "manifest_created", files=len(manifest["files"]))
        elif args.command == "verify-manifest":
            manifest = verify_manifest(args.root)
            _emit("ok", "manifest_verified", files=len(manifest["files"]))
        elif args.command == "show-set-id":
            manifest = verify_manifest(args.root)
            print(manifest["set_id_sha256"])
        elif args.command == "show-postgres-backup":
            print(postgres_backup_path(args.root))
        elif args.command == "validate-secret-recovery":
            value = validate_secret_recovery(_read_json(args.file))
            _emit("ok", "secret_recovery_valid", entries=len(value["entries"]))
        elif args.command == "validate-qdrant-rebuild":
            value = validate_qdrant_rebuild(_read_json(args.file))
            _emit("ok", "qdrant_rebuild_valid", collections=len(value["collections"]))
        elif args.command == "validate-configuration-inventory":
            value = validate_configuration_inventory(_read_json(args.file))
            _emit(
                "ok", "configuration_inventory_valid", artifacts=len(value["artifacts"])
            )
        elif args.command == "validate-data-inventory":
            validate_data_inventory(_read_json(args.file), component=args.component)
            _emit("ok", "data_inventory_valid")
        elif args.command == "verify-offsite-receipt":
            verify_offsite_receipt(args.root, args.receipt, args.gate_receipt)
        elif args.command == "verify-drill-receipt":
            verify_drill_receipt(args.root, args.receipt, args.gate_receipt)
        elif args.command == "write-offsite-receipt":
            write_offsite_receipt(
                args.root,
                args.output,
                repository_id=args.repository_id,
                snapshot_id=args.snapshot_id,
                encryption_key_id_sha256=args.encryption_key_id_sha256,
                gate_receipt_path=args.gate_receipt,
            )
            _emit("ok", "local_offsite_evidence_written")
        elif args.command == "write-drill-receipt":
            write_drill_receipt(
                args.root,
                args.output,
                elapsed_seconds=args.elapsed_seconds,
                snapshot_id=args.snapshot_id,
                gate_receipt_path=args.gate_receipt,
            )
            _emit("ok", "local_restore_evidence_written")
        elif args.command == "verify-gate-08":
            verify_gate08_receipt(
                args.root,
                args.receipt,
                args.action,
                snapshot_id=args.snapshot_id,
            )
            _emit("ok", "gate_08_verified")
        elif args.command == "verify-gate-08-selection":
            verify_gate08_selection(
                args.receipt,
                args.action,
                set_id=args.set_id,
                snapshot_id=args.snapshot_id,
            )
            _emit("ok", "gate_08_selection_verified")
        elif args.command == "render-metrics":
            payload = render_metrics(args.status).encode("ascii")
            _atomic_write(args.output, payload, replace=True)
            _emit("ok", "metrics_rendered")
        elif args.command == "validate-restore-images":
            validate_restore_images(args.file)
            _emit("ok", "restore_images_valid")
        else:  # pragma: no cover - argparse enforces the command set.
            _fail("unknown_command")
    except DrError as exc:
        _emit("blocked", exc.reason)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
