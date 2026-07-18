from __future__ import annotations

from alembic import command
import json

import pytest
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.exc import DBAPIError

from sealai_v2.core.material_rulesets import (
    MaterialRulesetErrorCode,
    MaterialRulesetIntegrityError,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import (
    V2MaterialRuleset,
    V2MaterialRulesetSnapshot,
    V2MaterialSnapshotAuditEvent,
    V2MaterialSnapshotValidationEvent,
)


RULESET_ID = "mrs_11111111111111111111111111111111"
CREATED_AT = "2026-07-17T12:00:00Z"


def _raw_payload() -> str:
    return json.dumps(
        {
            "snapshot_schema_version": 1,
            "canonicalization_version": 1,
            "mat_gov_contract_version": "MAT-GOV-03A.v1",
            "domain_pack_id": "material.test.v1",
            "positive_statement_allowed": False,
            "rules": [
                {
                    "rule_ref": "MR-TEST-001",
                    "material": "TEST-MATERIAL",
                    "medium": "TEST-MEDIUM",
                    "condition": "TEST-CONDITION",
                    "verdict": "bedingt",
                    "statement": "Synthetischer Persistenztest.",
                    "scope": {
                        "materials": ["TEST-MATERIAL"],
                        "media": ["TEST-MEDIUM"],
                        "conditions": ["TEST-CONDITION"],
                    },
                    "evidence_binding": {"state": "unbound"},
                }
            ],
        },
        ensure_ascii=False,
    )


def _repository(tmp_path, name="mat-gov-03a.db"):
    engine = make_engine(f"sqlite:///{tmp_path / name}")
    _upgrade_engine(engine, "20260717_0011")
    return engine, MaterialRulesetRepository(make_sessionmaker(engine))


def _store(repository: MaterialRulesetRepository):
    repository.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    return repository.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_raw_payload(),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )


def test_fresh_migration_creates_only_the_four_03a_tables_and_internal_fks(
    tmp_path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    before = set(_upgrade_to_previous(engine))
    _upgrade_engine(engine, "20260717_0011")
    after = set(inspect(engine).get_table_names())
    assert after - before == {
        "v2_material_rulesets",
        "v2_material_ruleset_snapshots",
        "v2_material_snapshot_validation_events",
        "v2_material_snapshot_audit_events",
    }
    assert migration_status(engine) == ("20260717_0011", "20260718_0017")
    expected = {
        "v2_material_ruleset_snapshots": (
            "ruleset_id",
            "v2_material_rulesets",
            "ruleset_id",
        ),
        "v2_material_snapshot_validation_events": (
            "snapshot_id",
            "v2_material_ruleset_snapshots",
            "snapshot_id",
        ),
        "v2_material_snapshot_audit_events": (
            "snapshot_id",
            "v2_material_ruleset_snapshots",
            "snapshot_id",
        ),
    }
    for table, relation in expected.items():
        foreign_keys = inspect(engine).get_foreign_keys(table)
        assert len(foreign_keys) == 1
        foreign_key = foreign_keys[0]
        assert (
            foreign_key["constrained_columns"][0],
            foreign_key["referred_table"],
            foreign_key["referred_columns"][0],
        ) == relation
        assert foreign_key["options"]["ondelete"].upper() == "RESTRICT"


def _upgrade_to_previous(engine) -> list[str]:
    _upgrade_engine(engine, "20260714_0010")
    return inspect(engine).get_table_names()


def test_repository_round_trip_revalidates_and_records_append_only_events(
    tmp_path,
) -> None:
    engine, repository = _repository(tmp_path)
    stored = _store(repository)
    loaded = repository.load_snapshot(stored.snapshot_id)
    assert loaded == stored
    assert repository.validation_event_count(stored.snapshot_id) == 1
    assert repository.audit_event_count(stored.snapshot_id) == 1
    with make_sessionmaker(engine)() as session:
        validation = session.scalar(select(V2MaterialSnapshotValidationEvent))
        audit = session.scalar(select(V2MaterialSnapshotAuditEvent))
    assert validation is not None
    assert validation.validation_state == "valid"
    assert validation.error_code == "none"
    assert audit is not None
    assert audit.event_type == "snapshot_created"
    assert audit.event_payload_json == {
        "content_sha256": stored.content_sha256,
        "snapshot_id": stored.snapshot_id,
        "validation_event_id": validation.event_id,
    }


def test_repository_is_idempotent_for_the_same_content_identity(tmp_path) -> None:
    _engine, repository = _repository(tmp_path)
    first = _store(repository)
    second = repository.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_raw_payload(),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    assert second == first
    assert repository.validation_event_count(first.snapshot_id) == 1
    assert repository.audit_event_count(first.snapshot_id) == 1


def test_repository_exposes_no_immutable_update_or_delete_surface(tmp_path) -> None:
    _engine, repository = _repository(tmp_path)
    assert not hasattr(repository, "update_ruleset")
    assert not hasattr(repository, "update_snapshot")
    assert not hasattr(repository, "delete_ruleset")
    assert not hasattr(repository, "delete_snapshot")
    assert not hasattr(repository, "approve")
    assert not hasattr(repository, "activate")


@pytest.mark.parametrize(
    "model",
    [
        V2MaterialRuleset,
        V2MaterialRulesetSnapshot,
        V2MaterialSnapshotValidationEvent,
        V2MaterialSnapshotAuditEvent,
    ],
)
def test_sqlite_triggers_reject_update_and_delete_for_every_03a_row(
    tmp_path, model
) -> None:
    engine, repository = _repository(tmp_path, f"immutable-{model.__name__}.db")
    stored = _store(repository)
    key_column = next(iter(model.__table__.primary_key.columns))
    with make_sessionmaker(engine)() as session:
        row = session.scalar(select(model))
    assert row is not None
    key = getattr(row, key_column.name)
    with pytest.raises(DBAPIError, match="MAT-GOV-03A immutable table"):
        with engine.begin() as connection:
            connection.execute(
                update(model).where(key_column == key).values({key_column.name: key})
            )
    with pytest.raises(DBAPIError, match="MAT-GOV-03A immutable table"):
        with engine.begin() as connection:
            connection.execute(delete(model).where(key_column == key))
    assert repository.load_snapshot(stored.snapshot_id) == stored


def test_load_detects_hash_drift_as_quarantine_candidate_without_mutation(
    tmp_path,
) -> None:
    engine, repository = _repository(tmp_path)
    stored = _store(repository)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            'DROP TRIGGER "trg_v2_material_ruleset_snapshots_update_immutable"'
        )
        connection.exec_driver_sql(
            "UPDATE v2_material_ruleset_snapshots SET canonical_bytes = ? "
            "WHERE snapshot_id = ?",
            (b"{}", stored.snapshot_id),
        )
    with pytest.raises(MaterialRulesetIntegrityError) as exc:
        repository.load_snapshot(stored.snapshot_id)
    assert exc.value.quarantine_candidate is True
    assert exc.value.code in {
        MaterialRulesetErrorCode.UNKNOWN_FIELD,
        MaterialRulesetErrorCode.DB_INTEGRITY,
        MaterialRulesetErrorCode.HASH_MISMATCH,
    }
    with make_sessionmaker(engine)() as session:
        row = session.get(V2MaterialRulesetSnapshot, stored.snapshot_id)
    assert bytes(row.canonical_bytes) == b"{}"


def test_empty_downgrade_is_allowed_and_nonempty_downgrade_fails_closed(
    tmp_path,
) -> None:
    empty_engine, _empty_repository = _repository(tmp_path, "empty.db")
    with empty_engine.begin() as connection:
        command.downgrade(_config(connection=connection), "20260714_0010")
    assert not {
        "v2_material_rulesets",
        "v2_material_ruleset_snapshots",
        "v2_material_snapshot_validation_events",
        "v2_material_snapshot_audit_events",
    } & set(inspect(empty_engine).get_table_names())

    populated_engine, populated_repository = _repository(tmp_path, "populated.db")
    _store(populated_repository)
    with pytest.raises(RuntimeError, match="contain data"):
        with populated_engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260714_0010")
    assert migration_status(populated_engine)[0] == "20260717_0011"


def test_partial_precreated_03a_schema_is_rejected(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    _upgrade_to_previous(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE v2_material_rulesets "
            "(ruleset_id TEXT PRIMARY KEY, domain_pack_id TEXT NOT NULL, "
            "created_by_subject TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
    with pytest.raises(RuntimeError, match="partial MAT-GOV-03A schema"):
        _upgrade_engine(engine)


def test_exact_03a_schema_is_adopted_without_object_replacement(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'exact-adoption.db'}")
    _upgrade_engine(engine, "20260717_0011")
    with engine.begin() as connection:
        before = list(
            connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name LIKE 'v2_material_%' "
                "OR name LIKE 'trg_v2_material_%' ORDER BY type,name"
            )
        )
        connection.exec_driver_sql("DROP TABLE alembic_version")
    _upgrade_engine(engine, "20260717_0011")
    with engine.connect() as connection:
        after = list(
            connection.exec_driver_sql(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name LIKE 'v2_material_%' "
                "OR name LIKE 'trg_v2_material_%' ORDER BY type,name"
            )
        )
    assert after == before


def test_03a_adoption_rejects_same_named_check_with_changed_expression(
    tmp_path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'check-drift.db'}")
    _upgrade_to_previous(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE v2_material_rulesets ("
            "ruleset_id VARCHAR(36) NOT NULL, domain_pack_id VARCHAR(128) NOT NULL, "
            "created_by_subject VARCHAR(255) NOT NULL, created_at VARCHAR(40) NOT NULL, "
            "CONSTRAINT ck_v2_material_ruleset_id CHECK (length(ruleset_id)=35), "
            "PRIMARY KEY (ruleset_id))"
        )
        for table in (
            "v2_material_ruleset_snapshots",
            "v2_material_snapshot_validation_events",
            "v2_material_snapshot_audit_events",
        ):
            connection.exec_driver_sql(f"CREATE TABLE {table} (id TEXT)")
    with pytest.raises(RuntimeError, match="structural adoption fingerprint mismatch"):
        _upgrade_engine(engine, "20260717_0011")
