from __future__ import annotations

import datetime as dt
import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "ops" / "redis_legacy_cleanup.py"
SPEC = importlib.util.spec_from_file_location("redis_legacy_cleanup", MODULE_PATH)
assert SPEC and SPEC.loader
cleanup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cleanup
SPEC.loader.exec_module(cleanup)

HOSTNAME = "production.example"
MACHINE_SHA256 = "a" * 64
COMMIT = "b" * 40
TREE = "c" * 40
CONTAINER_ID = "d" * 64
IMAGE_ID = "sha256:" + "e" * 64
RUN_ID = "f" * 40
MAXMEMORY = 1024**3
LASTSAVE = 1_700_000_000


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def timestamp(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def category(
    category_id: str,
    prefix: str,
    safety_class: str,
    *,
    count: int,
    key_type: str,
    status: str,
    ttl_policy: str = "persistent_only",
) -> dict[str, Any]:
    persistent = count if ttl_policy == "persistent_only" else 0
    return {
        "category_id": category_id,
        "namespace_prefix": prefix,
        "owner": "paperless",
        "safety_class": safety_class,
        "rebuildability": {
            "status": status,
            "evidence_sha256": "1" * 64,
        },
        "ttl_policy": ttl_policy,
        "allowed_types": [key_type],
        "expected": {
            "count": count,
            "persistent_count": persistent,
            "expiring_count": count - persistent,
            "type_counts": {key_type: count},
        },
    }


def manifest_value(now: dt.datetime | None = None) -> dict[str, Any]:
    captured_at = now or utc_now()
    host = cleanup.HostBinding(HOSTNAME, MACHINE_SHA256)
    checkout = cleanup.CheckoutBinding(
        cleanup.PRODUCTION_CHECKOUT,
        "main",
        COMMIT,
        TREE,
        "",
    )
    checkout = cleanup.CheckoutBinding(
        checkout.path,
        checkout.branch,
        checkout.commit,
        checkout.tree,
        cleanup._repository_fingerprint(host, checkout),
    )
    persistence = cleanup.PersistenceBinding(
        "yes",
        "900 1 300 10 60 10000",
        Path("/data"),
        "dump.rdb",
        "appendonlydir",
        LASTSAVE,
        "",
    )
    persistence = cleanup.PersistenceBinding(
        persistence.appendonly,
        persistence.save,
        persistence.directory,
        persistence.dbfilename,
        persistence.appenddirname,
        persistence.lastsave_epoch,
        cleanup._persistence_fingerprint(persistence),
    )
    redis = cleanup.RedisBinding(
        CONTAINER_ID,
        IMAGE_ID,
        cleanup.APPROVED_DATABASE,
        RUN_ID,
        "7.4.0",
        "master",
        MAXMEMORY,
        "noeviction",
        0,
        0,
        "",
        persistence,
    )
    redis = cleanup.RedisBinding(
        redis.container_id,
        redis.image_id,
        redis.database,
        redis.run_id,
        redis.version,
        redis.role,
        redis.maxmemory_bytes,
        redis.maxmemory_policy,
        redis.evicted_keys,
        redis.write_error_total,
        cleanup._redis_fingerprint(redis),
        redis.persistence,
    )
    raw_categories = [
        category(
            "legacy-checkpoints",
            "checkpoint:",
            "legacy_rebuildable",
            count=2,
            key_type="ReJSON-RL",
            status="VERIFIED_REBUILDABLE",
        ),
        category(
            "protected-queue",
            "kombu:",
            "queue",
            count=1,
            key_type="set",
            status="PROTECTED",
        ),
    ]
    specs = tuple(
        cleanup._validate_category(value, index)
        for index, value in enumerate(raw_categories)
    )
    dbsize = 3
    inventory_sha256 = cleanup._canonical_sha256(
        cleanup._inventory_binding_value(specs, dbsize)
    )
    cleanup_categories = ["legacy-checkpoints"]
    production_fingerprint = cleanup._canonical_sha256(
        {
            "host": {
                "hostname": host.hostname,
                "machine_id_sha256": host.machine_id_sha256,
            },
            "repository_fingerprint_sha256": checkout.fingerprint_sha256,
            "redis_instance_fingerprint_sha256": redis.instance_fingerprint_sha256,
            "inventory_binding_sha256": inventory_sha256,
            "operation_kind": cleanup.OPERATION_KIND,
            "cleanup_categories": cleanup_categories,
        }
    )
    return {
        "schema_version": cleanup.SCHEMA_VERSION,
        "gate_id": cleanup.APPROVAL_GATE,
        "purpose": "synthetic review-only GATE-04 unit test",
        "operation": {
            "operation_id": "gate04:test-001",
            "kind": cleanup.OPERATION_KIND,
            "host": {
                "hostname": host.hostname,
                "machine_id_sha256": host.machine_id_sha256,
            },
            "checkout": {
                "path": str(checkout.path),
                "branch": checkout.branch,
                "commit": checkout.commit,
                "tree": checkout.tree,
                "clean": True,
                "fingerprint_sha256": checkout.fingerprint_sha256,
            },
            "redis": {
                "container_name": cleanup.REDIS_CONTAINER,
                "container_id": redis.container_id,
                "image_id": redis.image_id,
                "database": redis.database,
                "run_id": redis.run_id,
                "version": redis.version,
                "role": redis.role,
                "maxmemory_bytes": redis.maxmemory_bytes,
                "maxmemory_policy": redis.maxmemory_policy,
                "evicted_keys": redis.evicted_keys,
                "write_error_total": redis.write_error_total,
                "instance_fingerprint_sha256": redis.instance_fingerprint_sha256,
                "persistence": {
                    "appendonly": persistence.appendonly,
                    "save": persistence.save,
                    "dir": str(persistence.directory),
                    "dbfilename": persistence.dbfilename,
                    "appenddirname": persistence.appenddirname,
                    "lastsave_epoch": persistence.lastsave_epoch,
                    "fingerprint_sha256": persistence.fingerprint_sha256,
                },
            },
            "expected_dbsize": dbsize,
            "inventory_binding_sha256": inventory_sha256,
            "production_fingerprint_sha256": production_fingerprint,
            "target_max_memory_percent": cleanup.TARGET_MAX_MEMORY_PERCENT,
            "scan_count": 100,
        },
        "categories": raw_categories,
        "cleanup_categories": cleanup_categories,
        "recovery_evidence": {
            "persistence": {
                "evidence_id": "aof-rdb:test-001",
                "kind": "redis_aof_rdb_live_verified",
                "status": "VERIFIED",
                "evidence_sha256": "2" * 64,
                "verified_at": timestamp(captured_at - dt.timedelta(minutes=5)),
                "valid_until": timestamp(captured_at + dt.timedelta(hours=2)),
            },
            "restore": {
                "evidence_id": "restore:test-001",
                "kind": "redis_backup_restore_drill_verified",
                "status": "RESTORE_VERIFIED",
                "evidence_sha256": "3" * 64,
                "verified_at": timestamp(captured_at - dt.timedelta(minutes=5)),
                "valid_until": timestamp(captured_at + dt.timedelta(hours=2)),
            },
        },
    }


def write_manifest(path: Path, value: dict[str, Any] | None = None) -> Any:
    path.write_text(json.dumps(value or manifest_value()), encoding="utf-8")
    path.chmod(0o600)
    return cleanup.load_manifest(path)


def observation(
    count: int,
    key_type: str,
    memory_sum: int,
) -> Any:
    binding = cleanup.CategoryBinding(count, count, 0, ((key_type, count),))
    return cleanup.CategoryObservation(binding, memory_sum)


def inventory_for(manifest: Any) -> Any:
    observations = {
        "legacy-checkpoints": observation(2, "ReJSON-RL", 4 * MAXMEMORY),
        "protected-queue": observation(1, "set", 1024),
    }
    return cleanup.Inventory(
        observations,
        3,
        manifest.inventory_binding_sha256,
    )


def health(*, used_memory: int = MAXMEMORY * 95 // 100) -> Any:
    return cleanup.RedisHealth(used_memory, MAXMEMORY, 3, 0, 0)


def test_valid_manifest_is_non_executable_observation_input(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "manifest.json")

    assert manifest.cleanup_categories == ("legacy-checkpoints",)
    assert cleanup.EXECUTION_IMPLEMENTED is False


def test_private_documents_reject_permissions_and_symlinks(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest_value()), encoding="utf-8")
    path.chmod(0o640)
    with pytest.raises(cleanup.CleanupError, match="unsafe"):
        cleanup.load_manifest(path)

    path.chmod(0o600)
    link = tmp_path / "linked.json"
    link.symlink_to(path)
    with pytest.raises(cleanup.CleanupError, match="unavailable"):
        cleanup.load_manifest(link)


def test_manifest_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,"gate_id":"GATE-04"}',
        encoding="utf-8",
    )
    path.chmod(0o600)

    with pytest.raises(cleanup.CleanupError, match="duplicate JSON key"):
        cleanup.load_manifest(path)


@pytest.mark.parametrize(
    ("field_path", "boolean"),
    [
        (("schema_version",), True),
        (("operation", "redis", "database"), False),
        (("operation", "redis", "maxmemory_bytes"), True),
        (("operation", "redis", "evicted_keys"), False),
        (("operation", "redis", "write_error_total"), False),
        (("operation", "redis", "persistence", "lastsave_epoch"), True),
        (("operation", "expected_dbsize"), True),
        (("operation", "target_max_memory_percent"), True),
        (("operation", "scan_count"), True),
        (("categories", 0, "expected", "count"), True),
        (("categories", 0, "expected", "persistent_count"), True),
        (("categories", 0, "expected", "expiring_count"), False),
        (("categories", 0, "expected", "type_counts", "ReJSON-RL"), True),
    ],
)
def test_every_manifest_integer_field_rejects_boolean_values(
    tmp_path: Path, field_path: tuple[object, ...], boolean: bool
) -> None:
    value: Any = manifest_value()
    target = value
    for segment in field_path[:-1]:
        target = target[segment]
    target[field_path[-1]] = boolean
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(cleanup.CleanupError):
        cleanup.load_manifest(path)


def test_config_get_rejects_duplicate_names() -> None:
    response = "appendonly\nyes\nappendonly\nyes\n"

    with pytest.raises(cleanup.CleanupError, match="duplicate names"):
        cleanup._parse_config(response, ("appendonly",))


def test_manifest_rejects_memory_sum_as_a_binding_field(tmp_path: Path) -> None:
    value = manifest_value()
    value["categories"][0]["expected"]["aggregate_memory_bytes"] = 999
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(cleanup.CleanupError, match="binding schema"):
        cleanup.load_manifest(path)


def test_manifest_never_selects_queue_session_lock_cache_or_authority(
    tmp_path: Path,
) -> None:
    value = manifest_value()
    value["cleanup_categories"] = ["protected-queue"]
    specs = tuple(
        cleanup._validate_category(item, index)
        for index, item in enumerate(value["categories"])
    )
    inventory = cleanup._canonical_sha256(cleanup._inventory_binding_value(specs, 3))
    value["operation"]["inventory_binding_sha256"] = inventory
    value["operation"]["production_fingerprint_sha256"] = cleanup._canonical_sha256(
        {
            "host": value["operation"]["host"],
            "repository_fingerprint_sha256": value["operation"]["checkout"][
                "fingerprint_sha256"
            ],
            "redis_instance_fingerprint_sha256": value["operation"]["redis"][
                "instance_fingerprint_sha256"
            ],
            "inventory_binding_sha256": inventory,
            "operation_kind": cleanup.OPERATION_KIND,
            "cleanup_categories": ["protected-queue"],
        }
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(cleanup.CleanupError, match="not safe and rebuildable"):
        cleanup.load_manifest(path)


def test_execute_is_hard_denied_before_any_runtime_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "manifest.json"
    write_manifest(path)
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("runtime probe must not run")

    monkeypatch.setattr(cleanup, "observe_consistency", forbidden)

    assert cleanup.main([str(path), "--execute"]) == 2
    assert called is False
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "denied"
    assert output["execution_implemented"] is False


def test_inventory_uses_only_eval_ro_and_never_returns_raw_keys(
    tmp_path: Path,
) -> None:
    manifest = write_manifest(tmp_path / "manifest.json")
    token_a = "1" * 80 + ":10"
    token_b = "2" * 80 + ":11"
    token_c = "3" * 80 + ":12"
    commands: list[list[str]] = []

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command = list(command)
        commands.append(command)
        assert "EVAL_RO" in command
        assert "EVAL" not in command
        cursor = command[command.index("EVAL_RO") + 3]
        if cursor == "0":
            value = {
                "cursor": "17",
                "rows": [
                    [1, token_a, "ReJSON-RL", -1, 2 * MAXMEMORY],
                    [2, token_c, "set", -1, 1024],
                ],
                "unknown": 0,
                "vanished": 0,
            }
        else:
            value = {
                "cursor": "0",
                "rows": [
                    [1, token_a, "ReJSON-RL", -1, 2 * MAXMEMORY],
                    [1, token_b, "ReJSON-RL", -1, 2 * MAXMEMORY],
                ],
                "unknown": 0,
                "vanished": 0,
            }
        return subprocess.CompletedProcess(command, 0, json.dumps(value), "")

    inventory = cleanup.collect_inventory(manifest, CONTAINER_ID, runner)

    assert inventory.dbsize == 3
    assert inventory.binding_sha256 == manifest.inventory_binding_sha256
    assert (
        inventory.observations["legacy-checkpoints"].observed_memory_usage_sum_bytes
        == 4 * MAXMEMORY
    )
    assert all(
        "checkpoint:raw-user-key" not in " ".join(command) for command in commands
    )


def test_inventory_stops_on_unknown_or_unstable_categories(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "manifest.json")

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        value = {"cursor": "0", "rows": [], "unknown": 1, "vanished": 0}
        return subprocess.CompletedProcess(list(command), 0, json.dumps(value), "")

    with pytest.raises(cleanup.CleanupError, match="unknown or unstable"):
        cleanup.collect_inventory(manifest, CONTAINER_ID, runner)


def test_two_cursor_passes_with_same_binding_and_health_are_consistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = write_manifest(tmp_path / "manifest.json")
    health_calls = 0
    inventory_calls = 0
    inspect_calls = 0

    def health_probe(_manifest: Any, container_id: str, _runner: Any) -> Any:
        nonlocal health_calls
        health_calls += 1
        assert container_id == CONTAINER_ID
        return health()

    def inspect_probe(_manifest: Any, _runner: Any) -> str:
        nonlocal inspect_calls
        inspect_calls += 1
        return CONTAINER_ID

    first = inventory_for(manifest)
    second_observations = dict(first.observations)
    second_observations["legacy-checkpoints"] = observation(
        2, "ReJSON-RL", 9 * MAXMEMORY
    )
    second = cleanup.Inventory(
        second_observations, 3, manifest.inventory_binding_sha256
    )
    inventories = iter((first, second))

    def inventory_probe(*_args: object) -> Any:
        nonlocal inventory_calls
        inventory_calls += 1
        return next(inventories)

    monkeypatch.setattr(cleanup, "_validate_host_checkout", lambda *_args: None)
    monkeypatch.setattr(cleanup, "_inspect_redis_container", inspect_probe)
    monkeypatch.setattr(cleanup, "_validate_redis_health", health_probe)
    monkeypatch.setattr(cleanup, "collect_inventory", inventory_probe)

    result = cleanup.observe_consistency(manifest)

    assert result.inventory_passes == 2
    assert result.health == health()
    assert health_calls == 3
    assert inventory_calls == 2
    assert inspect_calls == 3


def test_recovery_evidence_must_still_be_current_after_both_cursor_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = utc_now()
    value = manifest_value(started)
    value["recovery_evidence"]["persistence"]["valid_until"] = timestamp(
        started + dt.timedelta(seconds=1)
    )
    value["recovery_evidence"]["restore"]["valid_until"] = timestamp(
        started + dt.timedelta(seconds=1)
    )
    manifest = write_manifest(tmp_path / "manifest.json", value)

    monkeypatch.setattr(cleanup, "_validate_host_checkout", lambda *_args: None)
    monkeypatch.setattr(
        cleanup, "_inspect_redis_container", lambda *_args: CONTAINER_ID
    )
    monkeypatch.setattr(cleanup, "_validate_redis_health", lambda *_args: health())
    monkeypatch.setattr(
        cleanup, "collect_inventory", lambda *_args: inventory_for(manifest)
    )
    monkeypatch.setattr(cleanup, "_utc_now", lambda: started + dt.timedelta(seconds=2))

    with pytest.raises(cleanup.CleanupError, match="evidence expired"):
        cleanup.observe_consistency(manifest, now=started)


def test_two_cursor_passes_stop_on_equal_dbsize_but_category_count_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = write_manifest(tmp_path / "manifest.json")
    first = inventory_for(manifest)
    drifted = cleanup.Inventory(
        {
            "legacy-checkpoints": observation(1, "ReJSON-RL", MAXMEMORY),
            "protected-queue": observation(2, "set", 2048),
        },
        3,
        "4" * 64,
    )
    inventories = iter((first, drifted))
    monkeypatch.setattr(cleanup, "_validate_host_checkout", lambda *_args: None)
    monkeypatch.setattr(
        cleanup, "_inspect_redis_container", lambda *_args: CONTAINER_ID
    )
    monkeypatch.setattr(cleanup, "_validate_redis_health", lambda *_args: health())
    monkeypatch.setattr(cleanup, "collect_inventory", lambda *_args: next(inventories))

    with pytest.raises(cleanup.CleanupError, match="category count"):
        cleanup.observe_consistency(manifest)


def test_source_has_no_redis_mutation_primitive() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    script = cleanup.INVENTORY_LUA.upper()

    assert cleanup.EXECUTION_IMPLEMENTED is False
    assert "EVAL_RO" in source
    assert "REDIS.CALL('UNLINK'" not in script
    assert "REDIS.CALL('DEL'" not in script
    assert "REDIS.CALL('FLUSH" not in script
    assert "REDIS.CALL('CONFIG', 'SET'" not in script


def test_source_and_cli_have_no_local_write_or_report_path() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    option_names = {action.dest for action in cleanup.build_parser()._actions}

    assert "report" not in option_names
    assert "approval" not in option_names
    assert "O_WRONLY" not in source
    assert "O_CREAT" not in source
    assert "os.write(" not in source
    assert "fsync(" not in source
    with pytest.raises(SystemExit):
        cleanup.build_parser().parse_args(["manifest.json", "--report", "out.json"])


def test_redis_exec_uses_verified_container_id_not_mutable_name() -> None:
    commands: list[list[str]] = []

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command = list(command)
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "3", "")

    assert cleanup._redis_command(CONTAINER_ID, ["DBSIZE"], runner) == "3"
    assert commands == [
        [
            cleanup.DOCKER_BINARY,
            "exec",
            CONTAINER_ID,
            cleanup.REDIS_CLI,
            "--raw",
            "-n",
            "0",
            "DBSIZE",
        ]
    ]
    assert cleanup.REDIS_CONTAINER not in commands[0]


def test_container_name_and_id_are_reinspected_and_must_match(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "manifest.json")
    references: list[str] = []

    def item(container_id: str) -> list[dict[str, Any]]:
        return [
            {
                "Id": container_id,
                "Image": IMAGE_ID,
                "Name": "/redis",
                "State": {
                    "Running": True,
                    "Status": "running",
                    "Health": {"Status": "healthy"},
                },
            }
        ]

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        reference = list(command)[-1]
        references.append(reference)
        return subprocess.CompletedProcess(
            list(command), 0, json.dumps(item(CONTAINER_ID)), ""
        )

    assert cleanup._inspect_redis_container(manifest, runner) == CONTAINER_ID
    assert references == [cleanup.REDIS_CONTAINER, CONTAINER_ID]

    def drift_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        reference = list(command)[-1]
        observed_id = "9" * 64 if reference == cleanup.REDIS_CONTAINER else CONTAINER_ID
        return subprocess.CompletedProcess(
            list(command), 0, json.dumps(item(observed_id)), ""
        )

    with pytest.raises(cleanup.CleanupError, match="name-to-id binding"):
        cleanup._inspect_redis_container(manifest, drift_runner)


def test_main_labels_observation_as_no_snapshot_proof_or_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "manifest.json"
    manifest = write_manifest(path)
    result = cleanup.ConsistentObservation(health(), inventory_for(manifest), 2)
    monkeypatch.setattr(cleanup, "observe_consistency", lambda *_args: result)

    assert cleanup.main([str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "CONSISTENT_READ_ONLY_OBSERVATION"
    assert output["inventory_passes"] == 2
    assert output["is_snapshot"] is False
    assert output["is_proof"] is False
    assert output["is_approval"] is False
    assert output["gate04_closed"] is True
    assert output["memory_usage_semantics"] == "NONADDITIVE_DIAGNOSTIC_ONLY"


def test_internal_redis_runner_rejects_every_non_allowlisted_command() -> None:
    called = False

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess(list(command), 0, "OK", "")

    with pytest.raises(cleanup.CleanupError, match="read-only allowlist"):
        cleanup._redis_command(CONTAINER_ID, ["SET", "synthetic", "value"], runner)
    assert called is False


def test_program_is_executable() -> None:
    assert stat.S_IMODE(MODULE_PATH.stat().st_mode) & stat.S_IXUSR
