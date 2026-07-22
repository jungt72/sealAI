"""chat_response surfaces the Modus-E Gegencheck verdict (deterministic API field).

The structured verdict rides the response so the SPA can render a Gegencheck badge
deterministically — independent of how L1 phrased the answer. None when the turn is
not a Gegencheck situation. Offline, no LLM.
"""

from __future__ import annotations

import pytest

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import (
    Answer,
    EvaluationState,
    Flags,
    GroundingFact,
    InputResolutionState,
    MaterialConstraintMatch,
    MaterialConstraintResult,
    MaterialConstraintVerdict,
    MediumCardinality,
    PipelineResult,
    RelationState,
    VerifierAction,
    VerifierVerdict,
)


def _result(
    gegencheck, *, material_constraints=None, material_constraints_enabled=False
):
    return PipelineResult(
        question="Wir verwenden FKM in Heißdampf, passt das?",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
        gegencheck=gegencheck,
        material_constraints=material_constraints,
        material_constraints_enabled=material_constraints_enabled,
    )


def _verified_result(verifier, *, verified=True, guard=None):
    return PipelineResult(
        question="Welche Härte für die O-Ring-Nut?",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
        verified=verified,
        verifier=verifier,
        guard=guard,
    )


def test_disqualifying_verdict_is_serialised():
    verdict = {
        "disqualified": True,
        "reason": "FKM hydrolysiert in Heißdampf",
        "source": "Verträglichkeitsmatrix · MX-FKM-DAMPF (reviewed; …)",
    }
    out = chat_response(_result(verdict))
    assert out["gegencheck"] == verdict
    assert out["gegencheck"]["disqualified"] is True


def test_no_gegencheck_situation_serialises_none():
    out = chat_response(_result(None))
    assert out["gegencheck"] is None


def test_flag_off_legacy_payload_has_no_new_key_and_keeps_verdict_exactly() -> None:
    verdict = {"disqualified": False, "basis": "matrix_compatible"}
    out = chat_response(_result(verdict))
    assert out["gegencheck"] == verdict
    assert "material_constraints" not in out


def test_enabled_canonical_result_is_additive_and_legacy_output_is_unchanged() -> None:
    match = MaterialConstraintMatch(
        rule_ref="MX-NBR-SYNTHETIKOEL",
        verdict=MaterialConstraintVerdict.BEDINGT,
        statement="Nur nach anwendungsbezogener Prüfung.",
        source_ref="matrix-cell:MX-NBR-SYNTHETIKOEL",
    )
    canonical = MaterialConstraintResult(
        material_state=InputResolutionState.KNOWN,
        medium_state=InputResolutionState.KNOWN,
        medium_cardinality=MediumCardinality.SINGLE,
        relation_state=RelationState.NOT_APPLICABLE,
        evaluation_state=EvaluationState.EVALUATED,
        verdict=MaterialConstraintVerdict.BEDINGT,
        matches=(match,),
        decisive_ref=match.rule_ref,
    )
    legacy = {
        "disqualified": False,
        "basis": "matrix_conditional",
        "condition": match.statement,
        "source": match.source_ref,
    }
    out = chat_response(
        _result(
            legacy,
            material_constraints=canonical,
            material_constraints_enabled=True,
        )
    )
    assert out["gegencheck"] == legacy
    assert out["material_constraints"] == canonical.to_dict()


def test_enabled_contract_cannot_be_silently_omitted() -> None:
    with pytest.raises(ValueError, match="requires an explicit result"):
        chat_response(_result(None, material_constraints_enabled=True))


def test_disabled_contract_cannot_leak_a_canonical_result() -> None:
    match = MaterialConstraintMatch(
        rule_ref="MX-NBR-SYNTHETIKOEL",
        verdict=MaterialConstraintVerdict.BEDINGT,
        statement="Nur nach anwendungsbezogener Prüfung.",
        source_ref="matrix-cell:MX-NBR-SYNTHETIKOEL",
    )
    canonical = MaterialConstraintResult(
        material_state=InputResolutionState.KNOWN,
        medium_state=InputResolutionState.KNOWN,
        medium_cardinality=MediumCardinality.SINGLE,
        relation_state=RelationState.NOT_APPLICABLE,
        evaluation_state=EvaluationState.EVALUATED,
        verdict=MaterialConstraintVerdict.BEDINGT,
        matches=(match,),
        decisive_ref=match.rule_ref,
    )
    with pytest.raises(ValueError, match="disabled material-constraint"):
        chat_response(_result(None, material_constraints=canonical))


# --- P1.5: L3 verification status on the chat payload ------------------------------------------
# Without this block the client cannot tell a verified answer from a hedge or a
# silently-unverified one. ``verified`` is the conservative, honest signal; the nested
# ``verification`` object carries the raw action / parse_ok / hedged for a precise badge.


def test_pass_verdict_is_verified():
    out = chat_response(
        _verified_result(VerifierVerdict(action=VerifierAction.PASS, parse_ok=True))
    )
    assert out["verified"] is True
    assert out["verification"]["action"] == "pass"
    assert out["verification"]["parse_ok"] is True
    assert out["verification"]["hedged"] is False
    assert out["verification"]["ran"] is True


def test_corrected_verdict_is_verified():
    # CORRECTED = blocked then regenerated against a REVIEWED correction → clean; still confident.
    out = chat_response(
        _verified_result(
            VerifierVerdict(
                action=VerifierAction.CORRECTED, regenerated=True, parse_ok=True
            )
        )
    )
    assert out["verified"] is True
    assert out["verification"]["action"] == "corrected"
    assert out["verification"]["hedged"] is False


def test_flag_verdict_is_verified():
    out = chat_response(
        _verified_result(VerifierVerdict(action=VerifierAction.FLAG, parse_ok=True))
    )
    assert out["verified"] is True
    assert out["verification"]["action"] == "flag"
    assert out["verification"]["hedged"] is False


def test_blocked_hedge_verdict_is_not_verified_and_hedged():
    out = chat_response(
        _verified_result(
            VerifierVerdict(action=VerifierAction.BLOCKED_HEDGE, parse_ok=True)
        )
    )
    assert out["verified"] is False
    assert out["verification"]["action"] == "blocked_hedge"
    assert out["verification"]["hedged"] is True
    assert out["verification"]["ran"] is True


def test_output_guard_hedge_is_not_reported_as_confidently_verified():
    out = chat_response(
        _verified_result(
            VerifierVerdict(action=VerifierAction.PASS, parse_ok=True),
            guard={"action": "PASS", "hedged": True},
        )
    )
    assert out["verified"] is False
    assert out["verification"]["hedged"] is True


def test_parse_failure_is_not_verified():
    # Fail-open: L3 ran but its output did not parse → never report a confident "verified".
    out = chat_response(
        _verified_result(VerifierVerdict(action=VerifierAction.PASS, parse_ok=False))
    )
    assert out["verified"] is False
    assert out["verification"]["parse_ok"] is False
    assert out["verification"]["hedged"] is False


def test_no_verifier_is_not_verified():
    # L3 absent/disabled — the silently-unverified case the client must be able to detect.
    out = chat_response(_verified_result(None, verified=False))
    assert out["verified"] is False
    assert out["verification"]["action"] is None
    assert out["verification"]["parse_ok"] is None
    assert out["verification"]["hedged"] is False
    assert out["verification"]["ran"] is False


def test_verification_values_are_json_safe():
    # action must be the enum's .value (a plain str), not the Enum member.
    out = chat_response(
        _verified_result(VerifierVerdict(action=VerifierAction.PASS, parse_ok=True))
    )
    assert isinstance(out["verification"]["action"], str)
    assert type(out["verification"]["action"]) is str


def test_citations_are_bound_to_the_terminal_answer_claims():
    used = GroundingFact(
        text="FKM gegen Heißdampf: unverträglich.",
        quelle="Matrix",
        card_id="MX-USED",
        kind="matrix",
        sources=("Primärquelle A",),
    )
    unused = GroundingFact(
        text="EPDM gegen Heißdampf: beständig.",
        quelle="Matrix",
        card_id="MX-UNUSED",
        kind="matrix",
    )
    result = PipelineResult(
        question="Passt FKM in Heißdampf?",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="FKM ist in Heißdampf unverträglich.", model="fake"),
        grounding_facts=(used, unused),
        guard={
            "action": "PASS",
            "hedged": False,
            "citation_binding": "strict",
            "claim_mappings": [{"sentence_index": 0, "claim_id": "MX-USED"}],
        },
    )
    assert chat_response(result)["citations"] == [
        {
            "text": used.text,
            "sources": ["Primärquelle A"],
            "kind": "matrix",
            "source_status": "primary",
            "sentence_indexes": [0],
        }
    ]


def test_strict_unmapped_or_hedged_answer_has_no_stale_citations():
    fact = GroundingFact(
        text="FKM gegen Heißdampf: unverträglich.",
        quelle="Matrix",
        card_id="MX-USED",
        kind="matrix",
    )
    base = dict(
        question="Passt FKM in Heißdampf?",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="Bitte beim Hersteller absichern.", model="guard"),
        grounding_facts=(fact,),
    )
    unmapped = PipelineResult(
        **base,
        guard={
            "action": "PASS",
            "hedged": False,
            "citation_binding": "strict",
            "claim_mappings": [],
        },
    )
    hedged = PipelineResult(
        **base,
        guard={
            "action": "BLOCK",
            "hedged": True,
            "citation_binding": "strict",
            "claim_mappings": [{"sentence_index": 0, "claim_id": "MX-USED"}],
        },
    )
    assert chat_response(unmapped)["citations"] == []
    assert chat_response(hedged)["citations"] == []


def test_internal_matrix_citation_is_not_labeled_as_fachkarte():
    fact = GroundingFact(
        text="Interner Matrixbefund.",
        quelle="Matrix",
        card_id="MX-INTERNAL",
        kind="matrix",
    )
    result = PipelineResult(
        question="x",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="x", model="fake"),
        grounding_facts=(fact,),
    )
    cite = chat_response(result)["citations"][0]
    assert cite["sources"] == ["geprüfte Verträglichkeitsmatrix (intern)"]
    assert cite["source_status"] == "reviewed_internal"
