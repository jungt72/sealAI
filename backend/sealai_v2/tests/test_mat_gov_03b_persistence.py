from __future__ import annotations

from alembic import command
from dataclasses import replace
import json

import pytest
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sealai_v2.core.contracts import (
    InputResolutionState,
    MediumCardinality,
    RelationState,
    VerifiedIdentity,
)
from sealai_v2.core.material_shadow import (
    ServerVerifiedCanonicalId,
    ShadowBinding,
    ShadowBindingEventType,
    ShadowEnvironment,
    ShadowMaterialInput,
    ShadowPurpose,
    ShadowScopeKind,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status, up
from sealai_v2.db.models import (
    V2MaterialShadowBinding,
    V2MaterialShadowBindingEvent,
    V2MaterialShadowOutbox,
    V2MaterialShadowPin,
    V2MaterialShadowSessionUpgradeEvent,
    V2MaterialShadowSessionVersion,
)
from sealai_v2.material_shadow.hmac_refs import TENANT_REF_DOMAIN, ShadowHmacKeyring


NOW = "2026-07-17T12:00:00.000000Z"
ONE = "2026-07-17T13:00:00.000000Z"
TWO = "2026-07-17T14:00:00.000000Z"
RULESET_ID = "mrs_" + "1" * 32
IDENTITY = VerifiedIdentity("tenant-a", "session-a", "subject:owner")


def _payload() -> str:
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
                    "material": "MAT.NBR",
                    "medium": "MED.OIL",
                    "condition": "TEST-CONDITION",
                    "verdict": "bedingt",
                    "statement": "Synthetic condition; not a material release.",
                    "scope": {
                        "materials": ["MAT.NBR"],
                        "media": ["MED.OIL"],
                        "conditions": ["COND.TEST"],
                    },
                    "evidence_binding": {"state": "unbound"},
                }
            ],
        }
    )


def _database(tmp_path, name="shadow.db"):
    engine = make_engine(f"sqlite:///{tmp_path / name}")
    up(engine)
    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    snapshot = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_payload(),
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    return engine, factory, rulesets, snapshot


def _binding(snapshot, *, suffix="2", start=NOW, end=ONE, **changes):
    values = {
        "binding_id": "mshb_" + suffix * 32,
        "snapshot_id": snapshot.snapshot_id,
        "content_sha256": snapshot.content_sha256,
        "environment": ShadowEnvironment.STAGING,
        "purpose": ShadowPurpose.MATERIAL_RULESET_SHADOW,
        "scope_kind": ShadowScopeKind.GLOBAL,
        "tenant_ref_hmac": None,
        "hmac_key_id": None,
        "domain_pack_id": "material.test.v1",
        "domain_pack_version": "1.0.0",
        "evaluator_version": "MAT-GOV-03B.eval.v1",
        "kernel_version": "MAT-GOV-02.kernel.v1",
        "runtime_profile_sha256": "3" * 64,
        "build_git_sha": "4" * 40,
        "build_tree_hash": "5" * 40,
        "valid_from": start,
        "valid_until": end,
        "creator_subject": IDENTITY.subject,
        "reason": "MAT-GOV-03B.synthetic-binding",
        "sampling_policy_version": "MAT-GOV-03B.shadow.v1",
        "sampling_basis_points": 0,
    }
    values.update(changes)
    return ShadowBinding(**values)


def _input() -> ShadowMaterialInput:
    return ShadowMaterialInput(
        material_id=ServerVerifiedCanonicalId("MAT.NBR", "registry.material.v1"),
        medium_id=ServerVerifiedCanonicalId("MED.OIL", "registry.material.v1"),
        material_state=InputResolutionState.KNOWN,
        medium_state=InputResolutionState.KNOWN,
        medium_cardinality=MediumCardinality.SINGLE,
        relation_state=RelationState.NOT_APPLICABLE,
        domain_pack_id="material.test.v1",
        domain_pack_version="1.0.0",
    )


def _keyring() -> ShadowHmacKeyring:
    return ShadowHmacKeyring(
        {"key-v1": "a" * 32, "key-old": "b" * 32}, active_key_id="key-v1"
    )


def test_fresh_03b_migration_is_empty_additive_and_pointerless(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    before = set(
        _upgrade_engine(engine, "20260717_0011") or inspect(engine).get_table_names()
    )
    _upgrade_engine(engine)
    added = set(inspect(engine).get_table_names()) - before
    assert added == {
        "v2_material_shadow_bindings",
        "v2_material_shadow_binding_events",
        "v2_material_shadow_pins",
        "v2_material_shadow_session_versions",
        "v2_material_shadow_session_upgrade_events",
        "v2_material_shadow_outbox",
        "v2_material_shadow_evaluations",
        "v2_material_shadow_evaluation_matches",
        "v2_material_shadow_evaluation_refs",
    }
    assert migration_status(engine) == ("20260717_0013", "20260717_0013")
    outbox_columns = {
        column["name"]
        for column in inspect(engine).get_columns("v2_material_shadow_outbox")
    }
    assert {"lease_owner", "lease_expires_at"} <= outbox_columns
    assert not any(
        token in table
        for table in added
        for token in ("active_pointer", "approval", "deployment", "cohort", "stage_ack")
    )
    with engine.connect() as connection:
        assert all(
            connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            == 0
            for table in added
        )


def test_complete_modeled_03b_schema_is_adopted_only_after_shape_validation(
    tmp_path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'adoption.db'}")
    up(engine)
    with engine.begin() as connection:
        before = list(
            connection.execute(
                text(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "WHERE name LIKE 'v2_material_%' "
                    "OR name LIKE 'trg_v2_material_%' ORDER BY type,name"
                )
            )
        )
        connection.exec_driver_sql("DROP TABLE alembic_version")

    up(engine)

    assert migration_status(engine) == ("20260717_0013", "20260717_0013")
    with engine.connect() as connection:
        after = list(
            connection.execute(
                text(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "WHERE name LIKE 'v2_material_%' "
                    "OR name LIKE 'trg_v2_material_%' ORDER BY type,name"
                )
            )
        )
        triggers = set(
            connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='trigger' AND name LIKE 'trg_v2_material_shadow_%'"
                )
            ).scalars()
        )
    assert after == before
    assert "trg_v2_material_shadow_pins_update_immutable" in triggers
    assert "trg_v2_material_shadow_binding_insert_guard" in triggers
    assert "trg_v2_material_shadow_outbox_insert_lease_guard" in triggers


def test_adoption_rejects_same_named_index_with_different_semantics(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'adoption-index-drift.db'}")
    up(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.exec_driver_sql("DROP INDEX ix_v2_material_shadow_binding_lookup")
        connection.exec_driver_sql(
            "CREATE INDEX ix_v2_material_shadow_binding_lookup "
            "ON v2_material_shadow_bindings(binding_id)"
        )
    with pytest.raises(RuntimeError, match="structural adoption fingerprint mismatch"):
        up(engine)


def test_adoption_rejects_same_named_trigger_with_different_body(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'adoption-trigger-drift.db'}")
    up(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.exec_driver_sql(
            "DROP TRIGGER trg_v2_material_shadow_pins_update_immutable"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER trg_v2_material_shadow_pins_update_immutable "
            "BEFORE UPDATE ON v2_material_shadow_pins BEGIN SELECT 1; END"
        )
    with pytest.raises(RuntimeError, match="structural adoption fingerprint mismatch"):
        up(engine)


def test_lease_migration_rejects_predecessor_drift_before_first_mutation(
    tmp_path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'lease-predecessor-drift.db'}")
    _upgrade_engine(engine, "20260717_0012")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "DROP TRIGGER trg_v2_material_shadow_outbox_update_guard"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER trg_v2_material_shadow_outbox_update_guard "
            "BEFORE UPDATE ON v2_material_shadow_outbox BEGIN SELECT 1; END"
        )
    with pytest.raises(RuntimeError, match="structural adoption fingerprint mismatch"):
        _upgrade_engine(engine, "20260717_0013")
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("v2_material_shadow_outbox")
    }
    assert "lease_owner" not in columns
    assert "lease_expires_at" not in columns


def test_partial_precreated_03b_schema_is_rejected(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    _upgrade_engine(engine, "20260717_0011")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE v2_material_shadow_bindings " "(binding_id TEXT PRIMARY KEY)"
        )
    with pytest.raises(RuntimeError, match="partial MAT-GOV-03B schema"):
        _upgrade_engine(engine)


def test_binding_overlap_is_rejected_and_terminal_event_does_not_free_interval(
    tmp_path,
) -> None:
    _engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    first = _binding(snapshot)
    repository.create_binding(first, identity=IDENTITY, created_at=NOW)
    with pytest.raises((IntegrityError, DBAPIError), match="overlapping binding"):
        repository.create_binding(
            _binding(
                snapshot,
                suffix="6",
                start="2026-07-17T12:30:00.000000Z",
                end="2026-07-17T13:30:00.000000Z",
            ),
            identity=IDENTITY,
            created_at=NOW,
        )
    repository.terminate_binding(
        first.binding_id,
        event_type=ShadowBindingEventType.REVOKED,
        identity=IDENTITY,
        reason="MAT-GOV-03B.synthetic-revocation",
        effective_at="2026-07-17T12:10:00.000000Z",
        created_at="2026-07-17T12:10:00.000000Z",
    )
    with pytest.raises((IntegrityError, DBAPIError), match="overlapping binding"):
        repository.create_binding(
            _binding(
                snapshot,
                suffix="7",
                start="2026-07-17T12:20:00.000000Z",
                end="2026-07-17T12:40:00.000000Z",
            ),
            identity=IDENTITY,
            created_at=NOW,
        )
    adjacent = _binding(snapshot, suffix="8", start=ONE, end=TWO)
    repository.create_binding(adjacent, identity=IDENTITY, created_at=ONE)


def test_binding_creation_is_atomic_and_immutable(tmp_path) -> None:
    engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    binding = _binding(snapshot)
    repository.create_binding(binding, identity=IDENTITY, created_at=NOW)
    with factory() as session:
        binding_row = session.get(V2MaterialShadowBinding, binding.binding_id)
        assert (
            session.scalar(select(func.count(V2MaterialShadowBinding.binding_id))) == 1
        )
        assert (
            session.scalar(select(func.count(V2MaterialShadowBindingEvent.event_id)))
            == 1
        )
    assert binding_row is not None
    binding_json = json.dumps(
        {
            column.name: getattr(binding_row, column.name)
            for column in V2MaterialShadowBinding.__table__.columns
        },
        default=str,
    )
    assert IDENTITY.tenant_id not in binding_json
    with pytest.raises(DBAPIError, match="immutable"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE v2_material_shadow_bindings SET reason='changed' "
                    "WHERE binding_id=:binding_id"
                ),
                {"binding_id": binding.binding_id},
            )


def test_canary_overlap_is_detected_across_retained_hmac_keys(tmp_path) -> None:
    _engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    keyring = _keyring()
    first = _binding(
        snapshot,
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=keyring.digest_fields(
            TENANT_REF_DOMAIN, (IDENTITY.tenant_id,), key_id="key-old"
        ),
        hmac_key_id="key-old",
    )
    repository.create_binding(
        first,
        identity=IDENTITY,
        created_at=NOW,
        hmac_keyring=keyring,
    )
    rotated = _binding(
        snapshot,
        suffix="7",
        scope_kind=ShadowScopeKind.TENANT_CANARY,
        tenant_ref_hmac=keyring.digest_fields(
            TENANT_REF_DOMAIN, (IDENTITY.tenant_id,), key_id="key-v1"
        ),
        hmac_key_id="key-v1",
    )
    with pytest.raises(ValueError, match="overlapping binding"):
        repository.create_binding(
            rotated,
            identity=IDENTITY,
            created_at=NOW,
            hmac_keyring=keyring,
        )
    with factory() as session:
        assert (
            session.scalar(select(func.count(V2MaterialShadowBinding.binding_id))) == 1
        )


def test_pin_and_job_are_atomic_idempotent_pseudonymous_and_sequenced(tmp_path) -> None:
    _engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    binding = _binding(snapshot)
    repository.create_binding(binding, identity=IDENTITY, created_at=NOW)
    first = repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="raw-session-must-not-persist",
        correlation_id="raw-request-must-not-persist",
        case_id="raw-case-must-not-persist",
        decision_id="raw-decision-must-not-persist",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
    )
    duplicate = repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="raw-session-must-not-persist",
        correlation_id="raw-request-must-not-persist",
        case_id="raw-case-must-not-persist",
        decision_id="raw-decision-must-not-persist",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
    )
    second = repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="raw-session-must-not-persist",
        correlation_id="second-raw-request",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:06:00.000000Z",
    )
    assert first.created is True
    assert duplicate.created is False
    assert duplicate.job_id == first.job_id
    assert second.sequence_no == 2
    assert first.pin.authority.value == "SHADOW_NON_AUTHORITATIVE"
    assert first.pin.positive_statement_allowed is False
    with factory() as session:
        pins = session.scalars(select(V2MaterialShadowPin)).all()
        jobs = session.scalars(select(V2MaterialShadowOutbox)).all()
        versions = session.scalars(select(V2MaterialShadowSessionVersion)).all()
    assert len(pins) == len(jobs) == 2
    assert len(versions) == 1
    serialized = json.dumps(
        [
            {
                column.name: getattr(job, column.name)
                for column in V2MaterialShadowOutbox.__table__.columns
            }
            for job in jobs
        ],
        default=str,
    )
    assert "raw-session-must-not-persist" not in serialized
    assert "raw-request-must-not-persist" not in serialized
    assert "raw-case-must-not-persist" not in serialized
    assert "raw-decision-must-not-persist" not in serialized
    assert IDENTITY.tenant_id not in serialized
    assert IDENTITY.subject not in serialized
    assert all(job.hmac_key_id == "key-v1" for job in jobs)


def test_hmac_rotation_preserves_the_existing_session_lineage(tmp_path) -> None:
    _engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    binding = _binding(snapshot)
    repository.create_binding(binding, identity=IDENTITY, created_at=NOW)
    old_keyring = ShadowHmacKeyring(
        {"key-v1": "a" * 32, "key-old": "b" * 32},
        active_key_id="key-old",
    )
    first = repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="rotation-session",
        correlation_id="request-before-rotation",
        material_input=_input(),
        hmac_keyring=old_keyring,
        acquired_at="2026-07-17T12:05:00.000000Z",
    )
    rotated = repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="rotation-session",
        correlation_id="request-after-rotation",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:06:00.000000Z",
    )
    assert rotated.session_version_id == first.session_version_id
    assert (first.sequence_no, rotated.sequence_no) == (1, 2)
    with factory() as session:
        versions = session.scalars(select(V2MaterialShadowSessionVersion)).all()
        jobs = session.scalars(
            select(V2MaterialShadowOutbox).order_by(V2MaterialShadowOutbox.sequence_no)
        ).all()
    assert len(versions) == 1
    assert versions[0].hmac_key_id == "key-old"
    assert [job.hmac_key_id for job in jobs] == ["key-old", "key-v1"]


def test_session_lineage_lookup_and_uniqueness_are_tenant_bound(tmp_path) -> None:
    _engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    binding = _binding(snapshot)
    repository.create_binding(binding, identity=IDENTITY, created_at=NOW)
    tenant_b = VerifiedIdentity("tenant-b", "session-b", "subject:b")
    first = repository.persist_pin_and_job(
        binding=binding,
        identity=IDENTITY,
        session_id="same-session",
        correlation_id="request-a",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
    )
    second = repository.persist_pin_and_job(
        binding=binding,
        identity=tenant_b,
        session_id="same-session",
        correlation_id="request-b",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:06:00.000000Z",
    )
    assert first.session_version_id != second.session_version_id
    with factory() as session:
        versions = session.scalars(
            select(V2MaterialShadowSessionVersion).order_by(
                V2MaterialShadowSessionVersion.session_version_id
            )
        ).all()
    assert len(versions) == 2
    assert len({row.tenant_ref_hmac for row in versions}) == 2
    assert len({row.session_ref_hmac for row in versions}) == 2

    duplicate = V2MaterialShadowSessionVersion(
        session_version_id="mshs_" + "f" * 32,
        tenant_ref_hmac=versions[0].tenant_ref_hmac,
        session_ref_hmac=versions[0].session_ref_hmac,
        hmac_key_id=versions[0].hmac_key_id,
        version_no=versions[0].version_no,
        pin_id=versions[0].pin_id,
        created_at="2026-07-17T12:07:00.000000Z",
    )
    with pytest.raises(IntegrityError):
        with factory() as session, session.begin():
            session.add(duplicate)


def test_pin_and_job_require_exact_live_binding_interval_and_domain(tmp_path) -> None:
    _engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    binding = _binding(snapshot)
    repository.create_binding(binding, identity=IDENTITY, created_at=NOW)

    with pytest.raises(ValueError, match="inside the binding interval"):
        repository.persist_pin_and_job(
            binding=binding,
            identity=IDENTITY,
            session_id="session-a",
            correlation_id="request-before-window",
            material_input=_input(),
            hmac_keyring=_keyring(),
            acquired_at="2026-07-17T11:59:59.999999Z",
        )
    mismatched_input = replace(_input(), domain_pack_version="2.0.0")
    with pytest.raises(ValueError, match="domain pack differ"):
        repository.persist_pin_and_job(
            binding=binding,
            identity=IDENTITY,
            session_id="session-a",
            correlation_id="request-domain-drift",
            material_input=mismatched_input,
            hmac_keyring=_keyring(),
            acquired_at="2026-07-17T12:05:00.000000Z",
        )
    repository.terminate_binding(
        binding.binding_id,
        event_type=ShadowBindingEventType.REVOKED,
        identity=IDENTITY,
        reason="MAT-GOV-03B.synthetic-revocation",
        effective_at="2026-07-17T12:04:00.000000Z",
        created_at="2026-07-17T12:04:00.000000Z",
    )
    with pytest.raises(ValueError, match="terminal"):
        repository.persist_pin_and_job(
            binding=binding,
            identity=IDENTITY,
            session_id="session-a",
            correlation_id="request-after-revocation",
            material_input=_input(),
            hmac_keyring=_keyring(),
            acquired_at="2026-07-17T12:05:00.000000Z",
        )
    with factory() as session:
        assert session.scalar(select(func.count(V2MaterialShadowPin.pin_id))) == 0
        assert session.scalar(select(func.count(V2MaterialShadowOutbox.job_id))) == 0


def test_crash_after_flush_rolls_back_pin_session_and_job_together(tmp_path) -> None:
    _engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    binding = _binding(snapshot)
    repository.create_binding(binding, identity=IDENTITY, created_at=NOW)

    def crash_after_flush(_session, _flush_context) -> None:
        raise RuntimeError("synthetic crash before commit")

    event.listen(factory.class_, "after_flush_postexec", crash_after_flush, once=True)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        repository.persist_pin_and_job(
            binding=binding,
            identity=IDENTITY,
            session_id="session-a",
            correlation_id="request-crash",
            material_input=_input(),
            hmac_keyring=_keyring(),
            acquired_at="2026-07-17T12:05:00.000000Z",
        )
    with factory() as session:
        assert session.scalar(select(func.count(V2MaterialShadowPin.pin_id))) == 0
        assert (
            session.scalar(
                select(func.count(V2MaterialShadowSessionVersion.session_version_id))
            )
            == 0
        )
        assert session.scalar(select(func.count(V2MaterialShadowOutbox.job_id))) == 0


def test_session_binding_change_requires_explicit_immutable_upgrade(tmp_path) -> None:
    _engine, factory, _rulesets, snapshot = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    first_binding = _binding(snapshot)
    next_binding = _binding(snapshot, suffix="9", start=ONE, end=TWO)
    repository.create_binding(first_binding, identity=IDENTITY, created_at=NOW)
    repository.create_binding(next_binding, identity=IDENTITY, created_at=ONE)
    repository.persist_pin_and_job(
        binding=first_binding,
        identity=IDENTITY,
        session_id="session-a",
        correlation_id="request-1",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
    )
    with pytest.raises(ValueError, match="frozen"):
        repository.persist_pin_and_job(
            binding=next_binding,
            identity=IDENTITY,
            session_id="session-a",
            correlation_id="request-2",
            material_input=_input(),
            hmac_keyring=_keyring(),
            acquired_at="2026-07-17T13:05:00.000000Z",
        )
    upgraded = repository.persist_pin_and_job(
        binding=next_binding,
        identity=IDENTITY,
        session_id="session-a",
        correlation_id="request-2",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T13:05:00.000000Z",
        upgrade_reason="MAT-GOV-03B.synthetic-session-upgrade",
    )
    assert upgraded.sequence_no == 1
    with factory() as session:
        versions = session.scalars(
            select(V2MaterialShadowSessionVersion).order_by(
                V2MaterialShadowSessionVersion.version_no
            )
        ).all()
        events = session.scalars(select(V2MaterialShadowSessionUpgradeEvent)).all()
    assert [version.version_no for version in versions] == [1, 2]
    assert len(events) == 1
    assert events[0].from_session_version_id == versions[0].session_version_id
    assert events[0].to_session_version_id == versions[1].session_version_id


def test_empty_downgrade_succeeds_and_used_03b_refuses(tmp_path) -> None:
    empty = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    up(empty)
    with empty.begin() as connection:
        command.downgrade(_config(connection=connection), "20260717_0011")
    assert not any(
        table.startswith("v2_material_shadow_")
        for table in inspect(empty).get_table_names()
    )

    used, factory, _rulesets, snapshot = _database(tmp_path, "used.db")
    MaterialShadowRepository(factory).create_binding(
        _binding(snapshot), identity=IDENTITY, created_at=NOW
    )
    with pytest.raises(RuntimeError, match="contain data"):
        with used.begin() as connection:
            command.downgrade(_config(connection=connection), "20260717_0011")
    assert migration_status(used)[0] == "20260717_0013"
