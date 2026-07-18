from __future__ import annotations

from alembic import command
import json

import pytest
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from sealai_v2.core.material_evidence import (
    EvidenceClaimScopeV1,
    MaterialEvidenceErrorCode,
    MaterialEvidenceIntegrityError,
    MaterialEvidenceValidationError,
    derive_claim_ref,
    derive_source_ref,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import (
    V2MaterialEvidenceAuditEvent,
    V2MaterialEvidenceManifest,
    V2MaterialEvidenceSnapshot,
    V2MaterialEvidenceValidationEvent,
)


RULESET_ID = "mrs_11111111111111111111111111111111"
MANIFEST_ID = "mef_22222222222222222222222222222222"
CREATED_AT = "2026-07-18T10:00:00Z"
EVIDENCE_TABLES = {
    "v2_material_evidence_manifests",
    "v2_material_evidence_snapshots",
    "v2_material_evidence_validation_events",
    "v2_material_evidence_audit_events",
}


def _ruleset_payload() -> str:
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
                    "statement": "Synthetic technical rule.",
                    "scope": {
                        "materials": ["TEST-MATERIAL"],
                        "media": ["TEST-MEDIUM"],
                        "conditions": ["TEST-CONDITION"],
                    },
                    "evidence_binding": {"state": "unbound"},
                }
            ],
        }
    )


def _manifest_payload(
    ruleset_snapshot_id: str, *, rule_ref: str = "MR-TEST-001"
) -> str:
    source_values = {
        "document_id": "DOC-TEST-001",
        "document_revision": "rev-1",
        "publication_edition": "edition-2026-01",
        "content_sha256": "3" * 64,
    }
    source_ref = derive_source_ref(**source_values)
    scope = EvidenceClaimScopeV1(
        materials=("TEST-MATERIAL",),
        media=("TEST-MEDIUM",),
        conditions=("TEST-CONDITION",),
    )
    claim_text = "Synthetic atomic evidence claim."
    claim_ref = derive_claim_ref(claim_text=claim_text, scope=scope)
    return json.dumps(
        {
            "evidence_manifest_schema_version": 1,
            "canonicalization_version": 1,
            "mat_evid_contract_version": "MAT-EVID-01A.v1",
            "ruleset_snapshot_id": ruleset_snapshot_id,
            "domain_pack_id": "material.test.v1",
            "sources": [{"source_ref": source_ref, **source_values}],
            "claims": [
                {
                    "claim_ref": claim_ref,
                    "claim_text": claim_text,
                    "scope": scope.to_dict(),
                    "source_refs": [source_ref],
                }
            ],
            "rule_claim_bindings": [{"rule_ref": rule_ref, "claim_ref": claim_ref}],
        }
    )


def _repository(tmp_path, name: str = "mat-evid-01a.db"):
    engine = make_engine(f"sqlite:///{tmp_path / name}")
    _upgrade_engine(engine)
    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    ruleset_snapshot = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset_payload(),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    evidence = MaterialEvidenceRepository(factory)
    evidence.create_manifest(
        manifest_id=MANIFEST_ID,
        ruleset_snapshot_id=ruleset_snapshot.snapshot_id,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    return engine, evidence, ruleset_snapshot


def _store(repository: MaterialEvidenceRepository, ruleset_snapshot_id: str):
    return repository.store_snapshot(
        manifest_id=MANIFEST_ID,
        raw_payload=_manifest_payload(ruleset_snapshot_id),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )


def test_migration_is_additive_empty_and_uses_restrict_foreign_keys(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _upgrade_engine(engine, "20260717_0013")
    before = set(inspect(engine).get_table_names())
    _upgrade_engine(engine)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - before == EVIDENCE_TABLES
    assert migration_status(engine) == ("20260718_0014", "20260718_0014")
    manifest_uniques = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("v2_material_evidence_manifests")
    }
    assert ("ruleset_snapshot_id",) in manifest_uniques
    with engine.connect() as connection:
        for table in EVIDENCE_TABLES:
            assert (
                connection.exec_driver_sql(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).scalar_one()
                == 0
            )
    expected = {
        "v2_material_evidence_manifests": (
            "ruleset_snapshot_id",
            "v2_material_ruleset_snapshots",
            "snapshot_id",
        ),
        "v2_material_evidence_snapshots": (
            "manifest_id",
            "v2_material_evidence_manifests",
            "manifest_id",
        ),
        "v2_material_evidence_validation_events": (
            "snapshot_id",
            "v2_material_evidence_snapshots",
            "snapshot_id",
        ),
        "v2_material_evidence_audit_events": (
            "snapshot_id",
            "v2_material_evidence_snapshots",
            "snapshot_id",
        ),
    }
    for table, relation in expected.items():
        foreign_keys = inspector.get_foreign_keys(table)
        assert len(foreign_keys) == 1
        foreign_key = foreign_keys[0]
        assert (
            foreign_key["constrained_columns"][0],
            foreign_key["referred_table"],
            foreign_key["referred_columns"][0],
        ) == relation
        assert foreign_key["options"]["ondelete"].upper() == "RESTRICT"


def test_repository_round_trip_and_append_only_technical_events(tmp_path) -> None:
    engine, repository, ruleset_snapshot = _repository(tmp_path)
    stored = _store(repository, ruleset_snapshot.snapshot_id)
    assert repository.load_snapshot(stored.snapshot_id) == stored
    assert repository.validation_event_count(stored.snapshot_id) == 1
    assert repository.audit_event_count(stored.snapshot_id) == 1
    with make_sessionmaker(engine)() as session:
        validation = session.scalar(select(V2MaterialEvidenceValidationEvent))
        audit = session.scalar(select(V2MaterialEvidenceAuditEvent))
    assert validation is not None
    assert validation.validation_state == "valid"
    assert validation.error_code == "none"
    assert audit is not None
    assert audit.event_type == "snapshot_created"
    assert "review" not in audit.event_payload_json
    assert "approval" not in audit.event_payload_json


def test_store_is_idempotent_and_repository_exposes_no_lifecycle_surface(
    tmp_path,
) -> None:
    _engine, repository, ruleset_snapshot = _repository(tmp_path)
    first = _store(repository, ruleset_snapshot.snapshot_id)
    second = _store(repository, ruleset_snapshot.snapshot_id)
    assert first == second
    assert repository.validation_event_count(first.snapshot_id) == 1
    for method in (
        "update_manifest",
        "update_snapshot",
        "delete_manifest",
        "delete_snapshot",
        "review",
        "approve",
        "activate",
        "deploy",
    ):
        assert not hasattr(repository, method)


def test_one_manifest_family_owns_all_versions_for_one_ruleset_snapshot(
    tmp_path,
) -> None:
    _engine, repository, ruleset_snapshot = _repository(tmp_path)
    with pytest.raises(IntegrityError):
        repository.create_manifest(
            manifest_id="mef_" + "9" * 32,
            ruleset_snapshot_id=ruleset_snapshot.snapshot_id,
            domain_pack_id="material.test.v1",
            created_by_subject="subject:creator",
            created_at=CREATED_AT,
        )


def test_binding_to_rule_absent_from_exact_ruleset_snapshot_fails_closed(
    tmp_path,
) -> None:
    _engine, repository, ruleset_snapshot = _repository(tmp_path)
    with pytest.raises(MaterialEvidenceValidationError) as exc:
        repository.store_snapshot(
            manifest_id=MANIFEST_ID,
            raw_payload=_manifest_payload(
                ruleset_snapshot.snapshot_id, rule_ref="MR-ABSENT-001"
            ),
            created_by_subject="subject:creator",
            created_at=CREATED_AT,
        )
    assert exc.value.code is MaterialEvidenceErrorCode.DANGLING_REF


@pytest.mark.parametrize(
    "model",
    [
        V2MaterialEvidenceManifest,
        V2MaterialEvidenceSnapshot,
        V2MaterialEvidenceValidationEvent,
        V2MaterialEvidenceAuditEvent,
    ],
)
def test_sqlite_rejects_update_and_delete_for_every_evidence_row(
    tmp_path, model
) -> None:
    engine, repository, ruleset_snapshot = _repository(
        tmp_path, f"immutable-{model.__name__}.db"
    )
    stored = _store(repository, ruleset_snapshot.snapshot_id)
    key_column = next(iter(model.__table__.primary_key.columns))
    with make_sessionmaker(engine)() as session:
        row = session.scalar(select(model))
    assert row is not None
    key = getattr(row, key_column.name)
    with pytest.raises(DBAPIError, match="MAT-EVID-01A immutable table"):
        with engine.begin() as connection:
            connection.execute(
                update(model).where(key_column == key).values({key_column.name: key})
            )
    with pytest.raises(DBAPIError, match="MAT-EVID-01A immutable table"):
        with engine.begin() as connection:
            connection.execute(delete(model).where(key_column == key))
    assert repository.load_snapshot(stored.snapshot_id) == stored


def test_load_detects_persisted_hash_drift_without_mutating_it(tmp_path) -> None:
    engine, repository, ruleset_snapshot = _repository(tmp_path)
    stored = _store(repository, ruleset_snapshot.snapshot_id)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            'DROP TRIGGER "trg_v2_material_evidence_snapshots_update_immutable"'
        )
        connection.exec_driver_sql(
            "UPDATE v2_material_evidence_snapshots SET canonical_bytes = ? "
            "WHERE snapshot_id = ?",
            (b"{}", stored.snapshot_id),
        )
    with pytest.raises(MaterialEvidenceIntegrityError) as exc:
        repository.load_snapshot(stored.snapshot_id)
    assert exc.value.quarantine_candidate is True
    with make_sessionmaker(engine)() as session:
        row = session.get(V2MaterialEvidenceSnapshot, stored.snapshot_id)
    assert bytes(row.canonical_bytes) == b"{}"


def test_load_revalidates_the_complete_bound_03a_snapshot(tmp_path) -> None:
    engine, repository, ruleset_snapshot = _repository(tmp_path)
    stored = _store(repository, ruleset_snapshot.snapshot_id)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            'DROP TRIGGER "trg_v2_material_ruleset_snapshots_update_immutable"'
        )
        connection.exec_driver_sql(
            "UPDATE v2_material_ruleset_snapshots SET content_sha256 = ? "
            "WHERE snapshot_id = ?",
            ("f" * 64, ruleset_snapshot.snapshot_id),
        )
    with pytest.raises(MaterialEvidenceIntegrityError) as exc:
        repository.load_snapshot(stored.snapshot_id)
    assert exc.value.code is MaterialEvidenceErrorCode.DB_INTEGRITY


def test_empty_downgrade_only_and_partial_adoption_fail_closed(tmp_path) -> None:
    empty = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    _upgrade_engine(empty)
    with empty.begin() as connection:
        command.downgrade(_config(connection=connection), "20260717_0013")
    assert not EVIDENCE_TABLES & set(inspect(empty).get_table_names())

    populated, repository, ruleset_snapshot = _repository(tmp_path, "populated.db")
    _store(repository, ruleset_snapshot.snapshot_id)
    with pytest.raises(RuntimeError, match="contain data"):
        with populated.begin() as connection:
            command.downgrade(_config(connection=connection), "20260717_0013")
    assert migration_status(populated)[0] == "20260718_0014"

    partial = make_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    _upgrade_engine(partial, "20260717_0013")
    with partial.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE v2_material_evidence_manifests "
            "(manifest_id TEXT PRIMARY KEY)"
        )
    with pytest.raises(RuntimeError, match="partial MAT-EVID-01A schema"):
        _upgrade_engine(partial)
