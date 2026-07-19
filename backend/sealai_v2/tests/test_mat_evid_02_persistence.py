from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from alembic import command
import pytest
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_evidence_review import (
    APPROVE_ROLE,
    CREATE_ROLE,
    HUMAN_ROLE,
    REVIEW_ROLE,
    FactualApprovalState,
    EvidenceReviewValidationError,
)
from sealai_v2.core.material_evidence_binding import EvidenceRuntimeBindingState
from sealai_v2.core.material_evidence_binding_v2 import EvidenceRuntimeBindingV2
from sealai_v2.core.material_evidence_v2 import (
    AtomicEvidenceClaimV2,
    EvidenceManifestPayloadV2,
    EvidenceSourceV2,
    MaterialRelationClaimScopeV2,
    MaterialRelationTargetV2,
    MediaIdentityClaimScopeV2,
    MediaIdentityTargetV2,
    RuleClaimBindingV2,
    derive_claim_ref_v2,
    derive_source_ref_v2,
)
from sealai_v2.core.medium_catalog import (
    MediumCatalogEntryV1,
    MediumIdentityKind,
    derive_media_id,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence_review_v2 import (
    MaterialEvidenceReviewRepositoryV2,
)
from sealai_v2.db.material_evidence_binding_v2 import (
    MaterialEvidenceRuntimeRepositoryV2,
    _audit_hash,
)
from sealai_v2.db.material_evidence_v2 import MaterialEvidenceRepositoryV2
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.db.medium_catalog import MediumCatalogRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import (
    V2MaterialEvidenceAuditEventV2,
    V2MaterialEvidenceManifestV2,
    V2MaterialEvidenceRuntimeAuditEventV2,
    V2MaterialEvidenceRuntimeBindingV2,
    V2MaterialEvidenceRuntimePinV2,
    V2MaterialEvidenceReviewAuditEventV2,
    V2MaterialEvidenceReviewDossierV2,
    V2MaterialEvidenceReviewLifecycleEventV2,
    V2MaterialEvidenceReviewSnapshotV2,
    V2MaterialEvidenceReviewValidationEventV2,
    V2MaterialEvidenceSnapshotV2,
    V2MaterialEvidenceValidationEventV2,
    V2MaterialShadowEvaluation,
)
from sealai_v2.material_evidence_binding.evaluator_v2 import (
    evaluate_with_evidence_v2,
)
from sealai_v2.material_shadow.worker import MaterialShadowWorker
from sealai_v2.tests.test_mat_gov_03b_persistence import (
    IDENTITY as SHADOW_IDENTITY,
    _binding as _shadow_binding,
    _input as _shadow_input,
    _keyring,
)
from sealai_v2.tests.test_mat_gov_03b_worker import DictCache


RULESET_ID = "mrs_" + "1" * 32
MATERIAL_MANIFEST_ID = "mef_" + "2" * 32
MEDIA_MANIFEST_ID = "mef_" + "3" * 32
REVIEW_ID = "mer_" + "4" * 32
CATALOG_ID = "mcf_" + "5" * 32
CREATED_AT = "2026-07-18T18:00:00Z"
DOMAIN_PACK = "material.test.v2"
MEDIA_REF = derive_media_id(
    "Synthetic V2 Catalog Medium", MediumIdentityKind.DEFINED_MIXTURE
)
_ENTRY_TEMPLATE = MediumCatalogEntryV1(
    media_id=MEDIA_REF,
    canonical_name="Synthetic V2 Catalog Medium",
    identity_kind=MediumIdentityKind.DEFINED_MIXTURE,
    aliases=("Synthetic V2 Catalog Alias",),
    evidence_review_snapshot_id="mrv_" + "6" * 64,
    evidence_review_content_sha256="7" * 64,
    claim_refs=("mec_" + "8" * 64,),
)
IDENTITY_ASSERTION_REF = _ENTRY_TEMPLATE.identity_assertion_ref
V2_TABLES = {
    "v2_material_evidence_manifests_v2",
    "v2_material_evidence_snapshots_v2",
    "v2_material_evidence_validation_events_v2",
    "v2_material_evidence_audit_events_v2",
    "v2_material_evidence_runtime_bindings_v2",
    "v2_material_evidence_runtime_pins_v2",
    "v2_material_evidence_runtime_evaluations_v2",
    "v2_material_evidence_runtime_evaluation_refs_v2",
    "v2_material_evidence_runtime_audit_events_v2",
    "v2_material_evidence_review_dossiers_v2",
    "v2_material_evidence_review_snapshots_v2",
    "v2_material_evidence_review_validation_events_v2",
    "v2_material_evidence_review_lifecycle_events_v2",
    "v2_material_evidence_review_audit_events_v2",
}
GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures/mat_evid_02_golden.json").read_text(
        encoding="utf-8"
    )
)


def _actor(subject: str, role: str, tenant: str = "tenant-a") -> VerifiedIdentity:
    return VerifiedIdentity(
        tenant, f"session-{subject}", subject, roles=(HUMAN_ROLE, role)
    )


def _ruleset_payload() -> str:
    return json.dumps(
        {
            "snapshot_schema_version": 1,
            "canonicalization_version": 1,
            "mat_gov_contract_version": "MAT-GOV-03A.v1",
            "domain_pack_id": DOMAIN_PACK,
            "positive_statement_allowed": False,
            "rules": [
                {
                    "rule_ref": "MR-V2-TEST",
                    "material": "SYNTHETIC-MATERIAL",
                    "medium": MEDIA_REF,
                    "condition": "synthetic-condition",
                    "verdict": "unvertraeglich",
                    "statement": "Synthetic v2 test statement.",
                    "scope": {
                        "materials": ["SYNTHETIC-MATERIAL"],
                        "media": [MEDIA_REF],
                        "conditions": ["synthetic-condition"],
                    },
                    "evidence_binding": {"state": "unbound"},
                }
            ],
        }
    )


def _source() -> EvidenceSourceV2:
    identity = {
        "document_id": "DOC-V2-PERSISTENCE",
        "document_revision": "rev-2",
        "publication_edition": "edition-2",
        "content_sha256": "9" * 64,
    }
    return EvidenceSourceV2(source_ref=derive_source_ref_v2(**identity), **identity)


def _payload(ruleset_snapshot_id: str, *, media_identity: bool):
    scope = (
        MediaIdentityClaimScopeV2(MEDIA_REF, IDENTITY_ASSERTION_REF)
        if media_identity
        else MaterialRelationClaimScopeV2(
            materials=("SYNTHETIC-MATERIAL",),
            media=(MEDIA_REF,),
            conditions=("synthetic-condition",),
        )
    )
    claim_text = (
        "Synthetic v2 media identity claim."
        if media_identity
        else "Synthetic v2 material relation claim."
    )
    claim = AtomicEvidenceClaimV2(
        claim_ref=derive_claim_ref_v2(claim_text=claim_text, scope=scope),
        claim_text=claim_text,
        scope=scope,
        source_refs=(_source().source_ref,),
    )
    return EvidenceManifestPayloadV2(
        domain_pack_id=DOMAIN_PACK,
        target=(
            MediaIdentityTargetV2(MEDIA_REF)
            if media_identity
            else MaterialRelationTargetV2(ruleset_snapshot_id)
        ),
        sources=(_source(),),
        claims=(claim,),
        rule_claim_bindings=(
            ()
            if media_identity
            else (RuleClaimBindingV2("MR-V2-TEST", claim.claim_ref),)
        ),
    )


def _review_raw(evidence) -> str:
    claim = evidence.payload.claims[0]
    media_identity = type(claim.scope) is MediaIdentityClaimScopeV2
    return json.dumps(
        {
            "review_schema_version": 2,
            "canonicalization_version": 2,
            "mat_evid_review_contract_version": "MAT-EVID-01C.v2",
            "evidence_snapshot_id": evidence.snapshot_id,
            "evidence_content_sha256": evidence.content_sha256,
            "evidence_manifest_schema_version": 2,
            "evidence_contract_version": "MAT-EVID-01A.v2",
            "sources": [
                {
                    "source_ref": _source().source_ref,
                    "document_id": _source().document_id,
                    "document_title": "Synthetic v2 source",
                    "publisher": "Synthetic Test Publisher",
                    "document_type": "manufacturer_datasheet",
                    "document_revision": _source().document_revision,
                    "publication_edition": _source().publication_edition,
                    "content_sha256": _source().content_sha256,
                    "locator": {"state": "exact", "value": "synthetic locator"},
                    "rights_state": "permitted",
                    "rights_basis": "Synthetic test permission",
                    "excerpt": {"state": "omitted"},
                }
            ],
            "claims": [
                {
                    "claim_ref": claim.claim_ref,
                    "claim_type": (
                        "other_technical" if media_identity else "incompatibility"
                    ),
                    "scope": claim.scope.to_dict(),
                    "required_source_types": ["manufacturer_datasheet"],
                }
            ],
            "claim_relations": [],
        }
    )


def _repositories(tmp_path, name: str = "mat-evid-02.db"):
    engine = make_engine(f"sqlite:///{tmp_path / name}")
    _upgrade_engine(engine, "20260718_0018")
    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id=DOMAIN_PACK,
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    ruleset = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset_payload(),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    evidence = MaterialEvidenceRepositoryV2(factory)
    reviews = MaterialEvidenceReviewRepositoryV2(factory)
    return engine, factory, ruleset, evidence, reviews


def _store_evidence(evidence, ruleset, *, media_identity: bool):
    target = (
        MediaIdentityTargetV2(MEDIA_REF)
        if media_identity
        else MaterialRelationTargetV2(ruleset.snapshot_id)
    )
    manifest_id = MEDIA_MANIFEST_ID if media_identity else MATERIAL_MANIFEST_ID
    evidence.create_manifest(
        manifest_id=manifest_id,
        target=target,
        domain_pack_id=DOMAIN_PACK,
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    return evidence.store_snapshot(
        manifest_id=manifest_id,
        raw_payload=json.dumps(
            _payload(ruleset.snapshot_id, media_identity=media_identity).to_dict()
        ),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )


def test_migration_is_additive_empty_and_v1_tables_remain_separate(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _upgrade_engine(engine, "20260718_0017")
    before = set(inspect(engine).get_table_names())
    _upgrade_engine(engine, "20260718_0018")
    after = set(inspect(engine).get_table_names())
    assert after - before == V2_TABLES
    with engine.connect() as connection:
        assert all(
            connection.exec_driver_sql(f'SELECT COUNT(*) FROM "{table}"').scalar_one()
            == 0
            for table in V2_TABLES
        )
    assert "v2_material_evidence_snapshots" in before
    assert "v2_material_evidence_snapshots_v2" not in before


@pytest.mark.parametrize("media_identity", (False, True))
def test_manifest_v2_repository_roundtrip_and_exact_target(
    tmp_path, media_identity: bool
) -> None:
    _engine, factory, ruleset, evidence, _reviews = _repositories(
        tmp_path, f"manifest-{media_identity}.db"
    )
    stored = _store_evidence(evidence, ruleset, media_identity=media_identity)
    assert evidence.load_snapshot(stored.snapshot_id) == stored
    with factory() as session:
        family = session.scalar(select(V2MaterialEvidenceManifestV2))
        assert family is not None
        assert family.target_type == (
            "media_identity" if media_identity else "material_relation"
        )
        assert session.scalar(select(V2MaterialEvidenceValidationEventV2)) is not None
        assert session.scalar(select(V2MaterialEvidenceAuditEventV2)) is not None


def test_target_uniqueness_is_enforced_with_nullable_discriminated_columns(
    tmp_path,
) -> None:
    _engine, _factory, ruleset, evidence, _reviews = _repositories(tmp_path)
    _store_evidence(evidence, ruleset, media_identity=True)
    with pytest.raises((ValueError, IntegrityError)):
        evidence.create_manifest(
            manifest_id="mef_" + "f" * 32,
            target=MediaIdentityTargetV2(MEDIA_REF),
            domain_pack_id=DOMAIN_PACK,
            created_by_subject="subject:other",
            created_at=CREATED_AT,
        )


def test_review_v2_lifecycle_is_tenant_isolated_and_three_subject(tmp_path) -> None:
    _engine, _factory, ruleset, evidence, reviews = _repositories(tmp_path)
    manifest = _store_evidence(evidence, ruleset, media_identity=True)
    creator = _actor("creator", CREATE_ROLE)
    family = reviews.create_review(
        review_id=REVIEW_ID,
        evidence_snapshot_id=manifest.snapshot_id,
        identity=creator,
        created_at=CREATED_AT,
    )
    snapshot = reviews.store_snapshot(
        review_id=family.review_id,
        raw_payload=_review_raw(manifest),
        identity=creator,
        created_at=CREATED_AT,
    )
    reviews.record_review(
        snapshot.review_snapshot_id,
        identity=_actor("reviewer", REVIEW_ROLE),
        created_at=CREATED_AT,
    )
    projection = reviews.record_approval(
        snapshot.review_snapshot_id,
        identity=_actor("approver", APPROVE_ROLE),
        created_at=CREATED_AT,
    )
    assert projection.approval_state is FactualApprovalState.APPROVED
    assert (
        reviews.load_snapshot(snapshot.review_snapshot_id, identity=creator) == snapshot
    )
    with pytest.raises(EvidenceReviewValidationError):
        reviews.load_snapshot(
            snapshot.review_snapshot_id,
            identity=_actor("foreign", CREATE_ROLE, tenant="tenant-b"),
        )


def test_med_norm_accepts_exact_approved_v2_media_identity_without_materials(
    tmp_path,
) -> None:
    _engine, factory, ruleset, evidence, reviews = _repositories(tmp_path)
    manifest = _store_evidence(evidence, ruleset, media_identity=True)
    creator = _actor("creator", CREATE_ROLE)
    reviews.create_review(
        review_id=REVIEW_ID,
        evidence_snapshot_id=manifest.snapshot_id,
        identity=creator,
        created_at=CREATED_AT,
    )
    review = reviews.store_snapshot(
        review_id=REVIEW_ID,
        raw_payload=_review_raw(manifest),
        identity=creator,
        created_at=CREATED_AT,
    )
    reviews.record_review(
        review.review_snapshot_id,
        identity=_actor("reviewer", REVIEW_ROLE),
        created_at=CREATED_AT,
    )
    reviews.record_approval(
        review.review_snapshot_id,
        identity=_actor("approver", APPROVE_ROLE),
        created_at=CREATED_AT,
    )
    entry = {
        "media_id": MEDIA_REF,
        "canonical_name": "Synthetic V2 Catalog Medium",
        "identity_kind": "defined_mixture",
        "aliases": ["Synthetic V2 Catalog Alias"],
        "evidence_review_snapshot_id": review.review_snapshot_id,
        "evidence_review_content_sha256": review.content_sha256,
        "claim_refs": [manifest.payload.claims[0].claim_ref],
    }
    catalog = MediumCatalogRepository(factory, reviews)
    catalog.create_catalog(
        catalog_id=CATALOG_ID,
        identity=creator,
        domain_pack_id=DOMAIN_PACK,
        created_at=CREATED_AT,
    )
    stored = catalog.store_snapshot(
        catalog_id=CATALOG_ID,
        raw_payload=json.dumps(
            {
                "media_catalog_schema_version": 1,
                "canonicalization_version": 1,
                "med_norm_contract_version": "MED-NORM-01.v1",
                "domain_pack_id": DOMAIN_PACK,
                "entries": [entry],
            }
        ),
        identity=creator,
        created_at=CREATED_AT,
    )
    assert catalog.load_snapshot(stored.snapshot_id, identity=creator) == stored


def test_01b_v2_persists_exact_binding_pin_and_evaluation_companions(tmp_path) -> None:
    _engine, factory, ruleset, evidence, _reviews = _repositories(tmp_path)
    manifest = _store_evidence(evidence, ruleset, media_identity=False)
    shadow = MaterialShadowRepository(factory)
    shadow_binding = _shadow_binding(
        ruleset,
        suffix="a",
        domain_pack_id=DOMAIN_PACK,
        domain_pack_version="2.0.0",
        valid_from="2026-07-18T18:00:00.000000Z",
        valid_until="2026-07-18T19:00:00.000000Z",
    )
    shadow.create_binding(
        shadow_binding, identity=SHADOW_IDENTITY, created_at=CREATED_AT
    )
    companion = EvidenceRuntimeBindingV2(
        binding_id=shadow_binding.binding_id,
        state=EvidenceRuntimeBindingState.BOUND_UNREVIEWED,
        ruleset_snapshot_id=ruleset.snapshot_id,
        ruleset_content_sha256=ruleset.content_sha256,
        evidence_snapshot_id=manifest.snapshot_id,
        evidence_content_sha256=manifest.content_sha256,
        evidence_manifest_schema_version=2,
        evidence_canonicalization_version=2,
        evidence_contract_version="MAT-EVID-01A.v2",
        domain_pack_id=DOMAIN_PACK,
        domain_pack_version="2.0.0",
        evaluator_version=shadow_binding.evaluator_version,
        kernel_version=shadow_binding.kernel_version,
    )
    with factory() as session, session.begin():
        MaterialEvidenceRuntimeRepositoryV2.insert_binding_companion(
            session,
            companion=companion,
            shadow=shadow_binding,
            actor_subject=SHADOW_IDENTITY.subject,
            created_at=CREATED_AT,
        )
    material_input = replace(
        _shadow_input(),
        domain_pack_id=DOMAIN_PACK,
        domain_pack_version="2.0.0",
    )
    captured = shadow.persist_pin_and_job(
        binding=shadow_binding,
        identity=SHADOW_IDENTITY,
        session_id="session-v2-evidence",
        correlation_id="request-v2-evidence",
        material_input=material_input,
        hmac_keyring=_keyring(),
        acquired_at="2026-07-18T18:01:00.000000Z",
    )
    with factory() as session, session.begin():
        pin = MaterialEvidenceRuntimeRepositoryV2.insert_pin_companion(
            session, shadow_pin=captured.pin, created_at=CREATED_AT
        )
    runtime = MaterialEvidenceRuntimeRepositoryV2(factory)
    assert runtime.load_binding(companion.binding_id) == companion
    assert runtime.load_pin(pin.pin_id) == pin

    worker = MaterialShadowWorker(
        session_factory=factory,
        cache=DictCache(),
        keyring=_keyring(),
    )
    assert worker.drain_once(now="2026-07-18T18:02:00.000000Z").evaluated == 1
    result = evaluate_with_evidence_v2(
        pin=pin,
        ruleset=ruleset,
        evidence=manifest,
        material_input=material_input,
    )
    fixed_audit_payload = {
        "binding_id": "msb_" + "b" * 32,
        "evaluation_id": "mse_" + "a" * 32,
        "pin_id": "msp_" + "c" * 32,
        "result_sha256": result.result_sha256,
        "stable_error_code": result.stable_error_code,
    }
    assert (
        result.result_sha256,
        _audit_hash(fixed_audit_payload),
    ) == (
        GOLDEN["runtime_result_sha256"],
        GOLDEN["runtime_audit_sha256"],
    )
    with factory() as session, session.begin():
        shadow_evaluation = session.scalar(
            select(V2MaterialShadowEvaluation).where(
                V2MaterialShadowEvaluation.pin_id == pin.pin_id
            )
        )
        assert shadow_evaluation is not None
        MaterialEvidenceRuntimeRepositoryV2.insert_evaluation_companion(
            session,
            evaluation_id=shadow_evaluation.evaluation_id,
            pin=pin,
            result=result,
            ruleset=ruleset,
            evidence=manifest,
            created_at=CREATED_AT,
        )
    with factory() as session:
        assert session.get(V2MaterialEvidenceRuntimeBindingV2, companion.binding_id)
        assert session.get(V2MaterialEvidenceRuntimePinV2, pin.pin_id)
        assert session.scalar(select(V2MaterialEvidenceRuntimeAuditEventV2))


def test_v2_empty_downgrade_only_and_partial_adoption_fail_closed(tmp_path) -> None:
    empty = make_engine(f"sqlite:///{tmp_path / 'empty-downgrade.db'}")
    _upgrade_engine(empty)
    with empty.begin() as connection:
        command.downgrade(_config(connection=connection), "20260718_0017")
    assert not V2_TABLES & set(inspect(empty).get_table_names())
    assert migration_status(empty) == ("20260718_0017", "20260718_0019")

    populated, _factory, ruleset, evidence, _reviews = _repositories(
        tmp_path, "populated-downgrade.db"
    )
    _store_evidence(evidence, ruleset, media_identity=True)
    with pytest.raises(RuntimeError, match="contain data"):
        with populated.begin() as connection:
            command.downgrade(_config(connection=connection), "20260718_0017")
    assert migration_status(populated)[0] == "20260718_0018"

    partial = make_engine(f"sqlite:///{tmp_path / 'partial-adoption.db'}")
    _upgrade_engine(partial, "20260718_0017")
    with partial.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE v2_material_evidence_manifests_v2 "
            "(manifest_id TEXT PRIMARY KEY)"
        )
    with pytest.raises(RuntimeError, match="partial MAT-EVID-02 schema"):
        _upgrade_engine(partial)


@pytest.mark.parametrize(
    "model",
    (
        V2MaterialEvidenceManifestV2,
        V2MaterialEvidenceSnapshotV2,
        V2MaterialEvidenceValidationEventV2,
        V2MaterialEvidenceAuditEventV2,
        V2MaterialEvidenceReviewDossierV2,
        V2MaterialEvidenceReviewSnapshotV2,
        V2MaterialEvidenceReviewValidationEventV2,
        V2MaterialEvidenceReviewLifecycleEventV2,
        V2MaterialEvidenceReviewAuditEventV2,
    ),
)
def test_populated_v2_manifest_and_review_tables_are_immutable(tmp_path, model) -> None:
    engine, factory, ruleset, evidence, reviews = _repositories(
        tmp_path, f"immutable-{model.__name__}.db"
    )
    manifest = _store_evidence(evidence, ruleset, media_identity=True)
    creator = _actor("creator", CREATE_ROLE)
    reviews.create_review(
        review_id=REVIEW_ID,
        evidence_snapshot_id=manifest.snapshot_id,
        identity=creator,
        created_at=CREATED_AT,
    )
    review = reviews.store_snapshot(
        review_id=REVIEW_ID,
        raw_payload=_review_raw(manifest),
        identity=creator,
        created_at=CREATED_AT,
    )
    reviews.record_review(
        review.review_snapshot_id,
        identity=_actor("reviewer", REVIEW_ROLE),
        created_at=CREATED_AT,
    )
    with factory() as session:
        row = session.scalar(select(model))
    assert row is not None
    key_column = next(iter(model.__table__.primary_key.columns))
    key = getattr(row, key_column.name)
    with pytest.raises(DBAPIError, match="MAT-EVID-02 immutable table"):
        with engine.begin() as connection:
            connection.execute(
                update(model).where(key_column == key).values({key_column.name: key})
            )
    with pytest.raises(DBAPIError, match="MAT-EVID-02 immutable table"):
        with engine.begin() as connection:
            connection.execute(delete(model).where(key_column == key))
