from __future__ import annotations

import re
from typing import Any, Dict

from langchain_core.messages import HumanMessage


def _requires_rag_from_text(text: str) -> bool:
    lowered = (text or "").lower()
    if "ohne quellen" in lowered or "keine quellen" in lowered:
        return False
    return ("mit quellen" in lowered) or (" mit din" in lowered) or lowered.endswith(" din")


def test_rag_support_node_does_not_invoke_tool_when_requires_rag_false(monkeypatch) -> None:
    # Import graph first to avoid circular import edge-case (nodes_flows imports log_state_debug).
    import app.langgraph_v2.sealai_graph_v2  # noqa: F401
    from app.langgraph_v2.nodes import nodes_flows
    from app.langgraph_v2.state import SealAIState

    invoked = {"value": False}

    class _Tool:
        def invoke(self, _payload: Dict[str, Any]) -> str:
            invoked["value"] = True
            return "SHOULD_NOT_BE_CALLED"

    monkeypatch.setattr(nodes_flows, "search_knowledge_base", _Tool())

    state = SealAIState(
        messages=[HumanMessage(content="Vergleich FKM vs NBR")],
        user_id="u1",
        thread_id="t1",
        requires_rag=False,
    )

    patch = nodes_flows.rag_support_node(state)
    assert invoked["value"] is False, "search_knowledge_base.invoke must not be called"

    wm = patch.get("working_memory")
    notes = getattr(wm, "comparison_notes", {}) if wm is not None else {}
    assert "rag_context" not in notes
    assert "rag_reference" not in notes


def test_frontdoor_module_exposes_discovery_entrypoint() -> None:
    import app.langgraph_v2.sealai_graph_v2  # noqa: F401
    from app.langgraph_v2.nodes import nodes_frontdoor

    assert callable(getattr(nodes_frontdoor, "frontdoor_discovery_node", None))


def test_sources_phrase_ohne_quellen_disables_rag() -> None:
    assert _requires_rag_from_text("Vergleich FKM vs NBR bitte ohne Quellen") is False
    assert _requires_rag_from_text("Vergleich FKM vs NBR bitte keine Quellen") is False


def test_sources_phrase_mit_quellen_enables_rag() -> None:
    assert _requires_rag_from_text("Vergleich FKM vs NBR bitte mit Quellen") is True
    assert _requires_rag_from_text("Vergleich FKM vs NBR mit DIN") is True


def test_final_answer_router_always_contains_allgemeines_fachwissen_heading() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    text = (render_template("final_answer_router.j2", {"intent_goal": "explanation_or_comparison"}) or "").strip()
    assert "## Technische Mechanismen" in text


def test_final_answer_router_gates_wissensdatenbank_section() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    no_rag = (
        render_template(
            "final_answer_router.j2",
            {"intent_goal": "explanation_or_comparison", "requires_rag": False, "comparison_notes": {}},
        )
        or ""
    )
    assert "## Quellen / Belege" not in no_rag
    assert "Wissensdatenbank" not in no_rag
    assert "RAG" not in no_rag
    assert re.search(r"\bdb\b", no_rag, re.IGNORECASE) is None

    rag_without_citations = (
        render_template(
            "final_answer_router.j2",
            {
                "intent_goal": "explanation_or_comparison",
                "requires_rag": True,
                "comparison_notes": {"rag_context": "Kein Treffer", "rag_reference": None, "rag_note": "Quellen derzeit nicht verfügbar."},
            },
        )
        or ""
    )
    assert "## Quellen / Belege" not in rag_without_citations
    assert "## Relevante Auszüge (Wissensbasis)" in rag_without_citations
    assert "Kein Treffer" in rag_without_citations

    rag_with_citations = (
        render_template(
            "final_answer_router.j2",
            {
                "intent_goal": "explanation_or_comparison",
                "requires_rag": True,
                "comparison_notes": {"rag_reference": ["DIN 1234", "EN 681-1"]},
            },
        )
        or ""
    )
    assert "## Quellen / Belege" in rag_with_citations
    assert "- DIN 1234" in rag_with_citations
