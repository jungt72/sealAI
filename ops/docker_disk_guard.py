#!/usr/bin/env python3
"""Non-destructive disk-pressure guard for the Docker data filesystem.

The guard observes exactly one configured mount. It never invokes Docker and it
never removes data. Its JSON output and persisted records are deliberately
limited to operational state; configured paths and exception text are never
emitted.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import errno
import fcntl
import json
import math
import os
import secrets
import stat
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


SCHEMA_VERSION = 1
CONFIG_VERSION = 1
WARNING_PERCENT = 75
CRITICAL_PERCENT = 85
RECOVERY_PERCENT = 80
PREFLIGHT_STATE_MAX_AGE_SECONDS = 15 * 60
EXTERNAL_ALERT_DELIVERY_STATUS = "BLOCKED_EXTERNAL"

EXIT_OK = 0
EXIT_WARNING = 10
EXIT_CRITICAL = 20
EXIT_ASSERT_UNSTABLE = 21
EXIT_PREFLIGHT_BLOCKED = 22
EXIT_INTERNAL = 70
EXIT_OBSERVATION = 74
EXIT_LOCKED = 75
EXIT_CONFIG = 78

_CONFIG_KEYS = frozenset(
    {"version", "volume", "docker_root_dir", "state_dir", "lock_file"}
)
_STATE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "usage_percent",
        "critical_latched",
        "observed_at",
        "last_transition_at",
    }
)
_VALID_STATUSES = frozenset({"healthy", "warning", "critical", "recovering"})


class GuardError(Exception):
    """Expected, redacted operational failure."""

    def __init__(self, reason_code: str, exit_code: int) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.exit_code = exit_code


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: ARG002 - argparse API
        _emit(
            _error_payload(
                command="unknown",
                dry_run=False,
                reason_code="invalid_arguments",
            )
        )
        raise SystemExit(64)


@dataclasses.dataclass(frozen=True)
class Config:
    volume: Path
    docker_root_dir: Path
    state_dir: Path
    lock_file: Path

    @property
    def state_file(self) -> Path:
        return self.state_dir / "state.json"

    @property
    def alert_dir(self) -> Path:
        return self.state_dir / "alerts"

    @property
    def alert_file(self) -> Path:
        return self.alert_dir / "latest.json"


@dataclasses.dataclass(frozen=True)
class State:
    status: str
    usage_percent: int
    critical_latched: bool
    observed_at: str
    last_transition_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "usage_percent": self.usage_percent,
            "critical_latched": self.critical_latched,
            "observed_at": self.observed_at,
            "last_transition_at": self.last_transition_at,
        }


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _timestamp(value: dt.datetime) -> str:
    return (
        value.astimezone(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _thresholds() -> dict[str, int]:
    return {
        "warning_percent": WARNING_PERCENT,
        "critical_percent": CRITICAL_PERCENT,
        "recovery_percent": RECOVERY_PERCENT,
    }


def _base_payload(command: str, dry_run: bool) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "component": "sealai-disk-guard",
        "command": command,
        "dry_run": dry_run,
        "external_alert_delivery": EXTERNAL_ALERT_DELIVERY_STATUS,
        "thresholds": _thresholds(),
    }


def _error_payload(command: str, dry_run: bool, reason_code: str) -> dict[str, Any]:
    payload = _base_payload(command, dry_run)
    payload.update(
        {
            "result": "error",
            "status": "unknown",
            "reason_code": reason_code,
            "state_written": False,
            "alert_written": False,
        }
    )
    return payload


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _is_normalized_absolute(path: Path) -> bool:
    return path.is_absolute() and str(path) == os.path.normpath(str(path))


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _read_regular_json(
    path: Path,
    *,
    maximum_bytes: int,
    missing_ok: bool,
    required_mode: int | None = None,
    required_owner: int | None = None,
    reject_group_world_writable: bool = False,
    directory_fd: int | None = None,
) -> Any:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    open_path: str | Path = path.name if directory_fd is not None else path
    try:
        fd = os.open(open_path, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise GuardError("config_unavailable", EXIT_CONFIG) from None
    except OSError:
        raise GuardError("unsafe_or_unreadable_file", EXIT_CONFIG) from None

    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > maximum_bytes:
            raise GuardError("unsafe_or_invalid_file", EXIT_CONFIG)
        mode = stat.S_IMODE(file_stat.st_mode)
        if required_owner is not None and file_stat.st_uid != required_owner:
            raise GuardError("unsafe_file_owner", EXIT_CONFIG)
        if required_mode is not None and mode != required_mode:
            raise GuardError("unsafe_file_permissions", EXIT_CONFIG)
        if reject_group_world_writable and mode & 0o022:
            raise GuardError("unsafe_file_permissions", EXIT_CONFIG)
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum_bytes:
            raise GuardError("unsafe_or_invalid_file", EXIT_CONFIG)
    finally:
        os.close(fd)

    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GuardError("invalid_json", EXIT_CONFIG) from None


def _load_config(path: Path) -> Config:
    raw = _read_regular_json(
        path,
        maximum_bytes=64 * 1024,
        missing_ok=False,
        required_owner=os.geteuid(),
        reject_group_world_writable=True,
    )
    if not isinstance(raw, dict) or set(raw) != _CONFIG_KEYS:
        raise GuardError("invalid_config_schema", EXIT_CONFIG)
    if (
        not isinstance(raw.get("version"), int)
        or isinstance(raw.get("version"), bool)
        or raw.get("version") != CONFIG_VERSION
    ):
        raise GuardError("unsupported_config_version", EXIT_CONFIG)

    values = (
        raw.get("volume"),
        raw.get("docker_root_dir"),
        raw.get("state_dir"),
        raw.get("lock_file"),
    )
    if not all(isinstance(value, str) and value for value in values):
        raise GuardError("invalid_config_schema", EXIT_CONFIG)

    volume, docker_root_dir, state_dir, lock_file = (Path(value) for value in values)
    if not all(
        _is_normalized_absolute(path_value)
        for path_value in (volume, docker_root_dir, state_dir, lock_file)
    ):
        raise GuardError("invalid_config_path", EXIT_CONFIG)
    if lock_file == state_dir or _path_is_within(lock_file, state_dir):
        raise GuardError("lock_must_be_outside_state_spool", EXIT_CONFIG)

    return Config(
        volume=volume,
        docker_root_dir=docker_root_dir,
        state_dir=state_dir,
        lock_file=lock_file,
    )


def _open_checked_directory(
    path: Path,
    *,
    create: bool,
    required_mode: int | None,
    reject_untrusted_writable: bool,
    unavailable_reason: str,
    unsafe_reason: str,
    owner_reason: str,
    permissions_reason: str,
    exit_code: int,
) -> int | None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    created = False
    try:
        directory_fd = os.open(path, flags)
    except FileNotFoundError:
        if not create:
            return None
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=False)
            created = True
            directory_fd = os.open(path, flags)
        except (FileExistsError, OSError):
            raise GuardError(unavailable_reason, exit_code) from None
    except OSError:
        raise GuardError(unavailable_reason, exit_code) from None

    try:
        metadata = os.fstat(directory_fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise GuardError(unsafe_reason, exit_code)
        if metadata.st_uid != os.geteuid():
            raise GuardError(owner_reason, exit_code)
        if created:
            os.fchmod(directory_fd, 0o700)
            metadata = os.fstat(directory_fd)
        mode = stat.S_IMODE(metadata.st_mode)
        if required_mode is not None and mode != required_mode:
            raise GuardError(permissions_reason, exit_code)
        if reject_untrusted_writable and (
            mode & 0o002 or (mode & 0o020 and metadata.st_gid != os.getegid())
        ):
            raise GuardError(permissions_reason, exit_code)
    except GuardError:
        os.close(directory_fd)
        raise
    except OSError:
        os.close(directory_fd)
        raise GuardError(unavailable_reason, exit_code) from None
    return directory_fd


def _open_secure_state_directory(path: Path, *, create: bool) -> int | None:
    return _open_checked_directory(
        path,
        create=create,
        required_mode=0o700,
        reject_untrusted_writable=True,
        unavailable_reason="state_spool_unavailable",
        unsafe_reason="unsafe_state_spool",
        owner_reason="unsafe_state_spool_owner",
        permissions_reason="unsafe_state_spool_permissions",
        exit_code=EXIT_CONFIG,
    )


def _require_secure_directory(path: Path, *, create: bool) -> None:
    directory_fd = _open_secure_state_directory(path, create=create)
    if directory_fd is not None:
        os.close(directory_fd)


def _prepare_spools(config: Config) -> None:
    _require_secure_directory(config.state_dir, create=True)
    _require_secure_directory(config.alert_dir, create=True)


def _parse_timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise GuardError("invalid_state_schema", EXIT_CONFIG) from None
    if parsed.tzinfo is None:
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    return parsed.astimezone(dt.timezone.utc)


def _read_state(config: Config) -> State | None:
    directory_fd = _open_secure_state_directory(config.state_dir, create=False)
    if directory_fd is None:
        return None
    try:
        raw = _read_regular_json(
            config.state_file,
            maximum_bytes=16 * 1024,
            missing_ok=True,
            required_mode=0o600,
            required_owner=os.geteuid(),
            directory_fd=directory_fd,
        )
    finally:
        os.close(directory_fd)
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != _STATE_KEYS:
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    if raw.get("status") not in _VALID_STATUSES:
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    usage = raw.get("usage_percent")
    if not isinstance(usage, int) or isinstance(usage, bool) or not 0 <= usage <= 100:
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    if not isinstance(raw.get("critical_latched"), bool):
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    _parse_timestamp(raw.get("observed_at"))
    _parse_timestamp(raw.get("last_transition_at"))
    return State(
        status=raw["status"],
        usage_percent=usage,
        critical_latched=raw["critical_latched"],
        observed_at=raw["observed_at"],
        last_transition_at=raw["last_transition_at"],
    )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    directory = path.parent
    directory_fd = _open_secure_state_directory(directory, create=False)
    if directory_fd is None:
        raise GuardError("state_spool_write_failed", EXIT_CONFIG)
    pending_name = f".{path.name}.{os.getpid()}.{secrets.token_hex(12)}.tmp"
    pending_created = False
    file_fd: int | None = None
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        file_fd = os.open(pending_name, flags, 0o600, dir_fd=directory_fd)
        pending_created = True
        os.fchmod(file_fd, 0o600)
        metadata = os.fstat(file_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise OSError(errno.EPERM, "unsafe pending state file")
        handle = os.fdopen(file_fd, "w", encoding="utf-8")
        file_fd = None
        with handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            pending_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        pending_created = False
        os.fsync(directory_fd)
    except OSError:
        raise GuardError("state_spool_write_failed", EXIT_CONFIG) from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if pending_created:
            try:
                os.unlink(pending_name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


@contextlib.contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    parent = path.parent
    parent_fd: int | None = None
    fd: int | None = None
    try:
        parent_fd = _open_checked_directory(
            parent,
            create=True,
            required_mode=None,
            reject_untrusted_writable=True,
            unavailable_reason="lock_unavailable",
            unsafe_reason="lock_directory_unsafe",
            owner_reason="lock_directory_unsafe",
            permissions_reason="lock_directory_unsafe",
            exit_code=EXIT_LOCKED,
        )
        if parent_fd is None:  # pragma: no cover - create=True is exhaustive
            raise GuardError("lock_unavailable", EXIT_LOCKED)
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        lock_created = False
        try:
            fd = os.open(
                path.name,
                flags | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=parent_fd,
            )
            lock_created = True
        except FileExistsError:
            fd = os.open(path.name, flags, dir_fd=parent_fd)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            os.close(fd)
            fd = None
            raise GuardError("lock_unsafe", EXIT_LOCKED)
        if lock_created:
            os.fchmod(fd, 0o600)
            metadata = os.fstat(fd)
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            os.close(fd)
            fd = None
            raise GuardError("lock_unsafe", EXIT_LOCKED)
    except GuardError:
        if fd is not None:
            os.close(fd)
            fd = None
        raise
    except OSError:
        if fd is not None:
            os.close(fd)
            fd = None
        raise GuardError("lock_unavailable", EXIT_LOCKED) from None
    finally:
        if parent_fd is not None:
            os.close(parent_fd)

    if fd is None:  # pragma: no cover - defensive type narrowing
        raise GuardError("lock_unavailable", EXIT_LOCKED)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise GuardError("lock_busy", EXIT_LOCKED) from None
            raise GuardError("lock_unavailable", EXIT_LOCKED) from None
        yield
    finally:
        os.close(fd)


def _observe_usage_percent(volume: Path, docker_root_dir: Path) -> int:
    try:
        if not volume.is_dir() or not os.path.ismount(volume):
            raise GuardError("configured_volume_not_mounted", EXIT_OBSERVATION)
        if not docker_root_dir.is_dir():
            raise GuardError("docker_root_unavailable", EXIT_OBSERVATION)
        if volume.stat().st_dev != docker_root_dir.stat().st_dev:
            raise GuardError("docker_root_backing_mismatch", EXIT_OBSERVATION)
        filesystem = os.statvfs(volume)
    except GuardError:
        raise
    except OSError:
        raise GuardError("filesystem_observation_failed", EXIT_OBSERVATION) from None

    used_blocks = filesystem.f_blocks - filesystem.f_bfree
    user_visible_blocks = used_blocks + filesystem.f_bavail
    if used_blocks < 0 or user_visible_blocks <= 0:
        raise GuardError("invalid_filesystem_observation", EXIT_OBSERVATION)
    usage_percent = math.ceil((used_blocks * 100) / user_visible_blocks)
    if not 0 <= usage_percent <= 100:
        raise GuardError("invalid_filesystem_observation", EXIT_OBSERVATION)
    return usage_percent


def _classify(usage_percent: int, previous_latched: bool) -> tuple[str, bool]:
    if usage_percent >= CRITICAL_PERCENT:
        return "critical", True
    if previous_latched and usage_percent > RECOVERY_PERCENT:
        return "recovering", True
    if usage_percent >= WARNING_PERCENT:
        return "warning", False
    return "healthy", False


def _build_state(
    *,
    previous: State | None,
    status: str,
    usage_percent: int,
    latched: bool,
    now: dt.datetime,
) -> State:
    observed_at = _timestamp(now)
    transitioned = previous is None or previous.status != status
    last_transition_at = (
        observed_at if transitioned or previous is None else previous.last_transition_at
    )
    return State(
        status=status,
        usage_percent=usage_percent,
        critical_latched=latched,
        observed_at=observed_at,
        last_transition_at=last_transition_at,
    )


def _alert_event(previous: State | None, current: State) -> str | None:
    if previous is None:
        return "threshold_crossed" if current.status != "healthy" else None
    if previous.status == current.status:
        return None
    if current.status == "healthy":
        return "resolved"
    if previous.critical_latched and not current.critical_latched:
        return "critical_latch_cleared"
    return "status_transition"


def _result_payload(
    *,
    command: str,
    dry_run: bool,
    result: str,
    reason_code: str,
    state: State,
    state_written: bool,
    alert_written: bool,
) -> dict[str, Any]:
    payload = _base_payload(command, dry_run)
    payload.update(
        {
            "result": result,
            "status": state.status,
            "reason_code": reason_code,
            "usage_percent": state.usage_percent,
            "critical_latched": state.critical_latched,
            "observed_at": state.observed_at,
            "state_written": state_written,
            "alert_written": alert_written,
        }
    )
    return payload


def _state_is_fresh(state: State, now: dt.datetime) -> bool:
    observed_at = _parse_timestamp(state.observed_at)
    age_seconds = (now - observed_at).total_seconds()
    return -60 <= age_seconds <= PREFLIGHT_STATE_MAX_AGE_SECONDS


def _sustainable_target_decision(
    previous: State | None, current: State, now: dt.datetime
) -> tuple[bool, str]:
    if previous is None:
        return False, "monitor_state_missing"
    if not _state_is_fresh(previous, now):
        return False, "monitor_state_stale"
    if previous.usage_percent > RECOVERY_PERCENT or previous.critical_latched:
        return False, "monitor_state_above_recovery_target"
    if current.usage_percent > RECOVERY_PERCENT or current.critical_latched:
        return False, "current_state_above_recovery_target"
    return True, "sustainable_target_met"


def _execute(command: str, config: Config, dry_run: bool) -> int:
    previous = _read_state(config)
    usage_percent = _observe_usage_percent(config.volume, config.docker_root_dir)
    status, latched = _classify(
        usage_percent,
        previous_latched=previous.critical_latched if previous else False,
    )
    now = _utc_now()
    current = _build_state(
        previous=previous,
        status=status,
        usage_percent=usage_percent,
        latched=latched,
        now=now,
    )

    if command == "check":
        alert_event = _alert_event(previous, current)
        state_written = False
        alert_written = False
        if not dry_run:
            _prepare_spools(config)
            _atomic_write_json(config.state_file, current.as_dict())
            state_written = True
            if alert_event is not None:
                alert = {
                    "schema_version": SCHEMA_VERSION,
                    "component": "sealai-disk-guard",
                    "event": alert_event,
                    "external_alert_delivery": EXTERNAL_ALERT_DELIVERY_STATUS,
                    "status": current.status,
                    "usage_percent": current.usage_percent,
                    "observed_at": current.observed_at,
                    "thresholds": _thresholds(),
                }
                _atomic_write_json(config.alert_file, alert)
                alert_written = True

        exit_code = {
            "healthy": EXIT_OK,
            "warning": EXIT_WARNING,
            "critical": EXIT_CRITICAL,
            "recovering": EXIT_CRITICAL,
        }[current.status]
        _emit(
            _result_payload(
                command=command,
                dry_run=dry_run,
                result="ok" if exit_code == EXIT_OK else "attention",
                reason_code=f"usage_{current.status}",
                state=current,
                state_written=state_written,
                alert_written=alert_written,
            )
        )
        return exit_code

    if command == "assert-stable":
        stable, decision_reason = _sustainable_target_decision(previous, current, now)
        _emit(
            _result_payload(
                command=command,
                dry_run=dry_run,
                result="ok" if stable else "blocked",
                reason_code="stable" if stable else decision_reason,
                state=current,
                state_written=False,
                alert_written=False,
            )
        )
        return EXIT_OK if stable else EXIT_ASSERT_UNSTABLE

    if command == "preflight":
        allowed, decision_reason = _sustainable_target_decision(previous, current, now)
        reason_code = "preflight_passed" if allowed else decision_reason
        _emit(
            _result_payload(
                command=command,
                dry_run=dry_run,
                result="ok" if allowed else "blocked",
                reason_code=reason_code,
                state=current,
                state_written=False,
                alert_written=False,
            )
        )
        return EXIT_OK if allowed else EXIT_PREFLIGHT_BLOCKED

    raise GuardError("invalid_command", 64)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Non-destructive Docker disk guard")
    parser.add_argument(
        "--config",
        default="/etc/sealai/disk-guard.json",
        help="path to the disk-guard JSON configuration",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="observe and decide without writing state or alert spools",
    )
    parser.add_argument("command", choices=("check", "assert-stable", "preflight"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    command = str(arguments.command)
    dry_run = bool(arguments.dry_run)
    try:
        config_path = Path(arguments.config)
        if not _is_normalized_absolute(config_path):
            raise GuardError("invalid_config_path", EXIT_CONFIG)
        config = _load_config(config_path)
        with _exclusive_lock(config.lock_file):
            return _execute(command, config, dry_run)
    except GuardError as error:
        _emit(_error_payload(command, dry_run, error.reason_code))
        return error.exit_code
    except Exception:  # pragma: no cover - final fail-closed boundary
        _emit(_error_payload(command, dry_run, "internal_error"))
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
