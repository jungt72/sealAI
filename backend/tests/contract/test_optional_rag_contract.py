from __future__ import annotations

import re
from typing import Any, Dict

from langchain_core.messages import HumanMessage


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


def test_detect_sources_request_respects_explicit_opt_out() -> None:
    import app.langgraph_v2.sealai_graph_v2  # noqa: F401
    from app.langgraph_v2.nodes.nodes_frontdoor import detect_sources_request

    assert detect_sources_request("Vergleich FKM vs NBR bitte ohne Quellen") is False
    assert detect_sources_request("Vergleich FKM vs NBR bitte keine Quellen") is False
    assert detect_sources_request("Vergleich FKM vs NBR bitte mit Quellen") is True
    assert detect_sources_request("Vergleich FKM vs NBR mit DIN") is True


def test_comparison_flow_skips_rag_support_node_when_user_says_ohne_quellen(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    from langgraph.checkpoint.memory import MemorySaver

    import app.langgraph_v2.sealai_graph_v2 as graph_mod
    from app.langgraph_v2.state import Intent, SealAIState
    from app.langgraph_v2.utils.messages import latest_user_text
    from app.langgraph_v2.nodes import nodes_frontdoor

    def _frontdoor_stub(state: SealAIState, *_a, **_k):
        user_text = latest_user_text(state.messages or []) or ""
        requires_rag = nodes_frontdoor.detect_sources_request(user_text)
        return {
            "intent": Intent(goal="explanation_or_comparison", confidence=1.0, high_impact_gaps=[]),
            "requires_rag": requires_rag,
            "phase": "frontdoor",
            "last_node": "frontdoor_discovery_node",
        }

    def _comparison_stub(state: SealAIState, *_a, **_k):
        return {"phase": "knowledge", "last_node": "material_comparison_node"}

    def _final_stub(state: SealAIState):
        return {"final_text": "ok", "phase": "final", "last_node": "final_answer_node"}

    def _rag_stub(_state: SealAIState, *_a, **_k):
        return {"plan": {"rag_seen": True}, "last_node": "rag_support_node"}

    monkeypatch.setattr(graph_mod, "frontdoor_discovery_node", _frontdoor_stub)
    monkeypatch.setattr(graph_mod, "material_comparison_node", _comparison_stub)
    monkeypatch.setattr(graph_mod, "rag_support_node", _rag_stub)
    monkeypatch.setattr(graph_mod, "_build_final_answer_chain", lambda: _final_stub)

    graph = graph_mod.create_sealai_graph_v2(MemorySaver(), require_async=False)
    config = graph_mod.build_v2_config(thread_id="t1", user_id="u1", tenant_id="tenant-1")

    initial_state = {
        "messages": [HumanMessage(content="Vergleich FKM vs NBR bitte ohne Quellen")],
        "thread_id": "t1",
        "user_id": "u1",
    }
    graph.invoke(initial_state, config=config)
    snapshot = graph.get_state(config)
    values = snapshot.values or {}
    assert bool((values.get("plan") or {}).get("rag_seen")) is False


def test_comparison_flow_includes_rag_support_node_when_user_says_mit_quellen(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    from langgraph.checkpoint.memory import MemorySaver

    import app.langgraph_v2.sealai_graph_v2 as graph_mod
    from app.langgraph_v2.state import Intent, SealAIState
    from app.langgraph_v2.utils.messages import latest_user_text
    from app.langgraph_v2.nodes import nodes_frontdoor

    def _frontdoor_stub(state: SealAIState, *_a, **_k):
        user_text = latest_user_text(state.messages or []) or ""
        requires_rag = nodes_frontdoor.detect_sources_request(user_text)
        return {
            "intent": Intent(goal="explanation_or_comparison", confidence=1.0, high_impact_gaps=[]),
            "requires_rag": requires_rag,
            "phase": "frontdoor",
            "last_node": "frontdoor_discovery_node",
        }

    def _comparison_stub(state: SealAIState, *_a, **_k):
        return {"phase": "knowledge", "last_node": "material_comparison_node"}

    def _final_stub(state: SealAIState):
        return {"final_text": "ok", "phase": "final", "last_node": "final_answer_node"}

    def _rag_stub(_state: SealAIState, *_a, **_k):
        return {"plan": {"rag_seen": True}, "last_node": "rag_support_node"}

    monkeypatch.setattr(graph_mod, "frontdoor_discovery_node", _frontdoor_stub)
    monkeypatch.setattr(graph_mod, "material_comparison_node", _comparison_stub)
    monkeypatch.setattr(graph_mod, "rag_support_node", _rag_stub)
    monkeypatch.setattr(graph_mod, "_build_final_answer_chain", lambda: _final_stub)

    graph = graph_mod.create_sealai_graph_v2(MemorySaver(), require_async=False)
    config = graph_mod.build_v2_config(thread_id="t1", user_id="u1", tenant_id="tenant-1")

    initial_state = {
        "messages": [HumanMessage(content="Vergleich FKM vs NBR bitte mit Quellen")],
        "thread_id": "t1",
        "user_id": "u1",
        "requires_rag": False,
    }
    graph.invoke(initial_state, config=config)
    snapshot = graph.get_state(config)
    values = snapshot.values or {}
    assert bool((values.get("plan") or {}).get("rag_seen")) is True


def test_final_answer_router_always_contains_allgemeines_fachwissen_heading() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    text = (render_template("final_answer_router.j2", {"intent_goal": "explanation_or_comparison"}) or "").strip()
    assert "## Allgemeines Fachwissen" in text


def test_final_answer_router_gates_wissensdatenbank_section() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    no_rag = (
        render_template(
            "final_answer_router.j2",
            {"intent_goal": "explanation_or_comparison", "requires_rag": False, "comparison_notes": {}},
        )
        or ""
    )
    assert "## Wissensdatenbank (Quellen)" not in no_rag
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
    assert "## Wissensdatenbank (Quellen)" not in rag_without_citations
    assert "Quellen derzeit nicht verfügbar" in rag_without_citations

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
    assert "## Wissensdatenbank (Quellen)" in rag_with_citations
    assert "- DIN 1234" in rag_with_citations
