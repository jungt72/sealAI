from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPO_ROOT / "ops" / "dr_recovery.py"
QDRANT_HELPER_PATH = REPO_ROOT / "ops" / "dr_qdrant_drill.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dr = _load(HELPER_PATH, "dr_recovery")
qdrant_drill = _load(QDRANT_HELPER_PATH, "dr_qdrant_drill")


def _write(path: Path, payload: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_bytes(payload.encode() if isinstance(payload, str) else payload)
    path.chmod(0o600)


def _json(path: Path, value: Any) -> None:
    _write(path, json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _tenant_digest(counts: dict[str, int]) -> str:
    return hashlib.sha256(
        (json.dumps(counts, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def _recovery_set(tmp_path: Path) -> Path:
    root = tmp_path / "set"
    root.mkdir(parents=True, mode=0o700)
    for component in (*dr.REQUIRED_COMPONENTS, "recovery"):
        (root / component).mkdir(mode=0o700)

    postgres = root / "postgres" / "postgres-all-2026-07-14_00-00-00-ABC123.sql.gz"
    _write(postgres, b"postgres-backup")
    pg_sha = hashlib.sha256(postgres.read_bytes()).hexdigest()
    _write(
        postgres.with_name(f"{postgres.name}.sha256"), f"{pg_sha}  {postgres.name}\n"
    )

    snapshot = root / "qdrant" / "sealai_v2_knowledge_v1-test.snapshot"
    _write(snapshot, b"qdrant-snapshot")
    snapshot_sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    _write(
        snapshot.with_name(f"{snapshot.name}.sha256"),
        f"{snapshot_sha}  {snapshot.name}\n",
    )
    for component in ("uploads", "documents"):
        _json(
            root / component / "inventory.json",
            {
                "schema_version": 1,
                "component": component,
                "source_id_sha256": hashlib.sha256(component.encode()).hexdigest(),
                "file_count": 0,
                "total_bytes": 0,
                "empty_source_confirmed": True,
            },
        )
    configuration_paths = {
        "compose_base": "configuration/runtime/docker-compose.yml",
        "compose_deploy": "configuration/runtime/docker-compose.deploy.yml",
        "identity": "configuration/identity/keycloak.conf",
        "monitoring": "configuration/monitoring/prometheus.yml",
        "nginx": "configuration/nginx/default.conf",
        "release_control": "configuration/release/production-release-state.json",
    }
    configuration_artifacts = []
    for logical_id, relative_path in configuration_paths.items():
        path = root / relative_path
        payload = f"synthetic-{logical_id}\n"
        _write(path, payload)
        configuration_artifacts.append(
            {
                "logical_id": logical_id,
                "path": relative_path,
                "sha256": hashlib.sha256(payload.encode()).hexdigest(),
            }
        )
    _json(
        root / "configuration" / "inventory.json",
        {
            "schema_version": 1,
            "source_git_commit": "0" * 40,
            "artifacts": configuration_artifacts,
        },
    )

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    captured = now - dt.timedelta(minutes=5)

    def timestamp(value: dt.datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    component_values = {
        name: {
            "captured_at": timestamp(captured),
            "source_id_sha256": hashlib.sha256(name.encode()).hexdigest(),
            "rpo_target_seconds": 86400,
            "rto_target_seconds": 28800 if name != "configuration" else 7200,
        }
        for name in dr.REQUIRED_COMPONENTS
    }
    recovery_point = {
        "schema_version": 1,
        "recovery_point_id": "test_recovery_point",
        "created_at": timestamp(now),
        "source_git_commit": "0" * 40,
        "authority_epoch_sha256": "a" * 64,
        "components": component_values,
    }
    qdrant_plan = {
        "schema_version": 1,
        "mode": "snapshot_and_rebuild",
        "canonical_source": "postgres",
        "require_empty_target": True,
        "verify_no_orphans": True,
        "verify_tenant_counts": True,
        "collections": [
            {
                "logical_id": "knowledge",
                "collection_name": "sealai_v2_knowledge_v1",
                "ledger_database": "sealai_v2",
                "tenant_scope": "shared_reviewed",
                "authority_epoch_sha256": "a" * 64,
                "rebuild_command_id": "rebuild_knowledge_v1",
                "snapshot_path": f"qdrant/{snapshot.name}",
                "snapshot_sha256": snapshot_sha,
                "expected_points_count": 0,
                "tenant_payload_key": "tenant_id",
                "tenant_counts_sha256": _tenant_digest({}),
            }
        ],
    }
    secret_recovery = {
        "schema_version": 1,
        "entries": [
            {
                "secret_id": "repo",
                "purpose": "backup_encryption",
                "custody": "offline_escrow",
                "key_id_sha256": "b" * 64,
                "recovery_test": "nonproduction_key_verified",
                "rotate_after_restore": False,
            }
        ],
    }
    _json(root / "recovery" / "recovery-point.json", recovery_point)
    _json(root / "recovery" / "qdrant-rebuild.json", qdrant_plan)
    _json(root / "recovery" / "secret-recovery.json", secret_recovery)
    return root


def _manifest_set(tmp_path: Path) -> Path:
    root = _recovery_set(tmp_path)
    dr.create_manifest(root)
    return root


def test_manifest_round_trip_binds_every_required_component(tmp_path: Path) -> None:
    root = _manifest_set(tmp_path)
    manifest = dr.verify_manifest(root)
    assert {entry["path"].split("/", 1)[0] for entry in manifest["files"]} >= {
        *dr.REQUIRED_COMPONENTS,
        "recovery",
    }
    assert dr.postgres_backup_path(root).name.endswith(".sql.gz")
    assert len(manifest["set_id_sha256"]) == 64


@pytest.mark.parametrize("attack", ["tamper", "mode", "symlink", "hardlink"])
def test_manifest_rejects_file_and_metadata_attacks(
    tmp_path: Path, attack: str
) -> None:
    root = _manifest_set(tmp_path)
    target = root / "uploads" / "inventory.json"
    if attack == "tamper":
        target.write_text('{"changed":true}\n', encoding="utf-8")
    elif attack == "mode":
        target.chmod(0o666)
    elif attack == "symlink":
        target.unlink()
        target.symlink_to(root / "documents" / "inventory.json")
    else:
        linked = root / "uploads" / "linked.json"
        os.link(target, linked)
    with pytest.raises(dr.DrError):
        dr.verify_manifest(root)


def test_manifest_rejects_bad_or_missing_p0_checksum(tmp_path: Path) -> None:
    root = _recovery_set(tmp_path)
    sidecar = next((root / "postgres").glob("*.sha256"))
    sidecar.write_text(f"{'f' * 64}  wrong.sql.gz\n", encoding="ascii")
    sidecar.chmod(0o600)
    with pytest.raises(dr.DrError, match="invalid_p0_checksum"):
        dr.create_manifest(root)


@pytest.mark.parametrize("name", [".env.prod", "credentials.json", "server.key"])
def test_configuration_secret_filenames_are_forbidden(
    tmp_path: Path, name: str
) -> None:
    root = _recovery_set(tmp_path)
    _write(root / "configuration" / name, "not-a-secret\n")
    with pytest.raises(dr.DrError, match="configuration_secret_file_forbidden"):
        dr.create_manifest(root)


def test_duplicate_json_keys_and_secret_values_fail_closed(tmp_path: Path) -> None:
    root = _recovery_set(tmp_path)
    secret_file = root / "recovery" / "secret-recovery.json"
    _write(secret_file, '{"schema_version":1,"schema_version":1,"entries":[]}\n')
    with pytest.raises(dr.DrError, match="duplicate_json_key"):
        dr.create_manifest(root)

    value = {
        "schema_version": 1,
        "entries": [
            {
                "secret_id": "db",
                "purpose": "database_auth",
                "custody": "offline_escrow",
                "key_id_sha256": "a" * 64,
                "recovery_test": "procedure_only",
                "rotate_after_restore": True,
                "value": "canary-secret",
            }
        ],
    }
    with pytest.raises(dr.DrError, match="invalid_secret_recovery_entry"):
        dr.validate_secret_recovery(value)


def test_recovery_point_enforces_rpo_and_qdrant_authority(tmp_path: Path) -> None:
    root = _recovery_set(tmp_path)
    path = root / "recovery" / "recovery-point.json"
    value = json.loads(path.read_text())
    value["components"]["postgres"]["captured_at"] = "2026-01-01T00:00:00Z"
    _json(path, value)
    with pytest.raises(dr.DrError, match="rpo_target_missed"):
        dr.create_manifest(root)

    root = _recovery_set(tmp_path / "stale")
    path = root / "recovery" / "recovery-point.json"
    value = json.loads(path.read_text())
    value["created_at"] = "2026-01-02T00:00:00Z"
    value["components"]["postgres"]["captured_at"] = "2026-01-01T23:00:00Z"
    value["components"]["qdrant"]["captured_at"] = "2026-01-01T23:00:00Z"
    value["components"]["uploads"]["captured_at"] = "2026-01-01T23:00:00Z"
    value["components"]["documents"]["captured_at"] = "2026-01-01T23:00:00Z"
    value["components"]["configuration"]["captured_at"] = "2026-01-01T23:00:00Z"
    _json(path, value)
    with pytest.raises(dr.DrError, match="recovery_point_stale"):
        dr.create_manifest(root)

    root = _recovery_set(tmp_path / "second")
    plan_path = root / "recovery" / "qdrant-rebuild.json"
    plan = json.loads(plan_path.read_text())
    plan["collections"][0]["authority_epoch_sha256"] = "f" * 64
    _json(plan_path, plan)
    with pytest.raises(dr.DrError, match="qdrant_authority_epoch_mismatch"):
        dr.create_manifest(root)


def test_receipts_require_full_download_isolation_and_freshness(tmp_path: Path) -> None:
    root = _manifest_set(tmp_path)
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir(mode=0o700)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    offsite = receipt_dir / "offsite.json"
    drill = receipt_dir / "drill.json"
    dr.write_offsite_receipt(
        root,
        offsite,
        repository_id="1" * 64,
        snapshot_id="2" * 64,
        encryption_key_id_sha256="3" * 64,
        now=now,
    )
    dr.write_drill_receipt(root, drill, elapsed_seconds=60, now=now)
    dr.verify_offsite_receipt(root, offsite, now=now)
    dr.verify_drill_receipt(root, drill, now=now)

    value = json.loads(offsite.read_text())
    value["full_download_verified"] = False
    replacement = receipt_dir / "forged.json"
    _json(replacement, value)
    with pytest.raises(dr.DrError, match="offsite_verification_incomplete"):
        dr.verify_offsite_receipt(root, replacement, now=now)
    with pytest.raises(dr.DrError, match="receipt_stale"):
        dr.verify_offsite_receipt(root, offsite, now=now + dt.timedelta(days=2))


def test_receipt_writers_refuse_stale_recovery_points(tmp_path: Path) -> None:
    root = _manifest_set(tmp_path)
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir(mode=0o700)
    stale_now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) + dt.timedelta(
        days=2
    )

    with pytest.raises(dr.DrError, match="rpo_target_missed"):
        dr.write_offsite_receipt(
            root,
            receipt_dir / "offsite.json",
            repository_id="1" * 64,
            snapshot_id="2" * 64,
            encryption_key_id_sha256="3" * 64,
            now=stale_now,
        )
    with pytest.raises(dr.DrError, match="rpo_target_missed"):
        dr.write_drill_receipt(
            root, receipt_dir / "drill.json", elapsed_seconds=60, now=stale_now
        )


def test_drill_writer_refuses_missed_rto(tmp_path: Path) -> None:
    root = _manifest_set(tmp_path)
    receipts = tmp_path / "receipts"
    receipts.mkdir(mode=0o700)
    with pytest.raises(dr.DrError, match="rto_target_missed"):
        dr.write_drill_receipt(root, receipts / "late.json", elapsed_seconds=28801)


def test_gate_08_is_short_lived_action_and_manifest_bound(tmp_path: Path) -> None:
    root = _manifest_set(tmp_path)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    manifest = dr.verify_manifest(root)
    receipt = tmp_path / "gate.json"
    value = {
        "schema_version": 1,
        "gate_id": "GATE-08",
        "action": "dr_offsite_backup",
        "manifest_sha256": dr._manifest_digest(root),
        "set_id_sha256": manifest["set_id_sha256"],
        "approval_id_sha256": "4" * 64,
        "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _json(receipt, value)
    dr.verify_gate08_receipt(
        root,
        receipt,
        "dr_offsite_backup",
        now=now,
        required_uid=os.geteuid(),
    )
    with pytest.raises(dr.DrError, match="gate_receipt_scope_mismatch"):
        dr.verify_gate08_receipt(
            root,
            receipt,
            "dr_restore_drill",
            now=now,
            required_uid=os.geteuid(),
        )
    with pytest.raises(dr.DrError, match="gate_receipt_expired"):
        dr.verify_gate08_receipt(
            root,
            receipt,
            "dr_offsite_backup",
            now=now + dt.timedelta(minutes=11),
            required_uid=os.geteuid(),
        )


def test_metrics_have_only_stable_names_and_component_label(tmp_path: Path) -> None:
    status = tmp_path / "status.json"
    fields = {
        "backup_last_success_timestamp_seconds": 1,
        "backup_last_failure_timestamp_seconds": 2,
        "offsite_backup_last_success_timestamp_seconds": 3,
        "restore_drill_last_success_timestamp_seconds": 4,
        "backup_receipt_valid": 1,
    }
    components = {name: dict(fields) for name in dr.REQUIRED_COMPONENTS}
    _json(status, {"schema_version": 1, "components": components})
    rendered = dr.render_metrics(status)
    assert set(dr.METRIC_NAMES.values()) == {
        line.split("{", 1)[0] for line in rendered.splitlines()
    }
    assert all(
        any(f'{{component="{name}"}}' in line for name in dr.REQUIRED_COMPONENTS)
        for line in rendered.splitlines()
    )
    assert "snapshot" not in rendered and "repository" not in rendered

    _json(
        tmp_path / "missing-component.json",
        {"schema_version": 1, "components": {"postgres": fields}},
    )
    with pytest.raises(dr.DrError, match="invalid_status_components"):
        dr.render_metrics(tmp_path / "missing-component.json")

    _json(
        tmp_path / "bad.json",
        {"schema_version": 1, "components": {'bad"} 1\ncanary': fields}},
    )
    with pytest.raises(dr.DrError, match="invalid_status_component"):
        dr.render_metrics(tmp_path / "bad.json")

    _json(
        tmp_path / "object-label.json",
        {"schema_version": 1, "components": {"snapshot_deadbeef": fields}},
    )
    with pytest.raises(dr.DrError, match="invalid_status_component"):
        dr.render_metrics(tmp_path / "object-label.json")

    output_dir = tmp_path / "metrics"
    output_dir.mkdir(mode=0o700)
    output = output_dir / "sealai.prom"
    dr._atomic_write(output, rendered.encode(), replace=True)
    dr._atomic_write(output, rendered.replace(" 1\n", " 0\n").encode(), replace=True)
    assert output.stat().st_mode & 0o777 == 0o600


def test_restore_images_require_digest_only(tmp_path: Path) -> None:
    valid = tmp_path / "images.env"
    _write(
        valid,
        "\n".join(
            [
                f"DR_POSTGRES_IMAGE=registry.example/postgres@sha256:{'1' * 64}",
                f"DR_QDRANT_IMAGE=registry.example/qdrant@sha256:{'2' * 64}",
                f"DR_VERIFIER_IMAGE=registry.example/backend@sha256:{'3' * 64}",
            ]
        )
        + "\n",
    )
    assert set(dr.validate_restore_images(valid)) == dr.RESTORE_IMAGE_KEYS
    _write(
        tmp_path / "tagged.env",
        valid.read_text().replace(f"@sha256:{'1' * 64}", ":latest", 1),
    )
    with pytest.raises(dr.DrError, match="invalid_restore_image_reference"):
        dr.validate_restore_images(tmp_path / "tagged.env")


def test_repository_examples_are_value_free_valid_contract_shapes(
    tmp_path: Path,
) -> None:
    example_root = REPO_ROOT / "ops" / "dr"
    secret_value = json.loads(
        (example_root / "secret-recovery.example.json").read_text()
    )
    qdrant_value = json.loads(
        (example_root / "qdrant-rebuild.example.json").read_text()
    )
    recovery_value = json.loads(
        (example_root / "recovery-point.example.json").read_text()
    )
    configuration_value = json.loads(
        (example_root / "configuration-inventory.example.json").read_text()
    )
    data_value = json.loads((example_root / "data-inventory.example.json").read_text())
    dr.validate_secret_recovery(secret_value)
    dr.validate_qdrant_rebuild(qdrant_value)
    dr.validate_recovery_point(recovery_value)
    dr.validate_configuration_inventory(configuration_value)
    dr.validate_data_inventory(data_value, component="uploads")
    assert all(
        set(entry)
        == {
            "secret_id",
            "purpose",
            "custody",
            "key_id_sha256",
            "recovery_test",
            "rotate_after_restore",
        }
        for entry in secret_value["entries"]
    )

    status = tmp_path / "status.json"
    _write(status, (example_root / "status.example.json").read_bytes())
    assert "sealai_backup_receipt_valid" in dr.render_metrics(status)


def test_qdrant_verifier_detects_duplicate_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = {
        "collection": "knowledge",
        "expected_points_count": 2,
        "tenant_payload_key": "tenant_id",
        "tenant_counts_sha256": _tenant_digest({"tenant_a": 2}),
    }
    responses = iter(
        [
            {"status": "ok", "result": {"status": "green", "points_count": 2}},
            {
                "status": "ok",
                "result": {
                    "points": [
                        {"id": 1, "payload": {"tenant_id": "tenant_a"}},
                        {"id": 1, "payload": {"tenant_id": "tenant_a"}},
                    ],
                    "next_page_offset": None,
                },
            },
        ]
    )
    monkeypatch.setattr(
        qdrant_drill, "_request", lambda *args, **kwargs: next(responses)
    )
    with pytest.raises(qdrant_drill.DrillError, match="duplicate_point_id"):
        qdrant_drill._verify_collection("x" * 32, item)


def test_offsite_and_restore_scripts_preserve_security_boundaries() -> None:
    offsite = (REPO_ROOT / "ops" / "dr_offsite.sh").read_text()
    assert "/usr/bin/env -i" in offsite
    assert "verify-gate-08" in offsite
    assert "acquire_production_storage_lease" in offsite
    assert "backup_uploaded_unverified" in offsite
    assert "forget --dry-run" in offsite
    assert "forget --prune" not in offsite

    restore = (REPO_ROOT / "ops" / "dr_restore_drill.sh").read_text()
    for contract in (
        "SEALAI_DEDICATED_RECOVERY_RUNNER_V1",
        "production_container_present",
        "production_network_present",
        "verify-gate-08",
        "restic check --read-data",
        "pg_amcheck",
        "dr_qdrant_drill.py",
        "write-offsite-receipt",
        "write-drill-receipt",
        "unset DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG",
        "--host=unix:///var/run/docker.sock",
        "docker_socket_unsafe",
    ):
        assert contract in restore


def test_restore_compose_is_internal_unpublished_and_pinned() -> None:
    compose = (REPO_ROOT / "ops" / "dr" / "restore-compose.yml").read_text()
    assert "internal: true" in compose
    assert 'enable_ip_masquerade: "false"' in compose
    assert compose.count("pull_policy: never") == 3
    assert "ports:" not in compose
    assert "/home/thorsten" not in compose
    assert "/var/run/docker.sock" not in compose


def test_runbook_is_honest_about_external_and_p1d_blockers() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "disaster-recovery.md").read_text()
    for contract in (
        "BLOCKED_EXTERNAL",
        "P1-D",
        "GATE-08",
        "Postgres is canonical application truth",
        "Qdrant is a derived index",
        "two successful isolated full restores",
        "sealai_restore_drill_last_success_timestamp_seconds{component}",
        "never values",
    ):
        assert contract in runbook


def test_systemd_timer_targets_dedicated_runner_only() -> None:
    service = (
        REPO_ROOT / "ops" / "systemd" / "sealai-dr-restore-drill.service"
    ).read_text()
    timer = (
        REPO_ROOT / "ops" / "systemd" / "sealai-dr-restore-drill.timer"
    ).read_text()
    assert "ConditionPathExists=/etc/sealai/dr/isolated-recovery-runner" in service
    assert "NoNewPrivileges=yes" in service
    assert "ProtectSystem=strict" in service
    assert "OnCalendar=Sun *-*-01..07 04:00:00 UTC" in timer
