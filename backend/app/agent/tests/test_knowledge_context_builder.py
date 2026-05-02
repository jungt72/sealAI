from __future__ import annotations

from types import SimpleNamespace

from app.agent.communication.knowledge_context_builder import KnowledgeContextBuilder
from app.services.knowledge_case_bridge_service import KnowledgeConversationTurn


def test_context_builder_basic_adds_deterministic_evidence_without_structured_sources() -> None:
    context = KnowledgeContextBuilder().build(
        user_message="Was ist FKM?",
        deterministic_answer="FKM ist eine Fluorelastomer-Werkstofffamilie.",
    )

    assert context.user_message == "Was ist FKM?"
    assert context.deterministic_answer == "FKM ist eine Fluorelastomer-Werkstofffamilie."
    assert context.no_case is True
    assert context.evidence_items
    assert context.evidence_items[0].source_type == "deterministic"


def test_context_builder_bounds_history_and_keeps_only_visible_turns() -> None:
    raw_history = [
        KnowledgeConversationTurn(role="user", content="Was ist PTFE?"),
        KnowledgeConversationTurn(role="assistant", content="PTFE ist ein Fluorpolymer."),
        {"role": "system", "content": "internal instruction"},
        {"role": "tool", "content": "internal tool output"},
        {"role": "user", "content": "Und FKM?"},
        {"role": "assistant", "content": "FKM ist ein Fluorelastomer."},
        {"role": "user", "content": "Wie unterscheidet sich EPDM?"},
    ]

    context = KnowledgeContextBuilder(history_limit=4).build(
        user_message="Vergleich bitte kurz.",
        deterministic_answer="Deterministische Antwort.",
        recent_history=raw_history,
    )

    assert [turn.role for turn in context.recent_history] == [
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert [turn.content for turn in context.recent_history] == [
        "PTFE ist ein Fluorpolymer.",
        "Und FKM?",
        "FKM ist ein Fluorelastomer.",
        "Wie unterscheidet sich EPDM?",
    ]
    assert "internal instruction" not in str(context.as_dict())
    assert "internal tool output" not in str(context.as_dict())


def test_context_builder_maps_factcard_and_rag_evidence_safely() -> None:
    long_excerpt = " ".join(["RAG-Abschnitt"] * 120)
    answer_view = SimpleNamespace(
        sources=(
            SimpleNamespace(
                title="PTFE FactCard",
                excerpt=None,
                source_type="rag_verified",
                validation_status="documented",
                confidence=None,
            ),
            SimpleNamespace(
                title="FKM Grundlagen",
                excerpt=long_excerpt,
                source_type="rag_verified",
                validation_status="documented",
                confidence=0.82,
            ),
        ),
        rag_miss=False,
        validation_status="documented",
        user_visible_label="Kuratiertes/RAG-Wissen - dokumentiert",
    )

    context = KnowledgeContextBuilder(evidence_limit=4).build(
        user_message="Was ist FKM?",
        deterministic_answer="Deterministische Antwort.",
        answer_view=answer_view,
    )

    assert context.evidence_items[0].source_type == "fact_card"
    assert context.evidence_items[0].title == "PTFE FactCard"
    assert context.evidence_items[1].source_type == "rag"
    assert context.evidence_items[1].confidence == 0.82
    assert len(context.evidence_items[1].content) <= 900
    assert context.evidence_items[1].content.endswith("...")


def test_context_builder_marks_regulatory_currentness_limitation_for_pfas() -> None:
    context = KnowledgeContextBuilder().build(
        user_message="Was bedeutet PFAS fuer Dichtungen?",
        deterministic_answer="Kein kuratierter/RAG-Treffer.",
    )

    assert context.regulatory_currentness_required is True
    assert any(
        "No live regulatory source was retrieved" in limitation
        and "not current legal advice" in limitation
        for limitation in context.limitations
    )
