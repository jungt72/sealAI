from __future__ import annotations

import json
from pathlib import Path

import pytest

from sealai_v2.core.material_evidence import EvidenceManifestSnapshotV1
from sealai_v2.core.material_evidence_binding import (
    EvidenceRuntimeBindingState,
    MaterialEvidenceRuntimeErrorCode,
    MaterialEvidenceRuntimeIntegrityError,
)
from sealai_v2.core.material_evidence_binding_v2 import (
    EvidenceRuntimeBindingV2,
    EvidenceRuntimePinV2,
    validate_runtime_binding_v2,
)
from sealai_v2.core.material_evidence_review import (
    EvidenceReviewErrorCode,
    EvidenceReviewValidationError,
    compute_lifecycle_sha256,
)
from sealai_v2.core.material_evidence_review_v2 import (
    EvidenceReviewSnapshotV2,
    compute_review_audit_sha256_v2,
    compute_review_lifecycle_sha256_v2,
    compute_review_validation_sha256_v2,
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
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1


RULESET_ID = "mrs_" + "1" * 32
MANIFEST_ID = "mef_" + "2" * 32
REVIEW_ID = "mer_" + "3" * 32
MEDIA_REF = "med_" + "4" * 64
ASSERTION_REF = "med-norm-identity-sha256:" + "5" * 64
GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures/mat_evid_02_review_golden.json").read_text(
        encoding="utf-8"
    )
)


def _ruleset() -> MaterialRulesetSnapshotV1:
    return MaterialRulesetSnapshotV1.from_json(
        RULESET_ID,
        json.dumps(
            {
                "snapshot_schema_version": 1,
                "canonicalization_version": 1,
                "mat_gov_contract_version": "MAT-GOV-03A.v1",
                "domain_pack_id": "material.test.v2",
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
        ),
    )


def _source() -> EvidenceSourceV2:
    identity = {
        "document_id": "DOC-V2-REVIEW",
        "document_revision": "rev-2",
        "publication_edition": "edition-2",
        "content_sha256": "6" * 64,
    }
    return EvidenceSourceV2(source_ref=derive_source_ref_v2(**identity), **identity)


def _evidence(*, media_identity: bool) -> EvidenceManifestSnapshotV2:
    ruleset = _ruleset()
    scope = (
        MediaIdentityClaimScopeV2(MEDIA_REF, ASSERTION_REF)
        if media_identity
        else MaterialRelationClaimScopeV2(
            materials=("SYNTHETIC-MATERIAL",),
            media=(MEDIA_REF,),
            conditions=("synthetic-condition",),
        )
    )
    text = (
        "Synthetic v2 media identity claim."
        if media_identity
        else "Synthetic v2 material relation claim."
    )
    claim = AtomicEvidenceClaimV2(
        claim_ref=derive_claim_ref_v2(claim_text=text, scope=scope),
        claim_text=text,
        scope=scope,
        source_refs=(_source().source_ref,),
    )
    payload = EvidenceManifestPayloadV2(
        domain_pack_id="material.test.v2",
        target=(
            MediaIdentityTargetV2(MEDIA_REF)
            if media_identity
            else MaterialRelationTargetV2(ruleset.snapshot_id)
        ),
        sources=(_source(),),
        claims=(claim,),
        rule_claim_bindings=(
            ()
            if media_identity
            else (RuleClaimBindingV2("MR-V2-TEST", claim.claim_ref),)
        ),
    )
    return EvidenceManifestSnapshotV2.create(MANIFEST_ID, payload)


def _binding(evidence: EvidenceManifestSnapshotV2) -> EvidenceRuntimeBindingV2:
    ruleset = _ruleset()
    return EvidenceRuntimeBindingV2(
        binding_id="mshb_" + "7" * 32,
        state=EvidenceRuntimeBindingState.BOUND_UNREVIEWED,
        ruleset_snapshot_id=ruleset.snapshot_id,
        ruleset_content_sha256=ruleset.content_sha256,
        evidence_snapshot_id=evidence.snapshot_id,
        evidence_content_sha256=evidence.content_sha256,
        evidence_manifest_schema_version=2,
        evidence_canonicalization_version=2,
        evidence_contract_version="MAT-EVID-01A.v2",
        domain_pack_id="material.test.v2",
        domain_pack_version="2.0.0",
        evaluator_version="MAT-GOV-03B.eval.v1",
        kernel_version="MAT-GOV-02.kernel.v1",
    )


def _review_raw(evidence: EvidenceManifestSnapshotV2) -> str:
    claim = evidence.payload.claims[0]
    claim_type = (
        "other_technical"
        if type(claim.scope) is MediaIdentityClaimScopeV2
        else "incompatibility"
    )
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
                    "claim_type": claim_type,
                    "scope": claim.scope.to_dict(),
                    "required_source_types": ["manufacturer_datasheet"],
                }
            ],
            "claim_relations": [],
        }
    )


def test_01b_v2_binds_exact_material_relation_scope_only() -> None:
    ruleset = _ruleset()
    evidence = _evidence(media_identity=False)
    binding = _binding(evidence)
    resolved = validate_runtime_binding_v2(binding, ruleset=ruleset, evidence=evidence)
    assert resolved.references[0].rule_ref == "MR-V2-TEST"
    assert resolved.references[0].claim_ref == evidence.payload.claims[0].claim_ref
    assert binding.positive_statement_allowed is False
    assert (
        EvidenceRuntimePinV2("mshp_" + "8" * 32, binding).positive_statement_allowed
        is False
    )


def test_01b_v2_rejects_media_identity_manifest_and_v1_snapshot() -> None:
    ruleset = _ruleset()
    media = _evidence(media_identity=True)
    with pytest.raises(MaterialEvidenceRuntimeIntegrityError) as wrong_purpose:
        validate_runtime_binding_v2(_binding(media), ruleset=ruleset, evidence=media)
    assert wrong_purpose.value.code is MaterialEvidenceRuntimeErrorCode.SCOPE_MISMATCH

    with pytest.raises(MaterialEvidenceRuntimeIntegrityError) as wrong_version:
        validate_runtime_binding_v2(
            _binding(_evidence(media_identity=False)),
            ruleset=ruleset,
            evidence=object(),  # type: ignore[arg-type]
        )
    assert wrong_version.value.code is MaterialEvidenceRuntimeErrorCode.EVIDENCE_DRIFT
    assert EvidenceManifestSnapshotV1 is not EvidenceManifestSnapshotV2


@pytest.mark.parametrize("media_identity", (False, True))
def test_01c_v2_roundtrips_and_pins_exact_scope(media_identity: bool) -> None:
    evidence = _evidence(media_identity=media_identity)
    snapshot = EvidenceReviewSnapshotV2.from_json(REVIEW_ID, _review_raw(evidence))
    snapshot.payload.validate_against_evidence(evidence)
    snapshot.payload.validate_for_approval(evidence)
    assert snapshot.payload.claims[0].scope == evidence.payload.claims[0].scope
    assert snapshot.runtime_authority == "FACTUAL_REVIEW_ONLY"
    assert snapshot.positive_statement_allowed is False


def test_01c_v2_hash_domains_are_frozen() -> None:
    evidence = _evidence(media_identity=True)
    snapshot = EvidenceReviewSnapshotV2.from_json(REVIEW_ID, _review_raw(evidence))
    lifecycle_payload = {
        "actor_subject": "subject:reviewer",
        "event_type": "reviewed",
        "review_snapshot_id": "mrv_" + "a" * 64,
        "sequence_no": 1,
    }
    assert {
        "content_sha256": snapshot.content_sha256,
        "review_snapshot_id": snapshot.review_snapshot_id,
        "validation_sha256": compute_review_validation_sha256_v2(snapshot),
        "audit_sha256": compute_review_audit_sha256_v2(
            {
                "event_type": "review_snapshot_created",
                "review_snapshot_id": snapshot.review_snapshot_id,
            }
        ),
        "lifecycle_sha256": compute_review_lifecycle_sha256_v2(lifecycle_payload),
    } == GOLDEN
    assert compute_review_lifecycle_sha256_v2(
        lifecycle_payload
    ) != compute_lifecycle_sha256(lifecycle_payload)


def test_01c_v2_rejects_scope_drift_wrong_claim_type_unknown_fields_and_v1_versions() -> (
    None
):
    evidence = _evidence(media_identity=True)
    baseline = json.loads(_review_raw(evidence))

    drifted = json.loads(_review_raw(evidence))
    drifted["claims"][0]["scope"]["media_ref"] = "med_" + "9" * 64
    with pytest.raises(EvidenceReviewValidationError) as scope:
        EvidenceReviewSnapshotV2.from_json(
            REVIEW_ID, json.dumps(drifted)
        ).payload.validate_against_evidence(evidence)
    assert scope.value.code is EvidenceReviewErrorCode.CLAIM_SCOPE_MISMATCH

    wrong_type = json.loads(_review_raw(evidence))
    wrong_type["claims"][0]["claim_type"] = "incompatibility"
    with pytest.raises(EvidenceReviewValidationError) as claim_type:
        EvidenceReviewSnapshotV2.from_json(REVIEW_ID, json.dumps(wrong_type))
    assert claim_type.value.code is EvidenceReviewErrorCode.CLAIM_SCOPE_MISMATCH

    unknown = json.loads(_review_raw(evidence))
    unknown["claims"][0]["scope"]["materials"] = ["PLACEHOLDER"]
    with pytest.raises(EvidenceReviewValidationError) as field:
        EvidenceReviewSnapshotV2.from_json(REVIEW_ID, json.dumps(unknown))
    assert field.value.code is EvidenceReviewErrorCode.UNKNOWN_FIELD

    for key, value in (
        ("review_schema_version", 1),
        ("canonicalization_version", 1),
        ("mat_evid_review_contract_version", "MAT-EVID-01C.v1"),
        ("evidence_manifest_schema_version", 1),
        ("evidence_contract_version", "MAT-EVID-01A.v1"),
    ):
        changed = dict(baseline)
        changed[key] = value
        with pytest.raises(EvidenceReviewValidationError) as version:
            EvidenceReviewSnapshotV2.from_json(REVIEW_ID, json.dumps(changed))
        assert version.value.code is EvidenceReviewErrorCode.UNKNOWN_SCHEMA


@pytest.mark.parametrize(
    "required_source_types",
    (
        ["standard_metadata", "manufacturer_datasheet"],
        ["manufacturer_datasheet", "manufacturer_datasheet"],
    ),
)
def test_01c_v2_rejects_noncanonical_or_duplicate_required_source_types(
    required_source_types,
) -> None:
    evidence = _evidence(media_identity=True)
    value = json.loads(_review_raw(evidence))
    value["claims"][0]["required_source_types"] = required_source_types
    with pytest.raises(EvidenceReviewValidationError) as captured:
        EvidenceReviewSnapshotV2.from_json(REVIEW_ID, json.dumps(value))
    assert captured.value.code is EvidenceReviewErrorCode.NON_CANONICAL_ORDER
