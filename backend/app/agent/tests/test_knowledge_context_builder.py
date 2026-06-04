from __future__ import annotations

from types import SimpleNamespace

from app.agent.communication.knowledge_context_builder import KnowledgeContextBuilder
from app.services.knowledge_case_bridge_service import KnowledgeConversationTurn


def test_context_builder_basic_adds_deterministic_evidence_without_structured_sources() -> (
    None
):
    context = KnowledgeContextBuilder().build(
        user_message="Was ist FKM?",
        deterministic_answer="FKM ist eine Fluorelastomer-Werkstofffamilie.",
    )

    assert context.user_message == "Was ist FKM?"
    assert (
        context.deterministic_answer == "FKM ist eine Fluorelastomer-Werkstofffamilie."
    )
    assert context.no_case is True
    assert context.evidence_items
    assert context.evidence_items[0].source_type == "deterministic"


def test_context_builder_bounds_history_and_keeps_only_visible_turns() -> None:
    raw_history = [
        KnowledgeConversationTurn(role="user", content="Was ist PTFE?"),
        KnowledgeConversationTurn(
            role="assistant", content="PTFE ist ein Fluorpolymer."
        ),
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


def test_context_builder_resolves_elliptical_material_comparison_subjects() -> None:
    raw_history = [
        KnowledgeConversationTurn(
            role="user",
            content="Bitte gib mir detaillierte Informationen zu PTFE.",
        ),
        KnowledgeConversationTurn(
            role="assistant",
            content="PTFE ist ein Fluorpolymer mit breiter Chemieorientierung.",
        ),
    ]

    context = KnowledgeContextBuilder().build(
        user_message="bitte vergleiche mit NBR",
        deterministic_answer="Werkstoffvergleich PTFE vs NBR.",
        recent_history=raw_history,
    )

    assert context.requested_subjects == ("PTFE", "NBR")
    payload = context.as_dict()
    assert payload["recent_history"][0]["content"].startswith("Bitte gib mir")
    assert payload["requested_subjects"] == ["PTFE", "NBR"]


def test_context_builder_keeps_also_about_single_material_authoritative() -> None:
    raw_history = [
        KnowledgeConversationTurn(
            role="user",
            content="Bitte gib mir detaillierte Informationen zu PTFE.",
        ),
        KnowledgeConversationTurn(
            role="assistant",
            content="PTFE verhält sich nicht wie NBR, EPDM oder FKM.",
        ),
    ]

    context = KnowledgeContextBuilder().build(
        user_message="und auch über PEEK",
        deterministic_answer="PEEK ist ein Hochleistungsthermoplast.",
        recent_history=raw_history,
    )

    assert context.requested_subjects == ("PEEK",)


def test_context_builder_resolves_anaphoric_comparison_subjects_from_answer() -> None:
    context = KnowledgeContextBuilder().build(
        user_message="bitte vergleiche beide materialien",
        deterministic_answer="## Werkstoffvergleich: PTFE vs PEEK\n\nPTFE und PEEK sind Konstruktionswerkstoffe.",
        recent_history=(
            KnowledgeConversationTurn(role="user", content="Infos zu PTFE"),
            KnowledgeConversationTurn(
                role="assistant", content="PTFE ist ein Fluorpolymer."
            ),
            KnowledgeConversationTurn(role="user", content="und auch über PEEK"),
            KnowledgeConversationTurn(
                role="assistant", content="PEEK ist ein Hochleistungsthermoplast."
            ),
        ),
    )

    assert context.requested_subjects == ("PTFE", "PEEK")


def test_context_builder_can_keep_complete_case_side_history() -> None:
    raw_history = [
        KnowledgeConversationTurn(role="user", content=f"Turn {index}: " + "A" * 1200)
        for index in range(8)
    ]

    context = KnowledgeContextBuilder(
        history_limit=None, history_char_limit=None
    ).build(
        user_message="Was bedeutet das fuer FKM?",
        deterministic_answer="Deterministische Antwort.",
        recent_history=raw_history,
    )

    assert len(context.recent_history) == 8
    assert context.recent_history[0].content.startswith("Turn 0:")
    assert context.recent_history[-1].content.startswith("Turn 7:")
    assert "..." not in context.recent_history[0].content


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


def test_context_builder_prefers_explicit_evidence_priority_and_dedupes() -> None:
    deterministic_text = "Deterministische Antwort."
    answer_view = SimpleNamespace(
        knowledge_evidence=(
            SimpleNamespace(
                source_type="deterministic",
                title="Deterministic",
                content=deterministic_text,
            ),
            SimpleNamespace(
                source_type="fact_card",
                title="PTFE FactCard",
                content="PTFE: Temperaturbereich -200 bis 260 C.",
                source_name="Curated source",
            ),
            SimpleNamespace(
                source_type="rag",
                title="FKM Grundlagen",
                content="FKM ist eine Fluorelastomer-Werkstofffamilie.",
                source_name="FKM Grundlagen",
            ),
            SimpleNamespace(
                source_type="deterministic",
                title="Duplicate deterministic",
                content=deterministic_text,
            ),
        ),
        sources=(),
    )

    context = KnowledgeContextBuilder(evidence_limit=6).build(
        user_message="Vergleich bitte kurz.",
        deterministic_answer=deterministic_text,
        answer_view=answer_view,
    )

    assert [item.source_type for item in context.evidence_items] == [
        "rag",
        "fact_card",
        "deterministic",
    ]
    assert context.evidence_items[0].title == "FKM Grundlagen"
    assert context.evidence_items[1].source_name == "Curated source"
    assert (
        sum(1 for item in context.evidence_items if item.content == deterministic_text)
        == 1
    )


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
