#!/usr/bin/python3 -I
"""Fail-closed storage, checksum, receipt, and retention controls for backups."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import errno
import fcntl
import fnmatch
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any


CRITICAL_PERCENT = 85.0
RECOVERY_PERCENT = 80.0
MINIMUM_FREE_BYTES = 3 * 1024 * 1024 * 1024
MIN_BACKUP_BYTES = 1024
MAX_RECEIPT_BYTES = 64 * 1024
MAX_RECEIPT_AGE_SECONDS = 24 * 60 * 60
MAX_ENV_BYTES = 256 * 1024
TOKEN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})  ([^/\r\n]+)\n?$")
ENV_ASSIGNMENT_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
PRODUCTION_ENV_FILE = Path("/home/thorsten/sealai/.env.prod")
ENV_PROFILES: dict[str, tuple[tuple[str, str | None], ...]] = {
    "postgres": (
        ("POSTGRES_USER", "sealai"),
        ("POSTGRES_PASSWORD", None),
    ),
    "qdrant": (("SEALAI_V2_QDRANT_COLLECTION", "sealai_v2_fachkarten"),),
    "v2_database": (
        ("POSTGRES_USER", "sealai"),
        ("POSTGRES_PASSWORD", None),
        ("SEALAI_V2_DATABASE_NAME", "sealai_v2"),
    ),
}
WRITER_SCRIPTS = {
    "postgres": "backup_postgres.sh",
    "qdrant": "backup_qdrant.sh",
    "v2_database": "backup_v2_database.sh",
}
COMMON_WRITER_SETTINGS = (
    "RETENTION_DAYS",
    "BACKUP_MIN_LOCAL_COPIES",
    "BACKUP_MIN_FREE_BYTES",
    "BACKUP_ESTIMATED_BYTES",
    "BACKUP_SAFETY_STATE_DIR",
)
WRITER_SETTINGS = {
    "postgres": COMMON_WRITER_SETTINGS + ("POSTGRES_CONTAINER",),
    "qdrant": COMMON_WRITER_SETTINGS
    + (
        "BACKEND_CONTAINER",
        "QDRANT_CONTAINER",
        "QDRANT_INTERNAL_URL",
        "QDRANT_REMOTE_DELETE_POLICY",
        "QDRANT_OFFSITE_RECEIPT",
    ),
    "v2_database": COMMON_WRITER_SETTINGS + ("POSTGRES_CONTAINER",),
}
ORCHESTRATOR_SETTINGS = (
    "RETENTION_DAYS",
    "BACKUP_MIN_LOCAL_COPIES",
    "BACKUP_MIN_FREE_BYTES",
    "BACKUP_SAFETY_STATE_DIR",
    "POSTGRES_BACKUP_ESTIMATED_BYTES",
    "QDRANT_BACKUP_ESTIMATED_BYTES",
    "POSTGRES_CONTAINER",
    "BACKEND_CONTAINER",
    "QDRANT_CONTAINER",
    "QDRANT_INTERNAL_URL",
    "QDRANT_REMOTE_DELETE_POLICY",
    "QDRANT_OFFSITE_RECEIPT",
)
ORCHESTRATOR_LOG = Path("/home/thorsten/sealai-backups/backup.log")
RECEIPT_KEYS = {
    "schema_version",
    "backup_name",
    "local_plaintext_sha256",
    "downloaded_ciphertext_sha256",
    "decrypted_plaintext_sha256",
    "offsite_verified",
    "offsite_ciphertext_object_id_sha256",
    "encryption_key_id_sha256",
    "verified_at",
    "verification_method",
}
RECEIPT_METHODS = {"full-download-decrypt-sha256"}


class SafetyError(RuntimeError):
    """An expected fail-closed decision with a non-sensitive reason token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason if TOKEN_RE.fullmatch(reason) else "safety_error"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _token(value: str, *, field: str) -> str:
    if not TOKEN_RE.fullmatch(value):
        raise SafetyError(f"invalid_{field}")
    return value


def emit_event(
    component: str,
    event: str,
    status_value: str,
    reason: str,
    **metrics: int | float | bool,
) -> None:
    """Write one redacted JSON event; arbitrary text and paths are not accepted."""

    component = _token(component, field="component")
    event = _token(event, field="event")
    reason = _token(reason, field="reason")
    if status_value not in {"ok", "warn", "blocked", "error"}:
        raise SafetyError("invalid_status")

    safe_metrics: dict[str, int | float | bool] = {}
    for key, value in metrics.items():
        _token(key, field="metric")
        if isinstance(value, bool):
            safe_metrics[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            safe_metrics[key] = value
        else:
            raise SafetyError("invalid_metric_value")

    payload: dict[str, Any] = {
        "component": component,
        "event": event,
        "reason": reason,
        "status": status_value,
        "timestamp": _utc_now().isoformat().replace("+00:00", "Z"),
    }
    if safe_metrics:
        payload["metrics"] = safe_metrics
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)


def _parse_nonnegative(value: str, *, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SafetyError(f"invalid_{field}") from exc
    if parsed < 0:
        raise SafetyError(f"invalid_{field}")
    return parsed


def _parse_positive(value: str, *, field: str) -> int:
    parsed = _parse_nonnegative(value, field=field)
    if parsed == 0:
        raise SafetyError(f"invalid_{field}")
    return parsed


def _normalized_absolute(path: Path) -> Path:
    raw = str(path)
    if (
        not path.is_absolute()
        or "//" in raw
        or raw != os.path.normpath(raw)
        or any(part in {"~", ".", ".."} or part.startswith("~") for part in path.parts)
    ):
        raise SafetyError("path_not_normalized_absolute")
    return path


def _validated_path_argument(value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SafetyError("path_not_normalized_absolute")
    raw_parts = value.split("/")
    if (
        not value.startswith("/")
        or "//" in value
        or value != os.path.normpath(value)
        or any(part in {"~", ".", ".."} or part.startswith("~") for part in raw_parts)
    ):
        raise SafetyError("path_not_normalized_absolute")
    return _normalized_absolute(Path(value))


def _reject_symlink_components(path: Path, *, reason: str) -> None:
    normalized = _normalized_absolute(path)
    current = Path(normalized.anchor)
    for part in normalized.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SafetyError(reason) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise SafetyError(reason)


def _nearest_existing_directory(target_dir: Path) -> Path:
    candidate = _normalized_absolute(target_dir)
    _reject_symlink_components(candidate, reason="target_has_symlink")
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise SafetyError("target_parent_missing")
        candidate = parent
    if not candidate.is_dir():
        raise SafetyError("target_parent_not_directory")
    return candidate


def target_id(target_dir: Path) -> str:
    canonical = str(_normalized_absolute(target_dir)).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def evaluate_preflight(
    *,
    total_bytes: int,
    free_bytes: int,
    estimated_write_bytes: int,
    minimum_reserve_bytes: int,
    was_critical: bool,
) -> dict[str, Any]:
    """Evaluate capacity and 85/80 hysteresis without touching the filesystem."""

    if total_bytes <= 0 or not 0 <= free_bytes <= total_bytes:
        raise SafetyError("invalid_filesystem_capacity")
    if estimated_write_bytes < 0 or minimum_reserve_bytes < 0:
        raise SafetyError("invalid_capacity_requirement")
    if minimum_reserve_bytes < MINIMUM_FREE_BYTES:
        raise SafetyError("minimum_reserve_below_stop_condition")

    used_percent = ((total_bytes - free_bytes) / total_bytes) * 100.0
    projected_free = free_bytes - estimated_write_bytes
    projected_used_percent = (
        ((total_bytes - projected_free) / total_bytes) * 100.0
        if projected_free >= 0
        else 100.0
    )
    actually_critical = used_percent >= CRITICAL_PERCENT
    recovered = used_percent <= RECOVERY_PERCENT

    state = (
        "critical"
        if actually_critical or (was_critical and not recovered)
        else "normal"
    )
    allowed = True
    reason = "capacity_available"
    if actually_critical:
        allowed = False
        reason = "critical_threshold"
    elif was_critical and not recovered:
        allowed = False
        reason = "recovery_threshold"
    elif free_bytes < estimated_write_bytes + minimum_reserve_bytes:
        allowed = False
        reason = "reserve_unavailable"
    elif projected_used_percent >= CRITICAL_PERCENT:
        allowed = False
        reason = "projected_critical"

    return {
        "allowed": allowed,
        "reason": reason,
        "state": state,
        "used_percent": round(used_percent, 2),
        "projected_used_percent": round(projected_used_percent, 2),
        "free_bytes": free_bytes,
        "estimated_write_bytes": estimated_write_bytes,
        "minimum_reserve_bytes": minimum_reserve_bytes,
    }


def _state_path(state_dir: Path, identifier: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", identifier):
        raise SafetyError("invalid_target_id")
    return state_dir / f"target-{identifier}.json"


def _secure_private_directory(path: Path, *, create: bool) -> None:
    if not path.is_absolute():
        raise SafetyError("state_directory_not_absolute")
    _reject_symlink_components(path, reason="state_directory_unsafe")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if not create:
            raise SafetyError("state_directory_missing") from None
        try:
            path.mkdir(parents=True, mode=0o700, exist_ok=False)
            os.chmod(path, 0o700)
            metadata = path.lstat()
        except OSError as exc:
            raise SafetyError("state_directory_unavailable") from exc
    except OSError as exc:
        raise SafetyError("state_directory_unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise SafetyError("state_directory_unsafe")


def _read_private_text(path: Path, *, maximum_bytes: int, reason: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SafetyError(reason) from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > maximum_bytes
        ):
            raise SafetyError(reason)
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum_bytes:
            raise SafetyError(reason)
        try:
            return raw.decode("utf-8")
        except UnicodeError as exc:
            raise SafetyError(reason) from exc
    finally:
        os.close(descriptor)


def _read_state(path: Path, identifier: str) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SafetyError("invalid_state_file") from exc
    try:
        data = json.loads(
            _read_private_text(
                path, maximum_bytes=16 * 1024, reason="invalid_state_file"
            )
        )
    except json.JSONDecodeError as exc:
        raise SafetyError("invalid_state_file") from exc
    if not isinstance(data, dict):
        raise SafetyError("invalid_state_file")
    if data.get("schema_version") != 1 or data.get("target_id") != identifier:
        raise SafetyError("invalid_state_file")
    if data.get("state") not in {"normal", "critical"}:
        raise SafetyError("invalid_state_file")
    return data["state"] == "critical"


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise SafetyError("directory_fsync_failed") from exc


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _secure_private_directory(path.parent, create=True)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as exc:
        raise SafetyError("atomic_target_unsafe") from exc
    if metadata is not None:
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise SafetyError("atomic_target_unsafe")
    fd, temporary_name = tempfile.mkstemp(prefix=".backup-state-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def run_preflight(args: argparse.Namespace) -> int:
    target = _validated_path_argument(args.target_dir)
    existing = _nearest_existing_directory(target)
    usage = shutil.disk_usage(existing)
    estimated = _parse_nonnegative(
        args.estimated_write_bytes, field="estimated_write_bytes"
    )
    reserve = _parse_nonnegative(
        args.minimum_reserve_bytes, field="minimum_reserve_bytes"
    )
    identifier = target_id(target)
    state_dir = Path(args.state_dir).expanduser()
    _secure_private_directory(state_dir, create=True)
    state_path = _state_path(state_dir, identifier)
    was_critical = _read_state(state_path, identifier)
    result = evaluate_preflight(
        total_bytes=usage.total,
        free_bytes=usage.free,
        estimated_write_bytes=estimated,
        minimum_reserve_bytes=reserve,
        was_critical=was_critical,
    )
    _atomic_json(
        state_path,
        {
            "checked_at": _utc_now().isoformat().replace("+00:00", "Z"),
            "schema_version": 1,
            "state": result["state"],
            "target_id": identifier,
        },
    )
    emit_event(
        args.component,
        "storage_preflight",
        "ok" if result["allowed"] else "blocked",
        result["reason"],
        critical_percent=int(CRITICAL_PERCENT),
        estimated_write_bytes=estimated,
        free_bytes=usage.free,
        minimum_reserve_bytes=reserve,
        projected_used_percent=result["projected_used_percent"],
        recovery_percent=int(RECOVERY_PERCENT),
        used_percent=result["used_percent"],
    )
    return 0 if result["allowed"] else 1


def run_bound_preflight(args: argparse.Namespace) -> int:
    target = _validated_path_argument(args.target_dir)
    target_fd = _parse_nonnegative(args.target_fd, field="target_fd")
    lock_fd = _parse_nonnegative(args.lock_fd, field="lock_fd")
    _validate_lifecycle_bindings(target, target_fd, lock_fd)
    try:
        filesystem = os.fstatvfs(target_fd)
    except OSError as exc:
        raise SafetyError("bound_filesystem_unavailable") from exc
    block_size = filesystem.f_frsize or filesystem.f_bsize
    total_bytes = filesystem.f_blocks * block_size
    free_bytes = filesystem.f_bavail * block_size
    estimated = _parse_nonnegative(
        args.estimated_write_bytes, field="estimated_write_bytes"
    )
    reserve = _parse_nonnegative(
        args.minimum_reserve_bytes, field="minimum_reserve_bytes"
    )
    identifier = target_id(target)
    state_dir = _validated_path_argument(args.state_dir)
    _secure_private_directory(state_dir, create=True)
    state_path = _state_path(state_dir, identifier)
    result = evaluate_preflight(
        total_bytes=total_bytes,
        free_bytes=free_bytes,
        estimated_write_bytes=estimated,
        minimum_reserve_bytes=reserve,
        was_critical=_read_state(state_path, identifier),
    )
    _atomic_json(
        state_path,
        {
            "checked_at": _utc_now().isoformat().replace("+00:00", "Z"),
            "schema_version": 1,
            "state": result["state"],
            "target_id": identifier,
        },
    )
    emit_event(
        args.component,
        "storage_preflight",
        "ok" if result["allowed"] else "blocked",
        result["reason"],
        bound_target=True,
        critical_percent=int(CRITICAL_PERCENT),
        estimated_write_bytes=estimated,
        free_bytes=free_bytes,
        minimum_reserve_bytes=reserve,
        projected_used_percent=result["projected_used_percent"],
        recovery_percent=int(RECOVERY_PERCENT),
        used_percent=result["used_percent"],
    )
    return 0 if result["allowed"] else 1


def _regular_file(path: Path, *, reason: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise SafetyError(reason) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise SafetyError(reason)
    return metadata


def _private_regular_file(path: Path, *, reason: str) -> os.stat_result:
    metadata = _regular_file(path, reason=reason)
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise SafetyError(reason)
    return metadata


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SafetyError("backup_unreadable") from exc
    return digest.hexdigest()


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_uid,
        left.st_gid,
        left.st_nlink,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_uid,
        right.st_gid,
        right.st_nlink,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _read_all(descriptor: int, *, maximum_bytes: int, reason: str) -> bytes:
    chunks: list[bytes] = []
    remaining = maximum_bytes + 1
    while remaining:
        try:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
        except OSError as exc:
            raise SafetyError(reason) from exc
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > maximum_bytes:
        raise SafetyError(reason)
    return raw


def _parse_data_env(text: str, profile: str) -> tuple[tuple[str, str], ...]:
    """Parse a deliberately small dotenv subset without shell evaluation."""

    requested = ENV_PROFILES.get(profile)
    if requested is None:
        raise SafetyError("invalid_env_profile")
    requested_keys = {key for key, _ in requested}
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        if not raw_line or raw_line.startswith("#"):
            continue
        if raw_line != raw_line.strip() or "\r" in raw_line:
            raise SafetyError("production_env_syntax_invalid")
        match = ENV_ASSIGNMENT_RE.fullmatch(raw_line)
        if match is None:
            raise SafetyError("production_env_syntax_invalid")
        key, raw_value = match.groups()
        if key in values:
            raise SafetyError("production_env_duplicate_key")
        values[key] = raw_value
        # Unrequested values remain inert bytes. Compose interpolation in an
        # unrelated setting is neither evaluated nor imported by this parser.
        if key not in requested_keys:
            continue
        if any(token in raw_value for token in ("$(", "${", "`")):
            raise SafetyError("production_env_dynamic_value")
        if any(ord(character) < 32 or ord(character) == 127 for character in raw_value):
            raise SafetyError("production_env_syntax_invalid")
        if raw_value[:1] in {"'", '"'}:
            quote = raw_value[0]
            if len(raw_value) < 2 or raw_value[-1] != quote:
                raise SafetyError("production_env_syntax_invalid")
            value = raw_value[1:-1]
            if quote in value or "\\" in value:
                raise SafetyError("production_env_syntax_invalid")
        else:
            if any(character.isspace() for character in raw_value) or "\\" in raw_value:
                raise SafetyError("production_env_syntax_invalid")
            value = raw_value
        values[key] = value

    selected: list[tuple[str, str]] = []
    for key, default in requested:
        value = values.get(key, default)
        if value is None or value == "":
            raise SafetyError("production_env_required_value_missing")
        selected.append((key, value))
    return tuple(selected)


def read_production_env(profile: str) -> tuple[tuple[str, str], ...]:
    """Read the fixed private production env file as inert data."""

    path = PRODUCTION_ENV_FILE
    _normalized_absolute(path)
    _reject_symlink_components(path, reason="production_env_unsafe")
    try:
        before = path.lstat()
    except OSError as exc:
        raise SafetyError("production_env_unavailable") from exc
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SafetyError("production_env_unavailable") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size > MAX_ENV_BYTES
            or not _same_file_state(before, opened)
        ):
            raise SafetyError("production_env_unsafe")
        raw = _read_all(
            descriptor, maximum_bytes=MAX_ENV_BYTES, reason="production_env_unreadable"
        )
        after = os.fstat(descriptor)
        try:
            path_after = path.lstat()
        except OSError as exc:
            raise SafetyError("production_env_changed") from exc
        if not _same_file_state(opened, after) or not _same_file_state(
            after, path_after
        ):
            raise SafetyError("production_env_changed")
    finally:
        os.close(descriptor)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise SafetyError("production_env_syntax_invalid") from exc
    if "\x00" in text:
        raise SafetyError("production_env_syntax_invalid")
    return _parse_data_env(text, profile)


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _bound_directory_path(descriptor: int, fallback: Path) -> Path:
    proc_path = Path(f"/proc/self/fd/{descriptor}")
    if proc_path.is_dir():
        return proc_path
    # macOS exposes directory descriptors under /dev/fd but does not permit
    # directory traversal through them. Production is Linux; tests retain all
    # descriptor-bound unlink operations and use the already-validated path.
    return fallback


def _open_private_target_directory(path: Path, *, create: bool) -> int:
    """Open a private target by walking no-follow directory descriptors."""

    path = _normalized_absolute(path)
    current_fd = os.open(path.anchor, _directory_flags())
    try:
        for part in path.parts[1:]:
            try:
                next_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
            except FileNotFoundError:
                if not create:
                    raise SafetyError("target_directory_missing") from None
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                    next_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
                except OSError as exc:
                    raise SafetyError("target_directory_unavailable") from exc
            except OSError as exc:
                raise SafetyError("target_directory_unsafe") from exc
            os.close(current_fd)
            current_fd = next_fd
        metadata = os.fstat(current_fd)
        try:
            path_metadata = path.lstat()
        except OSError as exc:
            raise SafetyError("target_directory_changed") from exc
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or not _same_inode(metadata, path_metadata)
        ):
            raise SafetyError("target_directory_unsafe")
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _open_private_regular_at(
    directory_fd: int,
    name: str,
    *,
    access_flags: int,
    reason: str,
) -> int:
    if "/" in name or name in {"", ".", ".."}:
        raise SafetyError(reason)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        try:
            descriptor = os.open(
                name,
                access_flags | nofollow | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            os.fchmod(descriptor, 0o600)
        except FileExistsError:
            descriptor = os.open(name, access_flags | nofollow, dir_fd=directory_fd)
    except OSError as exc:
        raise SafetyError(reason) from exc
    try:
        metadata = os.fstat(descriptor)
        directory_metadata = os.fstat(directory_fd)
        path_metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or metadata.st_dev != directory_metadata.st_dev
            or not _same_file_state(metadata, path_metadata)
        ):
            raise SafetyError(reason)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _validate_lifecycle_bindings(target: Path, target_fd: int, lock_fd: int) -> None:
    if target_fd < 3 or lock_fd < 3 or target_fd == lock_fd:
        raise SafetyError("lifecycle_descriptor_invalid")
    try:
        target_metadata = os.fstat(target_fd)
        path_metadata = target.lstat()
        lock_metadata = os.fstat(lock_fd)
        lock_path_metadata = os.stat(
            ".backup-lifecycle.lock", dir_fd=target_fd, follow_symlinks=False
        )
    except OSError as exc:
        raise SafetyError("lifecycle_binding_changed") from exc
    if (
        not stat.S_ISDIR(target_metadata.st_mode)
        or target_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(target_metadata.st_mode) != 0o700
        or not _same_inode(target_metadata, path_metadata)
        or not stat.S_ISREG(lock_metadata.st_mode)
        or lock_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(lock_metadata.st_mode) != 0o600
        or lock_metadata.st_nlink != 1
        or lock_metadata.st_dev != target_metadata.st_dev
        or not _same_file_state(lock_metadata, lock_path_metadata)
    ):
        raise SafetyError("lifecycle_binding_changed")
    try:
        duplicate = os.dup(lock_fd)
        try:
            fcntl.flock(duplicate, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(duplicate)
    except OSError as exc:
        raise SafetyError("lifecycle_lock_not_owned") from exc


def _acquire_target_lifecycle(target: Path) -> tuple[int, int]:
    target_fd = _open_private_target_directory(target, create=True)
    try:
        lock_fd = _open_private_regular_at(
            target_fd,
            ".backup-lifecycle.lock",
            access_flags=os.O_RDWR,
            reason="lifecycle_lock_unsafe",
        )
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _validate_lifecycle_bindings(target, target_fd, lock_fd)
            os.set_inheritable(target_fd, True)
            os.set_inheritable(lock_fd, True)
            return target_fd, lock_fd
        except OSError as exc:
            os.close(lock_fd)
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise SafetyError("lifecycle_lock_busy") from None
            raise SafetyError("lifecycle_lock_unavailable") from exc
        except Exception:
            os.close(lock_fd)
            raise
    except Exception:
        os.close(target_fd)
        raise


def _durably_hash_backup(backup: Path) -> tuple[str, os.stat_result]:
    path_metadata = _regular_file(backup, reason="backup_not_regular")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(backup, flags)
    except OSError as exc:
        raise SafetyError("backup_unreadable") from exc
    try:
        opened_metadata = os.fstat(descriptor)
        if not stat.S_ISREG(opened_metadata.st_mode) or not _same_file_state(
            path_metadata, opened_metadata
        ):
            raise SafetyError("backup_changed")

        digest = hashlib.sha256()
        while True:
            try:
                chunk = os.read(descriptor, 1024 * 1024)
            except OSError as exc:
                raise SafetyError("backup_unreadable") from exc
            if not chunk:
                break
            digest.update(chunk)

        try:
            os.fsync(descriptor)
        except OSError as exc:
            raise SafetyError("backup_fsync_failed") from exc

        synced_metadata = os.fstat(descriptor)
        try:
            current_path_metadata = backup.lstat()
        except OSError as exc:
            raise SafetyError("backup_changed") from exc
        if not _same_file_state(
            opened_metadata, synced_metadata
        ) or not _same_file_state(synced_metadata, current_path_metadata):
            raise SafetyError("backup_changed")
        return digest.hexdigest(), synced_metadata
    finally:
        os.close(descriptor)


def checksum_path(backup: Path) -> Path:
    return backup.with_name(f"{backup.name}.sha256")


def receipt_path(backup: Path) -> Path:
    return backup.with_name(f"{backup.name}.offsite-receipt.json")


def write_checksum(backup: Path) -> str:
    digest, metadata = _durably_hash_backup(backup)
    if metadata.st_size < MIN_BACKUP_BYTES:
        raise SafetyError("backup_too_small")
    sidecar = checksum_path(backup)
    if sidecar.exists() and sidecar.is_symlink():
        raise SafetyError("checksum_is_symlink")
    fd, temporary_name = tempfile.mkstemp(prefix=".backup-checksum-", dir=backup.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"{digest}  {backup.name}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, sidecar)
        os.chmod(sidecar, 0o600)
        _fsync_directory(backup.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return digest


def verify_expected_backup(
    backup: Path, expected_bytes: int, expected_sha256: str
) -> str:
    metadata = _private_regular_file(backup, reason="backup_not_private")
    if expected_bytes < MIN_BACKUP_BYTES or metadata.st_size != expected_bytes:
        raise SafetyError("expected_size_mismatch")
    if not SHA256_RE.fullmatch(expected_sha256):
        raise SafetyError("expected_checksum_invalid")
    actual, durable_metadata = _durably_hash_backup(backup)
    if not _same_file_state(metadata, durable_metadata):
        raise SafetyError("backup_changed")
    if not hmac.compare_digest(actual, expected_sha256):
        raise SafetyError("expected_checksum_mismatch")
    return actual


def verify_bound_backup(
    backup: Path,
    descriptor: int,
    expected_bytes: int,
    expected_sha256: str,
) -> str:
    """Verify the exact open inode held by the caller through remote deletion."""

    if descriptor < 3:
        raise SafetyError("bound_descriptor_invalid")
    if expected_bytes < MIN_BACKUP_BYTES:
        raise SafetyError("expected_size_mismatch")
    if not SHA256_RE.fullmatch(expected_sha256):
        raise SafetyError("expected_checksum_invalid")

    path_metadata = _private_regular_file(backup, reason="backup_not_private")
    try:
        bound = os.dup(descriptor)
    except OSError as exc:
        raise SafetyError("bound_descriptor_unavailable") from exc
    try:
        try:
            fcntl.flock(bound, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SafetyError("bound_backup_lock_unavailable") from exc
        opened_metadata = os.fstat(bound)
        if (
            not stat.S_ISREG(opened_metadata.st_mode)
            or opened_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(opened_metadata.st_mode) & 0o077
            or opened_metadata.st_nlink != 1
            or opened_metadata.st_size != expected_bytes
            or not _same_file_state(path_metadata, opened_metadata)
        ):
            raise SafetyError("bound_backup_changed")

        try:
            os.lseek(bound, 0, os.SEEK_SET)
        except OSError as exc:
            raise SafetyError("bound_descriptor_unreadable") from exc
        digest = hashlib.sha256()
        while True:
            try:
                chunk = os.read(bound, 1024 * 1024)
            except OSError as exc:
                raise SafetyError("bound_descriptor_unreadable") from exc
            if not chunk:
                break
            digest.update(chunk)
        try:
            os.fsync(bound)
            synced_metadata = os.fstat(bound)
            current_path_metadata = backup.lstat()
        except OSError as exc:
            raise SafetyError("bound_backup_changed") from exc
        if not _same_file_state(
            opened_metadata, synced_metadata
        ) or not _same_file_state(synced_metadata, current_path_metadata):
            raise SafetyError("bound_backup_changed")
        actual = digest.hexdigest()
        if not hmac.compare_digest(actual, expected_sha256):
            raise SafetyError("expected_checksum_mismatch")
        return actual
    finally:
        os.close(bound)


def verify_local_backup(backup: Path) -> str:
    metadata = _private_regular_file(backup, reason="backup_not_private")
    if metadata.st_size < MIN_BACKUP_BYTES:
        raise SafetyError("backup_too_small")
    sidecar = checksum_path(backup)
    checksum_metadata = _private_regular_file(sidecar, reason="checksum_not_private")
    if checksum_metadata.st_size > 1024:
        raise SafetyError("checksum_invalid")
    try:
        content = sidecar.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise SafetyError("checksum_invalid") from exc
    match = CHECKSUM_RE.fullmatch(content)
    if match is None or match.group(2) != backup.name:
        raise SafetyError("checksum_invalid")
    actual = _sha256(backup)
    if not hmac.compare_digest(match.group(1), actual):
        raise SafetyError("checksum_mismatch")
    return actual


def _verified_at(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SafetyError("receipt_invalid")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise SafetyError("receipt_invalid") from exc
    now = _utc_now()
    if parsed > now + dt.timedelta(minutes=5):
        raise SafetyError("receipt_invalid")
    if parsed < now - dt.timedelta(seconds=MAX_RECEIPT_AGE_SECONDS):
        raise SafetyError("receipt_stale")
    return parsed


def _strict_json_object(text: str, *, reason: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SafetyError(reason)
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise SafetyError(reason) from exc


def verify_offsite_receipt(backup: Path, receipt: Path | None = None) -> str:
    local_digest = verify_local_backup(backup)
    proof = receipt or receipt_path(backup)
    metadata = _private_regular_file(proof, reason="receipt_not_private")
    if metadata.st_nlink != 1 or metadata.st_size > MAX_RECEIPT_BYTES:
        raise SafetyError("receipt_invalid")
    try:
        data = _strict_json_object(
            proof.read_text(encoding="utf-8"), reason="receipt_invalid"
        )
    except (OSError, UnicodeError) as exc:
        raise SafetyError("receipt_invalid") from exc
    if not isinstance(data, dict) or set(data) != RECEIPT_KEYS:
        raise SafetyError("receipt_invalid")
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != 2
        or data["backup_name"] != backup.name
    ):
        raise SafetyError("receipt_invalid")
    if data["offsite_verified"] is not True:
        raise SafetyError("receipt_unverified")
    if data["verification_method"] not in RECEIPT_METHODS:
        raise SafetyError("receipt_invalid")
    for identifier_key in (
        "offsite_ciphertext_object_id_sha256",
        "encryption_key_id_sha256",
    ):
        identifier = data[identifier_key]
        if not isinstance(identifier, str) or not SHA256_RE.fullmatch(identifier):
            raise SafetyError("receipt_invalid")
    _verified_at(data["verified_at"])
    local_claim = data["local_plaintext_sha256"]
    decrypted_claim = data["decrypted_plaintext_sha256"]
    ciphertext_claim = data["downloaded_ciphertext_sha256"]
    for claim in (local_claim, decrypted_claim, ciphertext_claim):
        if not isinstance(claim, str) or not SHA256_RE.fullmatch(claim):
            raise SafetyError("receipt_invalid")
    if not (
        hmac.compare_digest(local_claim, local_digest)
        and hmac.compare_digest(decrypted_claim, local_digest)
    ):
        raise SafetyError("receipt_checksum_mismatch")
    if hmac.compare_digest(ciphertext_claim, local_digest):
        raise SafetyError("receipt_ciphertext_invalid")
    return local_digest


def write_offsite_receipt(
    backup: Path,
    downloaded_ciphertext: Path,
    decrypted_plaintext_copy: Path,
    offsite_object_id_sha256: str,
    encryption_key_id_sha256: str,
) -> Path:
    """Bind a full ciphertext download and its decrypted plaintext to a backup."""

    local_digest = verify_local_backup(backup)
    local_metadata = _private_regular_file(backup, reason="backup_not_private")
    ciphertext_metadata = _private_regular_file(
        downloaded_ciphertext, reason="downloaded_ciphertext_not_private"
    )
    decrypted_metadata = _private_regular_file(
        decrypted_plaintext_copy, reason="decrypted_copy_not_private"
    )
    if ciphertext_metadata.st_size < MIN_BACKUP_BYTES:
        raise SafetyError("downloaded_ciphertext_too_small")
    if decrypted_metadata.st_size < MIN_BACKUP_BYTES:
        raise SafetyError("decrypted_copy_too_small")
    identities = {
        (local_metadata.st_dev, local_metadata.st_ino),
        (ciphertext_metadata.st_dev, ciphertext_metadata.st_ino),
        (decrypted_metadata.st_dev, decrypted_metadata.st_ino),
    }
    if (
        len(identities) != 3
        or local_metadata.st_nlink != 1
        or ciphertext_metadata.st_nlink != 1
        or decrypted_metadata.st_nlink != 1
    ):
        raise SafetyError("offsite_evidence_not_distinct")
    if not SHA256_RE.fullmatch(offsite_object_id_sha256):
        raise SafetyError("invalid_offsite_object_id")
    if not SHA256_RE.fullmatch(encryption_key_id_sha256):
        raise SafetyError("invalid_encryption_key_id")
    ciphertext_digest = _sha256(downloaded_ciphertext)
    decrypted_digest = _sha256(decrypted_plaintext_copy)
    if not hmac.compare_digest(local_digest, decrypted_digest):
        raise SafetyError("offsite_decryption_mismatch")
    if hmac.compare_digest(local_digest, ciphertext_digest):
        raise SafetyError("offsite_ciphertext_unencrypted")

    proof = receipt_path(backup)
    _atomic_json(
        proof,
        {
            "schema_version": 2,
            "backup_name": backup.name,
            "local_plaintext_sha256": local_digest,
            "downloaded_ciphertext_sha256": ciphertext_digest,
            "decrypted_plaintext_sha256": decrypted_digest,
            "offsite_verified": True,
            "offsite_ciphertext_object_id_sha256": offsite_object_id_sha256,
            "encryption_key_id_sha256": encryption_key_id_sha256,
            "verified_at": _utc_now()
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "verification_method": "full-download-decrypt-sha256",
        },
    )
    return proof


def run_checksum(args: argparse.Namespace) -> int:
    write_checksum(Path(args.backup))
    emit_event(args.component, "local_checksum", "ok", "checksum_written")
    return 0


def run_verify_local(args: argparse.Namespace) -> int:
    verify_local_backup(Path(args.backup))
    emit_event(args.component, "local_verification", "ok", "checksum_verified")
    return 0


def run_verify_expected(args: argparse.Namespace) -> int:
    verify_expected_backup(
        Path(args.backup),
        _parse_positive(args.expected_bytes, field="expected_bytes"),
        args.expected_sha256,
    )
    emit_event(args.component, "source_verification", "ok", "source_checksum_verified")
    return 0


def run_verify_receipt(args: argparse.Namespace) -> int:
    receipt = Path(args.receipt) if args.receipt else None
    verify_offsite_receipt(Path(args.backup), receipt)
    emit_event(args.component, "offsite_verification", "ok", "receipt_verified")
    return 0


def run_write_receipt(args: argparse.Namespace) -> int:
    write_offsite_receipt(
        Path(args.backup),
        Path(args.downloaded_ciphertext),
        Path(args.decrypted_plaintext_copy),
        args.offsite_object_id_sha256,
        args.encryption_key_id_sha256,
    )
    emit_event(args.component, "offsite_verification", "ok", "receipt_written")
    return 0


def run_remote_delete_eligible(args: argparse.Namespace) -> int:
    backup = Path(args.backup)
    receipt_digest = verify_local_backup(backup)
    if args.policy == "verified-offsite":
        receipt = Path(args.receipt) if args.receipt else None
        receipt_digest = verify_offsite_receipt(backup, receipt)
        reason = "verified_offsite_policy"
    else:
        reason = "verified_local_policy"
    bound_digest = verify_bound_backup(
        backup,
        _parse_nonnegative(args.backup_fd, field="backup_fd"),
        _parse_positive(args.expected_bytes, field="expected_bytes"),
        args.expected_sha256,
    )
    if not hmac.compare_digest(receipt_digest, bound_digest):
        raise SafetyError("receipt_bound_backup_mismatch")
    emit_event(args.component, "remote_delete_gate", "ok", reason)
    return 0


def _matches_backup(path: Path, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path.name, pattern)


@contextlib.contextmanager
def _retention_lock(target_dir: Path):
    directory_fd: int | None = None
    descriptor: int | None = None
    try:
        directory_fd = _open_private_target_directory(target_dir, create=False)
        descriptor = _open_private_regular_at(
            directory_fd,
            ".backup-lifecycle.lock",
            access_flags=os.O_RDWR | getattr(os, "O_CLOEXEC", 0),
            reason="retention_lock_unsafe",
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise SafetyError("retention_lock_busy") from None
            raise SafetyError("retention_lock_unavailable") from None
        _validate_lifecycle_bindings(target_dir, directory_fd, descriptor)
        yield directory_fd
    except SafetyError:
        raise
    except OSError as exc:
        raise SafetyError("retention_lock_unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_fd is not None:
            os.close(directory_fd)


def _verified_local_backups(
    target_dir: Path, pattern: str
) -> list[tuple[Path, os.stat_result]]:
    verified: list[tuple[Path, os.stat_result]] = []
    for candidate in target_dir.iterdir():
        if not _matches_backup(candidate, pattern):
            continue
        try:
            before = candidate.lstat()
            verify_local_backup(candidate)
            after = candidate.lstat()
        except (OSError, SafetyError):
            continue
        if (
            before.st_dev == after.st_dev
            and before.st_ino == after.st_ino
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
            and after.st_nlink == 1
        ):
            verified.append((candidate, after))
    return verified


def _sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _pinned_verified_local_backups(
    directory_fd: int, pattern: str
) -> list[tuple[str, int, os.stat_result, str]]:
    """Open and checksum-pin every good copy under the lifecycle lock."""

    pinned: list[tuple[str, int, os.stat_result, str]] = []
    file_flags = (
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    for name in os.listdir(directory_fd):
        if not fnmatch.fnmatchcase(name, pattern):
            continue
        backup_fd: int | None = None
        checksum_fd: int | None = None
        keep_backup_fd = False
        try:
            backup_fd = os.open(name, file_flags, dir_fd=directory_fd)
            before = os.fstat(backup_fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o077
                or before.st_size < MIN_BACKUP_BYTES
                or before.st_nlink != 1
            ):
                continue
            checksum_name = f"{name}.sha256"
            checksum_fd = os.open(checksum_name, file_flags, dir_fd=directory_fd)
            checksum_metadata = os.fstat(checksum_fd)
            if (
                not stat.S_ISREG(checksum_metadata.st_mode)
                or checksum_metadata.st_uid != os.geteuid()
                or stat.S_IMODE(checksum_metadata.st_mode) & 0o077
                or checksum_metadata.st_size > 1024
            ):
                continue
            checksum_raw = os.read(checksum_fd, 1025)
            try:
                checksum_text = checksum_raw.decode("ascii")
            except UnicodeError:
                continue
            match = CHECKSUM_RE.fullmatch(checksum_text)
            if match is None or match.group(2) != name:
                continue
            if not hmac.compare_digest(match.group(1), _sha256_fd(backup_fd)):
                continue
            after = os.fstat(backup_fd)
            path_metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or path_metadata.st_dev != after.st_dev
                or path_metadata.st_ino != after.st_ino
            ):
                continue
            pinned.append((name, backup_fd, after, match.group(1)))
            keep_backup_fd = True
        except OSError:
            continue
        finally:
            if checksum_fd is not None:
                os.close(checksum_fd)
            if backup_fd is not None and not keep_backup_fd:
                os.close(backup_fd)
    return pinned


def _prune_backups_locked(
    *,
    target_dir: Path,
    pattern: str,
    retention_days: int,
    minimum_local_copies: int,
    directory_fd: int,
    now: float | None = None,
) -> dict[str, int]:
    current_time = _utc_now().timestamp() if now is None else now
    cutoff = current_time - (retention_days * 86400)
    scanned = sum(
        1 for candidate in target_dir.iterdir() if _matches_backup(candidate, pattern)
    )
    verified = _verified_local_backups(target_dir, pattern)

    candidates: list[tuple[Path, os.stat_result]] = []
    skipped_without_receipt = 0
    for candidate, before in verified:
        if before.st_mtime >= cutoff:
            continue
        try:
            verify_offsite_receipt(candidate)
        except SafetyError:
            skipped_without_receipt += 1
            continue
        candidates.append((candidate, before))

    candidates.sort(key=lambda item: (item[1].st_mtime, item[0].name))
    deleted = 0
    retained_minimum = 0
    for candidate, expected in candidates:
        verify_offsite_receipt(candidate)
        # Pin and checksum every remaining copy under the cooperative
        # writer/prune lock immediately before this deletion decision.
        pinned = _pinned_verified_local_backups(directory_fd, pattern)
        try:
            for _, pinned_fd, _, expected_digest in pinned:
                if not hmac.compare_digest(expected_digest, _sha256_fd(pinned_fd)):
                    raise SafetyError("backup_changed_during_retention")
            pinned_by_name = {
                name: (pinned_fd, metadata) for name, pinned_fd, metadata, _ in pinned
            }
            if candidate.name not in pinned_by_name:
                continue
            if len(pinned) <= minimum_local_copies:
                retained_minimum += 1
                continue
            _candidate_fd, final = pinned_by_name[candidate.name]
            path_final = os.stat(
                candidate.name, dir_fd=directory_fd, follow_symlinks=False
            )
            if (
                final.st_dev != expected.st_dev
                or final.st_ino != expected.st_ino
                or final.st_size != expected.st_size
                or final.st_mtime_ns != expected.st_mtime_ns
                or path_final.st_dev != final.st_dev
                or path_final.st_ino != final.st_ino
            ):
                raise SafetyError("backup_changed_during_retention")
            os.unlink(candidate.name, dir_fd=directory_fd)
        finally:
            for _, pinned_fd, _, _ in pinned:
                os.close(pinned_fd)
        try:
            os.unlink(checksum_path(candidate).name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        deleted += 1

    return {
        "deleted": deleted,
        "eligible": len(candidates),
        "retained_minimum": retained_minimum,
        "scanned": scanned,
        "skipped_without_receipt": skipped_without_receipt,
        "verified_local": len(verified),
    }


def prune_backups(
    *,
    target_dir: Path,
    pattern: str,
    retention_days: int,
    minimum_local_copies: int,
    now: float | None = None,
) -> dict[str, int]:
    if (
        "/" in pattern
        or "\\" in pattern
        or pattern.count("*") != 1
        or any(character in pattern for character in "?[]")
    ):
        raise SafetyError("invalid_retention_pattern")
    prefix, suffix = pattern.split("*", 1)
    if (
        not prefix
        or not suffix
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", prefix)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", suffix)
    ):
        raise SafetyError("invalid_retention_pattern")
    if retention_days < 0 or minimum_local_copies < 1:
        raise SafetyError("invalid_retention_policy")
    target_dir = _normalized_absolute(target_dir)
    _reject_symlink_components(target_dir, reason="invalid_retention_target")
    try:
        target_metadata = target_dir.lstat()
    except OSError as exc:
        raise SafetyError("invalid_retention_target") from exc
    if (
        stat.S_ISLNK(target_metadata.st_mode)
        or not stat.S_ISDIR(target_metadata.st_mode)
        or target_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(target_metadata.st_mode) != 0o700
    ):
        raise SafetyError("invalid_retention_target")
    with _retention_lock(target_dir) as directory_fd:
        bound_target = _bound_directory_path(directory_fd, target_dir)
        return _prune_backups_locked(
            target_dir=bound_target,
            pattern=pattern,
            retention_days=retention_days,
            minimum_local_copies=minimum_local_copies,
            directory_fd=directory_fd,
            now=now,
        )


def run_prune(args: argparse.Namespace) -> int:
    result = prune_backups(
        target_dir=_validated_path_argument(args.target_dir),
        pattern=args.pattern,
        retention_days=_parse_nonnegative(args.retention_days, field="retention_days"),
        minimum_local_copies=_parse_positive(
            args.minimum_local_copies, field="minimum_local_copies"
        ),
    )
    reason = "retention_completed" if result["deleted"] else "nothing_delete_safe"
    emit_event(args.component, "retention", "ok", reason, **result)
    return 0


def _parse_metrics(raw_metrics: list[str]) -> dict[str, int | float | bool]:
    metrics: dict[str, int | float | bool] = {}
    for raw in raw_metrics:
        key, separator, value = raw.partition("=")
        if not separator:
            raise SafetyError("invalid_metric")
        _token(key, field="metric")
        if value in {"true", "false"}:
            metrics[key] = value == "true"
            continue
        try:
            metrics[key] = int(value)
        except ValueError:
            try:
                metrics[key] = float(value)
            except ValueError as exc:
                raise SafetyError("invalid_metric_value") from exc
    return metrics


def run_event(args: argparse.Namespace) -> int:
    emit_event(
        args.component,
        args.event,
        args.status,
        args.reason,
        **_parse_metrics(args.metric),
    )
    return 0


def run_read_production_env(args: argparse.Namespace) -> int:
    values = read_production_env(args.profile)
    output = sys.stdout.buffer
    for key, value in values:
        output.write(key.encode("ascii") + b"\0" + value.encode("utf-8") + b"\0")
    output.flush()
    return 0


def _validated_runtime_settings(
    raw_settings: list[str], expected_keys: tuple[str, ...]
) -> dict[str, str]:
    settings: dict[str, str] = {}
    for raw in raw_settings:
        key, separator, value = raw.partition("=")
        if not separator or key not in expected_keys or key in settings:
            raise SafetyError("runtime_setting_invalid")
        settings[key] = value
    if set(settings) != set(expected_keys):
        raise SafetyError("runtime_setting_missing")

    for key in (
        "RETENTION_DAYS",
        "BACKUP_MIN_FREE_BYTES",
        "BACKUP_ESTIMATED_BYTES",
        "POSTGRES_BACKUP_ESTIMATED_BYTES",
        "QDRANT_BACKUP_ESTIMATED_BYTES",
    ):
        if key in settings:
            if not re.fullmatch(r"0|[1-9][0-9]*", settings[key]):
                raise SafetyError("runtime_setting_invalid")
            _parse_nonnegative(settings[key], field="runtime_setting")
            if (
                key == "BACKUP_MIN_FREE_BYTES"
                and int(settings[key]) < MINIMUM_FREE_BYTES
            ):
                raise SafetyError("runtime_setting_invalid")
    if "BACKUP_MIN_LOCAL_COPIES" in settings:
        if not re.fullmatch(r"[1-9][0-9]*", settings["BACKUP_MIN_LOCAL_COPIES"]):
            raise SafetyError("runtime_setting_invalid")
        _parse_positive(settings["BACKUP_MIN_LOCAL_COPIES"], field="runtime_setting")
    if "BACKUP_SAFETY_STATE_DIR" in settings:
        settings["BACKUP_SAFETY_STATE_DIR"] = str(
            _validated_path_argument(settings["BACKUP_SAFETY_STATE_DIR"])
        )
    for key in ("POSTGRES_CONTAINER", "BACKEND_CONTAINER", "QDRANT_CONTAINER"):
        if key in settings and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", settings[key]
        ):
            raise SafetyError("runtime_setting_invalid")
    if "QDRANT_INTERNAL_URL" in settings and settings["QDRANT_INTERNAL_URL"] != (
        "http://qdrant:6333"
    ):
        raise SafetyError("runtime_setting_invalid")
    if "QDRANT_REMOTE_DELETE_POLICY" in settings and settings[
        "QDRANT_REMOTE_DELETE_POLICY"
    ] not in {"verified-local", "verified-offsite"}:
        raise SafetyError("runtime_setting_invalid")
    if "QDRANT_OFFSITE_RECEIPT" in settings:
        receipt = settings["QDRANT_OFFSITE_RECEIPT"]
        if receipt:
            settings["QDRANT_OFFSITE_RECEIPT"] = str(_validated_path_argument(receipt))
        if (
            settings.get("QDRANT_REMOTE_DELETE_POLICY") == "verified-offsite"
            and not receipt
        ):
            raise SafetyError("runtime_setting_invalid")
    return settings


def run_with_lifecycle(args: argparse.Namespace) -> int:
    target = _validated_path_argument(args.target_dir)
    script_name = WRITER_SCRIPTS[args.writer]
    runtime_settings = _validated_runtime_settings(
        args.setting, WRITER_SETTINGS[args.writer]
    )
    target_fd, lock_fd = _acquire_target_lifecycle(target)
    environment = {
        "HOME": "/home/thorsten",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }
    environment.update(runtime_settings)
    environment.update(
        {
            "TARGET_DIR": str(target),
            "SEALAI_BACKUP_TARGET_FD": str(target_fd),
            "SEALAI_BACKUP_LIFECYCLE_FD": str(lock_fd),
        }
    )
    script = Path(__file__).resolve().parent / script_name
    os.execve(script, [str(script)], environment)
    raise AssertionError("execve returned")


def run_validate_lifecycle(args: argparse.Namespace) -> int:
    _validate_lifecycle_bindings(
        _validated_path_argument(args.target_dir),
        _parse_nonnegative(args.target_fd, field="target_fd"),
        _parse_nonnegative(args.lock_fd, field="lock_fd"),
    )
    return 0


def _validate_orchestrator_bindings(
    log_path: Path, directory_fd: int, log_fd: int, lock_fd: int
) -> None:
    if (
        len({directory_fd, log_fd, lock_fd}) != 3
        or min(directory_fd, log_fd, lock_fd) < 3
    ):
        raise SafetyError("orchestrator_descriptor_invalid")
    try:
        directory_metadata = os.fstat(directory_fd)
        directory_path_metadata = log_path.parent.lstat()
        log_metadata = os.fstat(log_fd)
        log_path_metadata = os.stat(
            log_path.name, dir_fd=directory_fd, follow_symlinks=False
        )
        lock_metadata = os.fstat(lock_fd)
        lock_path_metadata = os.stat(
            ".backup-run.lock", dir_fd=directory_fd, follow_symlinks=False
        )
    except OSError as exc:
        raise SafetyError("orchestrator_binding_changed") from exc
    if (
        not stat.S_ISDIR(directory_metadata.st_mode)
        or directory_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(directory_metadata.st_mode) != 0o700
        or not _same_inode(directory_metadata, directory_path_metadata)
        or not stat.S_ISREG(log_metadata.st_mode)
        or log_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(log_metadata.st_mode) != 0o600
        or log_metadata.st_nlink != 1
        or log_metadata.st_dev != directory_metadata.st_dev
        or not _same_file_state(log_metadata, log_path_metadata)
        or not stat.S_ISREG(lock_metadata.st_mode)
        or lock_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(lock_metadata.st_mode) != 0o600
        or lock_metadata.st_nlink != 1
        or lock_metadata.st_dev != directory_metadata.st_dev
        or not _same_file_state(lock_metadata, lock_path_metadata)
    ):
        raise SafetyError("orchestrator_binding_changed")
    try:
        duplicate = os.dup(lock_fd)
        try:
            fcntl.flock(duplicate, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(duplicate)
    except OSError as exc:
        raise SafetyError("orchestrator_lock_not_owned") from exc


def _acquire_orchestrator_bindings(log_path: Path) -> tuple[int, int, int]:
    directory_fd = _open_private_target_directory(log_path.parent, create=True)
    log_fd: int | None = None
    lock_fd: int | None = None
    try:
        log_fd = _open_private_regular_at(
            directory_fd,
            log_path.name,
            access_flags=os.O_WRONLY | os.O_APPEND,
            reason="log_file_unsafe",
        )
        lock_fd = _open_private_regular_at(
            directory_fd,
            ".backup-run.lock",
            access_flags=os.O_RDWR,
            reason="run_lock_unsafe",
        )
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise SafetyError("run_lock_busy") from None
            raise SafetyError("run_lock_unavailable") from exc
        _validate_orchestrator_bindings(log_path, directory_fd, log_fd, lock_fd)
        for descriptor in (directory_fd, log_fd, lock_fd):
            os.set_inheritable(descriptor, True)
        return directory_fd, log_fd, lock_fd
    except Exception:
        if lock_fd is not None:
            os.close(lock_fd)
        if log_fd is not None:
            os.close(log_fd)
        os.close(directory_fd)
        raise


def run_with_orchestrator_lock(args: argparse.Namespace) -> int:
    runtime_settings = _validated_runtime_settings(args.setting, ORCHESTRATOR_SETTINGS)
    directory_fd, log_fd, lock_fd = _acquire_orchestrator_bindings(ORCHESTRATOR_LOG)
    environment = {
        "HOME": "/home/thorsten",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }
    environment.update(runtime_settings)
    environment.update(
        {
            "SEALAI_BACKUP_LOG_DIR_FD": str(directory_fd),
            "SEALAI_BACKUP_LOG_FD": str(log_fd),
            "SEALAI_BACKUP_RUN_LOCK_FD": str(lock_fd),
        }
    )
    script = Path(__file__).resolve().parent / "backup_run.sh"
    os.execve(script, [str(script)], environment)
    raise AssertionError("execve returned")


def run_validate_orchestrator(args: argparse.Namespace) -> int:
    _validate_orchestrator_bindings(
        ORCHESTRATOR_LOG,
        _parse_nonnegative(args.directory_fd, field="directory_fd"),
        _parse_nonnegative(args.log_fd, field="log_fd"),
        _parse_nonnegative(args.lock_fd, field="lock_fd"),
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def component_argument(command: argparse.ArgumentParser) -> None:
        command.add_argument("--component", required=True)

    preflight = subparsers.add_parser("preflight")
    component_argument(preflight)
    preflight.add_argument("--target-dir", required=True)
    preflight.add_argument("--estimated-write-bytes", required=True)
    preflight.add_argument("--minimum-reserve-bytes", required=True)
    preflight.add_argument("--state-dir", required=True)
    preflight.set_defaults(handler=run_preflight, event_name="storage_preflight")

    bound_preflight = subparsers.add_parser("preflight-bound")
    component_argument(bound_preflight)
    bound_preflight.add_argument("--target-dir", required=True)
    bound_preflight.add_argument("--target-fd", required=True)
    bound_preflight.add_argument("--lock-fd", required=True)
    bound_preflight.add_argument("--estimated-write-bytes", required=True)
    bound_preflight.add_argument("--minimum-reserve-bytes", required=True)
    bound_preflight.add_argument("--state-dir", required=True)
    bound_preflight.set_defaults(
        handler=run_bound_preflight, event_name="storage_preflight"
    )

    checksum = subparsers.add_parser("write-checksum")
    component_argument(checksum)
    checksum.add_argument("--backup", required=True)
    checksum.set_defaults(handler=run_checksum, event_name="local_checksum")

    verify_local = subparsers.add_parser("verify-local")
    component_argument(verify_local)
    verify_local.add_argument("--backup", required=True)
    verify_local.set_defaults(handler=run_verify_local, event_name="local_verification")

    verify_expected = subparsers.add_parser("verify-expected")
    component_argument(verify_expected)
    verify_expected.add_argument("--backup", required=True)
    verify_expected.add_argument("--expected-bytes", required=True)
    verify_expected.add_argument("--expected-sha256", required=True)
    verify_expected.set_defaults(
        handler=run_verify_expected, event_name="source_verification"
    )

    verify_receipt = subparsers.add_parser("verify-receipt")
    component_argument(verify_receipt)
    verify_receipt.add_argument("--backup", required=True)
    verify_receipt.add_argument("--receipt")
    verify_receipt.set_defaults(
        handler=run_verify_receipt, event_name="offsite_verification"
    )

    write_receipt = subparsers.add_parser("write-receipt")
    component_argument(write_receipt)
    write_receipt.add_argument("--backup", required=True)
    write_receipt.add_argument("--downloaded-ciphertext", required=True)
    write_receipt.add_argument("--decrypted-plaintext-copy", required=True)
    write_receipt.add_argument("--offsite-object-id-sha256", required=True)
    write_receipt.add_argument("--encryption-key-id-sha256", required=True)
    write_receipt.set_defaults(
        handler=run_write_receipt, event_name="offsite_verification"
    )

    remote_gate = subparsers.add_parser("remote-delete-eligible")
    component_argument(remote_gate)
    remote_gate.add_argument("--backup", required=True)
    remote_gate.add_argument(
        "--policy", choices=("verified-local", "verified-offsite"), required=True
    )
    remote_gate.add_argument("--receipt")
    remote_gate.add_argument("--backup-fd", required=True)
    remote_gate.add_argument("--expected-bytes", required=True)
    remote_gate.add_argument("--expected-sha256", required=True)
    remote_gate.set_defaults(
        handler=run_remote_delete_eligible, event_name="remote_delete_gate"
    )

    prune = subparsers.add_parser("prune")
    component_argument(prune)
    prune.add_argument("--target-dir", required=True)
    prune.add_argument("--pattern", required=True)
    prune.add_argument("--retention-days", required=True)
    prune.add_argument("--minimum-local-copies", required=True)
    prune.set_defaults(handler=run_prune, event_name="retention")

    event = subparsers.add_parser("event")
    component_argument(event)
    event.add_argument("--event", required=True)
    event.add_argument(
        "--status", choices=("ok", "warn", "blocked", "error"), required=True
    )
    event.add_argument("--reason", required=True)
    event.add_argument("--metric", action="append", default=[])
    event.set_defaults(handler=run_event, event_name="event")

    read_env = subparsers.add_parser("read-production-env")
    read_env.add_argument("--profile", choices=tuple(ENV_PROFILES), required=True)
    read_env.set_defaults(
        handler=run_read_production_env,
        component="backup_env",
        event_name="configuration",
    )

    lifecycle = subparsers.add_parser("run-with-lifecycle")
    lifecycle.add_argument("--writer", choices=tuple(WRITER_SCRIPTS), required=True)
    lifecycle.add_argument("--target-dir", required=True)
    lifecycle.add_argument("--setting", action="append", default=[])
    lifecycle.set_defaults(
        handler=run_with_lifecycle,
        component="backup_lifecycle",
        event_name="lifecycle_lock",
    )

    validate_lifecycle = subparsers.add_parser("validate-lifecycle")
    validate_lifecycle.add_argument("--target-dir", required=True)
    validate_lifecycle.add_argument("--target-fd", required=True)
    validate_lifecycle.add_argument("--lock-fd", required=True)
    validate_lifecycle.set_defaults(
        handler=run_validate_lifecycle,
        component="backup_lifecycle",
        event_name="lifecycle_lock",
    )

    orchestrator = subparsers.add_parser("run-with-orchestrator-lock")
    orchestrator.add_argument("--setting", action="append", default=[])
    orchestrator.set_defaults(
        handler=run_with_orchestrator_lock,
        component="backup_run",
        event_name="backup_run",
    )

    validate_orchestrator = subparsers.add_parser("validate-orchestrator")
    validate_orchestrator.add_argument("--directory-fd", required=True)
    validate_orchestrator.add_argument("--log-fd", required=True)
    validate_orchestrator.add_argument("--lock-fd", required=True)
    validate_orchestrator.set_defaults(
        handler=run_validate_orchestrator,
        component="backup_run",
        event_name="backup_run",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except SafetyError as exc:
        try:
            emit_event(args.component, args.event_name, "blocked", exc.reason)
        except SafetyError:
            print(
                '{"component":"backup_safety","event":"internal_error",'
                '"reason":"invalid_event","status":"error"}',
                file=sys.stderr,
            )
        return 1
    except Exception:
        try:
            emit_event(args.component, args.event_name, "error", "internal_error")
        except SafetyError:
            print(
                '{"component":"backup_safety","event":"internal_error",'
                '"reason":"internal_error","status":"error"}',
                file=sys.stderr,
            )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
