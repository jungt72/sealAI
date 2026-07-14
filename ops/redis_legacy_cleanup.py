#!/usr/bin/env python3
"""Read-only GATE-04 consistency observer; cleanup execution is hard-disabled."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCHEMA_VERSION = 1
APPROVAL_GATE = "GATE-04"
OPERATION_KIND = "UNLINK_EXACT_REBUILDABLE_KEYS"
EXECUTION_IMPLEMENTED = False
TARGET_MAX_MEMORY_PERCENT = 70
APPROVED_DATABASE = 0
MAX_SCAN_COUNT = 2_000
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_INVENTORY_ITERATIONS = 100_000
MAX_EVIDENCE_LIFETIME = dt.timedelta(hours=24)
PRODUCTION_CHECKOUT = Path("/home/thorsten/sealai")
DOCKER_BINARY = "/usr/bin/docker"
GIT_BINARY = "/usr/bin/git"
REDIS_CONTAINER = "redis"
REDIS_CLI = "redis-cli"
LOCAL_DOCKER_HOST = "unix:///var/run/docker.sock"
GIT_SAFE_CONFIG_ARGS = (
    "--no-optional-locks",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.fsmonitor=false",
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-._A-Za-z0-9]+)?$")
TYPE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
NAMESPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,126}:$")
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
KEY_TOKEN_RE = re.compile(r"^[0-9a-f]{80}:[1-9][0-9]{0,9}$")
SAFE_CATEGORY_CLASSES = frozenset(
    {"legacy_rebuildable", "cache", "queue", "session", "lock", "authority"}
)
NEVER_DELETE_CLASSES = frozenset({"cache", "queue", "session", "lock", "authority"})
WRITE_ERROR_KINDS = frozenset({"OOM", "MISCONF", "READONLY", "NOREPLICAS"})
CONFIG_READ_FIELDS = (
    "appendonly",
    "save",
    "dir",
    "dbfilename",
    "appenddirname",
    "maxmemory",
    "maxmemory-policy",
)


# The server enforces read-only script semantics. The script returns only a
# double SHA-1 token and metadata, never a Redis key. Tokens are used solely to
# deduplicate SCAN results in process memory. They are not an exact-key proof,
# are not persisted, and are deliberately excluded from manifest bindings.
INVENTORY_LUA = r"""
local cursor = ARGV[1]
local scan_count = tonumber(ARGV[2])
local prefix_count = tonumber(ARGV[3])
local prefixes = {}
for i = 1, prefix_count do prefixes[i] = ARGV[3 + i] end
local page = redis.call('SCAN', cursor, 'COUNT', scan_count)
local rows = {}
local unknown = 0
local vanished = 0
for _, key in ipairs(page[2]) do
  local category = 0
  for i, prefix in ipairs(prefixes) do
    if string.sub(key, 1, string.len(prefix)) == prefix then
      if category ~= 0 then return redis.error_reply('AMBIGUOUS_CATEGORY') end
      category = i
    end
  end
  if category == 0 then
    unknown = unknown + 1
  else
    local key_type = redis.call('TYPE', key).ok
    local ttl = redis.call('PTTL', key)
    local memory = redis.call('MEMORY', 'USAGE', key)
    if not memory or key_type == 'none' or ttl == -2 then
      vanished = vanished + 1
    else
      local token = redis.sha1hex(key) .. redis.sha1hex(string.reverse(key)) .. ':' .. tostring(string.len(key))
      table.insert(rows, {category, token, key_type, ttl, memory})
    end
  end
end
return cjson.encode({cursor=page[1], rows=rows, unknown=unknown, vanished=vanished})
""".strip()


class CleanupError(RuntimeError):
    """Expected fail-closed validation or runtime denial."""


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
    fingerprint_sha256: str


@dataclass(frozen=True)
class PersistenceBinding:
    appendonly: str
    save: str
    directory: Path
    dbfilename: str
    appenddirname: str
    lastsave_epoch: int
    fingerprint_sha256: str


@dataclass(frozen=True)
class RedisBinding:
    container_id: str
    image_id: str
    database: int
    run_id: str
    version: str
    role: str
    maxmemory_bytes: int
    maxmemory_policy: str
    evicted_keys: int
    write_error_total: int
    instance_fingerprint_sha256: str
    persistence: PersistenceBinding


@dataclass(frozen=True)
class RecoveryEvidence:
    evidence_id: str
    kind: str
    status: str
    evidence_sha256: str
    verified_at: dt.datetime
    valid_until: dt.datetime


@dataclass(frozen=True)
class CategoryBinding:
    count: int
    persistent_count: int
    expiring_count: int
    type_counts: tuple[tuple[str, int], ...]

    def public(self) -> dict[str, object]:
        return {
            "count": self.count,
            "persistent_count": self.persistent_count,
            "expiring_count": self.expiring_count,
            "type_counts": dict(self.type_counts),
        }


@dataclass(frozen=True)
class CategorySpec:
    category_id: str
    namespace_prefix: str
    owner: str
    safety_class: str
    rebuildability_status: str
    rebuildability_evidence_sha256: str
    ttl_policy: str
    allowed_types: tuple[str, ...]
    expected: CategoryBinding


@dataclass(frozen=True)
class CleanupManifest:
    digest: str
    operation_id: str
    host: HostBinding
    checkout: CheckoutBinding
    redis: RedisBinding
    categories: tuple[CategorySpec, ...]
    cleanup_categories: tuple[str, ...]
    expected_dbsize: int
    inventory_binding_sha256: str
    production_fingerprint_sha256: str
    scan_count: int
    persistence_evidence: RecoveryEvidence
    restore_evidence: RecoveryEvidence


@dataclass(frozen=True)
class CategoryObservation:
    binding: CategoryBinding
    observed_memory_usage_sum_bytes: int


@dataclass(frozen=True)
class Inventory:
    observations: Mapping[str, CategoryObservation]
    dbsize: int
    binding_sha256: str


@dataclass(frozen=True)
class RedisHealth:
    used_memory: int
    maxmemory: int
    dbsize: int
    lazyfree_pending_objects: int
    aof_pending_bio_fsync: int

    @property
    def target_reached(self) -> bool:
        return self.used_memory * 100 <= self.maxmemory * TARGET_MAX_MEMORY_PERCENT

    @property
    def used_percent_basis_points(self) -> int:
        return self.used_memory * 10_000 // self.maxmemory


@dataclass(frozen=True)
class ConsistentObservation:
    health: RedisHealth
    inventory: Inventory
    inventory_passes: int


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
HostProbe = Callable[[], HostBinding]


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "DOCKER_", "REDIS"))
    }
    environment["PATH"] = "/usr/sbin:/usr/bin:/sbin:/bin"
    environment["DOCKER_HOST"] = LOCAL_DOCKER_HOST
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


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CleanupError("private document contains a duplicate JSON key")
        value[key] = item
    return value


def _is_plain_int(value: object) -> bool:
    return type(value) is int


def emit(event: str, status_value: str, **fields: object) -> None:
    payload = {
        "event": event,
        "status": status_value,
        "timestamp": _utc_now()
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
        data = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CleanupError("private document is invalid") from exc
    if not isinstance(data, dict):
        raise CleanupError("private document root must be an object")
    return raw, data


def _parse_utc(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise CleanupError(f"{field} timestamp is invalid")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CleanupError(f"{field} timestamp is invalid") from exc


def _validate_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.startswith("/"):
        raise CleanupError(f"{field} must be an absolute path")
    path = Path(value)
    if str(path) != value or any(part in {".", ".."} for part in path.parts):
        raise CleanupError(f"{field} must be lexically normalized")
    return path


def _validate_evidence(
    value: Any, *, kind: str, status_value: str, field: str
) -> RecoveryEvidence:
    expected = {
        "evidence_id",
        "kind",
        "status",
        "evidence_sha256",
        "verified_at",
        "valid_until",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise CleanupError(f"{field} evidence schema is invalid")
    if value["kind"] != kind or value["status"] != status_value:
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
    if valid_until <= verified_at or valid_until > verified_at + MAX_EVIDENCE_LIFETIME:
        raise CleanupError(f"{field} evidence lifetime is invalid")
    return RecoveryEvidence(
        value["evidence_id"],
        kind,
        status_value,
        value["evidence_sha256"],
        verified_at,
        valid_until,
    )


def _validate_binding(value: Any, field: str) -> CategoryBinding:
    expected = {"count", "persistent_count", "expiring_count", "type_counts"}
    if not isinstance(value, dict) or set(value) != expected:
        raise CleanupError(f"{field} category binding schema is invalid")
    for name in ("count", "persistent_count", "expiring_count"):
        if not _is_plain_int(value[name]) or value[name] < 0:
            raise CleanupError(f"{field} category count is invalid")
    if value["persistent_count"] + value["expiring_count"] != value["count"]:
        raise CleanupError(f"{field} TTL counts do not equal category count")
    raw_types = value["type_counts"]
    if (
        not isinstance(raw_types, dict)
        or not raw_types
        or any(
            not isinstance(key, str)
            or not TYPE_RE.fullmatch(key)
            or not _is_plain_int(count)
            or count < 0
            for key, count in raw_types.items()
        )
        or sum(raw_types.values()) != value["count"]
    ):
        raise CleanupError(f"{field} type counts are invalid")
    return CategoryBinding(
        value["count"],
        value["persistent_count"],
        value["expiring_count"],
        tuple(sorted(raw_types.items())),
    )


def _validate_category(value: Any, index: int) -> CategorySpec:
    expected = {
        "category_id",
        "namespace_prefix",
        "owner",
        "safety_class",
        "rebuildability",
        "ttl_policy",
        "allowed_types",
        "expected",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise CleanupError(f"category {index} schema is invalid")
    for name in ("category_id", "owner"):
        if not isinstance(value[name], str) or not TOKEN_RE.fullmatch(value[name]):
            raise CleanupError(f"category {index} {name} is invalid")
    prefix = value["namespace_prefix"]
    if not isinstance(prefix, str) or not NAMESPACE_RE.fullmatch(prefix):
        raise CleanupError(f"category {index} namespace is invalid")
    safety_class = value["safety_class"]
    if safety_class not in SAFE_CATEGORY_CLASSES:
        raise CleanupError(f"category {index} safety class is invalid")
    rebuildability = value["rebuildability"]
    if not isinstance(rebuildability, dict) or set(rebuildability) != {
        "status",
        "evidence_sha256",
    }:
        raise CleanupError(f"category {index} rebuildability schema is invalid")
    if rebuildability["status"] not in {"VERIFIED_REBUILDABLE", "PROTECTED"}:
        raise CleanupError(f"category {index} rebuildability status is invalid")
    if not isinstance(
        rebuildability["evidence_sha256"], str
    ) or not SHA256_RE.fullmatch(rebuildability["evidence_sha256"]):
        raise CleanupError(f"category {index} rebuildability evidence is invalid")
    ttl_policy = value["ttl_policy"]
    if ttl_policy not in {"persistent_only", "expiring_only", "mixed_protected"}:
        raise CleanupError(f"category {index} TTL policy is invalid")
    raw_types = value["allowed_types"]
    if (
        not isinstance(raw_types, list)
        or not raw_types
        or len(raw_types) != len(set(raw_types))
        or any(
            not isinstance(item, str) or not TYPE_RE.fullmatch(item)
            for item in raw_types
        )
    ):
        raise CleanupError(f"category {index} allowed types are invalid")
    binding = _validate_binding(value["expected"], f"category {index}")
    if set(dict(binding.type_counts)) - set(raw_types):
        raise CleanupError(f"category {index} expected type is not allowed")
    if ttl_policy == "persistent_only" and binding.expiring_count:
        raise CleanupError(f"category {index} persistent TTL binding is invalid")
    if ttl_policy == "expiring_only" and binding.persistent_count:
        raise CleanupError(f"category {index} expiring TTL binding is invalid")
    return CategorySpec(
        value["category_id"],
        prefix,
        value["owner"],
        safety_class,
        rebuildability["status"],
        rebuildability["evidence_sha256"],
        ttl_policy,
        tuple(sorted(raw_types)),
        binding,
    )


def _repository_fingerprint(host: HostBinding, checkout: CheckoutBinding) -> str:
    return _canonical_sha256(
        {
            "hostname": host.hostname,
            "machine_id_sha256": host.machine_id_sha256,
            "checkout_path": str(checkout.path),
            "branch": checkout.branch,
            "commit": checkout.commit,
            "tree": checkout.tree,
            "clean": True,
        }
    )


def _persistence_fingerprint(value: PersistenceBinding) -> str:
    return _canonical_sha256(
        {
            "appendonly": value.appendonly,
            "save": value.save,
            "dir": str(value.directory),
            "dbfilename": value.dbfilename,
            "appenddirname": value.appenddirname,
            "lastsave_epoch": value.lastsave_epoch,
        }
    )


def _redis_fingerprint(redis: RedisBinding) -> str:
    return _canonical_sha256(
        {
            "container_name": REDIS_CONTAINER,
            "container_id": redis.container_id,
            "image_id": redis.image_id,
            "database": redis.database,
            "run_id": redis.run_id,
            "version": redis.version,
            "role": redis.role,
            "maxmemory_bytes": redis.maxmemory_bytes,
            "maxmemory_policy": redis.maxmemory_policy,
            "persistence_sha256": redis.persistence.fingerprint_sha256,
        }
    )


def _inventory_binding_value(
    categories: Sequence[CategorySpec], dbsize: int
) -> dict[str, object]:
    return {
        "dbsize": dbsize,
        "categories": {
            item.category_id: {
                "namespace_prefix": item.namespace_prefix,
                "owner": item.owner,
                "safety_class": item.safety_class,
                "rebuildability_status": item.rebuildability_status,
                "rebuildability_evidence_sha256": item.rebuildability_evidence_sha256,
                "ttl_policy": item.ttl_policy,
                "allowed_types": list(item.allowed_types),
                "expected": item.expected.public(),
            }
            for item in categories
        },
    }


def load_manifest(path: Path) -> CleanupManifest:
    raw, data = _read_private_json(path)
    if set(data) != {
        "schema_version",
        "gate_id",
        "purpose",
        "operation",
        "categories",
        "cleanup_categories",
        "recovery_evidence",
    }:
        raise CleanupError("manifest has missing or unexpected root fields")
    if (
        not _is_plain_int(data["schema_version"])
        or data["schema_version"] != SCHEMA_VERSION
        or data["gate_id"] != APPROVAL_GATE
    ):
        raise CleanupError("manifest schema or gate is invalid")
    if not isinstance(data["purpose"], str) or not data["purpose"].strip():
        raise CleanupError("manifest purpose is required")
    operation = data["operation"]
    if not isinstance(operation, dict) or set(operation) != {
        "operation_id",
        "kind",
        "host",
        "checkout",
        "redis",
        "expected_dbsize",
        "inventory_binding_sha256",
        "production_fingerprint_sha256",
        "target_max_memory_percent",
        "scan_count",
    }:
        raise CleanupError("operation schema is invalid")
    operation_id = operation["operation_id"]
    if (
        operation["kind"] != OPERATION_KIND
        or not isinstance(operation_id, str)
        or not TOKEN_RE.fullmatch(operation_id)
    ):
        raise CleanupError("operation identity is invalid")

    host_value = operation["host"]
    if not isinstance(host_value, dict) or set(host_value) != {
        "hostname",
        "machine_id_sha256",
    }:
        raise CleanupError("host binding schema is invalid")
    if not isinstance(host_value["hostname"], str) or not HOSTNAME_RE.fullmatch(
        host_value["hostname"]
    ):
        raise CleanupError("host name is invalid")
    if not isinstance(host_value["machine_id_sha256"], str) or not SHA256_RE.fullmatch(
        host_value["machine_id_sha256"]
    ):
        raise CleanupError("machine identity is invalid")
    host = HostBinding(host_value["hostname"], host_value["machine_id_sha256"])

    checkout_value = operation["checkout"]
    if not isinstance(checkout_value, dict) or set(checkout_value) != {
        "path",
        "branch",
        "commit",
        "tree",
        "clean",
        "fingerprint_sha256",
    }:
        raise CleanupError("checkout binding schema is invalid")
    checkout_path = _validate_path(checkout_value["path"], "checkout path")
    if (
        checkout_path != PRODUCTION_CHECKOUT
        or checkout_value["branch"] != "main"
        or checkout_value["clean"] is not True
        or not isinstance(checkout_value["commit"], str)
        or not GIT_OID_RE.fullmatch(checkout_value["commit"])
        or not isinstance(checkout_value["tree"], str)
        or not GIT_OID_RE.fullmatch(checkout_value["tree"])
        or not isinstance(checkout_value["fingerprint_sha256"], str)
        or not SHA256_RE.fullmatch(checkout_value["fingerprint_sha256"])
    ):
        raise CleanupError("checkout binding is invalid")
    checkout = CheckoutBinding(
        checkout_path,
        "main",
        checkout_value["commit"],
        checkout_value["tree"],
        checkout_value["fingerprint_sha256"],
    )
    if _repository_fingerprint(host, checkout) != checkout.fingerprint_sha256:
        raise CleanupError("checkout fingerprint is invalid")

    redis_value = operation["redis"]
    if not isinstance(redis_value, dict) or set(redis_value) != {
        "container_name",
        "container_id",
        "image_id",
        "database",
        "run_id",
        "version",
        "role",
        "maxmemory_bytes",
        "maxmemory_policy",
        "evicted_keys",
        "write_error_total",
        "instance_fingerprint_sha256",
        "persistence",
    }:
        raise CleanupError("Redis binding schema is invalid")
    if (
        redis_value["container_name"] != REDIS_CONTAINER
        or not isinstance(redis_value["container_id"], str)
        or not CONTAINER_ID_RE.fullmatch(redis_value["container_id"])
        or not isinstance(redis_value["image_id"], str)
        or not IMAGE_ID_RE.fullmatch(redis_value["image_id"])
        or not _is_plain_int(redis_value["database"])
        or redis_value["database"] != APPROVED_DATABASE
        or not isinstance(redis_value["run_id"], str)
        or not SHA1_RE.fullmatch(redis_value["run_id"])
        or not isinstance(redis_value["version"], str)
        or not VERSION_RE.fullmatch(redis_value["version"])
        or redis_value["role"] != "master"
        or not _is_plain_int(redis_value["maxmemory_bytes"])
        or redis_value["maxmemory_bytes"] <= 0
        or not isinstance(redis_value["maxmemory_policy"], str)
        or not TOKEN_RE.fullmatch(redis_value["maxmemory_policy"])
    ):
        raise CleanupError("Redis identity binding is invalid")
    for counter in ("evicted_keys", "write_error_total"):
        if not _is_plain_int(redis_value[counter]) or redis_value[counter] < 0:
            raise CleanupError("Redis safety counter binding is invalid")

    persistence_value = redis_value["persistence"]
    if not isinstance(persistence_value, dict) or set(persistence_value) != {
        "appendonly",
        "save",
        "dir",
        "dbfilename",
        "appenddirname",
        "lastsave_epoch",
        "fingerprint_sha256",
    }:
        raise CleanupError("Redis persistence binding schema is invalid")
    persistence_dir = _validate_path(persistence_value["dir"], "Redis persistence dir")
    if (
        persistence_value["appendonly"] != "yes"
        or not isinstance(persistence_value["save"], str)
        or not persistence_value["save"].strip()
        or not isinstance(persistence_value["dbfilename"], str)
        or not TOKEN_RE.fullmatch(persistence_value["dbfilename"])
        or not isinstance(persistence_value["appenddirname"], str)
        or not TOKEN_RE.fullmatch(persistence_value["appenddirname"])
        or not _is_plain_int(persistence_value["lastsave_epoch"])
        or persistence_value["lastsave_epoch"] <= 0
        or not isinstance(persistence_value["fingerprint_sha256"], str)
        or not SHA256_RE.fullmatch(persistence_value["fingerprint_sha256"])
    ):
        raise CleanupError("Redis persistence binding is invalid")
    persistence = PersistenceBinding(
        "yes",
        persistence_value["save"],
        persistence_dir,
        persistence_value["dbfilename"],
        persistence_value["appenddirname"],
        persistence_value["lastsave_epoch"],
        persistence_value["fingerprint_sha256"],
    )
    if _persistence_fingerprint(persistence) != persistence.fingerprint_sha256:
        raise CleanupError("Redis persistence fingerprint is invalid")
    redis = RedisBinding(
        redis_value["container_id"],
        redis_value["image_id"],
        APPROVED_DATABASE,
        redis_value["run_id"],
        redis_value["version"],
        "master",
        redis_value["maxmemory_bytes"],
        redis_value["maxmemory_policy"],
        redis_value["evicted_keys"],
        redis_value["write_error_total"],
        redis_value["instance_fingerprint_sha256"],
        persistence,
    )
    if _redis_fingerprint(redis) != redis.instance_fingerprint_sha256:
        raise CleanupError("Redis instance fingerprint is invalid")

    raw_categories = data["categories"]
    if not isinstance(raw_categories, list) or not raw_categories:
        raise CleanupError("manifest category catalog is empty")
    categories = tuple(
        _validate_category(item, index) for index, item in enumerate(raw_categories)
    )
    ids = [item.category_id for item in categories]
    prefixes = [item.namespace_prefix for item in categories]
    if len(ids) != len(set(ids)) or len(prefixes) != len(set(prefixes)):
        raise CleanupError("category ids and namespaces must be unique")
    if any(
        left.startswith(right) or right.startswith(left)
        for index, left in enumerate(prefixes)
        for right in prefixes[index + 1 :]
    ):
        raise CleanupError("category namespaces must not overlap")
    cleanup_categories = data["cleanup_categories"]
    if (
        not isinstance(cleanup_categories, list)
        or not cleanup_categories
        or cleanup_categories != sorted(cleanup_categories)
        or len(cleanup_categories) != len(set(cleanup_categories))
        or any(item not in ids for item in cleanup_categories)
    ):
        raise CleanupError("cleanup category selection is invalid")
    category_map = {item.category_id: item for item in categories}
    for category_id in cleanup_categories:
        category = category_map[category_id]
        if (
            category.safety_class != "legacy_rebuildable"
            or category.safety_class in NEVER_DELETE_CLASSES
            or category.rebuildability_status != "VERIFIED_REBUILDABLE"
            or category.ttl_policy != "persistent_only"
            or category.expected.count <= 0
        ):
            raise CleanupError("selected category is not safe and rebuildable")

    expected_dbsize = operation["expected_dbsize"]
    if (
        not _is_plain_int(expected_dbsize)
        or expected_dbsize <= 0
        or expected_dbsize != sum(item.expected.count for item in categories)
    ):
        raise CleanupError("exact Redis DB size binding is invalid")
    inventory_binding_sha256 = _canonical_sha256(
        _inventory_binding_value(categories, expected_dbsize)
    )
    if operation["inventory_binding_sha256"] != inventory_binding_sha256:
        raise CleanupError("inventory binding fingerprint is invalid")
    scan_count = operation["scan_count"]
    if (
        not _is_plain_int(operation["target_max_memory_percent"])
        or operation["target_max_memory_percent"] != TARGET_MAX_MEMORY_PERCENT
        or not _is_plain_int(scan_count)
        or not 1 <= scan_count <= MAX_SCAN_COUNT
    ):
        raise CleanupError("read-only cursor or memory target is invalid")
    production_fingerprint = _canonical_sha256(
        {
            "host": {
                "hostname": host.hostname,
                "machine_id_sha256": host.machine_id_sha256,
            },
            "repository_fingerprint_sha256": checkout.fingerprint_sha256,
            "redis_instance_fingerprint_sha256": redis.instance_fingerprint_sha256,
            "inventory_binding_sha256": inventory_binding_sha256,
            "operation_kind": OPERATION_KIND,
            "cleanup_categories": cleanup_categories,
        }
    )
    if operation["production_fingerprint_sha256"] != production_fingerprint:
        raise CleanupError("production fingerprint is invalid")

    recovery = data["recovery_evidence"]
    if not isinstance(recovery, dict) or set(recovery) != {"persistence", "restore"}:
        raise CleanupError("recovery evidence schema is invalid")
    persistence_evidence = _validate_evidence(
        recovery["persistence"],
        kind="redis_aof_rdb_live_verified",
        status_value="VERIFIED",
        field="persistence",
    )
    restore_evidence = _validate_evidence(
        recovery["restore"],
        kind="redis_backup_restore_drill_verified",
        status_value="RESTORE_VERIFIED",
        field="restore",
    )
    return CleanupManifest(
        hashlib.sha256(raw).hexdigest(),
        operation_id,
        host,
        checkout,
        redis,
        categories,
        tuple(cleanup_categories),
        expected_dbsize,
        inventory_binding_sha256,
        production_fingerprint,
        scan_count,
        persistence_evidence,
        restore_evidence,
    )


def _ensure_evidence_current(manifest: CleanupManifest, now: dt.datetime) -> None:
    for field, evidence in (
        ("persistence", manifest.persistence_evidence),
        ("restore", manifest.restore_evidence),
    ):
        if evidence.verified_at > now + dt.timedelta(minutes=5):
            raise CleanupError(f"{field} evidence is future-dated")
        if evidence.valid_until <= now:
            raise CleanupError(f"{field} evidence expired")


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
        raw = os.read(descriptor, 257).strip()
    finally:
        os.close(descriptor)
    if not re.fullmatch(rb"[0-9a-f]{32}", raw):
        raise CleanupError("machine identity source is invalid")
    return HostBinding(hostname, hashlib.sha256(raw).hexdigest())


def _command_stdout(command: Sequence[str], runner: Runner, failure: str) -> str:
    result = runner(command)
    if result.returncode != 0 or not isinstance(result.stdout, str):
        raise CleanupError(failure)
    return result.stdout.rstrip("\n")


def _validate_host_checkout(
    manifest: CleanupManifest, runner: Runner, host_probe: HostProbe
) -> None:
    host = host_probe()
    if host != manifest.host:
        raise CleanupError("approved host identity changed")
    prefix = [
        GIT_BINARY,
        *GIT_SAFE_CONFIG_ARGS,
        "-C",
        str(manifest.checkout.path),
    ]
    values = {
        "root": _command_stdout(
            [*prefix, "rev-parse", "--show-toplevel"], runner, "checkout unavailable"
        ),
        "branch": _command_stdout(
            [*prefix, "symbolic-ref", "--short", "HEAD"], runner, "branch unavailable"
        ),
        "commit": _command_stdout(
            [*prefix, "rev-parse", "HEAD"], runner, "commit unavailable"
        ),
        "tree": _command_stdout(
            [*prefix, "rev-parse", "HEAD^{tree}"], runner, "tree unavailable"
        ),
        "status": _command_stdout(
            [*prefix, "status", "--porcelain=v1", "--untracked-files=all"],
            runner,
            "checkout status unavailable",
        ),
    }
    if values != {
        "root": str(manifest.checkout.path),
        "branch": manifest.checkout.branch,
        "commit": manifest.checkout.commit,
        "tree": manifest.checkout.tree,
        "status": "",
    }:
        raise CleanupError("production checkout fingerprint drifted")
    checkout = CheckoutBinding(
        manifest.checkout.path,
        values["branch"],
        values["commit"],
        values["tree"],
        manifest.checkout.fingerprint_sha256,
    )
    if _repository_fingerprint(host, checkout) != checkout.fingerprint_sha256:
        raise CleanupError("production checkout fingerprint drifted")


def _redis_command(container_id: str, args: Sequence[str], runner: Runner) -> str:
    if not CONTAINER_ID_RE.fullmatch(container_id):
        raise CleanupError("Redis exec container identity is invalid")
    arguments = tuple(args)
    allowed = (
        arguments == ("INFO", "all")
        or arguments == ("LASTSAVE",)
        or arguments == ("DBSIZE",)
        or arguments == ("CONFIG", "GET", *CONFIG_READ_FIELDS)
        or (
            len(arguments) >= 7
            and arguments[0] == "EVAL_RO"
            and arguments[1] == INVENTORY_LUA
            and arguments[2] == "0"
        )
    )
    if not allowed:
        raise CleanupError("Redis command is outside the fixed read-only allowlist")
    return _command_stdout(
        [
            DOCKER_BINARY,
            "exec",
            container_id,
            REDIS_CLI,
            "--raw",
            "-n",
            str(APPROVED_DATABASE),
            *arguments,
        ],
        runner,
        "Redis read-only probe failed",
    )


def _parse_info(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.rstrip("\r")
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or key in values:
            raise CleanupError("Redis INFO response is invalid")
        values[key] = value
    return values


def _parse_nonnegative(value: str | None, field: str) -> int:
    if value is None or not value.isdigit():
        raise CleanupError(f"Redis {field} is invalid")
    return int(value)


def _parse_config(raw: str, names: Sequence[str]) -> dict[str, str]:
    lines = [line.rstrip("\r") for line in raw.splitlines()]
    if len(lines) % 2:
        raise CleanupError("Redis CONFIG response is invalid")
    keys = lines[0::2]
    if len(names) != len(set(names)) or len(keys) != len(set(keys)):
        raise CleanupError("Redis CONFIG response contains duplicate names")
    result = dict(zip(keys, lines[1::2], strict=True))
    if set(result) != set(names):
        raise CleanupError("Redis CONFIG response is incomplete")
    return result


def _write_error_total(info: Mapping[str, str]) -> int:
    total = 0
    for kind in WRITE_ERROR_KINDS:
        value = info.get(f"errorstat_{kind}")
        if value is None:
            continue
        match = re.fullmatch(r"count=([0-9]+)", value)
        if not match:
            raise CleanupError("Redis write-error counter is invalid")
        total += int(match.group(1))
    return total


def _inspect_one_container(reference: str, runner: Runner) -> dict[str, Any]:
    inspect_raw = _command_stdout(
        [DOCKER_BINARY, "container", "inspect", reference],
        runner,
        "Redis container inspection failed",
    )
    try:
        inspected = json.loads(
            inspect_raw, object_pairs_hook=_reject_duplicate_json_keys
        )
    except json.JSONDecodeError as exc:
        raise CleanupError("Redis container inspection is invalid") from exc
    if (
        not isinstance(inspected, list)
        or len(inspected) != 1
        or not isinstance(inspected[0], dict)
    ):
        raise CleanupError("Redis container identity is invalid")
    return inspected[0]


def _inspect_redis_container(manifest: CleanupManifest, runner: Runner) -> str:
    by_name = _inspect_one_container(REDIS_CONTAINER, runner)
    by_id = _inspect_one_container(manifest.redis.container_id, runner)
    if by_name.get("Id") != by_id.get("Id"):
        raise CleanupError("Redis container name-to-id binding changed")
    item = by_id
    state = item.get("State")
    if (
        item.get("Id") != manifest.redis.container_id
        or item.get("Image") != manifest.redis.image_id
        or item.get("Name") not in {None, f"/{REDIS_CONTAINER}"}
        or not isinstance(state, dict)
        or state.get("Running") is not True
        or state.get("Status") != "running"
        or not isinstance(state.get("Health"), dict)
        or state["Health"].get("Status") != "healthy"
    ):
        raise CleanupError("Redis container identity or health changed")
    return manifest.redis.container_id


def _validate_redis_health(
    manifest: CleanupManifest, container_id: str, runner: Runner
) -> RedisHealth:
    if container_id != manifest.redis.container_id:
        raise CleanupError("Redis health probe container identity changed")
    info = _parse_info(_redis_command(container_id, ["INFO", "all"], runner))
    config = _parse_config(
        _redis_command(container_id, ["CONFIG", "GET", *CONFIG_READ_FIELDS], runner),
        CONFIG_READ_FIELDS,
    )
    lastsave = _redis_command(container_id, ["LASTSAVE"], runner)
    dbsize = _redis_command(container_id, ["DBSIZE"], runner)
    if not lastsave.isdigit() or not dbsize.isdigit():
        raise CleanupError("Redis persistence or DB size probe is invalid")
    persistence = PersistenceBinding(
        config["appendonly"],
        config["save"],
        _validate_path(config["dir"], "runtime Redis persistence dir"),
        config["dbfilename"],
        config["appenddirname"],
        int(lastsave),
        manifest.redis.persistence.fingerprint_sha256,
    )
    if persistence != manifest.redis.persistence or (
        _persistence_fingerprint(persistence) != persistence.fingerprint_sha256
    ):
        raise CleanupError("Redis persistence identity changed")
    maxmemory = _parse_nonnegative(info.get("maxmemory"), "maxmemory")
    if config["maxmemory"] != str(maxmemory):
        raise CleanupError("Redis maxmemory probes disagree")
    if (
        info.get("redis_version") != manifest.redis.version
        or info.get("run_id") != manifest.redis.run_id
        or info.get("role") != manifest.redis.role
        or maxmemory != manifest.redis.maxmemory_bytes
        or info.get("maxmemory_policy") != manifest.redis.maxmemory_policy
        or config["maxmemory-policy"] != manifest.redis.maxmemory_policy
    ):
        raise CleanupError("Redis instance configuration changed")
    required_states = {
        "loading": "0",
        "async_loading": "0",
        "rdb_bgsave_in_progress": "0",
        "rdb_last_bgsave_status": "ok",
        "aof_enabled": "1",
        "aof_rewrite_in_progress": "0",
        "aof_last_bgrewrite_status": "ok",
        "aof_last_write_status": "ok",
    }
    if any(info.get(key) != value for key, value in required_states.items()):
        raise CleanupError("Redis AOF/RDB health is uncertain")
    if (
        _parse_nonnegative(info.get("evicted_keys"), "evicted_keys")
        != manifest.redis.evicted_keys
        or _write_error_total(info) != manifest.redis.write_error_total
    ):
        raise CleanupError("Redis eviction or write-error counter drifted")
    health = RedisHealth(
        _parse_nonnegative(info.get("used_memory"), "used_memory"),
        maxmemory,
        int(dbsize),
        _parse_nonnegative(
            info.get("lazyfree_pending_objects"), "lazyfree_pending_objects"
        ),
        _parse_nonnegative(info.get("aof_pending_bio_fsync"), "aof_pending_bio_fsync"),
    )
    keyspace = info.get(f"db{APPROVED_DATABASE}")
    keyspace_count = 0
    if keyspace is not None:
        match = re.fullmatch(
            r"keys=([0-9]+),expires=([0-9]+),avg_ttl=([0-9]+)", keyspace
        )
        if not match:
            raise CleanupError("Redis keyspace summary is invalid")
        keyspace_count = int(match.group(1))
    if health.dbsize != keyspace_count or health.maxmemory <= 0:
        raise CleanupError("Redis memory or key count is inconsistent")
    runtime = RedisBinding(
        container_id,
        manifest.redis.image_id,
        APPROVED_DATABASE,
        info["run_id"],
        info["redis_version"],
        info["role"],
        maxmemory,
        info["maxmemory_policy"],
        manifest.redis.evicted_keys,
        manifest.redis.write_error_total,
        manifest.redis.instance_fingerprint_sha256,
        persistence,
    )
    if _redis_fingerprint(runtime) != runtime.instance_fingerprint_sha256:
        raise CleanupError("Redis instance fingerprint drifted")
    return health


def _eval_inventory_page(
    manifest: CleanupManifest, container_id: str, cursor: str, runner: Runner
) -> dict[str, Any]:
    prefixes = [item.namespace_prefix for item in manifest.categories]
    raw = _redis_command(
        container_id,
        [
            "EVAL_RO",
            INVENTORY_LUA,
            "0",
            cursor,
            str(manifest.scan_count),
            str(len(prefixes)),
            *prefixes,
        ],
        runner,
    )
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        raise CleanupError("Redis bounded cursor response is invalid") from exc
    if not isinstance(value, dict):
        raise CleanupError("Redis bounded cursor response is invalid")
    return value


def collect_inventory(
    manifest: CleanupManifest, container_id: str, runner: Runner = _run
) -> Inventory:
    if container_id != manifest.redis.container_id:
        raise CleanupError("Redis inventory container identity changed")
    cursor = "0"
    seen_cursors: set[str] = set()
    records: dict[str, dict[str, tuple[str, int, int]]] = {
        item.category_id: {} for item in manifest.categories
    }
    unknown = 0
    vanished = 0
    for _ in range(MAX_INVENTORY_ITERATIONS):
        if cursor in seen_cursors and cursor != "0":
            raise CleanupError("Redis inventory cursor cycled")
        seen_cursors.add(cursor)
        value = _eval_inventory_page(manifest, container_id, cursor, runner)
        if set(value) != {"cursor", "rows", "unknown", "vanished"}:
            raise CleanupError("Redis inventory cursor schema is invalid")
        next_cursor = value["cursor"]
        rows = value["rows"]
        if (
            not isinstance(next_cursor, str)
            or not next_cursor.isdigit()
            or not isinstance(rows, list)
            or not _is_plain_int(value["unknown"])
            or value["unknown"] < 0
            or not _is_plain_int(value["vanished"])
            or value["vanished"] < 0
        ):
            raise CleanupError("Redis inventory cursor values are invalid")
        unknown += value["unknown"]
        vanished += value["vanished"]
        for row in rows:
            if not isinstance(row, list) or len(row) != 5:
                raise CleanupError("Redis inventory row is invalid")
            category_index, token, key_type, ttl, memory = row
            if (
                not _is_plain_int(category_index)
                or not 1 <= category_index <= len(manifest.categories)
                or not isinstance(token, str)
                or not KEY_TOKEN_RE.fullmatch(token)
                or not isinstance(key_type, str)
                or not TYPE_RE.fullmatch(key_type)
                or not _is_plain_int(ttl)
                or ttl < -1
                or not _is_plain_int(memory)
                or memory <= 0
            ):
                raise CleanupError("Redis inventory row values are invalid")
            category = manifest.categories[category_index - 1]
            previous = records[category.category_id].get(token)
            current = (key_type, ttl, memory)
            if previous is not None and previous != current:
                raise CleanupError("Redis cursor or diagnostic token drifted")
            records[category.category_id][token] = current
        cursor = next_cursor
        if cursor == "0":
            break
    else:
        raise CleanupError("Redis inventory exceeded its cursor limit")
    if unknown or vanished:
        raise CleanupError("Redis contains unknown or unstable key categories")

    observations: dict[str, CategoryObservation] = {}
    for category in manifest.categories:
        category_records = records[category.category_id]
        type_counts = {key_type: 0 for key_type in category.allowed_types}
        persistent = 0
        expiring = 0
        diagnostic_memory = 0
        for key_type, ttl, memory in category_records.values():
            if key_type not in type_counts:
                raise CleanupError("Redis category type drifted")
            type_counts[key_type] += 1
            if ttl == -1:
                persistent += 1
            else:
                expiring += 1
            diagnostic_memory += memory
        binding = CategoryBinding(
            len(category_records),
            persistent,
            expiring,
            tuple(sorted(type_counts.items())),
        )
        observations[category.category_id] = CategoryObservation(
            binding, diagnostic_memory
        )
    dbsize = sum(item.binding.count for item in observations.values())
    binding_value = {
        "dbsize": dbsize,
        "categories": {
            category.category_id: {
                "namespace_prefix": category.namespace_prefix,
                "owner": category.owner,
                "safety_class": category.safety_class,
                "rebuildability_status": category.rebuildability_status,
                "rebuildability_evidence_sha256": (
                    category.rebuildability_evidence_sha256
                ),
                "ttl_policy": category.ttl_policy,
                "allowed_types": list(category.allowed_types),
                "expected": observations[category.category_id].binding.public(),
            }
            for category in manifest.categories
        },
    }
    return Inventory(observations, dbsize, _canonical_sha256(binding_value))


def observe_consistency(
    manifest: CleanupManifest,
    *,
    runner: Runner = _run,
    host_probe: HostProbe = _default_host_probe,
    now: dt.datetime | None = None,
) -> ConsistentObservation:
    current = now or _utc_now()
    _ensure_evidence_current(manifest, current)
    _validate_host_checkout(manifest, runner, host_probe)
    container_id = _inspect_redis_container(manifest, runner)
    health_before = _validate_redis_health(manifest, container_id, runner)
    first = collect_inventory(manifest, container_id, runner)
    if _inspect_redis_container(manifest, runner) != container_id:
        raise CleanupError("Redis container identity drifted between cursor passes")
    health_between = _validate_redis_health(manifest, container_id, runner)
    second = collect_inventory(manifest, container_id, runner)
    health_after = _validate_redis_health(manifest, container_id, runner)
    if _inspect_redis_container(manifest, runner) != container_id:
        raise CleanupError("Redis container identity drifted after cursor passes")
    _validate_host_checkout(manifest, runner, host_probe)
    _ensure_evidence_current(manifest, _utc_now())
    if not health_before == health_between == health_after:
        raise CleanupError(
            "Redis health or allocator memory drifted across cursor passes"
        )
    if health_after.dbsize != first.dbsize or health_after.dbsize != second.dbsize:
        raise CleanupError("Redis DB size drifted across cursor passes")
    if health_after.lazyfree_pending_objects or health_after.aof_pending_bio_fsync:
        raise CleanupError("Redis recovery is not quiescent")
    expected = {item.category_id: item.expected for item in manifest.categories}
    first_actual = {
        category_id: observation.binding
        for category_id, observation in first.observations.items()
    }
    second_actual = {
        category_id: observation.binding
        for category_id, observation in second.observations.items()
    }
    if (
        first_actual != expected
        or second_actual != expected
        or first.dbsize != manifest.expected_dbsize
        or second.dbsize != manifest.expected_dbsize
    ):
        raise CleanupError("Redis category count, TTL, or type binding drifted")
    if (
        first.binding_sha256 != manifest.inventory_binding_sha256
        or second.binding_sha256 != manifest.inventory_binding_sha256
        or first.binding_sha256 != second.binding_sha256
    ):
        raise CleanupError("Redis inventory binding fingerprint drifted")
    return ConsistentObservation(health_after, second, 2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="always denied: exact-key execution is intentionally unimplemented",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        manifest = load_manifest(args.manifest)
        if args.execute:
            raise CleanupError(
                "GATE-04 execution is hard-disabled: exact-key selection is not proven"
            )
        result = observe_consistency(manifest)
        emit(
            "redis_cleanup_observation",
            "CONSISTENT_READ_ONLY_OBSERVATION",
            manifest_sha256=manifest.digest,
            operation_id=manifest.operation_id,
            exact_dbsize=result.inventory.dbsize,
            inventory_binding_sha256=result.inventory.binding_sha256,
            inventory_passes=result.inventory_passes,
            used_memory_percent_basis_points=result.health.used_percent_basis_points,
            target_max_memory_percent=TARGET_MAX_MEMORY_PERCENT,
            target_reached=result.health.target_reached,
            execution_implemented=EXECUTION_IMPLEMENTED,
            execution_authorized=False,
            gate04_closed=True,
            is_snapshot=False,
            is_proof=False,
            is_approval=False,
            exact_key_selection_proven=False,
            memory_usage_semantics="NONADDITIVE_DIAGNOSTIC_ONLY",
            diagnostic_memory_is_allocator_share=False,
            raw_keys_included=False,
        )
        return 0
    except CleanupError as exc:
        emit(
            "redis_cleanup",
            "denied",
            reason=str(exc),
            execution_implemented=EXECUTION_IMPLEMENTED,
            raw_keys_included=False,
        )
        return 2
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError, TypeError):
        emit(
            "redis_cleanup",
            "denied",
            reason="unexpected local runtime failure",
            execution_implemented=EXECUTION_IMPLEMENTED,
            raw_keys_included=False,
        )
        return 2
    except Exception:
        emit(
            "redis_cleanup",
            "denied",
            reason="internal fail-closed boundary",
            execution_implemented=EXECUTION_IMPLEMENTED,
            raw_keys_included=False,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
