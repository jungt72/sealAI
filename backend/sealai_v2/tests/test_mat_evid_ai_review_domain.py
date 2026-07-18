from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import json

import pytest

from sealai_v2.core.contracts import MaterialConstraintVerdict
from sealai_v2.core.material_evidence_ai_review import (
    AIEvidenceRisk,
    AIClaimContextV1,
    AIClaimPurpose,
    AIMaterialGranularity,
    AIMediumIdentityClaimContextV1,
    AIMediumIdentityContextV1,
    AIReviewEnvironment,
    AIReviewErrorCode,
    AIReviewEventType,
    AIReviewPayloadV1,
    AIReviewProjectionV1,
    AIReviewSnapshotV1,
    AIReviewState,
    AIReviewValidationError,
    AI_REVIEW_REQUIRED_USER_NOTICE,
    AISingleSourceTreatment,
    AISourceContextV1,
    AdjudicatorAgentRunV1,
    AgentExecutionIsolationV1,
    ChallengerAgentRunV1,
    CreatorAgentRunV1,
    canonicalize_ai_review_payload,
    compute_ai_review_audit_sha256,
    compute_ai_review_lifecycle_sha256,
    compute_ai_review_validation_sha256,
    parse_ai_review_payload,
    transition_ai_review,
)
from sealai_v2.core.material_evidence_review import (
    EvidenceDocumentType,
    EvidenceRightsState,
    ExactLocatorV1,
    IncludedExcerptV1,
    OmittedExcerptV1,
    ReviewedSourceMetadataV1,
    UnavailableLocatorV1,
)
from sealai_v2.core.material_evidence_v2 import (
    AtomicEvidenceClaimV2,
    EvidenceManifestPayloadV2,
    EvidenceManifestSnapshotV2,
    EvidenceSourceV2,
    MaterialRelationClaimScopeV2,
    MaterialRelationTargetV2,
    MediaIdentityClaimScopeV2,
    MediaIdentityTargetV2,
    RuleClaimBindingV2,
    derive_claim_ref_v2,
    derive_source_ref_v2,
)
from sealai_v2.core.material_rulesets import (
    MaterialRuleScopeV1,
    MaterialRuleV1,
    MaterialRulesetPayloadV1,
    MaterialRulesetSnapshotV1,
)
from sealai_v2.core.medium_catalog import (
    MediumIdentityKind,
    derive_media_id,
    derive_medium_identity_assertion_ref,
)
from sealai_v2.material_evidence_ai_review.audit import (
    AIFindingCategory,
    AIFindingSeverity,
    ClaudeChallengeV1,
    FindingAdjudicationV1,
    FindingDisposition,
    build_claude_audit_input,
    create_adjudication,
    create_corrected_media_identity_snapshot,
    create_corrected_snapshot_pair,
    parse_claude_audit_report,
)


RULESET_ID = "mrs_" + "1" * 32
MANIFEST_ID = "mef_" + "2" * 32
BATCH_ID = "mai_" + "3" * 32
MEDIUM_NAME = "SYNTHETIC-MEDIUM"
MEDIUM_KIND = MediumIdentityKind.FLUID_CLASS
MEDIA_REF = derive_media_id(MEDIUM_NAME, MEDIUM_KIND)
IDENTITY_ASSERTION_REF = derive_medium_identity_assertion_ref(
    media_id=MEDIA_REF,
    canonical_name=MEDIUM_NAME,
    identity_kind=MEDIUM_KIND,
    aliases=(),
)
DOMAIN_PACK = "material.ai.test.v1"
CLAIM_TEXT = "Synthetic source-scoped incompatibility claim."
SHA = lambda char: char * 64  # noqa: E731


def _creator(run_id: str = "codex-creator-run") -> CreatorAgentRunV1:
    return CreatorAgentRunV1(
        agent_model="codex-test-model",
        agent_version="test-version",
        prompt_version="creator-prompt.v1",
        prompt_sha256=SHA("a"),
        run_id=run_id,
        input_sha256=SHA("b"),
        output_sha256=SHA("c"),
    )


def _source_identity(digest: str = SHA("d")) -> EvidenceSourceV2:
    values = {
        "document_id": "DOC-AI-TEST-001",
        "document_revision": "rev-1",
        "publication_edition": "edition-1",
        "content_sha256": digest,
    }
    return EvidenceSourceV2(source_ref=derive_source_ref_v2(**values), **values)


def _ruleset() -> MaterialRulesetSnapshotV1:
    scope = MaterialRuleScopeV1(
        materials=("SYNTHETIC-COMPOUND",),
        media=(MEDIA_REF,),
        conditions=("synthetic-condition",),
    )
    return MaterialRulesetSnapshotV1.create(
        RULESET_ID,
        MaterialRulesetPayloadV1(
            domain_pack_id=DOMAIN_PACK,
            rules=(
                MaterialRuleV1(
                    rule_ref="MR-AI-TEST-001",
                    material=scope.materials[0],
                    medium=scope.media[0],
                    condition=scope.conditions[0],
                    verdict=MaterialConstraintVerdict.UNVERTRAEGLICH,
                    statement=CLAIM_TEXT,
                    scope=scope,
                ),
            ),
        ),
    )


def _evidence(ruleset: MaterialRulesetSnapshotV1 | None = None):
    ruleset = ruleset or _ruleset()
    source = _source_identity()
    scope = MaterialRelationClaimScopeV2(
        materials=("SYNTHETIC-COMPOUND",),
        media=(MEDIA_REF,),
        conditions=("synthetic-condition",),
    )
    claim = AtomicEvidenceClaimV2(
        claim_ref=derive_claim_ref_v2(claim_text=CLAIM_TEXT, scope=scope),
        claim_text=CLAIM_TEXT,
        scope=scope,
        source_refs=(source.source_ref,),
    )
    return EvidenceManifestSnapshotV2.create(
        MANIFEST_ID,
        EvidenceManifestPayloadV2(
            domain_pack_id=DOMAIN_PACK,
            target=MaterialRelationTargetV2(ruleset.snapshot_id),
            sources=(source,),
            claims=(claim,),
            rule_claim_bindings=(
                RuleClaimBindingV2("MR-AI-TEST-001", claim.claim_ref),
            ),
        ),
    )


def _identity_evidence() -> EvidenceManifestSnapshotV2:
    source = _source_identity()
    claim_text = "Synthetic source identifies the synthetic test medium."
    scope = MediaIdentityClaimScopeV2(
        media_ref=MEDIA_REF,
        identity_assertion_ref=IDENTITY_ASSERTION_REF,
    )
    claim = AtomicEvidenceClaimV2(
        claim_ref=derive_claim_ref_v2(claim_text=claim_text, scope=scope),
        claim_text=claim_text,
        scope=scope,
        source_refs=(source.source_ref,),
    )
    return EvidenceManifestSnapshotV2.create(
        "mef_" + "8" * 32,
        EvidenceManifestPayloadV2(
            domain_pack_id=DOMAIN_PACK,
            target=MediaIdentityTargetV2(MEDIA_REF),
            sources=(source,),
            claims=(claim,),
            rule_claim_bindings=(),
        ),
    )


def _payload(
    *,
    locator=None,
    rights_state: EvidenceRightsState = EvidenceRightsState.PERMITTED,
    creator: CreatorAgentRunV1 | None = None,
) -> tuple[AIReviewPayloadV1, MaterialRulesetSnapshotV1, EvidenceManifestSnapshotV2]:
    ruleset = _ruleset()
    evidence = _evidence(ruleset)
    identity_evidence = _identity_evidence()
    source = evidence.payload.sources[0]
    claim = evidence.payload.claims[0]
    payload = AIReviewPayloadV1(
        environment=AIReviewEnvironment.TEST,
        tenant_id="tenant-ai-test",
        domain_pack_id=DOMAIN_PACK,
        ruleset_snapshot_id=ruleset.snapshot_id,
        ruleset_content_sha256=ruleset.content_sha256,
        evidence_snapshot_id=evidence.snapshot_id,
        evidence_content_sha256=evidence.content_sha256,
        creator=creator or _creator(),
        sources=(
            AISourceContextV1(
                metadata=ReviewedSourceMetadataV1(
                    source_ref=source.source_ref,
                    document_id=source.document_id,
                    document_title="Synthetic test source",
                    publisher="Synthetic Independent Publisher",
                    document_type=EvidenceDocumentType.TECHNICAL_REPORT,
                    document_revision=source.document_revision,
                    publication_edition=source.publication_edition,
                    content_sha256=source.content_sha256,
                    locator=locator or ExactLocatorV1("section 1, table 2"),
                    rights_state=rights_state,
                    rights_basis="Synthetic test permission",
                    excerpt=(
                        OmittedExcerptV1()
                        if rights_state
                        in {EvidenceRightsState.UNKNOWN, EvidenceRightsState.RESTRICTED}
                        else IncludedExcerptV1(
                            text=(
                                "Synthetic source-scoped incompatibility claim; "
                                "synthetic source identifies the test medium."
                            ),
                            rights_basis="Synthetic test permission",
                        )
                    ),
                ),
                independence_group="publisher:synthetic-independent",
            ),
        ),
        media_identities=(
            AIMediumIdentityContextV1(
                media_ref=MEDIA_REF,
                canonical_name=MEDIUM_NAME,
                identity_kind=MEDIUM_KIND,
                aliases=(),
                identity_assertion_ref=IDENTITY_ASSERTION_REF,
                evidence_snapshot_id=identity_evidence.snapshot_id,
                evidence_content_sha256=identity_evidence.content_sha256,
                claims=tuple(
                    AIMediumIdentityClaimContextV1(
                        claim_ref=item.claim_ref,
                        claim_text=item.claim_text,
                        scope=item.scope,
                        source_refs=item.source_refs,
                    )
                    for item in identity_evidence.payload.claims
                ),
            ),
        ),
        claims=(
            AIClaimContextV1(
                claim_ref=claim.claim_ref,
                rule_ref="MR-AI-TEST-001",
                purpose=AIClaimPurpose.RULE_PRIMARY,
                claim_text=claim.claim_text,
                scope=claim.scope,
                source_refs=claim.source_refs,
                primary_source_refs=claim.source_refs,
                seal_type_scope="radial shaft seal",
                temperature_scope="source states no temperature extension",
                application_scope="synthetic test application only",
                conditions_and_exclusions="synthetic-condition; no extrapolation",
                expected_verdict=MaterialConstraintVerdict.UNVERTRAEGLICH,
                evidence_risk=AIEvidenceRisk.ORDINARY,
                material_granularity=AIMaterialGranularity.EXACT_COMPOUND,
                single_source_treatment=AISingleSourceTreatment.NARROW_SCOPE,
                conflicting_claim_refs=(),
            ),
        ),
    )
    return payload, ruleset, evidence


def _pass_report(snapshot: AIReviewSnapshotV1) -> str:
    claim_results = []
    for claim_ref in snapshot.payload.audit_claim_refs:
        claim_results.append(
            {
                "claim_ref": claim_ref,
                "contradiction_assessment": "No supplied contradiction.",
                "findings": [],
                "material_granularity_assessment": "Exact test scope.",
                "missing_conditions_assessment": "No missing condition found.",
                "positive_statement_assessment": "No positive statement.",
                "scope_assessment": "Scope matches the supplied test source.",
                "severity": "NONE",
                "source_coverage": "One exact source and locator supplied.",
                "source_overreach_assessment": "No overreach found.",
                "verdict": "PASS",
            }
        )
    return json.dumps(
        {
            "audit_contract_version": "MAT-EVID-AI-CHALLENGE.v1",
            "audit_schema_version": 1,
            "claim_results": claim_results,
            "overall_verdict": "PASS",
            "review_content_sha256": snapshot.content_sha256,
            "review_snapshot_id": snapshot.review_snapshot_id,
            "transport_complete": True,
        }
    )


def _challenger(snapshot: AIReviewSnapshotV1, report_hash: str) -> ChallengerAgentRunV1:
    return ChallengerAgentRunV1(
        agent_version="claude-cli-test-version",
        prompt_version="challenge.v1",
        prompt_sha256=SHA("e"),
        run_id="claude-independent-run",
        audit_input_sha256=build_claude_audit_input(snapshot).audit_input_sha256,
        audit_output_sha256=report_hash,
        isolation=AgentExecutionIsolationV1(False, False, False, 0, 0, False),
    )


def _adjudicator(run_id: str = "codex-adjudicator-run") -> AdjudicatorAgentRunV1:
    return AdjudicatorAgentRunV1(
        agent_model="codex-test-model",
        agent_version="test-version",
        prompt_version="adjudication.v1",
        prompt_sha256=SHA("f"),
        run_id=run_id,
        input_sha256=SHA("1"),
        output_sha256=SHA("2"),
    )


def test_snapshot_is_canonical_immutable_and_exactly_bound() -> None:
    payload, ruleset, evidence = _payload()
    payload.validate_against(ruleset, evidence, (_identity_evidence(),))
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    assert snapshot.canonical_bytes == canonicalize_ai_review_payload(payload)
    assert parse_ai_review_payload(snapshot.canonical_bytes) == payload
    assert snapshot.payload.authority == "AI_CROSS_REVIEW_NON_AUTHORITATIVE"
    assert snapshot.payload.positive_statement_allowed is False
    assert snapshot.payload.required_user_notice == AI_REVIEW_REQUIRED_USER_NOTICE
    with pytest.raises(FrozenInstanceError):
        snapshot.payload.tenant_id = "other"  # type: ignore[misc]


def test_ai_review_golden_hash_domains_are_frozen() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    audit_input = build_claude_audit_input(snapshot)
    report = parse_claude_audit_report(_pass_report(snapshot), snapshot)
    from sealai_v2.material_evidence_ai_review.audit import AUDIT_OUTPUT_DOMAIN

    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenge = ClaudeChallengeV1.create(
        snapshot,
        _challenger(snapshot, report_hash),
        report,
    )
    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator(),
        finding_adjudications=(),
    )

    assert snapshot.content_sha256 == (
        "1045adaa6023086c0bde3f86055866be3b856b73179d369a29b11dd914d35d2b"
    )
    assert snapshot.review_snapshot_id == (
        "mas_336fd08b3b68b8840089ca6dfd50ed4b981413be1821cbaef3415b304fc24f05"
    )
    assert compute_ai_review_validation_sha256(snapshot) == (
        "1136f191fb071ca35f139fe25db584a9dea2f2207fbdbb393ca5b695cfde9583"
    )
    assert audit_input.audit_input_sha256 == (
        "a234959e7f8e7d481f6db36a238b1efd4590c5c084e3491abdeb1d825c49bce9"
    )
    assert report_hash == (
        "605c1f7c24179141744c63a53bd13f81d4586c525d0162f0492a0359732991b2"
    )
    assert challenge.challenge_id == (
        "mac_dbe9a7ca462a0ddb448c3283cbeb7ca0ceb5fae7da20c050b269d818b2f84a6d"
    )
    assert adjudication.adjudication_id == (
        "maa_63705bb5799482cbe54c67044484cbacaabf6e4f1cde35f179682d0138477c46"
    )
    assert compute_ai_review_audit_sha256({"event": "golden", "sequence": 1}) == (
        "630e79eb4ead1dee89a3f6d88ac4f04c8cebcacc45ab44fadc8ee6b091b85948"
    )
    assert (
        compute_ai_review_lifecycle_sha256({"event": "golden", "sequence": 1})
        == "9071e4c1f44af3a1507dabf3a221889dd2afe752e1fc4e450fcb623bcdd77dd0"
    )


@pytest.mark.parametrize(
    "state",
    [
        "reviewed",
        "human_reviewed",
        "approved",
        "application_validated",
        "fachlich_freigegeben",
    ],
)
def test_human_or_approval_states_are_not_in_ai_taxonomy(state: str) -> None:
    with pytest.raises(ValueError):
        AIReviewState(state)


def test_production_and_positive_paths_fail_closed() -> None:
    payload, _, _ = _payload()
    raw = payload.to_dict()
    raw["environment"] = "production"
    with pytest.raises(AIReviewValidationError) as production:
        parse_ai_review_payload(json.dumps(raw))
    assert production.value.code is AIReviewErrorCode.INVALID_TYPE
    raw = payload.to_dict()
    raw["positive_statement_allowed"] = True
    with pytest.raises(AIReviewValidationError) as positive:
        parse_ai_review_payload(json.dumps(raw))
    assert positive.value.code is AIReviewErrorCode.POSITIVE_STATEMENT_FORBIDDEN


def test_verified_human_fields_do_not_exist_in_ai_serialization() -> None:
    payload, _, _ = _payload()
    serialized = json.dumps(payload.to_dict(), sort_keys=True)
    for forbidden in (
        "verified_human",
        "creator_subject",
        "reviewer_subject",
        "approver_subject",
        "approval_state",
        "human_reviewed",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda raw: raw.update({"authority": "FACTUAL_REVIEW_ONLY"}),
            AIReviewErrorCode.UNKNOWN_SCHEMA,
        ),
        (lambda raw: raw.update({"extra": "value"}), AIReviewErrorCode.UNKNOWN_FIELD),
        (
            lambda raw: raw["claims"][0].update({"expected_verdict": "vertraeglich"}),
            AIReviewErrorCode.POSITIVE_STATEMENT_FORBIDDEN,
        ),
        (
            lambda raw: raw["claims"][0].update({"ai_assisted": False}),
            AIReviewErrorCode.INVALID_TYPE,
        ),
        (
            lambda raw: raw.update({"required_user_notice": "Approved."}),
            AIReviewErrorCode.UNKNOWN_SCHEMA,
        ),
    ],
)
def test_closed_payload_rejects_authority_unknown_fields_and_positive_verdict(
    mutation, code
) -> None:
    payload, _, _ = _payload()
    raw = payload.to_dict()
    mutation(raw)
    with pytest.raises(AIReviewValidationError) as exc:
        parse_ai_review_payload(json.dumps(raw))
    assert exc.value.code is code


def test_missing_locator_and_unknown_rights_are_quarantine_preflight_failures() -> None:
    payload, _, _ = _payload(
        locator=UnavailableLocatorV1("exact location not established"),
        rights_state=EvidenceRightsState.UNKNOWN,
    )
    assert payload.eligibility_failures() == (
        f"excerpt:{payload.sources[0].source_ref}",
        f"locator:{payload.sources[0].source_ref}",
        f"rights:{payload.sources[0].source_ref}",
    )


def test_missing_permitted_excerpt_blocks_toolless_challenge() -> None:
    payload, _, _ = _payload()
    source = replace(
        payload.sources[0],
        metadata=replace(payload.sources[0].metadata, excerpt=OmittedExcerptV1()),
    )
    blocked = replace(payload, sources=(source,))
    assert blocked.eligibility_failures() == (
        f"excerpt:{payload.sources[0].source_ref}",
    )


def test_high_risk_family_single_source_fails_closed() -> None:
    payload, _, _ = _payload()
    claim = replace(
        payload.claims[0],
        evidence_risk=AIEvidenceRisk.FAMILY_WIDE,
        material_granularity=AIMaterialGranularity.MATERIAL_FAMILY,
        single_source_treatment=AISingleSourceTreatment.QUARANTINE,
    )
    changed = replace(payload, claims=(claim,))
    assert changed.eligibility_failures() == (
        f"family_single_source:{claim.claim_ref}",
    )


def test_high_risk_explicit_quarantine_blocks_challenge_eligibility() -> None:
    payload, _, _ = _payload()
    claim = replace(
        payload.claims[0],
        evidence_risk=AIEvidenceRisk.HARD_GATE,
        single_source_treatment=AISingleSourceTreatment.QUARANTINE,
    )
    changed = replace(payload, claims=(claim,))
    assert changed.eligibility_failures() == (
        f"single_source_quarantine:{claim.claim_ref}",
    )


def test_high_risk_single_source_without_narrow_or_quarantine_treatment_blocks() -> (
    None
):
    payload, _, _ = _payload()
    claim = replace(
        payload.claims[0],
        evidence_risk=AIEvidenceRisk.SAFETY_CRITICAL,
        single_source_treatment=AISingleSourceTreatment.STANDARD,
    )
    changed = replace(payload, claims=(claim,))
    assert changed.eligibility_failures() == (
        f"single_source_treatment_required:{claim.claim_ref}",
    )


def test_ordinary_exact_single_primary_source_is_eligible() -> None:
    payload, _, _ = _payload()
    claim = replace(
        payload.claims[0],
        evidence_risk=AIEvidenceRisk.ORDINARY,
        single_source_treatment=AISingleSourceTreatment.STANDARD,
    )
    assert replace(payload, claims=(claim,)).eligibility_failures() == ()


def test_conflict_references_must_be_internal_and_not_self_referential() -> None:
    payload, _, _ = _payload()
    for conflict_ref in (
        payload.claims[0].claim_ref,
        "mec_" + "9" * 64,
    ):
        with pytest.raises(AIReviewValidationError) as exc:
            replace(
                payload,
                claims=(
                    replace(
                        payload.claims[0],
                        conflicting_claim_refs=(conflict_ref,),
                    ),
                ),
            )
        assert exc.value.code is AIReviewErrorCode.INCOMPLETE_COVERAGE


def test_duplicate_property_and_non_nfc_have_stable_error_codes() -> None:
    payload, _, _ = _payload()
    raw = json.dumps(payload.to_dict(), ensure_ascii=False)
    duplicate = raw.replace(
        '"environment": "test"',
        '"environment": "test", "environment": "test"',
        1,
    )
    with pytest.raises(AIReviewValidationError) as duplicate_exc:
        parse_ai_review_payload(duplicate)
    assert duplicate_exc.value.code is AIReviewErrorCode.DUPLICATE_PROPERTY

    non_nfc = raw.replace("tenant-ai-test", "tenant-ai-te\u0301st")
    with pytest.raises(AIReviewValidationError) as nfc_exc:
        parse_ai_review_payload(non_nfc)
    assert nfc_exc.value.code is AIReviewErrorCode.NON_NFC


def test_snapshot_binding_rejects_hash_scope_and_rule_drift() -> None:
    payload, ruleset, evidence = _payload()
    with pytest.raises(AIReviewValidationError) as hash_drift:
        replace(payload, evidence_content_sha256=SHA("9")).validate_against(
            ruleset, evidence, (_identity_evidence(),)
        )
    assert hash_drift.value.code is AIReviewErrorCode.HASH_MISMATCH
    with pytest.raises(AIReviewValidationError) as claim_drift:
        replace(
            payload,
            claims=(replace(payload.claims[0], claim_text="Changed claim."),),
        ).validate_against(ruleset, evidence, (_identity_evidence(),))
    assert claim_drift.value.code is AIReviewErrorCode.SCOPE_MISMATCH


def test_rule_media_requires_exact_source_bound_non_authoritative_identity() -> None:
    payload, ruleset, evidence = _payload()
    identity_evidence = _identity_evidence()
    payload.validate_against(ruleset, evidence, (identity_evidence,))
    identity = payload.media_identities[0]
    assert identity.media_ref == payload.claims[0].scope.media[0]
    assert identity.identity_assertion_ref == IDENTITY_ASSERTION_REF
    assert identity.evidence_snapshot_id == identity_evidence.snapshot_id
    assert "evidence_review_snapshot_id" not in identity.to_dict()

    with pytest.raises(AIReviewValidationError) as absent:
        replace(payload, media_identities=())
    assert absent.value.code is AIReviewErrorCode.INVALID_TYPE

    with pytest.raises(AIReviewValidationError) as hash_drift:
        replace(
            payload,
            media_identities=(replace(identity, evidence_content_sha256=SHA("9")),),
        ).validate_against(ruleset, evidence, (identity_evidence,))
    assert hash_drift.value.code is AIReviewErrorCode.HASH_MISMATCH


def test_media_identity_candidate_cannot_impersonate_verified_catalog_entry() -> None:
    payload, _, _ = _payload()
    identity = payload.media_identities[0]
    with pytest.raises(AIReviewValidationError) as identity_drift:
        replace(identity, canonical_name="DIFFERENT-MEDIUM")
    assert identity_drift.value.code is AIReviewErrorCode.HASH_MISMATCH
    with pytest.raises(AIReviewValidationError) as assertion_drift:
        replace(
            identity,
            identity_assertion_ref=("med-norm-identity-sha256:" + "0" * 64),
        )
    assert assertion_drift.value.code is AIReviewErrorCode.HASH_MISMATCH


def test_claude_corpus_covers_rule_and_media_identity_claims_exactly() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    audit = json.loads(build_claude_audit_input(snapshot).canonical_bytes)
    assert tuple(item["claim_ref"] for item in audit["claims"]) == (
        payload.audit_claim_refs
    )
    assert {item["claim_kind"] for item in audit["claims"]} == {
        "material_rule",
        "media_identity",
    }
    assert audit["evidence_binding"]["media_identity_evidence"] == [
        {
            "evidence_content_sha256": payload.media_identities[
                0
            ].evidence_content_sha256,
            "evidence_snapshot_id": payload.media_identities[0].evidence_snapshot_id,
            "identity_assertion_ref": IDENTITY_ASSERTION_REF,
            "media_ref": MEDIA_REF,
        }
    ]


def test_audit_input_is_deterministic_and_excludes_identity_and_reasoning() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    first = build_claude_audit_input(snapshot)
    second = build_claude_audit_input(snapshot)
    assert first == second
    decoded = first.canonical_bytes.decode("utf-8")
    assert payload.tenant_id not in decoded
    assert payload.creator.run_id not in decoded
    assert 'creator_reasoning_included":false' in decoded
    assert CLAIM_TEXT in decoded


def test_pass_report_challenge_and_adjudication_are_independent() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    report = parse_claude_audit_report(_pass_report(snapshot), snapshot)
    from sealai_v2.material_evidence_ai_review.audit import AUDIT_OUTPUT_DOMAIN

    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenge = ClaudeChallengeV1.create(
        snapshot, _challenger(snapshot, report_hash), report
    )
    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator(),
        finding_adjudications=(),
    )
    assert adjudication.outcome.value == "ai_cross_reviewed_non_authoritative"

    assert adjudication.event_type is AIReviewEventType.CROSS_REVIEWED
    assert (
        len(
            {
                payload.creator.run_id,
                challenge.challenger.run_id,
                adjudication.adjudicator.run_id,
            }
        )
        == 3
    )


def test_report_requires_complete_exact_claim_coverage_and_closed_schema() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    raw = json.loads(_pass_report(snapshot))
    raw["unexpected"] = True
    with pytest.raises(AIReviewValidationError) as unknown:
        parse_claude_audit_report(json.dumps(raw), snapshot)
    assert unknown.value.code is AIReviewErrorCode.UNKNOWN_FIELD
    raw = json.loads(_pass_report(snapshot))
    raw["claim_results"] = []
    with pytest.raises(AIReviewValidationError):
        parse_claude_audit_report(json.dumps(raw), snapshot)


def test_medium_finding_cannot_be_accepted_nonblocking() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    raw = json.loads(_pass_report(snapshot))
    raw["overall_verdict"] = "CHANGES_REQUIRED"
    result = next(
        item
        for item in raw["claim_results"]
        if item["claim_ref"] == snapshot.payload.claims[0].claim_ref
    )
    result["verdict"] = "CHANGES_REQUIRED"
    result["severity"] = "MEDIUM"
    result["findings"] = [
        {
            "category": AIFindingCategory.SCOPE_ERROR.value,
            "detail": "Synthetic scope issue.",
            "finding_ref": "AIF-SCOPE-001",
            "recommended_correction": "Create a new narrower snapshot.",
            "severity": AIFindingSeverity.MEDIUM.value,
        }
    ]
    report = parse_claude_audit_report(json.dumps(raw), snapshot)
    from sealai_v2.material_evidence_ai_review.audit import AUDIT_OUTPUT_DOMAIN

    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenge = ClaudeChallengeV1.create(
        snapshot, _challenger(snapshot, report_hash), report
    )
    with pytest.raises(AIReviewValidationError) as exc:
        create_adjudication(
            snapshot=snapshot,
            challenge=challenge,
            adjudicator=_adjudicator(),
            finding_adjudications=(
                FindingAdjudicationV1(
                    "AIF-SCOPE-001",
                    FindingDisposition.ACCEPTED_NONBLOCKING,
                    "Not permitted for a medium finding.",
                ),
            ),
        )
    assert exc.value.code is AIReviewErrorCode.INVALID_TRANSITION


def test_factual_correction_requires_changed_immutable_evidence_and_new_challenge() -> (
    None
):
    payload, ruleset, evidence = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    raw = json.loads(_pass_report(snapshot))
    raw["overall_verdict"] = "CHANGES_REQUIRED"
    result = next(
        item
        for item in raw["claim_results"]
        if item["claim_ref"] == snapshot.payload.claims[0].claim_ref
    )
    result["verdict"] = "CHANGES_REQUIRED"
    result["severity"] = "MEDIUM"
    result["findings"] = [
        {
            "category": AIFindingCategory.SOURCE_COVERAGE.value,
            "detail": "Synthetic source revision requires a new Evidence snapshot.",
            "finding_ref": "AIF-SOURCE-REVISION-001",
            "recommended_correction": "Bind the exact revised source digest.",
            "severity": AIFindingSeverity.MEDIUM.value,
        }
    ]
    report = parse_claude_audit_report(json.dumps(raw), snapshot)
    from sealai_v2.material_evidence_ai_review.audit import AUDIT_OUTPUT_DOMAIN

    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenge = ClaudeChallengeV1.create(
        snapshot,
        _challenger(snapshot, report_hash),
        report,
    )

    revised_source = _source_identity(SHA("8"))
    revised_claim = replace(
        evidence.payload.claims[0],
        source_refs=(revised_source.source_ref,),
    )
    revised_payload = replace(
        evidence.payload,
        sources=(revised_source,),
        claims=(revised_claim,),
    )
    corrected_ruleset, corrected_evidence = create_corrected_snapshot_pair(
        previous_ruleset=ruleset,
        previous_evidence=evidence,
        ruleset_id=RULESET_ID,
        ruleset_payload=ruleset.payload,
        manifest_id=MANIFEST_ID,
        evidence_payload=revised_payload,
    )
    assert corrected_ruleset == ruleset
    assert corrected_evidence.content_sha256 != evidence.content_sha256

    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator("codex-correction-adjudicator"),
        finding_adjudications=(
            FindingAdjudicationV1(
                "AIF-SOURCE-REVISION-001",
                FindingDisposition.CORRECTED_IN_NEW_SNAPSHOT,
                "The exact source revision is bound in a new immutable manifest.",
            ),
        ),
        replacement_ruleset=corrected_ruleset,
        replacement_evidence=corrected_evidence,
    )
    assert adjudication.outcome.value == "changes_required"
    assert adjudication.replacement_ruleset_snapshot_id == ruleset.snapshot_id
    assert (
        adjudication.replacement_evidence_snapshot_id == corrected_evidence.snapshot_id
    )

    revised_source_context = replace(
        payload.sources[0],
        metadata=replace(
            payload.sources[0].metadata,
            source_ref=revised_source.source_ref,
            content_sha256=revised_source.content_sha256,
        ),
    )
    revised_claim_context = replace(
        payload.claims[0],
        source_refs=(revised_source.source_ref,),
        primary_source_refs=(revised_source.source_ref,),
    )
    revised_review_payload = replace(
        payload,
        evidence_snapshot_id=corrected_evidence.snapshot_id,
        evidence_content_sha256=corrected_evidence.content_sha256,
        creator=_creator("codex-corrected-creator-run"),
        sources=tuple(
            sorted(
                (payload.sources[0], revised_source_context),
                key=lambda item: item.source_ref,
            )
        ),
        claims=(revised_claim_context,),
    )
    revised_review_payload.validate_against(
        corrected_ruleset, corrected_evidence, (_identity_evidence(),)
    )
    revised_review = AIReviewSnapshotV1.create(
        "mai_" + "8" * 32,
        revised_review_payload,
    )
    assert revised_review.review_snapshot_id != snapshot.review_snapshot_id
    assert (
        build_claude_audit_input(revised_review).audit_input_sha256
        != challenge.challenger.audit_input_sha256
    )

    with pytest.raises(AIReviewValidationError) as no_op:
        create_corrected_snapshot_pair(
            previous_ruleset=ruleset,
            previous_evidence=evidence,
            ruleset_id=RULESET_ID,
            ruleset_payload=ruleset.payload,
            manifest_id="mef_" + "9" * 32,
            evidence_payload=evidence.payload,
        )
    assert no_op.value.code is AIReviewErrorCode.INVALID_TRANSITION


def test_media_identity_finding_requires_new_exact_identity_evidence_snapshot() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    raw = json.loads(_pass_report(snapshot))
    raw["overall_verdict"] = "CHANGES_REQUIRED"
    identity_claim_ref = payload.media_identities[0].claims[0].claim_ref
    result = next(
        item for item in raw["claim_results"] if item["claim_ref"] == identity_claim_ref
    )
    result["verdict"] = "CHANGES_REQUIRED"
    result["severity"] = "MEDIUM"
    result["findings"] = [
        {
            "category": AIFindingCategory.SOURCE_COVERAGE.value,
            "detail": "The media identity requires a corrected source snapshot.",
            "finding_ref": "AIF-MEDIA-IDENTITY-001",
            "recommended_correction": "Create new immutable identity Evidence.",
            "severity": AIFindingSeverity.MEDIUM.value,
        }
    ]
    report = parse_claude_audit_report(json.dumps(raw), snapshot)
    from sealai_v2.material_evidence_ai_review.audit import AUDIT_OUTPUT_DOMAIN

    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenge = ClaudeChallengeV1.create(
        snapshot, _challenger(snapshot, report_hash), report
    )

    previous = _identity_evidence()
    revised_source = _source_identity(SHA("7"))
    revised_claim = replace(
        previous.payload.claims[0], source_refs=(revised_source.source_ref,)
    )
    revised_payload = replace(
        previous.payload,
        sources=(revised_source,),
        claims=(revised_claim,),
    )
    corrected = create_corrected_media_identity_snapshot(
        previous_evidence=previous,
        manifest_id=previous.manifest_id,
        evidence_payload=revised_payload,
    )
    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator("codex-media-identity-correction"),
        finding_adjudications=(
            FindingAdjudicationV1(
                "AIF-MEDIA-IDENTITY-001",
                FindingDisposition.CORRECTED_IN_NEW_SNAPSHOT,
                "A new exact media_identity Evidence snapshot is required.",
            ),
        ),
        replacement_media_identity_evidence=(corrected,),
    )
    assert adjudication.outcome.value == "changes_required"
    assert adjudication.replacement_ruleset_snapshot_id == "not_applicable"
    assert adjudication.replacement_evidence_snapshot_id == "not_applicable"
    assert adjudication.replacement_media_identity_evidence[0].media_ref == MEDIA_REF

    with pytest.raises(AIReviewValidationError) as no_change:
        create_corrected_media_identity_snapshot(
            previous_evidence=previous,
            manifest_id="mef_" + "9" * 32,
            evidence_payload=previous.payload,
        )
    assert no_change.value.code is AIReviewErrorCode.INVALID_TRANSITION


def test_pass_with_low_finding_can_be_adjudicated_nonblocking() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    raw = json.loads(_pass_report(snapshot))
    result = next(
        item
        for item in raw["claim_results"]
        if item["claim_ref"] == snapshot.payload.claims[0].claim_ref
    )
    result["severity"] = "LOW"
    result["findings"] = [
        {
            "category": AIFindingCategory.NON_FACTUAL_DOCUMENTATION.value,
            "detail": "Synthetic documentation-only observation.",
            "finding_ref": "AIF-LOW-001",
            "recommended_correction": "Track as a non-factual follow-up.",
            "severity": AIFindingSeverity.LOW.value,
        }
    ]
    report = parse_claude_audit_report(json.dumps(raw), snapshot)
    from sealai_v2.material_evidence_ai_review.audit import AUDIT_OUTPUT_DOMAIN

    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenge = ClaudeChallengeV1.create(
        snapshot,
        _challenger(snapshot, report_hash),
        report,
    )
    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator("codex-low-adjudicator"),
        finding_adjudications=(
            FindingAdjudicationV1(
                "AIF-LOW-001",
                FindingDisposition.ACCEPTED_NONBLOCKING,
                "No factual, scope, rights, hash, or governance effect.",
            ),
        ),
    )
    assert adjudication.outcome.value == "ai_cross_reviewed_non_authoritative"

    result_with_finding = next(item for item in report.claim_results if item.findings)
    first = replace(result_with_finding, claim_ref="mec_" + "0" * 64)
    second = replace(result_with_finding, claim_ref="mec_" + "1" * 64)
    with pytest.raises(AIReviewValidationError) as duplicate_finding:
        type(report)(
            review_snapshot_id=report.review_snapshot_id,
            review_content_sha256=report.review_content_sha256,
            overall_verdict=report.overall_verdict,
            claim_results=(first, second),
            transport_complete=True,
        )
    assert duplicate_finding.value.code is AIReviewErrorCode.INCOMPLETE_COVERAGE


def test_low_factual_finding_cannot_be_accepted_nonblocking() -> None:
    payload, _, _ = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    raw = json.loads(_pass_report(snapshot))
    result = next(
        item
        for item in raw["claim_results"]
        if item["claim_ref"] == snapshot.payload.claims[0].claim_ref
    )
    result["severity"] = "LOW"
    result["findings"] = [
        {
            "category": AIFindingCategory.SCOPE_ERROR.value,
            "detail": "Synthetic factual scope observation.",
            "finding_ref": "AIF-LOW-SCOPE-001",
            "recommended_correction": "Change the factual scope.",
            "severity": AIFindingSeverity.LOW.value,
        }
    ]
    report = parse_claude_audit_report(json.dumps(raw), snapshot)
    from sealai_v2.material_evidence_ai_review.audit import AUDIT_OUTPUT_DOMAIN

    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenge = ClaudeChallengeV1.create(
        snapshot,
        _challenger(snapshot, report_hash),
        report,
    )
    with pytest.raises(AIReviewValidationError) as exc:
        create_adjudication(
            snapshot=snapshot,
            challenge=challenge,
            adjudicator=_adjudicator("codex-low-scope-adjudicator"),
            finding_adjudications=(
                FindingAdjudicationV1(
                    "AIF-LOW-SCOPE-001",
                    FindingDisposition.ACCEPTED_NONBLOCKING,
                    "A factual scope change cannot be nonblocking.",
                ),
            ),
        )
    assert exc.value.code is AIReviewErrorCode.INVALID_TRANSITION


def test_state_machine_has_no_approval_or_reentry_path() -> None:
    projection = transition_ai_review(
        AIReviewProjectionV1(), AIReviewEventType.CHALLENGED
    )
    assert projection.state is AIReviewState.AI_CHALLENGED
    projection = transition_ai_review(projection, AIReviewEventType.CROSS_REVIEWED)
    assert projection.state is AIReviewState.AI_CROSS_REVIEWED_NON_AUTHORITATIVE
    with pytest.raises(AIReviewValidationError):
        transition_ai_review(projection, AIReviewEventType.CHALLENGED)
    projection = transition_ai_review(projection, AIReviewEventType.QUARANTINED)
    assert projection.state is AIReviewState.QUARANTINED
    projection = transition_ai_review(projection, AIReviewEventType.REVOKED)
    assert projection.state is AIReviewState.REVOKED
    with pytest.raises(AIReviewValidationError):
        transition_ai_review(projection, AIReviewEventType.REVOKED)


def test_challenger_isolation_rejects_tool_web_or_session_access() -> None:
    for kwargs in (
        {"tools_enabled": True},
        {"mcp_enabled": True},
        {"hooks_enabled": True},
        {"web_search_requests": 1},
        {"web_fetch_requests": 1},
        {"session_persistence_enabled": True},
    ):
        values = {
            "tools_enabled": False,
            "mcp_enabled": False,
            "hooks_enabled": False,
            "web_search_requests": 0,
            "web_fetch_requests": 0,
            "session_persistence_enabled": False,
        }
        values.update(kwargs)
        with pytest.raises(AIReviewValidationError) as exc:
            AgentExecutionIsolationV1(**values)
        assert exc.value.code is AIReviewErrorCode.INVALID_AGENT
