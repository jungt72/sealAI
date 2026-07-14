#!/usr/bin/env python3
"""Read-only, fail-closed Redis capacity and namespace guard.

The guard speaks a deliberately small RESP2 subset over one exact Unix socket.
It never sends a datastore-mutating command. Raw keys, values, credentials,
prefixes, exception text, and Redis instance identifiers are never emitted or
persisted; only bounded aggregate metrics leave the process.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import errno
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import stat
import struct
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Mapping, Sequence


SCHEMA_VERSION = 2
CONFIG_VERSION = 2
MEMORY_TARGET_PERCENT = 70
MEMORY_WARNING_PERCENT = 75
MEMORY_HARD_DENY_PERCENT = 80
STATE_MAX_AGE_SECONDS = 30 * 60
EXTERNAL_ALERT_DELIVERY_STATUS = "BLOCKED_EXTERNAL"

EXIT_OK = 0
EXIT_ATTENTION = 10
EXIT_DENIED = 20
EXIT_ASSERT_UNSTABLE = 21
EXIT_INTERNAL = 70
EXIT_OBSERVATION = 74
EXIT_LOCKED = 75
EXIT_CONFIG = 78

MAX_INFO_BYTES = 2 * 1024 * 1024
MAX_RESP_LINE_BYTES = 16 * 1024
MAX_RESP_BULK_BYTES = 2 * 1024 * 1024
MAX_RESP_ARRAY_ITEMS = 5_000
MAX_RESP_TOTAL_BYTES = 4 * 1024 * 1024
MAX_RESP_TOTAL_ELEMENTS = 12_000
MAX_RESP_DEPTH = 3
MAX_COMMAND_PART_BYTES = 256 * 1024
MAX_PIPELINE_COMMANDS = 4_000
MAX_REQUEST_TOTAL_BYTES = 4 * 1024 * 1024
MAXIMUM_KEYS_HARD_LIMIT = 300_000

_CONFIG_KEYS = frozenset(
    {
        "version",
        "redis",
        "state_dir",
        "lock_file",
        "scan_count",
        "maximum_keys",
        "categories",
    }
)
_REDIS_KEYS = frozenset(
    {
        "unix_socket_path",
        "expected_socket_uid",
        "expected_socket_gid",
        "expected_socket_mode",
        "expected_peer_uid",
        "expected_peer_gid",
        "expected_run_id_sha256",
        "expected_acl_username_sha256",
        "expected_role",
        "expected_maxmemory_bytes",
        "expected_maxmemory_policy",
        "databases",
        "operation_timeout_ms",
    }
)
_CATEGORY_KEYS = frozenset(
    {
        "id",
        "owner",
        "database",
        "prefixes",
        "expected_types",
        "ttl_policy",
        "kind",
        "max_keys",
        "max_queue_depth",
    }
)
_CREDENTIAL_KEYS = frozenset({"username", "password"})
_STATE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "decision",
        "observed_at",
        "last_transition_at",
        "binding_fingerprint",
        "healthy_sample_count",
        "write_error_total",
        "evicted_keys_total",
    }
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_REDIS_TYPE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VALID_KINDS = frozenset({"cache", "checkpoint", "lock", "queue", "session", "system"})
_VALID_TTL_POLICIES = frozenset({"forbidden", "optional", "required"})
_VALID_STATUSES = frozenset({"healthy", "above_target", "warning", "critical"})
_VALID_MAXMEMORY_POLICIES = frozenset(
    {
        "allkeys-lfu",
        "allkeys-lru",
        "allkeys-random",
        "noeviction",
        "volatile-lfu",
        "volatile-lru",
        "volatile-random",
        "volatile-ttl",
    }
)
_QUEUE_DEPTH_COMMAND = {
    "list": "LLEN",
    "set": "SCARD",
    "stream": "XLEN",
    "zset": "ZCARD",
}
_REQUIRED_ACL_COMMAND_RULES = frozenset(
    {
        "-@all",
        "+acl|getuser",
        "+acl|whoami",
        "+dbsize",
        "+info",
        "+llen",
        "+ping",
        "+pttl",
        "+scan",
        "+scard",
        "+select",
        "+type",
        "+xlen",
        "+zcard",
    }
)

# Commandstats has no authoritative "failed write" aggregate. Failures for
# commands not in this conservative read-only allowlist are treated as
# potential write failures. A newly introduced read command therefore fails
# safe until this code is reviewed, instead of silently masking a writer.
_KNOWN_READ_ONLY_COMMANDSTATS = frozenset(
    {
        "acl|whoami",
        "acl|getuser",
        "auth",
        "command",
        "dbsize",
        "dump",
        "exists",
        "expiretime",
        "get",
        "getbit",
        "getrange",
        "hexists",
        "hget",
        "hgetall",
        "hkeys",
        "hlen",
        "hmget",
        "hscan",
        "hstrlen",
        "hvals",
        "info",
        "json.get",
        "json.mget",
        "json.objkeys",
        "json.objlen",
        "json.strlen",
        "json.type",
        "lindex",
        "llen",
        "lpos",
        "lrange",
        "memory|usage",
        "mget",
        "ping",
        "psubscribe",
        "pttl",
        "pubsub",
        "scan",
        "scard",
        "sdiff",
        "sinter",
        "sismember",
        "smembers",
        "smismember",
        "srandmember",
        "sscan",
        "strlen",
        "subscribe",
        "sunion",
        "time",
        "ttl",
        "type",
        "xinfo",
        "xlen",
        "xpending",
        "xrange",
        "xread",
        "xrevrange",
        "zcard",
        "zcount",
        "zlexcount",
        "zmscore",
        "zrange",
        "zrangebylex",
        "zrangebyscore",
        "zrank",
        "zrevrange",
        "zrevrangebylex",
        "zrevrangebyscore",
        "zrevrank",
        "zscan",
        "zscore",
    }
)


class GuardError(Exception):
    """Expected operational error whose reason is safe to emit."""

    def __init__(self, reason_code: str, exit_code: int) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.exit_code = exit_code


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: ARG002 - argparse API
        _emit(_error_payload("unknown", False, "invalid_arguments"))
        raise SystemExit(64)


@dataclasses.dataclass(frozen=True)
class RedisBinding:
    unix_socket_path: Path
    expected_socket_uid: int
    expected_socket_gid: int
    expected_socket_mode: int
    expected_peer_uid: int
    expected_peer_gid: int
    expected_run_id_sha256: str
    expected_acl_username_sha256: str
    expected_role: str
    expected_maxmemory_bytes: int
    expected_maxmemory_policy: str
    databases: tuple[int, ...]
    operation_timeout_ms: int


@dataclasses.dataclass(frozen=True)
class Category:
    category_id: str
    owner: str
    database: int
    prefixes: tuple[bytes, ...]
    expected_types: frozenset[str]
    ttl_policy: str
    kind: str
    max_keys: int
    max_queue_depth: int | None


@dataclasses.dataclass(frozen=True)
class Config:
    redis: RedisBinding
    state_dir: Path
    lock_file: Path
    scan_count: int
    maximum_keys: int
    categories: tuple[Category, ...]

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
class Credential:
    username: str
    password: str


@dataclasses.dataclass(frozen=True)
class State:
    status: str
    decision: str
    observed_at: str
    last_transition_at: str
    binding_fingerprint: str
    healthy_sample_count: int
    write_error_total: int
    evicted_keys_total: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "decision": self.decision,
            "observed_at": self.observed_at,
            "last_transition_at": self.last_transition_at,
            "binding_fingerprint": self.binding_fingerprint,
            "healthy_sample_count": self.healthy_sample_count,
            "write_error_total": self.write_error_total,
            "evicted_keys_total": self.evicted_keys_total,
        }


@dataclasses.dataclass(frozen=True)
class RuntimeIdentity:
    run_id_sha256: str
    role: str
    acl_contract_sha256: str
    server_version: str


@dataclasses.dataclass
class RespBudget:
    bytes_remaining: int = MAX_RESP_TOTAL_BYTES
    elements_remaining: int = MAX_RESP_TOTAL_ELEMENTS

    def consume_bytes(self, count: int) -> None:
        if count < 0 or count > self.bytes_remaining:
            raise GuardError("redis_response_budget_exceeded", EXIT_OBSERVATION)
        self.bytes_remaining -= count

    def consume_element(self, depth: int) -> None:
        if depth > MAX_RESP_DEPTH or self.elements_remaining <= 0:
            raise GuardError("redis_response_budget_exceeded", EXIT_OBSERVATION)
        self.elements_remaining -= 1


@dataclasses.dataclass
class CategoryAggregate:
    category: Category
    key_count: int = 0
    expiring_count: int = 0
    persistent_count: int = 0
    ttl_total_ms: int = 0
    ttl_min_ms: int | None = None
    ttl_max_ms: int | None = None
    queue_key_count: int = 0
    queue_total_depth: int = 0
    queue_max_depth: int = 0
    unexpected_type_count: int = 0
    ttl_policy_violation_count: int = 0
    queue_depth_violation_count: int = 0
    type_counts: dict[str, int] = dataclasses.field(default_factory=dict)

    def add_ttl(self, ttl_ms: int) -> None:
        if ttl_ms == -1:
            self.persistent_count += 1
            return
        self.expiring_count += 1
        self.ttl_total_ms += ttl_ms
        self.ttl_min_ms = (
            ttl_ms if self.ttl_min_ms is None else min(self.ttl_min_ms, ttl_ms)
        )
        self.ttl_max_ms = (
            ttl_ms if self.ttl_max_ms is None else max(self.ttl_max_ms, ttl_ms)
        )

    def as_payload(self) -> dict[str, Any]:
        ttl_average = (
            self.ttl_total_ms // self.expiring_count if self.expiring_count else None
        )
        return {
            "id": self.category.category_id,
            "owner": self.category.owner,
            "database": self.category.database,
            "kind": self.category.kind,
            "key_count": self.key_count,
            "max_keys": self.category.max_keys,
            "type_counts": dict(sorted(self.type_counts.items())),
            "ttl": {
                "policy": self.category.ttl_policy,
                "expiring_count": self.expiring_count,
                "persistent_count": self.persistent_count,
                "minimum_ms": self.ttl_min_ms,
                "average_ms": ttl_average,
                "maximum_ms": self.ttl_max_ms,
                "violation_count": self.ttl_policy_violation_count,
            },
            "queue": {
                "key_count": self.queue_key_count,
                "total_depth": self.queue_total_depth,
                "maximum_depth": self.queue_max_depth,
                "configured_maximum_depth": self.category.max_queue_depth,
                "violation_count": self.queue_depth_violation_count,
            },
            "unexpected_type_count": self.unexpected_type_count,
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
        "target_percent": MEMORY_TARGET_PERCENT,
        "warning_percent": MEMORY_WARNING_PERCENT,
        "hard_deny_percent": MEMORY_HARD_DENY_PERCENT,
    }


def _base_payload(command: str, dry_run: bool) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "component": "sealai-redis-capacity-guard",
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
            "decision": "deny",
            "reason_codes": [reason_code],
            "redis_instance_binding": "unverified",
            "redis_data_mutated": False,
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
    required_mode: int | frozenset[int] | None,
    reject_group_world_writable: bool,
    directory_fd: int | None = None,
    missing_ok: bool = False,
) -> Any:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    open_path: str | Path = path.name if directory_fd is not None else path
    try:
        file_fd = os.open(open_path, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise GuardError("required_file_unavailable", EXIT_CONFIG) from None
    except OSError:
        raise GuardError("unsafe_or_unreadable_file", EXIT_CONFIG) from None
    try:
        metadata = os.fstat(file_fd)
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_size > maximum_bytes
        ):
            raise GuardError("unsafe_or_invalid_file", EXIT_CONFIG)
        if required_mode is not None:
            allowed_modes = (
                required_mode
                if isinstance(required_mode, frozenset)
                else frozenset({required_mode})
            )
            if mode not in allowed_modes:
                raise GuardError("unsafe_file_permissions", EXIT_CONFIG)
        if reject_group_world_writable and mode & 0o022:
            raise GuardError("unsafe_file_permissions", EXIT_CONFIG)
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(file_fd, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum_bytes:
            raise GuardError("unsafe_or_invalid_file", EXIT_CONFIG)
    finally:
        os.close(file_fd)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GuardError("invalid_json", EXIT_CONFIG) from None


def _require_int(
    value: Any, *, minimum: int, maximum: int, reason: str = "invalid_config_schema"
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise GuardError(reason, EXIT_CONFIG)
    return value


def _validate_hash(value: Any) -> str:
    if not isinstance(value, str) or not _HEX_SHA256.fullmatch(value):
        raise GuardError("invalid_instance_binding", EXIT_CONFIG)
    if value == "0" * 64:
        raise GuardError("placeholder_instance_binding", EXIT_CONFIG)
    return value


def _load_category(raw: Any, databases: tuple[int, ...]) -> Category:
    if not isinstance(raw, dict) or set(raw) != _CATEGORY_KEYS:
        raise GuardError("invalid_category_schema", EXIT_CONFIG)
    category_id = raw.get("id")
    owner = raw.get("owner")
    if (
        not isinstance(category_id, str)
        or not _IDENTIFIER.fullmatch(category_id)
        or not isinstance(owner, str)
        or not _IDENTIFIER.fullmatch(owner)
    ):
        raise GuardError("invalid_category_identity", EXIT_CONFIG)
    database = _require_int(
        raw.get("database"), minimum=0, maximum=15, reason="invalid_category_database"
    )
    if database not in databases:
        raise GuardError("category_database_not_monitored", EXIT_CONFIG)
    prefixes_raw = raw.get("prefixes")
    if (
        not isinstance(prefixes_raw, list)
        or not prefixes_raw
        or len(prefixes_raw) > 32
        or not all(
            isinstance(item, str) and 1 <= len(item.encode()) <= 256
            for item in prefixes_raw
        )
    ):
        raise GuardError("invalid_category_prefixes", EXIT_CONFIG)
    prefixes: list[bytes] = []
    for item in prefixes_raw:
        encoded = item.encode("utf-8")
        if any(byte < 0x20 or byte == 0x7F for byte in encoded):
            raise GuardError("invalid_category_prefixes", EXIT_CONFIG)
        prefixes.append(encoded)
    if len(prefixes) != len(set(prefixes)):
        raise GuardError("duplicate_category_prefix", EXIT_CONFIG)

    types_raw = raw.get("expected_types")
    if (
        not isinstance(types_raw, list)
        or not types_raw
        or len(types_raw) > 16
        or not all(
            isinstance(item, str) and _REDIS_TYPE.fullmatch(item) for item in types_raw
        )
    ):
        raise GuardError("invalid_category_types", EXIT_CONFIG)
    expected_types = frozenset(types_raw)
    if len(expected_types) != len(types_raw):
        raise GuardError("duplicate_category_type", EXIT_CONFIG)

    ttl_policy = raw.get("ttl_policy")
    kind = raw.get("kind")
    if ttl_policy not in _VALID_TTL_POLICIES or kind not in _VALID_KINDS:
        raise GuardError("invalid_category_policy", EXIT_CONFIG)
    max_keys = _require_int(
        raw.get("max_keys"),
        minimum=1,
        maximum=2_000_000,
        reason="invalid_category_limit",
    )
    max_queue_depth_raw = raw.get("max_queue_depth")
    if kind == "queue":
        max_queue_depth = _require_int(
            max_queue_depth_raw,
            minimum=1,
            maximum=100_000_000,
            reason="invalid_queue_limit",
        )
        if not expected_types.issubset(_QUEUE_DEPTH_COMMAND):
            raise GuardError("unsupported_queue_type", EXIT_CONFIG)
    else:
        if max_queue_depth_raw is not None:
            raise GuardError("unexpected_queue_limit", EXIT_CONFIG)
        max_queue_depth = None
    return Category(
        category_id=category_id,
        owner=owner,
        database=database,
        prefixes=tuple(prefixes),
        expected_types=expected_types,
        ttl_policy=ttl_policy,
        kind=kind,
        max_keys=max_keys,
        max_queue_depth=max_queue_depth,
    )


def _load_config(path: Path) -> Config:
    raw = _read_regular_json(
        path,
        maximum_bytes=256 * 1024,
        required_mode=frozenset({0o400, 0o600}),
        reject_group_world_writable=True,
    )
    if not isinstance(raw, dict) or set(raw) != _CONFIG_KEYS:
        raise GuardError("invalid_config_schema", EXIT_CONFIG)
    if raw.get("version") != CONFIG_VERSION or isinstance(raw.get("version"), bool):
        raise GuardError("unsupported_config_version", EXIT_CONFIG)
    redis_raw = raw.get("redis")
    if not isinstance(redis_raw, dict) or set(redis_raw) != _REDIS_KEYS:
        raise GuardError("invalid_redis_binding_schema", EXIT_CONFIG)
    socket_path_raw = redis_raw.get("unix_socket_path")
    if not isinstance(socket_path_raw, str):
        raise GuardError("invalid_redis_socket_path", EXIT_CONFIG)
    socket_path = Path(socket_path_raw)
    if (
        not _is_normalized_absolute(socket_path)
        or len(os.fsencode(socket_path)) > 100
        or any(character in socket_path_raw for character in ("\0", "\n", "\r"))
    ):
        raise GuardError("invalid_redis_socket_path", EXIT_CONFIG)
    databases_raw = redis_raw.get("databases")
    if (
        not isinstance(databases_raw, list)
        or not databases_raw
        or len(databases_raw) > 16
        or not all(
            isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 15
            for item in databases_raw
        )
    ):
        raise GuardError("invalid_database_set", EXIT_CONFIG)
    databases = tuple(sorted(databases_raw))
    if len(databases) != len(set(databases)):
        raise GuardError("duplicate_database", EXIT_CONFIG)
    expected_role = redis_raw.get("expected_role")
    if expected_role not in {"master", "slave"}:
        raise GuardError("invalid_expected_role", EXIT_CONFIG)
    expected_policy = redis_raw.get("expected_maxmemory_policy")
    if expected_policy not in _VALID_MAXMEMORY_POLICIES:
        raise GuardError("invalid_expected_maxmemory_policy", EXIT_CONFIG)
    expected_socket_mode = _require_int(
        redis_raw.get("expected_socket_mode"),
        minimum=0o600,
        maximum=0o770,
        reason="invalid_redis_socket_mode",
    )
    if expected_socket_mode & 0o007:
        raise GuardError("unsafe_redis_socket_mode", EXIT_CONFIG)
    binding = RedisBinding(
        unix_socket_path=socket_path,
        expected_socket_uid=_require_int(
            redis_raw.get("expected_socket_uid"),
            minimum=0,
            maximum=2**31 - 1,
            reason="invalid_redis_socket_identity",
        ),
        expected_socket_gid=_require_int(
            redis_raw.get("expected_socket_gid"),
            minimum=0,
            maximum=2**31 - 1,
            reason="invalid_redis_socket_identity",
        ),
        expected_socket_mode=expected_socket_mode,
        expected_peer_uid=_require_int(
            redis_raw.get("expected_peer_uid"),
            minimum=0,
            maximum=2**31 - 1,
            reason="invalid_redis_peer_identity",
        ),
        expected_peer_gid=_require_int(
            redis_raw.get("expected_peer_gid"),
            minimum=0,
            maximum=2**31 - 1,
            reason="invalid_redis_peer_identity",
        ),
        expected_run_id_sha256=_validate_hash(redis_raw.get("expected_run_id_sha256")),
        expected_acl_username_sha256=_validate_hash(
            redis_raw.get("expected_acl_username_sha256")
        ),
        expected_role=expected_role,
        expected_maxmemory_bytes=_require_int(
            redis_raw.get("expected_maxmemory_bytes"),
            minimum=1,
            maximum=2**63 - 1,
            reason="invalid_expected_maxmemory",
        ),
        expected_maxmemory_policy=expected_policy,
        databases=databases,
        operation_timeout_ms=_require_int(
            redis_raw.get("operation_timeout_ms"),
            minimum=100,
            maximum=60_000,
            reason="invalid_redis_timeout",
        ),
    )
    state_dir_raw = raw.get("state_dir")
    lock_file_raw = raw.get("lock_file")
    if not isinstance(state_dir_raw, str) or not isinstance(lock_file_raw, str):
        raise GuardError("invalid_config_path", EXIT_CONFIG)
    state_dir = Path(state_dir_raw)
    lock_file = Path(lock_file_raw)
    if not _is_normalized_absolute(state_dir) or not _is_normalized_absolute(lock_file):
        raise GuardError("invalid_config_path", EXIT_CONFIG)
    if lock_file == state_dir or _path_is_within(lock_file, state_dir):
        raise GuardError("lock_must_be_outside_state_spool", EXIT_CONFIG)
    categories_raw = raw.get("categories")
    if (
        not isinstance(categories_raw, list)
        or not categories_raw
        or len(categories_raw) > 128
    ):
        raise GuardError("invalid_categories", EXIT_CONFIG)
    categories = tuple(_load_category(item, databases) for item in categories_raw)
    if len({item.category_id for item in categories}) != len(categories):
        raise GuardError("duplicate_category_identity", EXIT_CONFIG)
    if {item.database for item in categories} != set(databases):
        raise GuardError("database_without_category", EXIT_CONFIG)
    for index, category in enumerate(categories):
        for other in categories[index + 1 :]:
            if category.database != other.database:
                continue
            for prefix in category.prefixes:
                for other_prefix in other.prefixes:
                    if prefix.startswith(other_prefix) or other_prefix.startswith(
                        prefix
                    ):
                        raise GuardError("overlapping_category_prefixes", EXIT_CONFIG)
    return Config(
        redis=binding,
        state_dir=state_dir,
        lock_file=lock_file,
        scan_count=_require_int(
            raw.get("scan_count"),
            minimum=10,
            maximum=2_000,
            reason="invalid_scan_count",
        ),
        maximum_keys=_require_int(
            raw.get("maximum_keys"),
            minimum=1,
            maximum=MAXIMUM_KEYS_HARD_LIMIT,
            reason="invalid_maximum_keys",
        ),
        categories=tuple(sorted(categories, key=lambda item: item.category_id)),
    )


def _load_credential(path: Path, expected_username_hash: str) -> Credential:
    raw = _read_regular_json(
        path,
        maximum_bytes=8 * 1024,
        required_mode=frozenset({0o400, 0o600}),
        reject_group_world_writable=True,
    )
    if not isinstance(raw, dict) or set(raw) != _CREDENTIAL_KEYS:
        raise GuardError("invalid_credential_schema", EXIT_CONFIG)
    username = raw.get("username")
    password = raw.get("password")
    if (
        not isinstance(username, str)
        or not _IDENTIFIER.fullmatch(username)
        or username == "default"
        or not isinstance(password, str)
        or not 16 <= len(password.encode("utf-8")) <= 4096
    ):
        raise GuardError("invalid_credential", EXIT_CONFIG)
    actual = hashlib.sha256(username.encode()).hexdigest()
    if not hmac.compare_digest(actual, expected_username_hash):
        raise GuardError("acl_identity_binding_mismatch", EXIT_CONFIG)
    return Credential(username=username, password=password)


def _open_checked_directory(
    path: Path,
    *,
    create: bool,
    required_mode: int | None,
    exit_code: int,
    reason: str,
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
            raise GuardError(reason, exit_code) from None
    except OSError:
        raise GuardError(reason, exit_code) from None
    try:
        metadata = os.fstat(directory_fd)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise GuardError(reason, exit_code)
        if created:
            os.fchmod(directory_fd, 0o700)
            metadata = os.fstat(directory_fd)
        mode = stat.S_IMODE(metadata.st_mode)
        if required_mode is not None and mode != required_mode:
            raise GuardError(reason, exit_code)
        if mode & 0o002 or (mode & 0o020 and metadata.st_gid != os.getegid()):
            raise GuardError(reason, exit_code)
    except GuardError:
        os.close(directory_fd)
        raise
    except OSError:
        os.close(directory_fd)
        raise GuardError(reason, exit_code) from None
    return directory_fd


def _open_state_directory(path: Path, *, create: bool) -> int | None:
    return _open_checked_directory(
        path,
        create=create,
        required_mode=0o700,
        exit_code=EXIT_CONFIG,
        reason="unsafe_state_spool",
    )


def _prepare_spools(config: Config) -> None:
    for directory in (config.state_dir, config.alert_dir):
        directory_fd = _open_state_directory(directory, create=True)
        if directory_fd is not None:
            os.close(directory_fd)


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
    directory_fd = _open_state_directory(config.state_dir, create=False)
    if directory_fd is None:
        return None
    try:
        raw = _read_regular_json(
            config.state_file,
            maximum_bytes=16 * 1024,
            required_mode=0o600,
            reject_group_world_writable=True,
            directory_fd=directory_fd,
            missing_ok=True,
        )
    finally:
        os.close(directory_fd)
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != _STATE_KEYS:
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    status = raw.get("status")
    decision = raw.get("decision")
    binding_fingerprint = raw.get("binding_fingerprint")
    healthy_sample_count = raw.get("healthy_sample_count")
    write_error_total = raw.get("write_error_total")
    evicted_keys_total = raw.get("evicted_keys_total")
    if (
        status not in _VALID_STATUSES
        or decision not in {"observe", "deny"}
        or not isinstance(binding_fingerprint, str)
        or not _HEX_SHA256.fullmatch(binding_fingerprint)
        or not isinstance(healthy_sample_count, int)
        or isinstance(healthy_sample_count, bool)
        or not 0 <= healthy_sample_count <= 2
        or not isinstance(write_error_total, int)
        or isinstance(write_error_total, bool)
        or write_error_total < 0
        or not isinstance(evicted_keys_total, int)
        or isinstance(evicted_keys_total, bool)
        or evicted_keys_total < 0
    ):
        raise GuardError("invalid_state_schema", EXIT_CONFIG)
    _parse_timestamp(raw.get("observed_at"))
    _parse_timestamp(raw.get("last_transition_at"))
    return State(
        status=status,
        decision=decision,
        observed_at=raw["observed_at"],
        last_transition_at=raw["last_transition_at"],
        binding_fingerprint=binding_fingerprint,
        healthy_sample_count=healthy_sample_count,
        write_error_total=write_error_total,
        evicted_keys_total=evicted_keys_total,
    )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    directory_fd = _open_state_directory(path.parent, create=False)
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
            raise OSError(errno.EPERM, "unsafe pending spool")
        handle = os.fdopen(file_fd, "w", encoding="utf-8")
        file_fd = None
        with handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            pending_name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd
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
    parent_fd: int | None = None
    lock_fd: int | None = None
    try:
        parent_fd = _open_checked_directory(
            path.parent,
            create=True,
            required_mode=None,
            exit_code=EXIT_LOCKED,
            reason="unsafe_lock_directory",
        )
        if parent_fd is None:  # pragma: no cover - create=True is exhaustive
            raise GuardError("lock_unavailable", EXIT_LOCKED)
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        created = False
        try:
            lock_fd = os.open(
                path.name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd
            )
            created = True
        except FileExistsError:
            lock_fd = os.open(path.name, flags, dir_fd=parent_fd)
        metadata = os.fstat(lock_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise GuardError("unsafe_lock_file", EXIT_LOCKED)
        if created:
            os.fchmod(lock_fd, 0o600)
            metadata = os.fstat(lock_fd)
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise GuardError("unsafe_lock_file", EXIT_LOCKED)
    except GuardError:
        if lock_fd is not None:
            os.close(lock_fd)
            lock_fd = None
        raise
    except OSError:
        if lock_fd is not None:
            os.close(lock_fd)
            lock_fd = None
        raise GuardError("lock_unavailable", EXIT_LOCKED) from None
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
    if lock_fd is None:  # pragma: no cover - defensive narrowing
        raise GuardError("lock_unavailable", EXIT_LOCKED)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise GuardError("lock_busy", EXIT_LOCKED) from None
            raise GuardError("lock_unavailable", EXIT_LOCKED) from None
        yield
    finally:
        os.close(lock_fd)


def _validated_socket_identity(binding: RedisBinding) -> tuple[int, int, int, int, int]:
    try:
        metadata = binding.unix_socket_path.lstat()
    except OSError:
        raise GuardError("redis_socket_unavailable", EXIT_OBSERVATION) from None
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != binding.expected_socket_uid
        or metadata.st_gid != binding.expected_socket_gid
        or mode != binding.expected_socket_mode
    ):
        raise GuardError("redis_socket_identity_mismatch", EXIT_OBSERVATION)
    path_only = getattr(os, "O_PATH", None)
    if path_only is None:
        raise GuardError("redis_socket_fstat_unsupported", EXIT_OBSERVATION)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            binding.unix_socket_path,
            path_only | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
    except OSError:
        raise GuardError("redis_socket_fstat_failed", EXIT_OBSERVATION) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    opened_identity = (
        opened.st_dev,
        opened.st_ino,
        opened.st_uid,
        opened.st_gid,
        stat.S_IMODE(opened.st_mode),
    )
    lexical_identity = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        metadata.st_gid,
        mode,
    )
    if not stat.S_ISSOCK(opened.st_mode) or opened_identity != lexical_identity:
        raise GuardError("redis_socket_lstat_fstat_mismatch", EXIT_OBSERVATION)
    return lexical_identity


def _verify_peer_credentials(connection: socket.socket, binding: RedisBinding) -> None:
    peercred_option = getattr(socket, "SO_PEERCRED", None)
    if peercred_option is None:
        raise GuardError("redis_peer_credentials_unsupported", EXIT_OBSERVATION)
    credential_size = struct.calcsize("3i")
    try:
        raw = connection.getsockopt(socket.SOL_SOCKET, peercred_option, credential_size)
        if not isinstance(raw, bytes) or len(raw) != credential_size:
            raise OSError(errno.EPROTO, "unexpected peer credential size")
        peer_pid, peer_uid, peer_gid = struct.unpack("3i", raw)
    except (OSError, struct.error):
        raise GuardError(
            "redis_peer_credentials_unavailable", EXIT_OBSERVATION
        ) from None
    if (
        peer_pid <= 1
        or peer_uid != binding.expected_peer_uid
        or peer_gid != binding.expected_peer_gid
    ):
        raise GuardError("redis_peer_identity_mismatch", EXIT_OBSERVATION)


class RedisReadOnlyClient:
    """Minimal RESP2 client with an immutable read-only command boundary."""

    _SINGLE_COMMANDS = frozenset(
        {
            "AUTH",
            "DBSIZE",
            "INFO",
            "LLEN",
            "PING",
            "PTTL",
            "SCAN",
            "SCARD",
            "SELECT",
            "TYPE",
            "XLEN",
            "ZCARD",
        }
    )

    def __init__(self, binding: RedisBinding) -> None:
        self._binding = binding
        self._socket: socket.socket | None = None
        self._reader: BinaryIO | None = None

    def __enter__(self) -> RedisReadOnlyClient:
        try:
            before = _validated_socket_identity(self._binding)
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket = connection
            connection.settimeout(self._binding.operation_timeout_ms / 1000)
            connection.connect(str(self._binding.unix_socket_path))
            connected_metadata = os.fstat(connection.fileno())
            if not stat.S_ISSOCK(connected_metadata.st_mode):
                raise GuardError("redis_connected_descriptor_invalid", EXIT_OBSERVATION)
            after = _validated_socket_identity(self._binding)
            if before != after:
                raise GuardError(
                    "redis_socket_changed_during_connect", EXIT_OBSERVATION
                )
            _verify_peer_credentials(connection, self._binding)
            self._reader = connection.makefile("rb")
            return self
        except GuardError:
            self.close()
            raise
        except OSError:
            self.close()
            raise GuardError("redis_connection_failed", EXIT_OBSERVATION) from None

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._reader is not None:
            try:
                self._reader.close()
            except OSError:
                pass
            self._reader = None
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    @classmethod
    def _validate_command(cls, parts: Sequence[bytes | str | int]) -> None:
        if not parts or not isinstance(parts[0], (bytes, str)):
            raise GuardError("internal_command_boundary_violation", EXIT_INTERNAL)
        first = (
            parts[0].decode("ascii", "strict")
            if isinstance(parts[0], bytes)
            else parts[0]
        )
        command = first.upper()
        if command == "ACL":
            subcommand = (
                parts[1].decode("ascii", "strict")
                if len(parts) > 1 and isinstance(parts[1], bytes)
                else str(parts[1])
                if len(parts) > 1
                else ""
            ).upper()
            valid_whoami = subcommand == "WHOAMI" and len(parts) == 2
            valid_getuser = subcommand == "GETUSER" and len(parts) == 3
            if not valid_whoami and not valid_getuser:
                raise GuardError("internal_command_boundary_violation", EXIT_INTERNAL)
            return
        if command not in cls._SINGLE_COMMANDS:
            raise GuardError("internal_command_boundary_violation", EXIT_INTERNAL)

    @staticmethod
    def _encode(parts: Sequence[bytes | str | int]) -> bytes:
        encoded: list[bytes] = []
        for item in parts:
            if isinstance(item, bytes):
                value = item
            elif isinstance(item, str):
                value = item.encode("utf-8")
            elif isinstance(item, int) and not isinstance(item, bool):
                value = str(item).encode("ascii")
            else:
                raise GuardError("internal_command_encoding_error", EXIT_INTERNAL)
            if len(value) > MAX_COMMAND_PART_BYTES:
                raise GuardError("redis_command_part_too_large", EXIT_OBSERVATION)
            encoded.append(value)
        output = [f"*{len(encoded)}\r\n".encode()]
        for value in encoded:
            output.extend((f"${len(value)}\r\n".encode(), value, b"\r\n"))
        return b"".join(output)

    def _send(self, payload: bytes) -> None:
        if self._socket is None:
            raise GuardError("redis_connection_unavailable", EXIT_OBSERVATION)
        try:
            self._socket.sendall(payload)
        except OSError:
            raise GuardError("redis_transport_failed", EXIT_OBSERVATION) from None

    def _readline(self, budget: RespBudget) -> bytes:
        if self._reader is None:
            raise GuardError("redis_connection_unavailable", EXIT_OBSERVATION)
        try:
            line = self._reader.readline(MAX_RESP_LINE_BYTES + 1)
        except OSError:
            raise GuardError("redis_transport_failed", EXIT_OBSERVATION) from None
        if not line or len(line) > MAX_RESP_LINE_BYTES or not line.endswith(b"\r\n"):
            raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION)
        budget.consume_bytes(len(line))
        return line[:-2]

    def _read_exact(self, length: int, budget: RespBudget) -> bytes:
        if self._reader is None:
            raise GuardError("redis_connection_unavailable", EXIT_OBSERVATION)
        try:
            raw = self._reader.read(length)
        except OSError:
            raise GuardError("redis_transport_failed", EXIT_OBSERVATION) from None
        if raw is None or len(raw) != length:
            raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION)
        budget.consume_bytes(length)
        return raw

    def _read_response(self, budget: RespBudget, *, depth: int = 0) -> Any:
        budget.consume_element(depth)
        line = self._readline(budget)
        if not line:
            raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION)
        marker, payload = line[:1], line[1:]
        if marker == b"+":
            return payload
        if marker == b"-":
            raise GuardError("redis_command_rejected", EXIT_OBSERVATION)
        if marker == b":":
            try:
                return int(payload)
            except ValueError:
                raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION) from None
        if marker == b"$":
            try:
                length = int(payload)
            except ValueError:
                raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION) from None
            if length == -1:
                return None
            if not 0 <= length <= MAX_RESP_BULK_BYTES:
                raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION)
            raw = self._read_exact(length + 2, budget)
            if not raw.endswith(b"\r\n"):
                raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION)
            return raw[:-2]
        if marker == b"*":
            try:
                count = int(payload)
            except ValueError:
                raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION) from None
            if count == -1:
                return None
            if not 0 <= count <= MAX_RESP_ARRAY_ITEMS:
                raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION)
            return [self._read_response(budget, depth=depth + 1) for _ in range(count)]
        raise GuardError("invalid_redis_protocol", EXIT_OBSERVATION)

    def command(self, *parts: bytes | str | int) -> Any:
        self._validate_command(parts)
        payload = self._encode(parts)
        if len(payload) > MAX_REQUEST_TOTAL_BYTES:
            raise GuardError("redis_request_budget_exceeded", EXIT_OBSERVATION)
        self._send(payload)
        return self._read_response(RespBudget())

    def pipeline(self, commands: Sequence[Sequence[bytes | str | int]]) -> list[Any]:
        if not commands or len(commands) > MAX_PIPELINE_COMMANDS:
            raise GuardError("invalid_redis_pipeline", EXIT_INTERNAL)
        encoded: list[bytes] = []
        total_bytes = 0
        for command in commands:
            self._validate_command(command)
            payload = self._encode(command)
            total_bytes += len(payload)
            if total_bytes > MAX_REQUEST_TOTAL_BYTES:
                raise GuardError("redis_request_budget_exceeded", EXIT_OBSERVATION)
            encoded.append(payload)
        self._send(b"".join(encoded))
        budget = RespBudget()
        return [self._read_response(budget) for _ in commands]


def _as_bytes(value: Any, reason: str = "unexpected_redis_response") -> bytes:
    if not isinstance(value, bytes):
        raise GuardError(reason, EXIT_OBSERVATION)
    return value


def _as_int(value: Any, reason: str = "unexpected_redis_response") -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GuardError(reason, EXIT_OBSERVATION)
    return value


def _expect_ok(value: Any) -> None:
    if _as_bytes(value).upper() != b"OK":
        raise GuardError("unexpected_redis_response", EXIT_OBSERVATION)


def _parse_info(value: Any) -> dict[str, str]:
    raw = _as_bytes(value)
    if len(raw) > MAX_INFO_BYTES:
        raise GuardError("redis_info_too_large", EXIT_OBSERVATION)
    parsed: dict[str, str] = {}
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise GuardError("invalid_redis_info", EXIT_OBSERVATION) from None
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, item = line.partition(":")
        if not separator or not key or key in parsed:
            raise GuardError("invalid_redis_info", EXIT_OBSERVATION)
        parsed[key] = item
    return parsed


def _info_int(info: Mapping[str, str], key: str) -> int:
    value = info.get(key)
    try:
        parsed = int(value) if value is not None else -1
    except ValueError:
        raise GuardError("invalid_redis_metric", EXIT_OBSERVATION) from None
    if parsed < 0:
        raise GuardError("missing_redis_metric", EXIT_OBSERVATION)
    return parsed


def _verify_identity(
    client: RedisReadOnlyClient,
    binding: RedisBinding,
    credential: Credential,
) -> RuntimeIdentity:
    _expect_ok(client.command("AUTH", credential.username, credential.password))
    if _as_bytes(client.command("PING")).upper() != b"PONG":
        raise GuardError("redis_ping_failed", EXIT_OBSERVATION)
    whoami = _as_bytes(client.command("ACL", "WHOAMI"))
    if not hmac.compare_digest(whoami, credential.username.encode()):
        raise GuardError("redis_acl_identity_mismatch", EXIT_OBSERVATION)
    acl_contract_sha256 = _verify_acl_contract(
        client.command("ACL", "GETUSER", credential.username)
    )
    server = _parse_info(client.command("INFO", "server"))
    replication = _parse_info(client.command("INFO", "replication"))
    run_id = server.get("run_id")
    server_version = server.get("redis_version")
    role = replication.get("role")
    if run_id is None or server_version is None or role is None:
        raise GuardError("missing_instance_identity", EXIT_OBSERVATION)
    try:
        run_id_bytes = run_id.encode("ascii", "strict")
    except UnicodeEncodeError:
        raise GuardError("invalid_instance_identity", EXIT_OBSERVATION) from None
    actual_hash = hashlib.sha256(run_id_bytes).hexdigest()
    if not hmac.compare_digest(actual_hash, binding.expected_run_id_sha256):
        raise GuardError("redis_instance_binding_mismatch", EXIT_OBSERVATION)
    if not hmac.compare_digest(role, binding.expected_role):
        raise GuardError("redis_role_binding_mismatch", EXIT_OBSERVATION)
    if not re.fullmatch(r"[0-9A-Za-z_.-]{1,64}", server_version):
        raise GuardError("invalid_instance_identity", EXIT_OBSERVATION)
    return RuntimeIdentity(
        run_id_sha256=actual_hash,
        role=role,
        acl_contract_sha256=acl_contract_sha256,
        server_version=server_version,
    )


def _decode_acl_items(value: Any, reason: str) -> list[bytes]:
    if not isinstance(value, list) or not all(
        isinstance(item, bytes) for item in value
    ):
        raise GuardError(reason, EXIT_OBSERVATION)
    return value


def _verify_acl_contract(value: Any) -> str:
    """Require an exact named read-only ACL before any inventory command."""
    if not isinstance(value, list) or len(value) % 2:
        raise GuardError("invalid_redis_acl_contract", EXIT_OBSERVATION)
    fields: dict[bytes, Any] = {}
    for index in range(0, len(value), 2):
        name = value[index]
        if not isinstance(name, bytes) or name in fields:
            raise GuardError("invalid_redis_acl_contract", EXIT_OBSERVATION)
        fields[name] = value[index + 1]
    expected_fields = {
        b"flags",
        b"passwords",
        b"commands",
        b"keys",
        b"channels",
        b"selectors",
    }
    if set(fields) != expected_fields:
        raise GuardError("invalid_redis_acl_contract", EXIT_OBSERVATION)
    flags = set(_decode_acl_items(fields[b"flags"], "invalid_redis_acl_contract"))
    passwords = _decode_acl_items(fields[b"passwords"], "invalid_redis_acl_contract")
    keys = _decode_acl_items(fields[b"keys"], "invalid_redis_acl_contract")
    channels = _decode_acl_items(fields[b"channels"], "invalid_redis_acl_contract")
    selectors = fields[b"selectors"]
    commands_raw = fields[b"commands"]
    if (
        b"on" not in flags
        or b"off" in flags
        or b"nopass" in flags
        or not passwords
        or not all(password for password in passwords)
        or keys != [b"%R~*"]
        or channels
        or selectors != []
        or not isinstance(commands_raw, bytes)
    ):
        raise GuardError("redis_acl_not_strictly_read_only", EXIT_OBSERVATION)
    try:
        command_rules = commands_raw.decode("ascii").split()
    except UnicodeDecodeError:
        raise GuardError("invalid_redis_acl_contract", EXIT_OBSERVATION) from None
    if (
        len(command_rules) != len(set(command_rules))
        or set(command_rules) != _REQUIRED_ACL_COMMAND_RULES
    ):
        raise GuardError("redis_acl_not_strictly_read_only", EXIT_OBSERVATION)
    try:
        contract = {
            "flags": sorted(item.decode("ascii", "strict") for item in flags),
            "password_count": len(passwords),
            "command_rules": sorted(command_rules),
            "key_rules": [item.decode("ascii", "strict") for item in keys],
            "channel_rule_count": len(channels),
            "selector_count": len(selectors),
        }
    except UnicodeDecodeError:
        raise GuardError("invalid_redis_acl_contract", EXIT_OBSERVATION) from None
    return hashlib.sha256(
        json.dumps(
            contract, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def _binding_fingerprint(
    config: Config,
    identity: RuntimeIdentity,
    maxmemory_policy: str,
) -> str:
    material = {
        "binding_schema_version": SCHEMA_VERSION,
        "config_version": CONFIG_VERSION,
        "fixed_thresholds": _thresholds(),
        "redis": {
            "unix_socket_path": str(config.redis.unix_socket_path),
            "expected_socket_uid": config.redis.expected_socket_uid,
            "expected_socket_gid": config.redis.expected_socket_gid,
            "expected_socket_mode": config.redis.expected_socket_mode,
            "expected_peer_uid": config.redis.expected_peer_uid,
            "expected_peer_gid": config.redis.expected_peer_gid,
            "run_id_sha256": identity.run_id_sha256,
            "acl_username_sha256": config.redis.expected_acl_username_sha256,
            "acl_contract_sha256": identity.acl_contract_sha256,
            "role": identity.role,
            "server_version": identity.server_version,
            "maxmemory_bytes": config.redis.expected_maxmemory_bytes,
            "maxmemory_policy": maxmemory_policy,
            "databases": list(config.redis.databases),
            "operation_timeout_ms": config.redis.operation_timeout_ms,
        },
        "state_dir": str(config.state_dir),
        "lock_file": str(config.lock_file),
        "scan_count": config.scan_count,
        "maximum_keys": config.maximum_keys,
        "categories": [
            {
                "id": category.category_id,
                "owner": category.owner,
                "database": category.database,
                "prefix_hex": sorted(prefix.hex() for prefix in category.prefixes),
                "expected_types": sorted(category.expected_types),
                "ttl_policy": category.ttl_policy,
                "kind": category.kind,
                "max_keys": category.max_keys,
                "max_queue_depth": category.max_queue_depth,
            }
            for category in config.categories
        ],
    }
    return hashlib.sha256(
        json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def _parse_keyspace(info: Mapping[str, str]) -> dict[int, dict[str, int]]:
    parsed: dict[int, dict[str, int]] = {}
    for key, raw in info.items():
        if not key.startswith("db") or not key[2:].isdigit():
            continue
        database = int(key[2:])
        fields: dict[str, int] = {}
        for item in raw.split(","):
            name, separator, value = item.partition("=")
            if not separator:
                raise GuardError("invalid_keyspace_metric", EXIT_OBSERVATION)
            try:
                fields[name] = int(value)
            except ValueError:
                raise GuardError("invalid_keyspace_metric", EXIT_OBSERVATION) from None
        if "keys" not in fields or "expires" not in fields or min(fields.values()) < 0:
            raise GuardError("invalid_keyspace_metric", EXIT_OBSERVATION)
        parsed[database] = fields
    return parsed


def _command_error_metrics(info: Mapping[str, str]) -> tuple[int, int, int]:
    potential_write_errors = 0
    failed_read_calls = 0
    unclear_failed_commands = 0
    for key, raw in info.items():
        if not key.startswith("cmdstat_"):
            continue
        command_name = key.removeprefix("cmdstat_")
        fields: dict[str, int] = {}
        for item in raw.split(","):
            name, separator, value = item.partition("=")
            if not separator or name == "usec_per_call":
                continue
            try:
                fields[name] = int(value)
            except ValueError:
                raise GuardError(
                    "invalid_commandstats_metric", EXIT_OBSERVATION
                ) from None
        errors = fields.get("failed_calls", 0) + fields.get("rejected_calls", 0)
        if errors < 0:
            raise GuardError("invalid_commandstats_metric", EXIT_OBSERVATION)
        if not errors:
            continue
        if command_name in _KNOWN_READ_ONLY_COMMANDSTATS:
            failed_read_calls += errors
        else:
            potential_write_errors += errors
            unclear_failed_commands += 1
    return potential_write_errors, failed_read_calls, unclear_failed_commands


def _classify_key(config: Config, database: int, key: bytes) -> Category | None:
    matched: Category | None = None
    for category in config.categories:
        if category.database != database:
            continue
        if any(key.startswith(prefix) for prefix in category.prefixes):
            if matched is not None:  # pragma: no cover - config rejects overlaps
                raise GuardError("ambiguous_key_category", EXIT_OBSERVATION)
            matched = category
    return matched


def _pipeline_in_chunks(
    client: RedisReadOnlyClient,
    commands: Sequence[Sequence[bytes | str | int]],
    *,
    maximum_chunk_commands: int = MAX_PIPELINE_COMMANDS,
) -> list[Any]:
    responses: list[Any] = []
    for offset in range(0, len(commands), maximum_chunk_commands):
        responses.extend(
            client.pipeline(commands[offset : offset + maximum_chunk_commands])
        )
    return responses


def _scan_database(
    client: RedisReadOnlyClient,
    config: Config,
    database: int,
    aggregates: Mapping[str, CategoryAggregate],
    seen: set[bytes],
    reasons: set[str],
) -> tuple[int, int, int, int, int, int, int]:
    _expect_ok(client.command("SELECT", database))
    before_count = _as_int(client.command("DBSIZE"))
    cursor = b"0"
    scanned = 0
    expiring = 0
    persistent = 0
    ttl_total = 0
    ttl_min: int | None = None
    ttl_max: int | None = None
    unknown = 0
    while True:
        response = client.command("SCAN", cursor, "COUNT", config.scan_count)
        if not isinstance(response, list) or len(response) != 2:
            raise GuardError("invalid_scan_response", EXIT_OBSERVATION)
        cursor = _as_bytes(response[0], "invalid_scan_response")
        keys = response[1]
        if not isinstance(keys, list) or not all(
            isinstance(key, bytes) for key in keys
        ):
            raise GuardError("invalid_scan_response", EXIT_OBSERVATION)
        unique_keys: list[bytes] = []
        categories: list[Category | None] = []
        for key in keys:
            digest = hashlib.sha256(database.to_bytes(1, "big") + b"\0" + key).digest()
            if digest in seen:
                continue
            seen.add(digest)
            scanned += 1
            if scanned > config.maximum_keys or len(seen) > config.maximum_keys:
                raise GuardError("scan_key_limit_exceeded", EXIT_OBSERVATION)
            unique_keys.append(key)
            categories.append(_classify_key(config, database, key))
        if unique_keys:
            commands: list[tuple[bytes | str | int, ...]] = []
            for key in unique_keys:
                commands.extend((("TYPE", key), ("PTTL", key)))
            metadata = _pipeline_in_chunks(client, commands)
            queue_commands: list[tuple[bytes | str | int, ...]] = []
            queue_targets: list[CategoryAggregate] = []
            for index, (key, category) in enumerate(
                zip(unique_keys, categories, strict=True)
            ):
                key_type_raw = _as_bytes(metadata[index * 2])
                try:
                    key_type = key_type_raw.decode("ascii")
                except UnicodeDecodeError:
                    raise GuardError("invalid_key_type", EXIT_OBSERVATION) from None
                ttl_ms = _as_int(metadata[index * 2 + 1])
                if key_type == "none" or ttl_ms == -2:
                    reasons.add("concurrent_keyspace_change")
                    continue
                if ttl_ms < -1:
                    raise GuardError("invalid_ttl_metric", EXIT_OBSERVATION)
                if ttl_ms == -1:
                    persistent += 1
                else:
                    expiring += 1
                    ttl_total += ttl_ms
                    ttl_min = ttl_ms if ttl_min is None else min(ttl_min, ttl_ms)
                    ttl_max = ttl_ms if ttl_max is None else max(ttl_max, ttl_ms)
                if category is None:
                    unknown += 1
                    continue
                aggregate = aggregates[category.category_id]
                aggregate.key_count += 1
                aggregate.type_counts[key_type] = (
                    aggregate.type_counts.get(key_type, 0) + 1
                )
                aggregate.add_ttl(ttl_ms)
                if key_type not in category.expected_types:
                    aggregate.unexpected_type_count += 1
                    reasons.add("unexpected_key_type")
                if category.ttl_policy == "required" and ttl_ms == -1:
                    aggregate.ttl_policy_violation_count += 1
                    reasons.add("ttl_policy_violation")
                if category.ttl_policy == "forbidden" and ttl_ms >= 0:
                    aggregate.ttl_policy_violation_count += 1
                    reasons.add("ttl_policy_violation")
                if category.kind == "queue" and key_type in _QUEUE_DEPTH_COMMAND:
                    queue_commands.append((_QUEUE_DEPTH_COMMAND[key_type], key))
                    queue_targets.append(aggregate)
            if queue_commands:
                depths = _pipeline_in_chunks(client, queue_commands)
                for aggregate, raw_depth in zip(queue_targets, depths, strict=True):
                    depth = _as_int(raw_depth, "invalid_queue_metric")
                    if depth < 0:
                        raise GuardError("invalid_queue_metric", EXIT_OBSERVATION)
                    aggregate.queue_key_count += 1
                    aggregate.queue_total_depth += depth
                    aggregate.queue_max_depth = max(aggregate.queue_max_depth, depth)
                    maximum = aggregate.category.max_queue_depth
                    if maximum is not None and depth > maximum:
                        aggregate.queue_depth_violation_count += 1
                        reasons.add("queue_depth_limit_exceeded")
        if cursor == b"0":
            break
        if not cursor.isdigit() or len(cursor) > 32:
            raise GuardError("invalid_scan_cursor", EXIT_OBSERVATION)
    after_count = _as_int(client.command("DBSIZE"))
    if before_count != after_count or scanned != after_count:
        reasons.add("inconsistent_keyspace_snapshot")
    return (
        scanned,
        expiring,
        persistent,
        ttl_total,
        ttl_min if ttl_min is not None else -1,
        ttl_max if ttl_max is not None else -1,
        unknown,
    )


def _delta(
    current: int, previous: int | None, reasons: set[str], name: str
) -> int | None:
    if previous is None:
        if current > 0:
            reasons.add(f"{name}_baseline_unknown")
        return None
    if current < previous:
        reasons.add(f"{name}_counter_regressed")
        return None
    result = current - previous
    if result > 0:
        reasons.add(f"{name}_increased")
    return result


def _observe(
    client: RedisReadOnlyClient,
    config: Config,
    credential: Credential,
    previous: State | None,
) -> tuple[dict[str, Any], State]:
    identity = _verify_identity(client, config.redis, credential)
    memory = _parse_info(client.command("INFO", "memory"))
    maxmemory = _info_int(memory, "maxmemory")
    used_memory = _info_int(memory, "used_memory")
    if maxmemory != config.redis.expected_maxmemory_bytes:
        raise GuardError("redis_maxmemory_binding_mismatch", EXIT_OBSERVATION)
    maxmemory_policy = memory.get("maxmemory_policy")
    if maxmemory_policy != config.redis.expected_maxmemory_policy:
        raise GuardError("redis_maxmemory_policy_binding_mismatch", EXIT_OBSERVATION)
    binding_fingerprint = _binding_fingerprint(config, identity, maxmemory_policy)
    same_binding = previous is not None and hmac.compare_digest(
        previous.binding_fingerprint, binding_fingerprint
    )
    usage_basis_points = (used_memory * 10_000) // maxmemory

    stats = _parse_info(client.command("INFO", "stats"))
    keyspace = _parse_keyspace(_parse_info(client.command("INFO", "keyspace")))
    commandstats = _parse_info(client.command("INFO", "commandstats"))
    persistence_before = _parse_info(client.command("INFO", "persistence"))
    changes_before = _info_int(persistence_before, "rdb_changes_since_last_save")
    evicted_keys = _info_int(stats, "evicted_keys")
    total_error_replies = _info_int(stats, "total_error_replies")
    rejected_connections = _info_int(stats, "rejected_connections")
    potential_write_errors, failed_read_calls, unclear_failed_commands = (
        _command_error_metrics(commandstats)
    )

    reasons: set[str] = set()
    if used_memory * 100 >= maxmemory * MEMORY_HARD_DENY_PERCENT:
        reasons.add("memory_hard_deny_threshold_reached")
    elif used_memory * 100 >= maxmemory * MEMORY_WARNING_PERCENT:
        reasons.add("memory_warning_threshold_reached")
    elif used_memory * 100 > maxmemory * MEMORY_TARGET_PERCENT:
        reasons.add("memory_target_exceeded")

    aggregates = {
        item.category_id: CategoryAggregate(item) for item in config.categories
    }
    seen: set[bytes] = set()
    scanned = 0
    expiring = 0
    persistent = 0
    ttl_total = 0
    ttl_min: int | None = None
    ttl_max: int | None = None
    unknown = 0
    for database in config.redis.databases:
        result = _scan_database(client, config, database, aggregates, seen, reasons)
        (
            db_scanned,
            db_expiring,
            db_persistent,
            db_ttl_total,
            db_min,
            db_max,
            db_unknown,
        ) = result
        scanned += db_scanned
        expiring += db_expiring
        persistent += db_persistent
        ttl_total += db_ttl_total
        unknown += db_unknown
        if db_min >= 0:
            ttl_min = db_min if ttl_min is None else min(ttl_min, db_min)
        if db_max >= 0:
            ttl_max = db_max if ttl_max is None else max(ttl_max, db_max)

    unmonitored_database_keys = sum(
        metrics["keys"]
        for database, metrics in keyspace.items()
        if database not in config.redis.databases
    )
    unknown += unmonitored_database_keys
    if unknown:
        reasons.add("unowned_namespace_keys")
    for aggregate in aggregates.values():
        if aggregate.key_count > aggregate.category.max_keys:
            reasons.add("category_key_limit_exceeded")

    persistence_after = _parse_info(client.command("INFO", "persistence"))
    changes_after = _info_int(persistence_after, "rdb_changes_since_last_save")
    if changes_before != changes_after:
        reasons.add("concurrent_keyspace_change")
    identity_after = _verify_identity(client, config.redis, credential)
    if identity_after != identity:
        raise GuardError("redis_identity_changed_during_scan", EXIT_OBSERVATION)

    prior_write = previous.write_error_total if same_binding else None
    prior_evicted = previous.evicted_keys_total if same_binding else None
    write_delta = _delta(
        potential_write_errors, prior_write, reasons, "potential_write_errors"
    )
    evicted_delta = _delta(evicted_keys, prior_evicted, reasons, "evictions")
    hard_reasons = {
        reason
        for reason in reasons
        if reason not in {"memory_target_exceeded", "memory_warning_threshold_reached"}
    }
    if hard_reasons:
        status = "critical"
        decision = "deny"
        result_name = "blocked"
    elif used_memory * 100 >= maxmemory * MEMORY_WARNING_PERCENT:
        status = "warning"
        decision = "observe"
        result_name = "attention"
    elif used_memory * 100 > maxmemory * MEMORY_TARGET_PERCENT:
        status = "above_target"
        decision = "observe"
        result_name = "attention"
    else:
        status = "healthy"
        decision = "observe"
        result_name = "ok"

    now = _utc_now()
    observed_at = _timestamp(now)
    last_transition = (
        previous.last_transition_at
        if same_binding and previous is not None and previous.status == status
        else observed_at
    )
    if status == "healthy":
        healthy_sample_count = (
            min(previous.healthy_sample_count + 1, 2)
            if same_binding and previous is not None and previous.status == "healthy"
            else 1
        )
    else:
        healthy_sample_count = 0
    state = State(
        status=status,
        decision=decision,
        observed_at=observed_at,
        last_transition_at=last_transition,
        binding_fingerprint=binding_fingerprint,
        healthy_sample_count=healthy_sample_count,
        write_error_total=potential_write_errors,
        evicted_keys_total=evicted_keys,
    )
    categories_payload = [
        aggregates[item.category_id].as_payload() for item in config.categories
    ]
    queue_key_count = sum(item.queue_key_count for item in aggregates.values())
    queue_total_depth = sum(item.queue_total_depth for item in aggregates.values())
    queue_max_depth = max(
        (item.queue_max_depth for item in aggregates.values()), default=0
    )
    payload = {
        "result": result_name,
        "status": status,
        "decision": decision,
        "reason_codes": sorted(reasons) if reasons else ["observation_healthy"],
        "observed_at": observed_at,
        "redis_instance_binding": "verified",
        "binding_continuity": (
            "continued" if same_binding else "new" if previous is None else "reset"
        ),
        "healthy_sample_count": healthy_sample_count,
        "redis_data_mutated": False,
        "memory": {
            "used_bytes": used_memory,
            "max_bytes": maxmemory,
            "usage_basis_points": usage_basis_points,
            "maxmemory_policy": maxmemory_policy,
        },
        "keys": {
            "scanned_count": scanned,
            "expiring_count": expiring,
            "persistent_count": persistent,
            "unknown_category_count": unknown,
            "configured_database_count": len(config.redis.databases),
            "unmonitored_database_key_count": unmonitored_database_keys,
        },
        "ttl": {
            "minimum_ms": ttl_min,
            "average_ms": ttl_total // expiring if expiring else None,
            "maximum_ms": ttl_max,
        },
        "evictions": {"total": evicted_keys, "delta": evicted_delta},
        "write_errors": {
            "potential_write_total": potential_write_errors,
            "potential_write_delta": write_delta,
            "failed_read_total": failed_read_calls,
            "unclear_failed_command_count": unclear_failed_commands,
            "total_error_replies": total_error_replies,
        },
        "connections": {"rejected_total": rejected_connections},
        "queues": {
            "key_count": queue_key_count,
            "total_depth": queue_total_depth,
            "maximum_depth": queue_max_depth,
        },
        "categories": categories_payload,
    }
    return payload, state


def _state_is_fresh(state: State, now: dt.datetime) -> bool:
    age_seconds = (now - _parse_timestamp(state.observed_at)).total_seconds()
    return -60 <= age_seconds <= STATE_MAX_AGE_SECONDS


def _alert_event(previous: State | None, state: State) -> str | None:
    if previous is None:
        return "observation_started" if state.status == "healthy" else "guard_attention"
    if not hmac.compare_digest(previous.binding_fingerprint, state.binding_fingerprint):
        return "binding_changed"
    if previous.status == state.status:
        return None
    if state.status == "healthy":
        return "guard_resolved"
    return "guard_transition"


def _execute(
    command: str,
    config: Config,
    credential: Credential,
    dry_run: bool,
) -> int:
    previous = _read_state(config)
    with RedisReadOnlyClient(config.redis) as client:
        observation, state = _observe(client, config, credential, previous)
    payload = _base_payload(command, dry_run)
    payload.update(observation)
    payload["state_written"] = False
    payload["alert_written"] = False

    if command == "assert-stable":
        stable = (
            state.status == "healthy"
            and previous is not None
            and previous.status == "healthy"
            and hmac.compare_digest(
                previous.binding_fingerprint, state.binding_fingerprint
            )
            and state.healthy_sample_count >= 2
            and _state_is_fresh(previous, _utc_now())
        )
        payload["result"] = "ok" if stable else "blocked"
        payload["decision"] = "observe" if stable else "deny"
        if not stable:
            payload["reason_codes"] = sorted(
                set(payload["reason_codes"]) | {"stable_monitor_state_not_proven"}
            )
        _emit(payload)
        return EXIT_OK if stable else EXIT_ASSERT_UNSTABLE

    alert_event = _alert_event(previous, state)
    if not dry_run:
        _prepare_spools(config)
        _atomic_write_json(config.state_file, state.as_dict())
        payload["state_written"] = True
        if alert_event is not None:
            alert = {
                "schema_version": SCHEMA_VERSION,
                "component": "sealai-redis-capacity-guard",
                "event": alert_event,
                "status": state.status,
                "decision": state.decision,
                "reason_codes": payload["reason_codes"],
                "observed_at": state.observed_at,
                "memory_usage_basis_points": payload["memory"]["usage_basis_points"],
                "unknown_category_count": payload["keys"]["unknown_category_count"],
                "potential_write_error_delta": payload["write_errors"][
                    "potential_write_delta"
                ],
                "evicted_keys_delta": payload["evictions"]["delta"],
                "external_alert_delivery": EXTERNAL_ALERT_DELIVERY_STATUS,
                "redis_data_mutated": False,
            }
            _atomic_write_json(config.alert_file, alert)
            payload["alert_written"] = True
    _emit(payload)
    if state.status == "critical":
        return EXIT_DENIED
    if state.status in {"above_target", "warning"}:
        return EXIT_ATTENTION
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Read-only Redis capacity and namespace guard"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="path to a mode-0400/0600 systemd credential containing config JSON",
    )
    parser.add_argument(
        "--credential-file",
        required=True,
        help="path to a mode-0600 systemd credential JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="observe Redis without writing local state or alert spools",
    )
    parser.add_argument("command", choices=("check", "assert-stable"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    command = str(arguments.command)
    dry_run = bool(arguments.dry_run)
    try:
        config_path = Path(arguments.config)
        credential_path = Path(arguments.credential_file)
        if not _is_normalized_absolute(config_path) or not _is_normalized_absolute(
            credential_path
        ):
            raise GuardError("invalid_config_path", EXIT_CONFIG)
        config = _load_config(config_path)
        credential = _load_credential(
            credential_path, config.redis.expected_acl_username_sha256
        )
        with _exclusive_lock(config.lock_file):
            return _execute(command, config, credential, dry_run)
    except GuardError as error:
        _emit(_error_payload(command, dry_run, error.reason_code))
        return error.exit_code
    except Exception:  # pragma: no cover - final fail-closed boundary
        _emit(_error_payload(command, dry_run, "internal_error"))
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
