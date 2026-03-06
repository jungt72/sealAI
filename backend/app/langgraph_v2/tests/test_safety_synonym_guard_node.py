from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.safety_synonym_guard_node import (
    detect_safety_synonym_hits,
    safety_synonym_guard_node,
)
from app.langgraph_v2.state import SealAIState


def test_safety_synonym_guard_detects_hydrogen_and_routes_to_hitl() -> None:
    state = SealAIState(
        thread_id="safety-thread-1",
        messages=[HumanMessage(content="Wir nutzen Formiergas im PEM-Bereich mit schneller Druckentlastung.")],
    )

    command = safety_synonym_guard_node(state)

    assert command.goto == "human_review_node"
    assert command.update["system"]["requires_human_review"] is True
    assert command.update["system"]["safety_class"] == "SEV-1"
    assert command.update["system"]["pending_action"] == "human_review"
    assert command.update["system"]["confirm_status"] == "pending"
    assert "messages" in command.update["conversation"]
    assert len(command.update["conversation"]["messages"]) == 1
    assert "⚠️" in command.update["conversation"]["messages"][0].content
    assert command.update["system"]["final_answer"] == command.update["conversation"]["messages"][0].content
    assert command.update["reasoning"]["awaiting_user_input"] is False
    assert command.update["reasoning"]["streaming_complete"] is True
    categories = command.update["reasoning"]["flags"]["safety_synonym_categories"]
    assert "hydrogen_h2" in categories
    assert "aed_rgd_context" in categories


def test_safety_synonym_guard_detects_hf_and_amines() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Flusssäure (HF) mit Morpholin und Filming amines im Medium.")],
    )

    hits = detect_safety_synonym_hits(state)

    assert "hydrofluoric_acid_hf" in hits
    assert "amines" in hits


def test_safety_synonym_guard_whitelists_generic_amines_terms() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Medium enthält Filming Amines sowie weitere amines.")],
    )

    hits = detect_safety_synonym_hits(state)

    assert "amines" not in hits


def test_safety_synonym_guard_allows_non_safety_text_to_router() -> None:
    state = SealAIState(messages=[HumanMessage(content="Welche Dichtung ist fuer 20 bar Wasser geeignet?")])

    command = safety_synonym_guard_node(state)

    assert command.goto == "combinatorial_chemistry_guard_node"
    assert command.update["reasoning"]["flags"]["safety_synonym_guard_triggered"] is False
