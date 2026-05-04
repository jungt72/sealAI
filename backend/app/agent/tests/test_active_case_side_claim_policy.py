from __future__ import annotations

from app.agent.communication.active_case_side_claim_policy import (
    build_active_case_side_speakable_facts,
    enforce_active_case_side_claim_policy,
)
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernedSessionState,
    PendingQuestion,
)


def _pending_medium_question() -> PendingQuestion:
    return PendingQuestion(
        target_field="medium",
        expected_answer_type="medium_value",
        question_text="Welches Medium soll abgedichtet werden?",
        ambiguity_policy="clarify_if_broad_or_hazardous",
        source="governed_next_question",
        status="open",
    )


def test_active_case_side_claim_policy_detects_unsafe_material_claim_and_falls_back() -> None:
    facts = build_active_case_side_speakable_facts(
        GovernedSessionState(pending_question=_pending_medium_question())
    )

    result = enforce_active_case_side_claim_policy(
        latest_user_message="Und FKM mit NBR?",
        answer_markdown="FKM ist garantiert geeignet und final freigegeben.",
        speakable_facts=facts,
    )

    assert result.claim_policy_result == "fallback"
    assert result.answer_safety_fallback_used is True
    assert "garantiert geeignet" not in result.answer_markdown.casefold()
    assert "final freigegeben" not in result.answer_markdown.casefold()
    assert "Herstellerpruefung" in result.answer_markdown
    assert "vorlaeufige technische Einordnung" in result.answer_markdown
    assert set(result.forbidden_claims_detected) >= {
        "garantiert_geeignet",
        "final_freigegeben",
    }


def test_active_case_side_speakable_facts_distinguish_known_missing_and_evidence() -> None:
    state = GovernedSessionState(
        pending_question=_pending_medium_question(),
        asserted=AssertedState(
            assertions={
                "temperature_c": AssertedClaim(
                    field_name="temperature_c",
                    asserted_value=120,
                    status="user_stated",
                    provenance="user_stated",
                    confidence="confirmed",
                    evidence_refs=["upload:datasheet-1"],
                )
            },
            blocking_unknowns=["medium", "pressure_bar"],
        ),
    )

    facts = build_active_case_side_speakable_facts(state)

    assert facts.evidence_context_available is True
    assert facts.known_case_facts[0].field_name == "temperature_c"
    assert facts.known_case_facts[0].fact_status == "user_stated"
    assert facts.known_case_facts[0].provenance == "user_stated"
    assert "medium" in facts.missing_fields
    assert "pressure_bar" in facts.missing_fields
    assert "upload:datasheet-1" in facts.evidence_refs
