from __future__ import annotations

from dataclasses import replace
import json

import pytest

from sealai_v2.core.contracts import (
    InputResolutionState,
    MediumCardinality,
    RelationState,
)
from sealai_v2.core.material_evidence import (
    EvidenceClaimScopeV1,
    EvidenceManifestSnapshotV1,
    derive_claim_ref,
    derive_source_ref,
)
from sealai_v2.core.material_evidence_binding import (
    BoundEvidenceReferenceV1,
    EvidenceRuntimeAuthority,
    EvidenceRuntimeBindingState,
    EvidenceRuntimeBindingV1,
    EvidenceRuntimePinV1,
    MaterialEvidenceRuntimeErrorCode,
    MaterialEvidenceRuntimeIntegrityError,
    validate_runtime_binding,
)
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.core.material_shadow import (
    ServerVerifiedCanonicalId,
    ShadowEnvironment,
    ShadowMaterialInput,
    ShadowMaterialRulesetPin,
    ShadowPurpose,
    ShadowScopeKind,
)
from sealai_v2.material_evidence_binding.cache import evidence_cache_key
from sealai_v2.material_evidence_binding.evaluator import (
    EvidenceRuntimeEvaluationV1,
    _build_result,
    evaluate_with_evidence,
    integrity_blocked_evaluation,
)
from sealai_v2.material_shadow.evaluator import evaluate_snapshot


RULESET_ID = "mrs_" + "1" * 32
MANIFEST_ID = "mef_" + "2" * 32


def _ruleset(*, reverse: bool = False) -> MaterialRulesetSnapshotV1:
    rules = [
        {
            "rule_ref": "MR-TEST-001",
            "material": "MAT.NBR",
            "medium": "MED.OIL",
            "condition": "COND.HOT",
            "verdict": "bedingt",
            "statement": "Synthetic condition; not a material release.",
            "scope": {
                "materials": ["MAT.NBR"],
                "media": ["MED.OIL"],
                "conditions": ["COND.HOT"],
            },
            "evidence_binding": {"state": "unbound"},
        },
        {
            "rule_ref": "MR-TEST-002",
            "material": "MAT.NBR",
            "medium": "MED.OIL",
            "condition": "COND.HOT",
            "verdict": "unvertraeglich",
            "statement": "Synthetic conflict; not a material release.",
            "scope": {
                "materials": ["MAT.NBR"],
                "media": ["MED.OIL"],
                "conditions": ["COND.HOT"],
            },
            "evidence_binding": {"state": "unbound"},
        },
    ]
    if reverse:
        rules.reverse()
    return MaterialRulesetSnapshotV1.from_json(
        RULESET_ID,
        json.dumps(
            {
                "snapshot_schema_version": 1,
                "canonicalization_version": 1,
                "mat_gov_contract_version": "MAT-GOV-03A.v1",
                "domain_pack_id": "material.test.v1",
                "positive_statement_allowed": False,
                "rules": rules,
            }
        ),
    )


def _source(index: int) -> dict[str, str]:
    values = {
        "document_id": f"DOC-{index}",
        "document_revision": "rev-1",
        "publication_edition": "edition-1",
        "content_sha256": f"{index:064x}",
    }
    return {"source_ref": derive_source_ref(**values), **values}


def _evidence(
    ruleset: MaterialRulesetSnapshotV1,
    *,
    bindings: list[tuple[str, str]] | None = None,
    second_scope: dict[str, list[str]] | None = None,
) -> EvidenceManifestSnapshotV1:
    sources = [_source(1), _source(2)]
    scope_dicts = [
        {"materials": ["MAT.NBR"], "media": ["MED.OIL"], "conditions": ["COND.HOT"]},
        second_scope
        or {"materials": ["MAT.NBR"], "media": ["MED.OIL"], "conditions": ["COND.HOT"]},
    ]
    claims = []
    for index in (1, 2):
        scope = EvidenceClaimScopeV1(
            materials=tuple(scope_dicts[index - 1]["materials"]),
            media=tuple(scope_dicts[index - 1]["media"]),
            conditions=tuple(scope_dicts[index - 1]["conditions"]),
        )
        text = f"Synthetic atomic claim {index}."
        claims.append(
            {
                "claim_ref": derive_claim_ref(claim_text=text, scope=scope),
                "claim_text": text,
                "scope": scope.to_dict(),
                "source_refs": [sources[index - 1]["source_ref"]],
            }
        )
    chosen = bindings or [
        ("MR-TEST-001", claims[0]["claim_ref"]),
        ("MR-TEST-002", claims[1]["claim_ref"]),
    ]
    raw = {
        "evidence_manifest_schema_version": 1,
        "canonicalization_version": 1,
        "mat_evid_contract_version": "MAT-EVID-01A.v1",
        "ruleset_snapshot_id": ruleset.snapshot_id,
        "domain_pack_id": "material.test.v1",
        "sources": sources,
        "claims": claims,
        "rule_claim_bindings": [
            {"rule_ref": rule_ref, "claim_ref": claim_ref}
            for rule_ref, claim_ref in chosen
        ],
    }
    return EvidenceManifestSnapshotV1.from_json(MANIFEST_ID, json.dumps(raw))


def _binding(
    ruleset: MaterialRulesetSnapshotV1,
    evidence: EvidenceManifestSnapshotV1 | None,
) -> EvidenceRuntimeBindingV1:
    state = (
        EvidenceRuntimeBindingState.UNBOUND
        if evidence is None
        else EvidenceRuntimeBindingState.BOUND_UNREVIEWED
    )
    return EvidenceRuntimeBindingV1(
        binding_id="mshb_" + "3" * 32,
        state=state,
        ruleset_snapshot_id=ruleset.snapshot_id,
        ruleset_content_sha256=ruleset.content_sha256,
        evidence_snapshot_id=evidence.snapshot_id if evidence else None,
        evidence_content_sha256=evidence.content_sha256 if evidence else None,
        evidence_manifest_schema_version=1 if evidence else None,
        evidence_canonicalization_version=1 if evidence else None,
        evidence_contract_version="MAT-EVID-01A.v1" if evidence else None,
        domain_pack_id="material.test.v1",
        domain_pack_version="1.0.0",
        evaluator_version="MAT-GOV-03B.eval.v1",
        kernel_version="MAT-GOV-02.kernel.v1",
    )


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


def _shadow_pin(binding: EvidenceRuntimeBindingV1) -> ShadowMaterialRulesetPin:
    return ShadowMaterialRulesetPin(
        pin_id="mshp_" + "4" * 32,
        binding_id=binding.binding_id,
        snapshot_id=binding.ruleset_snapshot_id,
        content_sha256=binding.ruleset_content_sha256,
        environment=ShadowEnvironment.STAGING,
        purpose=ShadowPurpose.MATERIAL_RULESET_SHADOW,
        scope_kind=ShadowScopeKind.GLOBAL,
        tenant_ref_hmac="a" * 64,
        hmac_key_id="key-v1",
        domain_pack_id=binding.domain_pack_id,
        domain_pack_version=binding.domain_pack_version,
        evaluator_version=binding.evaluator_version,
        kernel_version=binding.kernel_version,
        runtime_profile_sha256="5" * 64,
        build_git_sha="6" * 40,
        build_tree_hash="7" * 40,
        sampling_policy_version="MAT-GOV-03B.shadow.v1",
        sampled=False,
        acquired_at="2026-07-18T10:00:00.000000Z",
        binding_valid_until="2026-07-18T11:00:00.000000Z",
    )


def test_exact_complete_binding_is_unreviewed_non_positive_and_deterministic() -> None:
    ruleset = _ruleset()
    evidence = _evidence(ruleset)
    binding = _binding(ruleset, evidence)
    resolved = validate_runtime_binding(binding, ruleset=ruleset, evidence=evidence)
    assert resolved.state is EvidenceRuntimeBindingState.BOUND_UNREVIEWED
    assert [item.rule_ref for item in resolved.references] == [
        "MR-TEST-001",
        "MR-TEST-002",
    ]
    assert binding.authority is EvidenceRuntimeAuthority.TECHNICAL_UNREVIEWED
    assert binding.positive_statement_allowed is False

    pin = EvidenceRuntimePinV1(pin_id="mshp_" + "4" * 32, binding=binding)
    result = evaluate_with_evidence(
        pin=pin, ruleset=ruleset, evidence=evidence, material_input=_input()
    )
    technical = evaluate_snapshot(ruleset, _input())
    assert result.shadow_projection() == technical
    assert result.verdict == "unvertraeglich"
    assert result.positive_statement_allowed is False
    assert result.evidence_binding_state is EvidenceRuntimeBindingState.BOUND_UNREVIEWED


@pytest.mark.parametrize(
    ("case", "second_scope", "code"),
    [
        ("incomplete", None, MaterialEvidenceRuntimeErrorCode.INCOMPLETE),
        ("foreign", None, MaterialEvidenceRuntimeErrorCode.FOREIGN_RULE),
        ("reused", None, MaterialEvidenceRuntimeErrorCode.CLAIM_REUSED),
        (
            "scope",
            {
                "materials": ["MAT.OTHER"],
                "media": ["MED.OIL"],
                "conditions": ["COND.HOT"],
            },
            MaterialEvidenceRuntimeErrorCode.SCOPE_MISMATCH,
        ),
    ],
)
def test_incomplete_foreign_reused_or_scope_drift_fail_closed(
    case, second_scope, code
) -> None:
    ruleset = _ruleset()
    complete = _evidence(ruleset, second_scope=second_scope)
    claims = complete.payload.claims
    bindings = {
        "incomplete": [
            ("MR-TEST-001", claims[0].claim_ref),
            ("MR-TEST-001", claims[1].claim_ref),
        ],
        "foreign": [
            ("MR-TEST-001", claims[0].claim_ref),
            ("MR-FOREIGN", claims[1].claim_ref),
        ],
        "reused": [
            ("MR-TEST-001", claims[0].claim_ref),
            ("MR-TEST-002", claims[0].claim_ref),
            ("MR-TEST-002", claims[1].claim_ref),
        ],
        "scope": None,
    }[case]
    evidence = _evidence(ruleset, bindings=bindings, second_scope=second_scope)
    with pytest.raises(MaterialEvidenceRuntimeIntegrityError) as exc:
        validate_runtime_binding(
            _binding(ruleset, evidence), ruleset=ruleset, evidence=evidence
        )
    assert exc.value.code is code


def test_unbound_and_identity_drift_never_return_a_verdict() -> None:
    ruleset = _ruleset()
    unbound = _binding(ruleset, None)
    with pytest.raises(MaterialEvidenceRuntimeIntegrityError) as exc:
        validate_runtime_binding(unbound, ruleset=ruleset, evidence=None)
    assert exc.value.code is MaterialEvidenceRuntimeErrorCode.UNBOUND
    blocked = integrity_blocked_evaluation(
        pin=EvidenceRuntimePinV1(pin_id="mshp_" + "4" * 32, binding=unbound),
        code=exc.value.code,
    )
    assert blocked.evaluation_state == "integrity_blocked"
    assert blocked.verdict is blocked.decisive_ref is None
    assert blocked.matches == blocked.references == ()
    assert blocked.positive_statement_allowed is False

    evidence = _evidence(ruleset)
    binding = _binding(ruleset, evidence)
    with pytest.raises(MaterialEvidenceRuntimeIntegrityError) as drift:
        validate_runtime_binding(
            replace(binding, ruleset_content_sha256="f" * 64),
            ruleset=ruleset,
            evidence=evidence,
        )
    assert drift.value.code is MaterialEvidenceRuntimeErrorCode.RULESET_DRIFT


def test_domain_pack_version_drift_returns_integrity_blocked_not_an_exception() -> None:
    ruleset = _ruleset()
    evidence = _evidence(ruleset)
    binding = _binding(ruleset, evidence)
    pin = EvidenceRuntimePinV1(pin_id="mshp_" + "4" * 32, binding=binding)
    material_input = replace(_input(), domain_pack_version="2.0.0")
    result = evaluate_with_evidence(
        pin=pin,
        ruleset=ruleset,
        evidence=evidence,
        material_input=material_input,
    )
    assert result.evaluation_state == "integrity_blocked"
    assert result.stable_error_code == "MAT_EVID_RUNTIME_DOMAIN_PACK_MISMATCH"
    assert result.verdict is result.decisive_ref is None


def test_cache_key_pins_both_snapshot_hashes_and_has_no_ambiguous_segments() -> None:
    ruleset = _ruleset()
    evidence = _evidence(ruleset)
    binding = _binding(ruleset, evidence)
    pin = EvidenceRuntimePinV1(pin_id="mshp_" + "4" * 32, binding=binding)
    shadow_pin = _shadow_pin(binding)
    baseline = evidence_cache_key(
        shadow_pin=shadow_pin, evidence_pin=pin, input_fingerprint="8" * 64
    )
    changed = evidence_cache_key(
        shadow_pin=shadow_pin,
        evidence_pin=replace(
            pin, binding=replace(binding, evidence_content_sha256="9" * 64)
        ),
        input_fingerprint="8" * 64,
    )
    assert baseline.startswith("mat-evid-bind:v1:")
    assert baseline != changed


def test_closed_result_deserialization_rejects_positive_or_unknown_states() -> None:
    ruleset = _ruleset()
    evidence = _evidence(ruleset)
    binding = _binding(ruleset, evidence)
    result = evaluate_with_evidence(
        pin=EvidenceRuntimePinV1(pin_id="mshp_" + "4" * 32, binding=binding),
        ruleset=ruleset,
        evidence=evidence,
        material_input=_input(),
    )
    assert EvidenceRuntimeEvaluationV1.from_dict(result.to_dict()) == result
    for field, value in (
        ("positive_statement_allowed", True),
        ("evidence_binding_state", "reviewed"),
        ("evaluation_state", "future_state"),
    ):
        payload = {**result.to_dict(), field: value}
        with pytest.raises((TypeError, ValueError)):
            EvidenceRuntimeEvaluationV1.from_dict(payload)


def _replace_result_references(
    result: EvidenceRuntimeEvaluationV1,
    references: tuple[BoundEvidenceReferenceV1, ...],
) -> EvidenceRuntimeEvaluationV1:
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


@pytest.mark.parametrize("case", ("missing", "foreign_rule"))
def test_completed_result_requires_references_for_exactly_its_matches(case) -> None:
    ruleset = _ruleset()
    evidence = _evidence(ruleset)
    binding = _binding(ruleset, evidence)
    result = evaluate_with_evidence(
        pin=EvidenceRuntimePinV1(pin_id="mshp_" + "4" * 32, binding=binding),
        ruleset=ruleset,
        evidence=evidence,
        material_input=_input(),
    )
    references = (
        ()
        if case == "missing"
        else tuple(
            sorted(
                (
                    *result.references,
                    BoundEvidenceReferenceV1(
                        rule_ref="MR-FOREIGN",
                        claim_ref="claim-forged",
                        source_refs=("source-forged",),
                    ),
                )
            )
        )
    )
    with pytest.raises(
        ValueError,
        match="requires evidence for exactly its matches",
    ):
        _replace_result_references(result, references)


def test_rule_and_manifest_order_do_not_change_bound_result() -> None:
    first = _ruleset()
    second = _ruleset(reverse=True)
    first_evidence = _evidence(first)
    second_evidence = _evidence(second)
    first_binding = _binding(first, first_evidence)
    second_binding = _binding(second, second_evidence)
    first_result = evaluate_with_evidence(
        pin=EvidenceRuntimePinV1(pin_id="mshp_" + "4" * 32, binding=first_binding),
        ruleset=first,
        evidence=first_evidence,
        material_input=_input(),
    )
    second_result = evaluate_with_evidence(
        pin=EvidenceRuntimePinV1(pin_id="mshp_" + "4" * 32, binding=second_binding),
        ruleset=second,
        evidence=second_evidence,
        material_input=_input(),
    )
    assert first_result.verdict == second_result.verdict
    assert first_result.decisive_ref == second_result.decisive_ref
    assert first_result.matches == second_result.matches
    assert first_result.references == second_result.references
