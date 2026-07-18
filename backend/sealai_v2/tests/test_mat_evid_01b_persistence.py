from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from sealai_v2.core.material_evidence_binding import (
    BoundEvidenceReferenceV1,
    EvidenceRuntimeBindingState,
    MaterialEvidenceRuntimeErrorCode,
    MaterialEvidenceRuntimeIntegrityError,
)
from sealai_v2.core.material_shadow import ShadowAuthority
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_evidence_binding import MaterialEvidenceRuntimeRepository
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.db.migrate import _upgrade_engine, migration_status
from sealai_v2.db.models import (
    V2MaterialEvidenceRuntimeAuditEvent,
    V2MaterialEvidenceRuntimeBinding,
    V2MaterialEvidenceRuntimeEvaluation,
    V2MaterialEvidenceRuntimeEvaluationRef,
    V2MaterialEvidenceRuntimePin,
    V2MaterialShadowEvaluation,
    V2MaterialShadowEvaluationMatch,
    V2MaterialShadowOutbox,
)
from sealai_v2.material_evidence_binding.evaluator import (
    _build_result,
    evaluate_with_evidence,
    integrity_blocked_evaluation,
)
from sealai_v2.material_shadow.worker import MaterialShadowWorker
from sealai_v2.tests.test_mat_evid_01b_domain import _binding as _evidence_binding
from sealai_v2.tests.test_mat_evid_01b_domain import _evidence, _ruleset
from sealai_v2.tests.test_mat_evid_01b_domain import _input as _evidence_input
from sealai_v2.tests.test_mat_gov_03b_persistence import (
    IDENTITY,
    NOW,
    RULESET_ID,
    _binding,
    _input,
    _keyring,
)
from sealai_v2.tests.test_mat_gov_03b_worker import DictCache


TABLES = {
    "v2_material_evidence_runtime_bindings",
    "v2_material_evidence_runtime_pins",
    "v2_material_evidence_runtime_evaluations",
    "v2_material_evidence_runtime_evaluation_refs",
    "v2_material_evidence_runtime_audit_events",
}


class EvidenceDictCache:
    def __init__(self) -> None:
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value, *, ttl_s):
        assert ttl_s == 90 * 86400
        self.values[key] = value


class PoisonedEvidenceCache:
    def __init__(self, value) -> None:
        self.value = value

    def get(self, _key):
        return self.value

    def put(self, _key, _value, *, ttl_s):
        raise AssertionError(f"poisoned cache must not be written: {ttl_s}")


def _database(tmp_path, name="evid-01b.db"):
    engine = make_engine(f"sqlite:///{tmp_path / name}")
    _upgrade_engine(engine, "20260718_0015")
    factory = make_sessionmaker(engine)
    ruleset_repository = MaterialRulesetRepository(factory)
    ruleset_repository.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    ruleset = ruleset_repository.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset().canonical_bytes,
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    evidence_repository = MaterialEvidenceRepository(factory)
    evidence_repository.create_manifest(
        manifest_id="mef_" + "2" * 32,
        ruleset_snapshot_id=ruleset.snapshot_id,
        domain_pack_id="material.test.v1",
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    raw_evidence = _evidence(ruleset).canonical_bytes
    evidence = evidence_repository.store_snapshot(
        manifest_id="mef_" + "2" * 32,
        raw_payload=raw_evidence,
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    return engine, factory, ruleset, evidence


def test_0015_migration_is_empty_additive_restrictive_and_immutable(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _upgrade_engine(engine, "20260718_0014")
    before = set(inspect(engine).get_table_names())
    _upgrade_engine(engine, "20260718_0015")
    assert set(inspect(engine).get_table_names()) - before == TABLES
    assert migration_status(engine) == ("20260718_0015", "20260718_0019")
    with engine.connect() as connection:
        assert all(
            connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            == 0
            for table in TABLES
        )
    for table, expected_target in {
        "v2_material_evidence_runtime_bindings": "v2_material_shadow_bindings",
        "v2_material_evidence_runtime_pins": "v2_material_shadow_pins",
        "v2_material_evidence_runtime_evaluations": "v2_material_shadow_evaluations",
        "v2_material_evidence_runtime_evaluation_refs": "v2_material_evidence_runtime_evaluations",
        "v2_material_evidence_runtime_audit_events": "v2_material_evidence_runtime_bindings",
    }.items():
        foreign_keys = inspect(engine).get_foreign_keys(table)
        assert any(item["referred_table"] == expected_target for item in foreign_keys)
        assert all(
            item["options"].get("ondelete") == "RESTRICT" for item in foreign_keys
        )


def test_binding_and_pin_companions_are_atomic_and_append_only(tmp_path) -> None:
    engine, factory, ruleset, evidence = _database(tmp_path)
    shadow_repository = MaterialShadowRepository(factory)
    shadow_binding = _binding(ruleset)
    companion = replace(
        _evidence_binding(ruleset, evidence), binding_id=shadow_binding.binding_id
    )
    shadow_repository.create_binding(
        shadow_binding,
        identity=IDENTITY,
        created_at=NOW,
        evidence_binding=companion,
    )
    captured = shadow_repository.persist_pin_and_job(
        binding=shadow_binding,
        identity=IDENTITY,
        session_id="session-evidence",
        correlation_id="request-evidence",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
        evidence_binding_required=True,
    )
    with factory() as session:
        binding_row = session.get(
            V2MaterialEvidenceRuntimeBinding, shadow_binding.binding_id
        )
        pin_row = session.get(V2MaterialEvidenceRuntimePin, captured.pin.pin_id)
        assert (
            binding_row.binding_state
            == EvidenceRuntimeBindingState.BOUND_UNREVIEWED.value
        )
        assert binding_row.positive_statement_allowed is False
        assert pin_row.evidence_snapshot_id == evidence.snapshot_id
        assert (
            session.scalar(
                select(func.count()).select_from(V2MaterialEvidenceRuntimeAuditEvent)
            )
            == 2
        )

    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE v2_material_evidence_runtime_bindings "
                    "SET binding_state='unbound' WHERE binding_id=:binding_id"
                ),
                {"binding_id": shadow_binding.binding_id},
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM v2_material_evidence_runtime_audit_events "
                    "WHERE binding_id=:binding_id"
                ),
                {"binding_id": shadow_binding.binding_id},
            )


def test_invalid_companion_rolls_back_the_shadow_binding(tmp_path) -> None:
    _engine, factory, ruleset, evidence = _database(tmp_path)
    repository = MaterialShadowRepository(factory)
    shadow_binding = _binding(ruleset)
    invalid = replace(
        _evidence_binding(ruleset, evidence), binding_id=shadow_binding.binding_id
    )
    invalid = replace(invalid, ruleset_content_sha256="f" * 64)
    with pytest.raises(Exception):
        repository.create_binding(
            shadow_binding,
            identity=IDENTITY,
            created_at=NOW,
            evidence_binding=invalid,
        )
    with factory() as session:
        assert (
            session.get(V2MaterialEvidenceRuntimeBinding, shadow_binding.binding_id)
            is None
        )


def test_enabled_worker_preserves_technical_projection_and_persists_references(
    tmp_path,
) -> None:
    _engine, factory, ruleset, evidence = _database(tmp_path, "worker.db")
    repository = MaterialShadowRepository(factory)
    shadow_binding = _binding(ruleset)
    companion = replace(
        _evidence_binding(ruleset, evidence), binding_id=shadow_binding.binding_id
    )
    repository.create_binding(
        shadow_binding,
        identity=IDENTITY,
        created_at=NOW,
        evidence_binding=companion,
    )
    captured = repository.persist_pin_and_job(
        binding=shadow_binding,
        identity=IDENTITY,
        session_id="session-evidence",
        correlation_id="request-evidence",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
        evidence_binding_required=True,
    )
    worker = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(),
        keyring=_keyring(),
        evidence_binding_enabled=True,
        evidence_cache=EvidenceDictCache(),
    )
    drained = worker.drain_once(now="2026-07-17T12:07:00.000000Z")
    assert drained.evaluated == 1
    with factory() as session:
        technical = session.scalar(
            select(V2MaterialShadowEvaluation).where(
                V2MaterialShadowEvaluation.pin_id == captured.pin.pin_id
            )
        )
        runtime = session.get(
            V2MaterialEvidenceRuntimeEvaluation, technical.evaluation_id
        )
        refs = session.scalars(
            select(V2MaterialEvidenceRuntimeEvaluationRef).where(
                V2MaterialEvidenceRuntimeEvaluationRef.evaluation_id
                == technical.evaluation_id
            )
        ).all()
        matches = session.scalars(
            select(V2MaterialShadowEvaluationMatch).where(
                V2MaterialShadowEvaluationMatch.evaluation_id == technical.evaluation_id
            )
        ).all()
        assert runtime.binding_state == "bound_unreviewed"
        assert runtime.positive_statement_allowed is False
        assert runtime.result_sha256 != technical.result_sha256
        assert {item.rule_ref for item in refs} == {match.rule_ref for match in matches}


def test_unbound_worker_persists_integrity_blocked_without_cache_or_verdict(
    tmp_path,
) -> None:
    _engine, factory, ruleset, _evidence_snapshot = _database(tmp_path, "unbound.db")
    repository = MaterialShadowRepository(factory)
    shadow_binding = _binding(ruleset)
    companion = replace(
        _evidence_binding(ruleset, None), binding_id=shadow_binding.binding_id
    )
    repository.create_binding(
        shadow_binding,
        identity=IDENTITY,
        created_at=NOW,
        evidence_binding=companion,
    )
    captured = repository.persist_pin_and_job(
        binding=shadow_binding,
        identity=IDENTITY,
        session_id="session-unbound",
        correlation_id="request-unbound",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
        evidence_binding_required=True,
    )
    evidence_cache = EvidenceDictCache()
    worker = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(),
        keyring=_keyring(),
        evidence_binding_enabled=True,
        evidence_cache=evidence_cache,
    )
    assert worker.drain_once(now="2026-07-17T12:07:00.000000Z").evaluated == 1
    assert evidence_cache.values == {}
    with factory() as session:
        technical = session.scalar(
            select(V2MaterialShadowEvaluation).where(
                V2MaterialShadowEvaluation.pin_id == captured.pin.pin_id
            )
        )
        runtime = session.get(
            V2MaterialEvidenceRuntimeEvaluation, technical.evaluation_id
        )
        assert technical.evaluation_state == "integrity_blocked"
        assert technical.verdict is technical.decisive_ref is None
        assert technical.stable_error_code == "MAT_EVID_RUNTIME_UNBOUND"
        assert runtime.binding_state == "unbound"
        assert runtime.authority == "NONE"
        assert (
            session.scalar(
                select(func.count())
                .select_from(V2MaterialEvidenceRuntimeEvaluationRef)
                .where(
                    V2MaterialEvidenceRuntimeEvaluationRef.evaluation_id
                    == technical.evaluation_id
                )
            )
            == 0
        )


def test_cache_cannot_replace_postgres_bound_evaluation(tmp_path) -> None:
    _engine, factory, ruleset, evidence = _database(tmp_path, "poisoned-cache.db")
    repository = MaterialShadowRepository(factory)
    shadow_binding = _binding(ruleset)
    companion = replace(
        _evidence_binding(ruleset, evidence), binding_id=shadow_binding.binding_id
    )
    repository.create_binding(
        shadow_binding,
        identity=IDENTITY,
        created_at=NOW,
        evidence_binding=companion,
    )
    captured = repository.persist_pin_and_job(
        binding=shadow_binding,
        identity=IDENTITY,
        session_id="session-poisoned",
        correlation_id="request-poisoned",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
        evidence_binding_required=True,
    )
    evidence_pin = MaterialEvidenceRuntimeRepository(factory).load_pin(
        captured.pin.pin_id
    )
    poisoned = integrity_blocked_evaluation(
        evidence_pin, MaterialEvidenceRuntimeErrorCode.INTERNAL
    )
    worker = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(),
        keyring=_keyring(),
        evidence_binding_enabled=True,
        evidence_cache=PoisonedEvidenceCache(poisoned),
    )
    result = worker.drain_once(now="2026-07-17T12:07:00.000000Z")
    assert result.retried == 1
    with factory() as session:
        job = session.get(V2MaterialShadowOutbox, captured.job_id)
        assert job.status == "pending"
        assert job.stable_error_code == "SHADOW_CACHE_UNAVAILABLE"
        assert (
            session.scalar(select(func.count()).select_from(V2MaterialShadowEvaluation))
            == 0
        )


def _replace_result_references(result, references):
    return _build_result(
        evaluation_state=result.evaluation_state,
        verdict=result.verdict,
        decisive_ref=result.decisive_ref,
        matches=result.matches,
        stable_error_code=result.stable_error_code,
        technical_result_sha256=result.technical_result_sha256,
        evidence_binding_state=result.evidence_binding_state,
        ruleset_snapshot_id=result.ruleset_snapshot_id,
        ruleset_content_sha256=result.ruleset_content_sha256,
        evidence_snapshot_id=result.evidence_snapshot_id,
        evidence_content_sha256=result.evidence_content_sha256,
        references=references,
    )


def _add_shadow_evaluation(session, *, captured, result, result_sha256=None):
    evaluation_id = "mshe_" + "a" * 32
    session.add(
        V2MaterialShadowEvaluation(
            evaluation_id=evaluation_id,
            job_id=captured.job_id,
            pin_id=captured.pin.pin_id,
            hmac_key_id=captured.pin.hmac_key_id,
            evaluation_state=result.evaluation_state,
            verdict=result.verdict,
            decisive_ref=result.decisive_ref,
            result_sha256=result_sha256 or result.technical_result_sha256,
            stable_error_code=result.stable_error_code,
            cache_hit=False,
            authority=ShadowAuthority.NON_AUTHORITATIVE.value,
            positive_statement_allowed=False,
            created_at="2026-07-17T12:07:00.000000Z",
            expires_at="2026-10-15T12:07:00.000000Z",
        )
    )
    for index, (rule_ref, verdict, source_ref) in enumerate(result.matches):
        session.add(
            V2MaterialShadowEvaluationMatch(
                match_id=f"mshm_{index:032x}",
                evaluation_id=evaluation_id,
                rule_ref=rule_ref,
                verdict=verdict,
                source_ref=source_ref,
            )
        )
    session.flush()
    return evaluation_id


def _runtime_persistence_fixture(tmp_path, name):
    _engine, factory, ruleset, evidence = _database(tmp_path, name)
    repository = MaterialShadowRepository(factory)
    shadow_binding = _binding(ruleset)
    companion = replace(
        _evidence_binding(ruleset, evidence), binding_id=shadow_binding.binding_id
    )
    repository.create_binding(
        shadow_binding,
        identity=IDENTITY,
        created_at=NOW,
        evidence_binding=companion,
    )
    captured = repository.persist_pin_and_job(
        binding=shadow_binding,
        identity=IDENTITY,
        session_id=f"session-{name}",
        correlation_id=f"request-{name}",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
        evidence_binding_required=True,
    )
    evidence_pin = MaterialEvidenceRuntimeRepository(factory).load_pin(
        captured.pin.pin_id
    )
    result = evaluate_with_evidence(
        pin=evidence_pin,
        ruleset=ruleset,
        evidence=evidence,
        material_input=_evidence_input(),
    )
    return factory, ruleset, evidence, captured, evidence_pin, result


@pytest.mark.parametrize("case", ("foreign_claim", "extra_claim", "source_drift"))
def test_persistence_rejects_references_not_in_exact_manifest(tmp_path, case) -> None:
    factory, ruleset, evidence, captured, evidence_pin, result = (
        _runtime_persistence_fixture(tmp_path, f"reference-{case}.db")
    )
    first = result.references[0]
    forged = BoundEvidenceReferenceV1(
        rule_ref=first.rule_ref,
        claim_ref=("claim-forged" if case != "source_drift" else first.claim_ref),
        source_refs=(
            "source-forged"
            if case in {"foreign_claim", "source_drift"}
            else first.source_refs[0],
        ),
    )
    references = (
        tuple(sorted((*result.references, forged)))
        if case == "extra_claim"
        else tuple(sorted((forged, *result.references[1:])))
    )
    forged_result = _replace_result_references(result, references)
    with pytest.raises(MaterialEvidenceRuntimeIntegrityError) as exc:
        with factory() as session, session.begin():
            evaluation_id = _add_shadow_evaluation(
                session,
                captured=captured,
                result=forged_result,
            )
            MaterialEvidenceRuntimeRepository.insert_evaluation_companion(
                session,
                evaluation_id=evaluation_id,
                pin=evidence_pin,
                result=forged_result,
                ruleset=ruleset,
                evidence=evidence,
                created_at="2026-07-17T12:07:00.000000Z",
            )
    assert exc.value.code is MaterialEvidenceRuntimeErrorCode.REFERENCE_DRIFT
    with factory() as session:
        assert session.get(V2MaterialShadowEvaluation, "mshe_" + "a" * 32) is None


def test_persistence_rejects_shadow_projection_drift(tmp_path) -> None:
    factory, ruleset, evidence, captured, evidence_pin, result = (
        _runtime_persistence_fixture(tmp_path, "projection-drift.db")
    )
    with pytest.raises(MaterialEvidenceRuntimeIntegrityError) as exc:
        with factory() as session, session.begin():
            evaluation_id = _add_shadow_evaluation(
                session,
                captured=captured,
                result=result,
                result_sha256="f" * 64,
            )
            MaterialEvidenceRuntimeRepository.insert_evaluation_companion(
                session,
                evaluation_id=evaluation_id,
                pin=evidence_pin,
                result=result,
                ruleset=ruleset,
                evidence=evidence,
                created_at="2026-07-17T12:07:00.000000Z",
            )
    assert exc.value.code is MaterialEvidenceRuntimeErrorCode.TECHNICAL_RESULT_DRIFT
