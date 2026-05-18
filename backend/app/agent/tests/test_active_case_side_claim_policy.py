from __future__ import annotations

from app.agent.communication.active_case_side_claim_policy import (
    build_active_case_side_evidence_context,
    build_active_case_side_speakable_facts,
    enrich_active_case_side_answer_with_evidence,
    enforce_active_case_side_claim_policy,
)
from app.domain.source_validation import SourceType, ValidationStatus
from app.services.knowledge_service import (
    KNOWLEDGE_RAG_HIT_LABEL,
    KnowledgeAnswerResult,
    KnowledgeEvidence,
    KnowledgeResponse,
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


def test_active_case_side_claim_policy_detects_unscoped_suitability_claim() -> None:
    facts = build_active_case_side_speakable_facts(
        GovernedSessionState(pending_question=_pending_medium_question())
    )

    result = enforce_active_case_side_claim_policy(
        latest_user_message="Ich benoetige die Grenzwerte von PTFE.",
        answer_markdown=(
            "PTFE Grenzwerte: PTFE ist fuer Anwendungen bei hohen Temperaturen geeignet. "
            "Das ist allgemeine Orientierung."
        ),
        speakable_facts=facts,
    )

    assert result.claim_policy_result == "fallback"
    assert result.answer_safety_fallback_used is True
    assert (
        "ist fuer anwendungen bei hohen temperaturen geeignet"
        not in result.answer_markdown.casefold()
    )
    assert "ist geeignet" not in result.answer_markdown.casefold()
    assert "nicht als konkrete eignung" in result.answer_markdown.casefold()
    assert "unscoped_material_suitability" in result.forbidden_claims_detected


def test_active_case_side_claim_policy_detects_unscoped_suitability_label() -> None:
    facts = build_active_case_side_speakable_facts(
        GovernedSessionState(pending_question=_pending_medium_question())
    )

    result = enforce_active_case_side_claim_policy(
        latest_user_message="Welche Grenzwerte hat PTFE?",
        answer_markdown="- Gute Eignung für hohe Temperaturen.",
        speakable_facts=facts,
    )

    assert result.claim_policy_result == "fallback"
    assert result.answer_safety_fallback_used is True
    assert "gute eignung" not in result.answer_markdown.casefold()
    assert "unscoped_suitability_label" in result.forbidden_claims_detected


def test_active_case_side_claim_policy_bounds_material_limit_answers_even_without_forbidden_claim() -> None:
    facts = build_active_case_side_speakable_facts(
        GovernedSessionState(pending_question=_pending_medium_question())
    )

    result = enforce_active_case_side_claim_policy(
        latest_user_message="Ich benoetige die Grenzwerte von PTFE.",
        answer_markdown=(
            "PTFE Grenzwerte: Dauergebrauch bis 260 °C, Schmelzpunkt 327 °C, "
            "Tieftemperatur moeglich."
        ),
        speakable_facts=facts,
    )

    answer = result.answer_markdown.casefold()
    assert result.claim_policy_result == "material_limit_bounded"
    assert result.answer_safety_rewritten is True
    assert "ptfe-grenzwerten" in answer
    assert "compound" in answer
    assert "produktgrenze" in answer
    assert "nicht als konkrete eignung" in answer
    assert "schmelzbereich um 327" in answer
    assert "keine sichere dauerbetriebsgrenze" in answer


def test_active_case_side_evidence_context_uses_existing_knowledge_evidence() -> None:
    knowledge_response = KnowledgeResponse(
        content="FKM und NBR unterscheiden sich.",
        answer_result=KnowledgeAnswerResult(
            answer="FKM und NBR unterscheiden sich.",
            answer_available=True,
            rag_lookup_attempted=True,
            rag_answer_found=True,
            rag_miss=False,
            source_type=SourceType.rag_verified,
            validation_status=ValidationStatus.documented,
            user_visible_label=KNOWLEDGE_RAG_HIT_LABEL,
            knowledge_evidence=(
                KnowledgeEvidence(
                    source_type="fact_card",
                    title="Elastomer-Werkstoffkontext",
                    content="FKM wird haeufig fuer Oele, Kraftstoffe und Temperatur betrachtet.",
                    source_name="SeaLAI FactCard",
                    note="documented",
                ),
            ),
        ),
    )

    evidence_context = build_active_case_side_evidence_context(
        knowledge_response=knowledge_response,
        latest_user_message="Und FKM mit NBR?",
    )
    enriched = enrich_active_case_side_answer_with_evidence(
        latest_user_message="Und FKM mit NBR?",
        answer_markdown=knowledge_response.content,
        evidence_context=evidence_context,
    )

    assert evidence_context.evidence_available is True
    assert evidence_context.evidence_refs == ("Elastomer-Werkstoffkontext",)
    assert evidence_context.source_validation_status == ("documented",)
    assert enriched.evidence_used_in_answer is True
    assert "Evidenzkontext: Elastomer-Werkstoffkontext" in enriched.answer_markdown
    assert "nicht als technische Freigabe" in enriched.answer_markdown


def test_active_case_side_claim_policy_catches_unsafe_answer_even_with_evidence_context() -> None:
    knowledge_response = KnowledgeResponse(
        content="FKM ist garantiert geeignet.",
        answer_result=KnowledgeAnswerResult(
            answer="FKM ist garantiert geeignet.",
            answer_available=True,
            rag_lookup_attempted=True,
            rag_answer_found=True,
            rag_miss=False,
            source_type=SourceType.rag_verified,
            validation_status=ValidationStatus.documented,
            user_visible_label=KNOWLEDGE_RAG_HIT_LABEL,
            knowledge_evidence=(
                KnowledgeEvidence(
                    source_type="fact_card",
                    title="Elastomer-Werkstoffkontext",
                    content="FKM wird haeufig bei Oelen, Kraftstoffen und Temperatur betrachtet.",
                ),
            ),
        ),
    )
    evidence_context = build_active_case_side_evidence_context(
        knowledge_response=knowledge_response,
        latest_user_message="Und FKM mit NBR?",
    )
    facts = build_active_case_side_speakable_facts(
        GovernedSessionState(pending_question=_pending_medium_question()),
        evidence_context=evidence_context,
    )
    enriched = enrich_active_case_side_answer_with_evidence(
        latest_user_message="Und FKM mit NBR?",
        answer_markdown=knowledge_response.content,
        evidence_context=evidence_context,
    )

    result = enforce_active_case_side_claim_policy(
        latest_user_message="Und FKM mit NBR?",
        answer_markdown=enriched.answer_markdown,
        speakable_facts=facts,
    )

    assert result.claim_policy_result == "fallback"
    assert result.answer_safety_fallback_used is True
    assert result.evidence_context_available is True
    assert "garantiert geeignet" not in result.answer_markdown.casefold()
    assert "Herstellerpruefung" in result.answer_markdown
    assert "garantiert_geeignet" in result.forbidden_claims_detected


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
