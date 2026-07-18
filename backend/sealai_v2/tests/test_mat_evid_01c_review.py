from __future__ import annotations

from alembic import command
import json

import pytest
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.exc import DBAPIError

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_evidence import (
    AtomicEvidenceClaimV1,
    EvidenceClaimScopeV1,
    EvidenceManifestPayloadV1,
    EvidenceManifestSnapshotV1,
    RuleClaimBindingV1,
    derive_claim_ref,
    derive_source_ref,
)
from sealai_v2.core.material_evidence_review import (
    APPROVE_ROLE,
    CREATE_ROLE,
    HUMAN_ROLE,
    REVIEW_ROLE,
    EvidenceReviewErrorCode,
    EvidenceReviewIntegrityError,
    EvidenceReviewProjection,
    EvidenceReviewValidationError,
    FactualApprovalState,
    FactualReviewState,
    NO_RUNTIME_AUTHORITY,
    parse_review_payload,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_evidence_review import MaterialEvidenceReviewRepository
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import (
    V2MaterialEvidenceReviewAuditEvent,
    V2MaterialEvidenceReviewDossier,
    V2MaterialEvidenceReviewLifecycleEvent,
    V2MaterialEvidenceReviewSnapshot,
    V2MaterialEvidenceReviewValidationEvent,
)


RULESET_ID = "mrs_" + "1" * 32
MANIFEST_ID = "mef_" + "2" * 32
REVIEW_ID = "mer_" + "3" * 32
CREATED_AT = "2026-07-18T14:00:00Z"
REVIEW_TABLES = {
    "v2_material_evidence_review_dossiers",
    "v2_material_evidence_review_snapshots",
    "v2_material_evidence_review_validation_events",
    "v2_material_evidence_review_lifecycle_events",
    "v2_material_evidence_review_audit_events",
}


def _actor(subject: str, role: str, *, tenant: str = "tenant-a") -> VerifiedIdentity:
    return VerifiedIdentity(
        tenant,
        f"session-{subject}",
        subject,
        roles=(HUMAN_ROLE, role),
    )


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


def _evidence_payload(ruleset_snapshot_id: str) -> tuple[str, str, str]:
    source_values = {
        "document_id": "DOC-TEST-001",
        "document_revision": "rev-1",
        "publication_edition": "edition-2026-01",
        "content_sha256": "4" * 64,
    }
    source_ref = derive_source_ref(**source_values)
    scope = EvidenceClaimScopeV1(
        materials=("TEST-MATERIAL",),
        media=("TEST-MEDIUM",),
        conditions=("TEST-CONDITION",),
    )
    claim_text = "Synthetic atomic evidence claim."
    claim_ref = derive_claim_ref(claim_text=claim_text, scope=scope)
    return (
        json.dumps(
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
                "rule_claim_bindings": [
                    {"rule_ref": "MR-TEST-001", "claim_ref": claim_ref}
                ],
            }
        ),
        source_ref,
        claim_ref,
    )


def _review_payload(
    evidence,
    source_ref: str,
    claim_ref: str,
    *,
    rights_state: str = "permitted",
    document_type: str = "manufacturer_datasheet",
    required_source_types: list[str] | None = None,
    claim_relations: list[dict] | None = None,
    locator: dict | None = None,
    excerpt: dict | None = None,
) -> str:
    return json.dumps(
        {
            "review_schema_version": 1,
            "canonicalization_version": 1,
            "mat_evid_review_contract_version": "MAT-EVID-01C.v1",
            "evidence_snapshot_id": evidence.snapshot_id,
            "evidence_content_sha256": evidence.content_sha256,
            "evidence_manifest_schema_version": 1,
            "evidence_contract_version": "MAT-EVID-01A.v1",
            "sources": [
                {
                    "source_ref": source_ref,
                    "document_id": "DOC-TEST-001",
                    "document_title": "Synthetic technical source metadata",
                    "publisher": "Synthetic Publisher",
                    "document_type": document_type,
                    "document_revision": "rev-1",
                    "publication_edition": "edition-2026-01",
                    "content_sha256": "4" * 64,
                    "locator": locator or {"state": "exact", "value": "page 7"},
                    "rights_state": rights_state,
                    "rights_basis": "Synthetic test permission record",
                    "excerpt": excerpt or {"state": "omitted"},
                }
            ],
            "claims": [
                {
                    "claim_ref": claim_ref,
                    "claim_type": "conditional_compatibility",
                    "scope": {
                        "materials": ["TEST-MATERIAL"],
                        "media": ["TEST-MEDIUM"],
                        "conditions": ["TEST-CONDITION"],
                    },
                    "required_source_types": required_source_types
                    or ["manufacturer_datasheet"],
                }
            ],
            "claim_relations": claim_relations or [],
        }
    )


def _repository(tmp_path, name: str = "mat-evid-01c.db"):
    engine = make_engine(f"sqlite:///{tmp_path / name}")
    _upgrade_engine(engine, "20260718_0016")
    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    ruleset = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset_payload(),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    evidence_repo = MaterialEvidenceRepository(factory)
    evidence_repo.create_manifest(
        manifest_id=MANIFEST_ID,
        ruleset_snapshot_id=ruleset.snapshot_id,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    raw_evidence, source_ref, claim_ref = _evidence_payload(ruleset.snapshot_id)
    evidence = evidence_repo.store_snapshot(
        manifest_id=MANIFEST_ID,
        raw_payload=raw_evidence,
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    reviews = MaterialEvidenceReviewRepository(factory)
    creator = _actor("subject:creator", CREATE_ROLE)
    reviews.create_review(
        review_id=REVIEW_ID,
        evidence_snapshot_id=evidence.snapshot_id,
        identity=creator,
        created_at=CREATED_AT,
    )
    return engine, reviews, evidence, source_ref, claim_ref


def _store(reviews, evidence, source_ref, claim_ref, **kwargs):
    return reviews.store_snapshot(
        review_id=REVIEW_ID,
        raw_payload=_review_payload(evidence, source_ref, claim_ref, **kwargs),
        identity=_actor("subject:creator", CREATE_ROLE),
        created_at=CREATED_AT,
    )


def test_review_contract_round_trip_is_content_addressed_and_non_authoritative(
    tmp_path,
) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref)
    loaded = reviews.load_snapshot(
        stored.review_snapshot_id,
        identity=VerifiedIdentity("tenant-a", "read", "reader"),
    )
    assert loaded == stored
    projection = reviews.load_projection(
        stored.review_snapshot_id,
        identity=VerifiedIdentity("tenant-a", "read", "reader"),
    )
    assert projection == EvidenceReviewProjection()
    assert projection.runtime_authority == NO_RUNTIME_AUTHORITY
    assert projection.positive_statement_allowed is False


def test_human_creator_reviewer_and_approver_are_three_distinct_subjects(
    tmp_path,
) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref)
    reviewed = reviews.record_review(
        stored.review_snapshot_id,
        identity=_actor("subject:reviewer", REVIEW_ROLE),
        created_at="2026-07-18T14:01:00Z",
    )
    assert reviewed.review_state is FactualReviewState.REVIEWED
    assert reviewed.approval_state is FactualApprovalState.NOT_APPROVED
    approved = reviews.record_approval(
        stored.review_snapshot_id,
        identity=_actor("subject:approver", APPROVE_ROLE),
        created_at="2026-07-18T14:02:00Z",
    )
    assert approved.review_state is FactualReviewState.REVIEWED
    assert approved.approval_state is FactualApprovalState.APPROVED
    assert approved.runtime_authority == NO_RUNTIME_AUTHORITY
    assert approved.positive_statement_allowed is False
    loaded = reviews.load_projection(
        stored.review_snapshot_id,
        identity=VerifiedIdentity("tenant-a", "read", "reader"),
    )
    assert loaded == approved


@pytest.mark.parametrize(
    ("subject", "role", "method", "code"),
    [
        (
            "subject:creator",
            REVIEW_ROLE,
            "record_review",
            EvidenceReviewErrorCode.SELF_REVIEW,
        ),
        (
            "subject:creator",
            APPROVE_ROLE,
            "record_approval",
            EvidenceReviewErrorCode.INVALID_TRANSITION,
        ),
    ],
)
def test_self_review_and_premature_approval_fail_closed(
    tmp_path, subject, role, method, code
) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref)
    with pytest.raises(EvidenceReviewValidationError) as exc:
        getattr(reviews, method)(
            stored.review_snapshot_id,
            identity=_actor(subject, role),
            created_at="2026-07-18T14:01:00Z",
        )
    assert exc.value.code is code


def test_reviewer_cannot_self_approve(tmp_path) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref)
    reviewer = "subject:reviewer"
    reviews.record_review(
        stored.review_snapshot_id,
        identity=_actor(reviewer, REVIEW_ROLE),
        created_at="2026-07-18T14:01:00Z",
    )
    with pytest.raises(EvidenceReviewValidationError) as exc:
        reviews.record_approval(
            stored.review_snapshot_id,
            identity=_actor(reviewer, APPROVE_ROLE),
            created_at="2026-07-18T14:02:00Z",
        )
    assert exc.value.code is EvidenceReviewErrorCode.SELF_APPROVAL


@pytest.mark.parametrize(
    "roles",
    [(), (REVIEW_ROLE,), (HUMAN_ROLE,), ("llm_agent", REVIEW_ROLE)],
)
def test_non_verified_human_or_missing_role_cannot_review(tmp_path, roles) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref)
    with pytest.raises(EvidenceReviewValidationError) as exc:
        reviews.record_review(
            stored.review_snapshot_id,
            identity=VerifiedIdentity("tenant-a", "session", "subject:x", roles=roles),
            created_at="2026-07-18T14:01:00Z",
        )
    assert exc.value.code is EvidenceReviewErrorCode.ROLE_REQUIRED


@pytest.mark.parametrize("rights", ["unknown", "restricted"])
def test_unknown_or_restricted_rights_block_approval(tmp_path, rights) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref, rights_state=rights)
    reviews.record_review(
        stored.review_snapshot_id,
        identity=_actor("subject:reviewer", REVIEW_ROLE),
        created_at="2026-07-18T14:01:00Z",
    )
    with pytest.raises(EvidenceReviewValidationError) as exc:
        reviews.record_approval(
            stored.review_snapshot_id,
            identity=_actor("subject:approver", APPROVE_ROLE),
            created_at="2026-07-18T14:02:00Z",
        )
    assert exc.value.code is EvidenceReviewErrorCode.RIGHTS_BLOCKED


def test_required_source_type_is_checked_against_claim_sources(tmp_path) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    with pytest.raises(EvidenceReviewValidationError) as exc:
        _store(
            reviews,
            evidence,
            source_ref,
            claim_ref,
            required_source_types=["peer_reviewed_publication"],
        )
    assert exc.value.code is EvidenceReviewErrorCode.SOURCE_TYPE_MISMATCH


def test_exact_source_identity_scope_and_complete_coverage_are_required(
    tmp_path,
) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    payload = json.loads(_review_payload(evidence, source_ref, claim_ref))
    payload["sources"][0]["content_sha256"] = "5" * 64
    with pytest.raises(EvidenceReviewValidationError) as source_exc:
        reviews.store_snapshot(
            review_id=REVIEW_ID,
            raw_payload=json.dumps(payload),
            identity=_actor("subject:creator", CREATE_ROLE),
            created_at=CREATED_AT,
        )
    assert source_exc.value.code is EvidenceReviewErrorCode.SOURCE_IDENTITY_MISMATCH

    payload = json.loads(_review_payload(evidence, source_ref, claim_ref))
    payload["sources"][0]["document_id"] = "DOC-OTHER"
    with pytest.raises(EvidenceReviewValidationError) as document_exc:
        reviews.store_snapshot(
            review_id=REVIEW_ID,
            raw_payload=json.dumps(payload),
            identity=_actor("subject:creator", CREATE_ROLE),
            created_at=CREATED_AT,
        )
    assert document_exc.value.code is EvidenceReviewErrorCode.SOURCE_IDENTITY_MISMATCH

    payload = json.loads(_review_payload(evidence, source_ref, claim_ref))
    payload["claims"][0]["scope"]["media"] = ["OTHER-MEDIUM"]
    with pytest.raises(EvidenceReviewValidationError) as scope_exc:
        reviews.store_snapshot(
            review_id=REVIEW_ID,
            raw_payload=json.dumps(payload),
            identity=_actor("subject:creator", CREATE_ROLE),
            created_at=CREATED_AT,
        )
    assert scope_exc.value.code is EvidenceReviewErrorCode.CLAIM_SCOPE_MISMATCH

    payload = json.loads(_review_payload(evidence, source_ref, claim_ref))
    payload["claims"] = []
    with pytest.raises(EvidenceReviewValidationError) as coverage_exc:
        reviews.store_snapshot(
            review_id=REVIEW_ID,
            raw_payload=json.dumps(payload),
            identity=_actor("subject:creator", CREATE_ROLE),
            created_at=CREATED_AT,
        )
    assert coverage_exc.value.code in {
        EvidenceReviewErrorCode.INVALID_TYPE,
        EvidenceReviewErrorCode.INCOMPLETE_COVERAGE,
    }


def test_conflict_relations_are_structured_but_block_approval(tmp_path) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    # A relation cannot target a foreign claim.
    payload = json.loads(_review_payload(evidence, source_ref, claim_ref))
    payload["claim_relations"] = [
        {
            "kind": "supersedes",
            "subject_claim_ref": claim_ref,
            "object_claim_ref": "mec_" + "9" * 64,
        }
    ]
    with pytest.raises(EvidenceReviewValidationError) as exc:
        parse_review_payload(json.dumps(payload))
    assert exc.value.code is EvidenceReviewErrorCode.DANGLING_REF


def test_valid_conflict_relation_blocks_factual_approval() -> None:
    raw_evidence, source_ref, first_claim_ref = _evidence_payload("mss_" + "8" * 64)
    base = EvidenceManifestSnapshotV1.from_json(MANIFEST_ID, raw_evidence)
    second_scope = EvidenceClaimScopeV1(
        materials=("TEST-MATERIAL",),
        media=("TEST-MEDIUM",),
        conditions=("SECOND-CONDITION",),
    )
    second_text = "Second synthetic atomic evidence claim."
    second_claim_ref = derive_claim_ref(claim_text=second_text, scope=second_scope)
    second_claim = AtomicEvidenceClaimV1(
        claim_ref=second_claim_ref,
        claim_text=second_text,
        scope=second_scope,
        source_refs=(source_ref,),
    )
    claims = tuple(
        sorted((*base.payload.claims, second_claim), key=lambda item: item.claim_ref)
    )
    bindings = tuple(
        sorted(
            (
                RuleClaimBindingV1("MR-TEST-001", first_claim_ref),
                RuleClaimBindingV1("MR-TEST-002", second_claim_ref),
            ),
            key=lambda item: (item.rule_ref, item.claim_ref),
        )
    )
    evidence = EvidenceManifestSnapshotV1.create(
        MANIFEST_ID,
        EvidenceManifestPayloadV1(
            ruleset_snapshot_id=base.payload.ruleset_snapshot_id,
            domain_pack_id=base.payload.domain_pack_id,
            sources=base.payload.sources,
            claims=claims,
            rule_claim_bindings=bindings,
        ),
    )
    raw_review = json.loads(_review_payload(evidence, source_ref, first_claim_ref))
    raw_review["claims"].append(
        {
            "claim_ref": second_claim_ref,
            "claim_type": "conditional_compatibility",
            "scope": second_scope.to_dict(),
            "required_source_types": ["manufacturer_datasheet"],
        }
    )
    raw_review["claims"].sort(key=lambda item: item["claim_ref"])
    first, second = sorted((first_claim_ref, second_claim_ref))
    raw_review["claim_relations"] = [
        {
            "kind": "conflicts",
            "subject_claim_ref": first,
            "object_claim_ref": second,
        }
    ]
    review = parse_review_payload(json.dumps(raw_review))
    review.validate_against_evidence(evidence)
    with pytest.raises(EvidenceReviewValidationError) as exc:
        review.validate_for_approval(evidence)
    assert exc.value.code is EvidenceReviewErrorCode.CONFLICT_BLOCKED


def test_strict_json_duplicate_keys_and_duplicate_scope_values_are_rejected(
    tmp_path,
) -> None:
    _engine, _reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    raw = _review_payload(evidence, source_ref, claim_ref)
    duplicate = raw.replace(
        '"review_schema_version": 1,',
        '"review_schema_version": 1, "review_schema_version": 1,',
        1,
    )
    with pytest.raises(EvidenceReviewValidationError) as duplicate_exc:
        parse_review_payload(duplicate)
    assert duplicate_exc.value.code is EvidenceReviewErrorCode.DUPLICATE_PROPERTY

    payload = json.loads(raw)
    payload["claims"][0]["scope"]["conditions"] *= 2
    with pytest.raises(EvidenceReviewValidationError) as order_exc:
        parse_review_payload(json.dumps(payload))
    assert order_exc.value.code is EvidenceReviewErrorCode.NON_CANONICAL_ORDER


def test_short_excerpt_limit_and_explicit_unavailable_locator(tmp_path) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(
        reviews,
        evidence,
        source_ref,
        claim_ref,
        locator={"state": "unavailable", "reason": "No stable pagination"},
        excerpt={
            "state": "included",
            "text": "Short synthetic excerpt.",
            "rights_basis": "Synthetic test permission",
        },
    )
    assert stored.payload.sources[0].locator.to_dict()["state"] == "unavailable"
    with pytest.raises(EvidenceReviewValidationError) as exc:
        _store(
            reviews,
            evidence,
            source_ref,
            claim_ref,
            excerpt={
                "state": "included",
                "text": "x" * 281,
                "rights_basis": "Synthetic test permission",
            },
        )
    assert exc.value.code is EvidenceReviewErrorCode.RIGHTS_BLOCKED


def test_revocation_and_quarantine_are_terminal_fail_closed_states(tmp_path) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref)
    reviews.record_review(
        stored.review_snapshot_id,
        identity=_actor("subject:reviewer", REVIEW_ROLE),
        created_at="2026-07-18T14:01:00Z",
    )
    reviews.record_approval(
        stored.review_snapshot_id,
        identity=_actor("subject:approver", APPROVE_ROLE),
        created_at="2026-07-18T14:02:00Z",
    )
    revoked = reviews.record_revocation(
        stored.review_snapshot_id,
        identity=_actor("subject:revoker", APPROVE_ROLE),
        created_at="2026-07-18T14:03:00Z",
    )
    assert revoked.review_state is FactualReviewState.REVOKED
    assert revoked.approval_state is FactualApprovalState.REVOKED
    assert revoked.positive_statement_allowed is False
    with pytest.raises(EvidenceReviewValidationError):
        reviews.record_quarantine(
            stored.review_snapshot_id,
            identity=_actor("subject:quarantine", APPROVE_ROLE),
            created_at="2026-07-18T14:04:00Z",
        )


def test_tenant_isolation_comes_only_from_verified_identity(tmp_path) -> None:
    _engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref)
    with pytest.raises(EvidenceReviewValidationError) as exc:
        reviews.load_snapshot(
            stored.review_snapshot_id,
            identity=VerifiedIdentity("tenant-b", "session", "subject:b"),
        )
    assert exc.value.code is EvidenceReviewErrorCode.TENANT_MISMATCH


def test_migration_is_additive_empty_restrictive_and_immutable(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _upgrade_engine(engine, "20260718_0015")
    before = set(inspect(engine).get_table_names())
    _upgrade_engine(engine, "20260718_0016")
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - before == REVIEW_TABLES
    assert migration_status(engine) == ("20260718_0016", "20260718_0016")
    with engine.connect() as connection:
        for table in REVIEW_TABLES:
            assert (
                connection.exec_driver_sql(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).scalar_one()
                == 0
            )
            for foreign_key in inspector.get_foreign_keys(table):
                assert foreign_key["options"]["ondelete"].upper() == "RESTRICT"


@pytest.mark.parametrize(
    "model",
    [
        V2MaterialEvidenceReviewDossier,
        V2MaterialEvidenceReviewSnapshot,
        V2MaterialEvidenceReviewValidationEvent,
        V2MaterialEvidenceReviewLifecycleEvent,
        V2MaterialEvidenceReviewAuditEvent,
    ],
)
def test_every_01c_row_rejects_update_and_delete(tmp_path, model) -> None:
    engine, reviews, evidence, source_ref, claim_ref = _repository(
        tmp_path, name=f"immutable-{model.__tablename__}.db"
    )
    stored = _store(reviews, evidence, source_ref, claim_ref)
    reviews.record_review(
        stored.review_snapshot_id,
        identity=_actor("subject:reviewer", REVIEW_ROLE),
        created_at="2026-07-18T14:01:00Z",
    )
    factory = make_sessionmaker(engine)
    with factory() as session:
        identity = session.scalar(select(model))
        assert identity is not None
        primary_key = inspect(model).primary_key[0]
        value = getattr(identity, primary_key.name)
    with factory() as session, pytest.raises(DBAPIError):
        with session.begin():
            session.execute(
                update(model)
                .where(primary_key == value)
                .values(
                    {
                        next(
                            column.name
                            for column in inspect(model).columns
                            if not column.primary_key
                        ): "tamper"
                    }
                )
            )
    with factory() as session, pytest.raises(DBAPIError):
        with session.begin():
            session.execute(delete(model).where(primary_key == value))


def test_downgrade_refuses_nonempty_review_tables(tmp_path) -> None:
    engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    _store(reviews, evidence, source_ref, claim_ref)
    with engine.begin() as connection, pytest.raises(RuntimeError):
        command.downgrade(_config(connection=connection), "20260718_0015")


def test_load_requires_unique_intact_technical_evidence(tmp_path) -> None:
    engine, reviews, evidence, source_ref, claim_ref = _repository(tmp_path)
    stored = _store(reviews, evidence, source_ref, claim_ref)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "DROP TRIGGER "
            "trg_v2_material_evidence_review_audit_events_delete_immutable"
        )
        connection.exec_driver_sql(
            "DELETE FROM v2_material_evidence_review_audit_events "
            "WHERE review_snapshot_id = ?",
            (stored.review_snapshot_id,),
        )
    with pytest.raises(EvidenceReviewIntegrityError) as exc:
        reviews.load_snapshot(
            stored.review_snapshot_id,
            identity=VerifiedIdentity("tenant-a", "read", "reader"),
        )
    assert exc.value.code is EvidenceReviewErrorCode.DB_INTEGRITY


def test_no_repository_activation_or_publication_surface() -> None:
    for name in (
        "activate",
        "deploy",
        "publish",
        "create_pointer",
        "bind_runtime",
        "allow_positive_statement",
    ):
        assert not hasattr(MaterialEvidenceReviewRepository, name)
