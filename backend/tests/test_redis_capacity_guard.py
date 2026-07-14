from __future__ import annotations

import dataclasses
import hashlib
import io
import importlib.util
import json
import os
import socket
import stat
import struct
import sys
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "ops" / "redis_capacity_guard.py"
WRAPPER_PATH = ROOT / "ops" / "redis-capacity-guard.sh"
EXAMPLE_PATH = ROOT / "ops" / "redis-capacity-guard.example.json"
SERVICE_PATH = ROOT / "ops" / "systemd" / "sealai-redis-capacity-guard.service"
SPEC = importlib.util.spec_from_file_location("redis_capacity_guard", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = guard
SPEC.loader.exec_module(guard)


RUN_ID = "a" * 40
USERNAME = "redis_guard"
AUTH_FIXTURE = "synthetic-auth-material-long-enough"
RUN_ID_HASH = hashlib.sha256(RUN_ID.encode()).hexdigest()
USERNAME_HASH = hashlib.sha256(USERNAME.encode()).hexdigest()
ACL_COMMANDS = " ".join(sorted(guard._REQUIRED_ACL_COMMAND_RULES))


def _info(**values: object) -> bytes:
    return (
        "\r\n".join(f"{key}:{value}" for key, value in values.items()) + "\r\n"
    ).encode()


class FakeRedis:
    def __init__(
        self,
        *,
        used_memory: int = 7000,
        maxmemory: int = 10000,
        maxmemory_policy: str = "noeviction",
        keys: dict[bytes, tuple[str, int, int]] | None = None,
        evicted_keys: int = 0,
        write_errors: int = 0,
        failed_read_calls: int = 0,
        unmonitored_keys: int = 0,
        run_id: str = RUN_ID,
        username: str = USERNAME,
        acl_commands: str = ACL_COMMANDS,
        acl_keys: list[bytes] | None = None,
        persistence_changes: tuple[int, int] = (5, 5),
    ) -> None:
        self.used_memory = used_memory
        self.maxmemory = maxmemory
        self.maxmemory_policy = maxmemory_policy
        self.keys = keys or {
            b"cache:one": ("string", 60_000, 0),
            b"checkpoint:one": ("ReJSON-RL", -1, 0),
            b"queue:one": ("zset", -1, 4),
        }
        self.evicted_keys = evicted_keys
        self.write_errors = write_errors
        self.failed_read_calls = failed_read_calls
        self.unmonitored_keys = unmonitored_keys
        self.run_id = run_id
        self.username = username
        self.acl_commands = acl_commands
        self.acl_keys = [b"%R~*"] if acl_keys is None else acl_keys
        self.persistence_changes = list(persistence_changes)
        self.persistence_calls = 0
        self.selected_db = 0
        self.commands: list[tuple[bytes | str | int, ...]] = []

    def __enter__(self) -> FakeRedis:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def _acl(self) -> list[Any]:
        return [
            b"flags",
            [b"on"],
            b"passwords",
            [b"not-emitted-password-hash"],
            b"commands",
            self.acl_commands.encode(),
            b"keys",
            self.acl_keys,
            b"channels",
            [],
            b"selectors",
            [],
        ]

    def command(self, *parts: bytes | str | int) -> Any:
        self.commands.append(parts)
        command = str(parts[0]).upper()
        if command == "AUTH":
            return b"OK"
        if command == "PING":
            return b"PONG"
        if command == "ACL" and str(parts[1]).upper() == "WHOAMI":
            return self.username.encode()
        if command == "ACL" and str(parts[1]).upper() == "GETUSER":
            return self._acl()
        if command == "INFO":
            section = str(parts[1]).lower()
            if section == "server":
                return _info(run_id=self.run_id, redis_version="7.4.0")
            if section == "replication":
                return _info(role="master")
            if section == "memory":
                return _info(
                    used_memory=self.used_memory,
                    maxmemory=self.maxmemory,
                    maxmemory_policy=self.maxmemory_policy,
                )
            if section == "stats":
                return _info(
                    evicted_keys=self.evicted_keys,
                    total_error_replies=self.write_errors + self.failed_read_calls,
                    rejected_connections=0,
                )
            if section == "keyspace":
                fields = {
                    "db0": f"keys={len(self.keys)},expires={sum(ttl >= 0 for _, ttl, _ in self.keys.values())},avg_ttl=1000"
                }
                if self.unmonitored_keys:
                    fields["db1"] = f"keys={self.unmonitored_keys},expires=0,avg_ttl=0"
                return _info(**fields)
            if section == "commandstats":
                return _info(
                    cmdstat_set=f"calls=1,usec=1,usec_per_call=1.00,rejected_calls=0,failed_calls={self.write_errors}",
                    cmdstat_get=f"calls=1,usec=1,usec_per_call=1.00,rejected_calls=0,failed_calls={self.failed_read_calls}",
                )
            if section == "persistence":
                index = min(self.persistence_calls, len(self.persistence_changes) - 1)
                value = self.persistence_changes[index]
                self.persistence_calls += 1
                return _info(rdb_changes_since_last_save=value)
        if command == "SELECT":
            self.selected_db = int(parts[1])
            return b"OK"
        if command == "DBSIZE":
            return len(self.keys) if self.selected_db == 0 else self.unmonitored_keys
        if command == "SCAN":
            return [b"0", list(self.keys)]
        raise AssertionError(f"unexpected fake command: {parts[0]}")

    def pipeline(self, commands: list[tuple[bytes | str | int, ...]]) -> list[Any]:
        self.commands.extend(commands)
        result: list[Any] = []
        for command in commands:
            name = str(command[0]).upper()
            key = command[1]
            assert isinstance(key, bytes)
            key_type, ttl, depth = self.keys[key]
            if name == "TYPE":
                result.append(key_type.encode())
            elif name == "PTTL":
                result.append(ttl)
            elif name in {"LLEN", "SCARD", "XLEN", "ZCARD"}:
                result.append(depth)
            else:
                raise AssertionError(f"unexpected fake pipeline command: {name}")
        return result


def _base_config(tmp_path: Path) -> dict[str, Any]:
    return {
        "version": 2,
        "redis": {
            "unix_socket_path": "/tmp/sealai-test-redis.sock",
            "expected_socket_uid": os.geteuid(),
            "expected_socket_gid": os.getegid(),
            "expected_socket_mode": 0o600,
            "expected_peer_uid": os.geteuid(),
            "expected_peer_gid": os.getegid(),
            "expected_run_id_sha256": RUN_ID_HASH,
            "expected_acl_username_sha256": USERNAME_HASH,
            "expected_role": "master",
            "expected_maxmemory_bytes": 10000,
            "expected_maxmemory_policy": "noeviction",
            "databases": [0],
            "operation_timeout_ms": 5000,
        },
        "state_dir": str(tmp_path / "state"),
        "lock_file": str(tmp_path / "run" / "guard.lock"),
        "scan_count": 100,
        "maximum_keys": 1000,
        "categories": [
            {
                "id": "cache",
                "owner": "paperless",
                "database": 0,
                "prefixes": ["cache:"],
                "expected_types": ["string"],
                "ttl_policy": "required",
                "kind": "cache",
                "max_keys": 10,
                "max_queue_depth": None,
            },
            {
                "id": "checkpoint",
                "owner": "paperless",
                "database": 0,
                "prefixes": ["checkpoint:"],
                "expected_types": ["ReJSON-RL"],
                "ttl_policy": "optional",
                "kind": "checkpoint",
                "max_keys": 10,
                "max_queue_depth": None,
            },
            {
                "id": "queue",
                "owner": "paperless",
                "database": 0,
                "prefixes": ["queue:"],
                "expected_types": ["zset"],
                "ttl_policy": "optional",
                "kind": "queue",
                "max_keys": 10,
                "max_queue_depth": 10,
            },
        ],
    }


def _write_inputs(
    tmp_path: Path, config: dict[str, Any] | None = None
) -> tuple[Path, Path]:
    config_path = tmp_path / "guard.json"
    credential_path = tmp_path / "credential.json"
    config_path.write_text(
        json.dumps(config or _base_config(tmp_path)), encoding="utf-8"
    )
    credential_path.write_text(
        json.dumps({"username": USERNAME, "password": AUTH_FIXTURE}), encoding="utf-8"
    )
    os.chmod(config_path, 0o600)
    os.chmod(credential_path, 0o600)
    return config_path, credential_path


def _state(
    *,
    status: str = "healthy",
    binding_fingerprint: str = "f" * 64,
    healthy_sample_count: int = 1,
    write_errors: int = 0,
    evictions: int = 0,
) -> Any:
    now = guard._timestamp(guard._utc_now())
    return guard.State(
        status=status,
        decision="observe" if status != "critical" else "deny",
        observed_at=now,
        last_transition_at=now,
        binding_fingerprint=binding_fingerprint,
        healthy_sample_count=healthy_sample_count,
        write_error_total=write_errors,
        evicted_keys_total=evictions,
    )


def _observe(
    tmp_path: Path,
    fake: FakeRedis,
    previous: Any | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Any]:
    config_path, credential_path = _write_inputs(tmp_path, config)
    config = guard._load_config(config_path)
    credential = guard._load_credential(credential_path, USERNAME_HASH)
    return guard._observe(fake, config, credential, previous)


@pytest.mark.parametrize(
    ("used", "status", "decision", "reason", "exit_attention"),
    [
        (6999, "healthy", "observe", "observation_healthy", False),
        (7000, "healthy", "observe", "observation_healthy", False),
        (7499, "above_target", "observe", "memory_target_exceeded", True),
        (7500, "warning", "observe", "memory_warning_threshold_reached", True),
        (7999, "warning", "observe", "memory_warning_threshold_reached", True),
        (8000, "critical", "deny", "memory_hard_deny_threshold_reached", False),
    ],
)
def test_fixed_memory_thresholds(
    tmp_path: Path,
    used: int,
    status: str,
    decision: str,
    reason: str,
    exit_attention: bool,
) -> None:
    payload, state = _observe(tmp_path, FakeRedis(used_memory=used))

    assert state.status == status
    assert payload["decision"] == decision
    assert reason in payload["reason_codes"]
    assert (status in {"above_target", "warning"}) is exit_attention


def test_redacted_aggregate_contains_required_metrics_and_no_raw_material(
    tmp_path: Path,
) -> None:
    fake = FakeRedis()
    payload, _state_value = _observe(tmp_path, fake)
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["redis_instance_binding"] == "verified"
    assert payload["redis_data_mutated"] is False
    assert payload["memory"] == {
        "used_bytes": 7000,
        "max_bytes": 10000,
        "usage_basis_points": 7000,
        "maxmemory_policy": "noeviction",
    }
    assert payload["keys"]["scanned_count"] == 3
    assert payload["keys"]["expiring_count"] == 1
    assert payload["keys"]["persistent_count"] == 2
    assert payload["ttl"] == {
        "minimum_ms": 60000,
        "average_ms": 60000,
        "maximum_ms": 60000,
    }
    assert payload["queues"] == {"key_count": 1, "total_depth": 4, "maximum_depth": 4}
    assert payload["evictions"]["total"] == 0
    assert payload["write_errors"]["potential_write_total"] == 0
    for forbidden in (
        "cache:one",
        "checkpoint:one",
        "queue:one",
        "cache:",
        "checkpoint:",
        "queue:",
        RUN_ID,
        USERNAME,
        AUTH_FIXTURE,
        "not-emitted-password-hash",
        str(tmp_path),
    ):
        assert forbidden not in rendered

    issued = {str(command[0]).upper() for command in fake.commands}
    assert issued <= guard.RedisReadOnlyClient._SINGLE_COMMANDS | {"ACL"}
    assert not issued & {"SET", "DEL", "EXPIRE", "EVAL", "FLUSHALL", "CONFIG"}


@pytest.mark.parametrize(
    ("keys", "reason"),
    [
        ({b"unknown:key": ("string", -1, 0)}, "unowned_namespace_keys"),
        ({b"cache:one": ("string", -1, 0)}, "ttl_policy_violation"),
        ({b"cache:one": ("hash", 1000, 0)}, "unexpected_key_type"),
        ({b"queue:one": ("zset", -1, 11)}, "queue_depth_limit_exceeded"),
    ],
)
def test_namespace_ttl_type_and_queue_violations_deny(
    tmp_path: Path,
    keys: dict[bytes, tuple[str, int, int]],
    reason: str,
) -> None:
    payload, state = _observe(tmp_path, FakeRedis(keys=keys))

    assert state.status == "critical"
    assert payload["decision"] == "deny"
    assert reason in payload["reason_codes"]


def test_unmonitored_database_keys_deny_without_scanning_raw_keys(
    tmp_path: Path,
) -> None:
    payload, state = _observe(tmp_path, FakeRedis(unmonitored_keys=2))

    assert state.status == "critical"
    assert payload["keys"]["unknown_category_count"] == 2
    assert payload["keys"]["unmonitored_database_key_count"] == 2
    assert "unowned_namespace_keys" in payload["reason_codes"]


def test_write_error_and_eviction_deltas_fail_closed(tmp_path: Path) -> None:
    first, first_state = _observe(
        tmp_path, FakeRedis(write_errors=3, evicted_keys=2), previous=None
    )
    assert first_state.status == "critical"
    assert "potential_write_errors_baseline_unknown" in first["reason_codes"]
    assert "evictions_baseline_unknown" in first["reason_codes"]

    _baseline_payload, baseline_state = _observe(tmp_path, FakeRedis())
    same_binding_previous = dataclasses.replace(
        baseline_state, write_error_total=3, evicted_keys_total=2
    )
    second, second_state = _observe(
        tmp_path,
        FakeRedis(write_errors=4, evicted_keys=3),
        previous=same_binding_previous,
    )
    assert second_state.status == "critical"
    assert second["write_errors"]["potential_write_delta"] == 1
    assert second["evictions"]["delta"] == 1
    assert "potential_write_errors_increased" in second["reason_codes"]
    assert "evictions_increased" in second["reason_codes"]


def test_counter_regression_and_concurrent_keyspace_change_deny(tmp_path: Path) -> None:
    _baseline_payload, baseline_state = _observe(tmp_path, FakeRedis())
    payload, state = _observe(
        tmp_path,
        FakeRedis(write_errors=1, evicted_keys=1, persistence_changes=(5, 6)),
        previous=dataclasses.replace(
            baseline_state, write_error_total=2, evicted_keys_total=2
        ),
    )

    assert state.status == "critical"
    assert "potential_write_errors_counter_regressed" in payload["reason_codes"]
    assert "evictions_counter_regressed" in payload["reason_codes"]
    assert "concurrent_keyspace_change" in payload["reason_codes"]


@pytest.mark.parametrize(
    ("fake", "reason"),
    [
        (FakeRedis(run_id="b" * 40), "redis_instance_binding_mismatch"),
        (FakeRedis(username="other_user"), "redis_acl_identity_mismatch"),
        (FakeRedis(maxmemory=20000), "redis_maxmemory_binding_mismatch"),
        (
            FakeRedis(maxmemory_policy="allkeys-lru"),
            "redis_maxmemory_policy_binding_mismatch",
        ),
        (
            FakeRedis(acl_commands="-@all +ping +set"),
            "redis_acl_not_strictly_read_only",
        ),
        (FakeRedis(acl_keys=[b"~*"]), "redis_acl_not_strictly_read_only"),
    ],
)
def test_exact_instance_and_read_only_acl_contract_fail_closed(
    tmp_path: Path, fake: FakeRedis, reason: str
) -> None:
    with pytest.raises(guard.GuardError, match=reason):
        _observe(tmp_path, fake)


def test_command_boundary_rejects_every_mutator_before_transport() -> None:
    for command in ("SET", "DEL", "EXPIRE", "EVAL", "FLUSHDB", "CONFIG", "JSON.SET"):
        with pytest.raises(
            guard.GuardError, match="internal_command_boundary_violation"
        ):
            guard.RedisReadOnlyClient._validate_command((command, "probe"))
    guard.RedisReadOnlyClient._validate_command(("ACL", "WHOAMI"))
    guard.RedisReadOnlyClient._validate_command(("ACL", "GETUSER", USERNAME))
    with pytest.raises(guard.GuardError, match="internal_command_boundary_violation"):
        guard.RedisReadOnlyClient._validate_command(("ACL", "SETUSER", USERNAME))


def test_unix_socket_peer_failure_sends_no_auth_or_other_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = Path(f"/tmp/sealai-guard-peer-{os.getpid()}-{id(tmp_path)}.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    received: list[bytes] = []
    try:
        server.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        server.listen(1)
        config = _base_config(tmp_path)
        config["redis"]["unix_socket_path"] = str(socket_path)
        metadata = socket_path.stat()
        config["redis"]["expected_socket_uid"] = metadata.st_uid
        config["redis"]["expected_socket_gid"] = metadata.st_gid
        config_path, _credential_path = _write_inputs(tmp_path, config)
        binding = guard._load_config(config_path).redis
        socket_identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_uid,
            metadata.st_gid,
            stat.S_IMODE(metadata.st_mode),
        )
        monkeypatch.setattr(
            guard, "_validated_socket_identity", lambda _binding: socket_identity
        )

        def accept_once() -> None:
            connection, _address = server.accept()
            with connection:
                connection.settimeout(2)
                received.append(connection.recv(4096))

        thread = threading.Thread(target=accept_once, daemon=True)
        thread.start()
        monkeypatch.setattr(
            guard,
            "_verify_peer_credentials",
            lambda _connection, _binding: (_ for _ in ()).throw(
                guard.GuardError("redis_peer_identity_mismatch", guard.EXIT_OBSERVATION)
            ),
        )
        with pytest.raises(guard.GuardError, match="redis_peer_identity_mismatch"):
            with guard.RedisReadOnlyClient(binding):
                pytest.fail("unverified peer must never enter the client context")
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert received == [b""]
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)


def test_linux_peer_credentials_are_bound_to_exact_uid_and_gid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path, _credential_path = _write_inputs(tmp_path)
    binding = guard._load_config(config_path).redis
    monkeypatch.setattr(guard.socket, "SO_PEERCRED", 17, raising=False)

    class PeerSocket:
        def __init__(self, uid: int, gid: int) -> None:
            self.uid = uid
            self.gid = gid

        def getsockopt(self, _level: int, _option: int, _length: int) -> bytes:
            return struct.pack("3i", 4242, self.uid, self.gid)

    guard._verify_peer_credentials(
        PeerSocket(binding.expected_peer_uid, binding.expected_peer_gid), binding
    )
    with pytest.raises(guard.GuardError, match="redis_peer_identity_mismatch"):
        guard._verify_peer_credentials(
            PeerSocket(binding.expected_peer_uid + 1, binding.expected_peer_gid),
            binding,
        )


def test_socket_metadata_rejects_symlink_and_inode_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_path = Path(f"/tmp/sealai-guard-meta-{os.getpid()}-{id(tmp_path)}.sock")
    link_path = Path(f"{socket_path}.link")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        link_path.symlink_to(socket_path)
        config = _base_config(tmp_path)
        config["redis"]["unix_socket_path"] = str(link_path)
        config_path, _credential_path = _write_inputs(tmp_path, config)
        binding = guard._load_config(config_path).redis
        with pytest.raises(guard.GuardError, match="redis_socket_identity_mismatch"):
            guard._validated_socket_identity(binding)

        config["redis"]["unix_socket_path"] = str(socket_path)
        config_path, _credential_path = _write_inputs(tmp_path, config)
        binding = guard._load_config(config_path).redis
        identities = iter(
            [
                (1, 10, os.geteuid(), os.getegid(), 0o600),
                (1, 11, os.geteuid(), os.getegid(), 0o600),
            ]
        )
        monkeypatch.setattr(
            guard, "_validated_socket_identity", lambda _binding: next(identities)
        )
        server.listen(1)
        received: list[bytes] = []

        def accept_once() -> None:
            connection, _address = server.accept()
            with connection:
                received.append(connection.recv(4096))

        thread = threading.Thread(target=accept_once, daemon=True)
        thread.start()
        with pytest.raises(
            guard.GuardError, match="redis_socket_changed_during_connect"
        ):
            with guard.RedisReadOnlyClient(binding):
                pytest.fail("inode drift must fail before the context is entered")
        thread.join(timeout=3)
        assert received == [b""]
    finally:
        server.close()
        link_path.unlink(missing_ok=True)
        socket_path.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "wire",
    [
        f"${guard.MAX_RESP_BULK_BYTES + 1}\r\n".encode(),
        (b"*1\r\n" * (guard.MAX_RESP_DEPTH + 2)) + b"+OK\r\n",
        f"*{guard.MAX_RESP_ARRAY_ITEMS + 1}\r\n".encode(),
    ],
)
def test_resp_poison_limits_and_depth_fail_closed(wire: bytes) -> None:
    binding = guard.RedisBinding(
        unix_socket_path=Path("/tmp/unused.sock"),
        expected_socket_uid=0,
        expected_socket_gid=0,
        expected_socket_mode=0o600,
        expected_peer_uid=0,
        expected_peer_gid=0,
        expected_run_id_sha256=RUN_ID_HASH,
        expected_acl_username_sha256=USERNAME_HASH,
        expected_role="master",
        expected_maxmemory_bytes=10000,
        expected_maxmemory_policy="noeviction",
        databases=(0,),
        operation_timeout_ms=1000,
    )
    client = guard.RedisReadOnlyClient(binding)
    client._reader = io.BytesIO(wire)
    with pytest.raises(
        guard.GuardError, match="invalid_redis_protocol|redis_response_budget_exceeded"
    ):
        client._read_response(guard.RespBudget())


def test_resp_budget_is_global_across_one_pipeline_response() -> None:
    config = guard.RespBudget(bytes_remaining=8, elements_remaining=2)
    binding = guard.RedisBinding(
        unix_socket_path=Path("/tmp/unused.sock"),
        expected_socket_uid=0,
        expected_socket_gid=0,
        expected_socket_mode=0o600,
        expected_peer_uid=0,
        expected_peer_gid=0,
        expected_run_id_sha256=RUN_ID_HASH,
        expected_acl_username_sha256=USERNAME_HASH,
        expected_role="master",
        expected_maxmemory_bytes=10000,
        expected_maxmemory_policy="noeviction",
        databases=(0,),
        operation_timeout_ms=1000,
    )
    client = guard.RedisReadOnlyClient(binding)
    client._reader = io.BytesIO(b"+OK\r\n+OK\r\n")
    assert client._read_response(config) == b"OK"
    with pytest.raises(guard.GuardError, match="redis_response_budget_exceeded"):
        client._read_response(config)


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda config: config["redis"].update(unix_socket_path="redis.sock"),
            "invalid_redis_socket_path",
        ),
        (
            lambda config: config["redis"].update(
                unix_socket_path="/run/../run/redis.sock"
            ),
            "invalid_redis_socket_path",
        ),
        (
            lambda config: config["redis"].update(expected_socket_mode=0o766),
            "unsafe_redis_socket_mode",
        ),
        (
            lambda config: config["redis"].update(expected_run_id_sha256="0" * 64),
            "placeholder_instance_binding",
        ),
        (
            lambda config: config["categories"][1].update(prefixes=["cache:child:"]),
            "overlapping_category_prefixes",
        ),
    ],
)
def test_config_rejects_ambiguous_or_unbound_inputs(
    tmp_path: Path, mutate: Any, reason: str
) -> None:
    config = _base_config(tmp_path)
    mutate(config)
    config_path, _credential_path = _write_inputs(tmp_path, config)

    with pytest.raises(guard.GuardError, match=reason):
        guard._load_config(config_path)


def test_config_and_credential_permissions_and_identity_are_enforced(
    tmp_path: Path,
) -> None:
    config_path, credential_path = _write_inputs(tmp_path)
    os.chmod(config_path, 0o666)
    with pytest.raises(guard.GuardError, match="unsafe_file_permissions"):
        guard._load_config(config_path)

    os.chmod(config_path, 0o600)
    os.chmod(credential_path, 0o644)
    with pytest.raises(guard.GuardError, match="unsafe_file_permissions"):
        guard._load_credential(credential_path, USERNAME_HASH)

    os.chmod(credential_path, 0o600)
    with pytest.raises(guard.GuardError, match="acl_identity_binding_mismatch"):
        guard._load_credential(credential_path, "f" * 64)

    config_link = tmp_path / "guard-link.json"
    config_link.symlink_to(config_path)
    with pytest.raises(guard.GuardError, match="unsafe_or_unreadable_file"):
        guard._load_config(config_link)


def test_scan_key_bound_fails_closed(tmp_path: Path) -> None:
    config = _base_config(tmp_path)
    config["maximum_keys"] = 1
    config_path, credential_path = _write_inputs(tmp_path, config)
    loaded = guard._load_config(config_path)
    credential = guard._load_credential(credential_path, USERNAME_HASH)

    with pytest.raises(guard.GuardError, match="scan_key_limit_exceeded"):
        guard._observe(FakeRedis(), loaded, credential, None)


def test_main_check_writes_only_bounded_redacted_local_spools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, credential_path = _write_inputs(tmp_path)
    fake = FakeRedis(used_memory=7500)
    monkeypatch.setattr(guard, "RedisReadOnlyClient", lambda _binding: fake)

    exit_code = guard.main(
        [
            "--config",
            str(config_path),
            "--credential-file",
            str(credential_path),
            "check",
        ]
    )
    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    state_dir = tmp_path / "state"

    assert exit_code == guard.EXIT_ATTENTION
    assert len(output.splitlines()) == 1
    assert payload["state_written"] is True
    assert payload["alert_written"] is True
    assert payload["external_alert_delivery"] == "BLOCKED_EXTERNAL"
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((state_dir / "state.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((state_dir / "alerts" / "latest.json").stat().st_mode) == 0o600
    assert sorted(path.name for path in (state_dir / "alerts").iterdir()) == [
        "latest.json"
    ]
    for path in (state_dir / "state.json", state_dir / "alerts" / "latest.json"):
        rendered = path.read_text(encoding="utf-8")
        assert "cache:one" not in rendered
        assert "cache:" not in rendered
        assert USERNAME not in rendered
        assert AUTH_FIXTURE not in rendered
        assert str(tmp_path) not in rendered


def test_dry_run_and_assert_stable_never_write_local_spools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, credential_path = _write_inputs(tmp_path)
    monkeypatch.setattr(guard, "RedisReadOnlyClient", lambda _binding: FakeRedis())
    common = ["--config", str(config_path), "--credential-file", str(credential_path)]

    dry_exit = guard.main([*common, "--dry-run", "check"])
    dry_payload = json.loads(capsys.readouterr().out)
    assert dry_exit == guard.EXIT_OK
    assert dry_payload["state_written"] is False
    assert not (tmp_path / "state").exists()

    assert_exit = guard.main([*common, "assert-stable"])
    assert_payload = json.loads(capsys.readouterr().out)
    assert assert_exit == guard.EXIT_ASSERT_UNSTABLE
    assert assert_payload["decision"] == "deny"
    assert "stable_monitor_state_not_proven" in assert_payload["reason_codes"]
    assert not (tmp_path / "state").exists()


def test_assert_stable_requires_fresh_prior_healthy_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, credential_path = _write_inputs(tmp_path)
    monkeypatch.setattr(guard, "RedisReadOnlyClient", lambda _binding: FakeRedis())
    common = ["--config", str(config_path), "--credential-file", str(credential_path)]
    assert guard.main([*common, "check"]) == guard.EXIT_OK
    capsys.readouterr()

    state_file = tmp_path / "state" / "state.json"
    before = state_file.read_bytes()
    assert guard.main([*common, "assert-stable"]) == guard.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "ok"
    assert state_file.read_bytes() == before

    state = json.loads(state_file.read_text(encoding="utf-8"))
    stale = guard._utc_now() - timedelta(seconds=guard.STATE_MAX_AGE_SECONDS + 1)
    state["observed_at"] = guard._timestamp(stale)
    state_file.write_text(json.dumps(state), encoding="utf-8")
    os.chmod(state_file, 0o600)
    assert guard.main([*common, "assert-stable"]) == guard.EXIT_ASSERT_UNSTABLE
    capsys.readouterr()


def test_binding_drift_resets_deltas_and_requires_two_new_healthy_samples(
    tmp_path: Path,
) -> None:
    first_payload, first_state = _observe(tmp_path, FakeRedis())
    second_payload, second_state = _observe(tmp_path, FakeRedis(), previous=first_state)
    assert first_payload["binding_continuity"] == "new"
    assert first_state.healthy_sample_count == 1
    assert second_payload["binding_continuity"] == "continued"
    assert second_state.healthy_sample_count == 2

    changed_config = _base_config(tmp_path)
    changed_config["categories"][0]["max_keys"] = 11
    reset_payload, reset_state = _observe(
        tmp_path, FakeRedis(), previous=second_state, config=changed_config
    )
    assert reset_payload["binding_continuity"] == "reset"
    assert reset_payload["write_errors"]["potential_write_delta"] is None
    assert reset_payload["evictions"]["delta"] is None
    assert reset_state.healthy_sample_count == 1
    assert reset_state.binding_fingerprint != second_state.binding_fingerprint

    continued_payload, continued_state = _observe(
        tmp_path, FakeRedis(), previous=reset_state, config=changed_config
    )
    assert continued_payload["binding_continuity"] == "continued"
    assert continued_state.healthy_sample_count == 2


def test_assert_stable_denies_binding_drift_until_second_matching_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, credential_path = _write_inputs(tmp_path)
    monkeypatch.setattr(guard, "RedisReadOnlyClient", lambda _binding: FakeRedis())
    common = ["--config", str(config_path), "--credential-file", str(credential_path)]
    assert guard.main([*common, "check"]) == guard.EXIT_OK
    capsys.readouterr()

    changed_config = _base_config(tmp_path)
    changed_config["categories"][0]["max_keys"] = 11
    config_path.write_text(json.dumps(changed_config), encoding="utf-8")
    os.chmod(config_path, 0o600)
    assert guard.main([*common, "assert-stable"]) == guard.EXIT_ASSERT_UNSTABLE
    payload = json.loads(capsys.readouterr().out)
    assert payload["binding_continuity"] == "reset"
    assert payload["healthy_sample_count"] == 1

    assert guard.main([*common, "check"]) == guard.EXIT_OK
    capsys.readouterr()
    assert guard.main([*common, "assert-stable"]) == guard.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["binding_continuity"] == "continued"
    assert payload["healthy_sample_count"] == 2


def test_old_state_schema_and_state_symlink_fail_closed_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, credential_path = _write_inputs(tmp_path)
    monkeypatch.setattr(guard, "RedisReadOnlyClient", lambda _binding: FakeRedis())
    common = ["--config", str(config_path), "--credential-file", str(credential_path)]
    assert guard.main([*common, "check"]) == guard.EXIT_OK
    capsys.readouterr()
    state_file = tmp_path / "state" / "state.json"
    old_state = json.loads(state_file.read_text(encoding="utf-8"))
    old_state["schema_version"] = 1
    old_state.pop("binding_fingerprint")
    old_state.pop("healthy_sample_count")
    state_file.write_text(json.dumps(old_state), encoding="utf-8")
    os.chmod(state_file, 0o600)
    before = state_file.read_bytes()
    assert guard.main([*common, "check"]) == guard.EXIT_CONFIG
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason_codes"] == ["invalid_state_schema"]
    assert state_file.read_bytes() == before

    state_file.unlink()
    target = tmp_path / "outside-state.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o600)
    state_file.symlink_to(target)
    loaded = guard._load_config(config_path)
    with pytest.raises(guard.GuardError, match="unsafe_or_unreadable_file"):
        guard._read_state(loaded)


def test_error_output_is_stable_redacted_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, credential_path = _write_inputs(tmp_path)
    monkeypatch.setattr(
        guard, "RedisReadOnlyClient", lambda _binding: FakeRedis(run_id="b" * 40)
    )

    exit_code = guard.main(
        [
            "--config",
            str(config_path),
            "--credential-file",
            str(credential_path),
            "check",
        ]
    )
    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert exit_code == guard.EXIT_OBSERVATION
    assert payload["decision"] == "deny"
    assert payload["reason_codes"] == ["redis_instance_binding_mismatch"]
    assert payload["redis_data_mutated"] is False
    assert RUN_ID not in output
    assert USERNAME not in output
    assert AUTH_FIXTURE not in output
    assert str(tmp_path) not in output


def test_example_is_non_runnable_and_wrapper_clears_environment(tmp_path: Path) -> None:
    example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    example["state_dir"] = str(tmp_path / "state")
    example["lock_file"] = str(tmp_path / "run" / "guard.lock")
    config_path, _credential_path = _write_inputs(tmp_path, example)
    with pytest.raises(guard.GuardError, match="placeholder_instance_binding"):
        guard._load_config(config_path)

    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    assert wrapper.startswith("#!/bin/bash -p\n")
    assert "/usr/bin/env -i" in wrapper
    assert "/usr/bin/python3 -I" in wrapper
    service = SERVICE_PATH.read_text(encoding="utf-8")
    assert "LoadCredentialEncrypted=redis-auth" in service
    assert "LoadCredentialEncrypted=redis-guard-config" in service
    assert "User=sealai-redis-guard" in service
    assert "RestrictAddressFamilies=AF_UNIX" in service
    assert "AF_INET" not in service
    assert "MemoryMax=256M" in service
    assert "TasksMax=32" in service
    assert "SuccessExitStatus=10\n" in service


def test_no_memory_usage_command_or_redis_mutator_is_reachable() -> None:
    allowed = guard.RedisReadOnlyClient._SINGLE_COMMANDS
    assert "MEMORY" not in allowed
    assert allowed == {
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
    assert guard.MEMORY_TARGET_PERCENT == 70
    assert guard.MEMORY_WARNING_PERCENT < guard.MEMORY_HARD_DENY_PERCENT == 80
