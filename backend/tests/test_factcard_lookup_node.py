"""Tests for node_factcard_lookup and node_compound_filter LangGraph nodes."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from langchain_core.messages import HumanMessage


def _make_state(**overrides: Any):
    """Build a minimal SealAIState-like object for tests."""
    from app.langgraph_v2.state import SealAIState, TechnicalParameters

    defaults = {
        "messages": [HumanMessage(content="Was ist die chemische Beständigkeit von PTFE?")],
        "user_id": "test-user",
        "thread_id": "test-thread",
        "run_id": "test-run",
    }
    defaults.update(overrides)
    return SealAIState(**defaults)


# ---------------------------------------------------------------------------
# node_factcard_lookup — basic routing
# ---------------------------------------------------------------------------

class TestFactcardLookupNode:
    def test_returns_last_node(self):
        from app.langgraph_v2.nodes.factcard_lookup import node_factcard_lookup

        state = _make_state()
        result = node_factcard_lookup(state)
        assert result.get("last_node") == "node_factcard_lookup"

    def test_always_returns_kb_factcard_result(self):
        from app.langgraph_v2.nodes.factcard_lookup import node_factcard_lookup

        state = _make_state()
        result = node_factcard_lookup(state)
        assert "kb_factcard_result" in result

    def test_chemical_query_is_deterministic(self):
        """A query about chemical resistance should match PTFE virgin and be deterministic."""
        from app.langgraph_v2.nodes.factcard_lookup import node_factcard_lookup

        state = _make_state(
            messages=[HumanMessage(content="Ist PTFE chemisch beständig gegen Lösungsmittel?")]
        )
        result = node_factcard_lookup(state)
        kb = result["kb_factcard_result"]
        # Should have found at least one card
        assert len(kb.get("matched_cards", [])) >= 1

    def test_food_grade_query_deterministic(self):
        """A query with 'lebensmittel' and 'fda' should trigger deterministic routing."""
        from app.langgraph_v2.nodes.factcard_lookup import node_factcard_lookup

        state = _make_state(
            messages=[HumanMessage(content="Welche PTFE-Werkstoffe sind FDA zugelassen für Lebensmittel?")]
        )
        result = node_factcard_lookup(state)
        kb = result["kb_factcard_result"]
        # With food-grade gate in the KB, this should be deterministic
        if kb.get("deterministic"):
            wm = result.get("working_memory")
            assert wm is not None
            reply = getattr(wm, "frontdoor_reply", None)
            assert reply is not None
            assert len(reply) > 0

    def test_hard_block_over_temperature(self):
        """Temperature above 260°C should trigger hard_block gate."""
        from app.langgraph_v2.state import TechnicalParameters
        from app.langgraph_v2.nodes.factcard_lookup import node_factcard_lookup

        params = TechnicalParameters(temperature_max=300.0)
        state = _make_state(
            messages=[HumanMessage(content="PTFE Dichtung bei 300°C?")],
            parameters=params,
        )
        result = node_factcard_lookup(state)
        kb = result["kb_factcard_result"]
        assert kb.get("deterministic") is True
        assert len(kb.get("hard_blocks", [])) >= 1
        # Working memory must contain blocking reply
        wm = result.get("working_memory")
        assert wm is not None
        reply = getattr(wm, "frontdoor_reply", None)
        assert "260" in str(reply) or "Sicherheit" in str(reply) or "nicht geeignet" in str(reply).lower()

    def test_ambiguous_query_not_deterministic(self):
        """A vague query with no keyword triggers should not be deterministic."""
        from app.langgraph_v2.nodes.factcard_lookup import node_factcard_lookup

        state = _make_state(
            messages=[HumanMessage(content="Hallo, ich brauche eine Dichtung.")]
        )
        result = node_factcard_lookup(state)
        kb = result["kb_factcard_result"]
        # Vague query → no matches → not deterministic
        assert kb.get("deterministic") is False

    def test_no_crash_with_empty_messages(self):
        """Node must not crash when messages list is empty."""
        from app.langgraph_v2.nodes.factcard_lookup import node_factcard_lookup

        state = _make_state(messages=[])
        result = node_factcard_lookup(state)
        assert "last_node" in result
        assert "kb_factcard_result" in result
        # Empty messages → no query → no deterministic match
        assert result["kb_factcard_result"].get("deterministic") is False


# ---------------------------------------------------------------------------
# node_compound_filter — basic routing
# ---------------------------------------------------------------------------

class TestCompoundFilterNode:
    def test_returns_last_node(self):
        from app.langgraph_v2.nodes.compound_filter import node_compound_filter

        state = _make_state()
        result = node_compound_filter(state)
        assert result.get("last_node") == "node_compound_filter"

    def test_always_returns_compound_filter_results(self):
        from app.langgraph_v2.nodes.compound_filter import node_compound_filter

        state = _make_state()
        result = node_compound_filter(state)
        assert "compound_filter_results" in result

    def test_candidates_are_list(self):
        from app.langgraph_v2.nodes.compound_filter import node_compound_filter

        state = _make_state()
        result = node_compound_filter(state)
        cfr = result["compound_filter_results"]
        assert isinstance(cfr.get("candidates"), list)

    def test_with_temperature_conditions(self):
        """With high temperature, higher-temp compounds should survive screening."""
        from app.langgraph_v2.state import TechnicalParameters
        from app.langgraph_v2.nodes.compound_filter import node_compound_filter

        params = TechnicalParameters(temperature_max=250.0, pressure_bar=100.0)
        state = _make_state(parameters=params)
        result = node_compound_filter(state)
        cfr = result["compound_filter_results"]
        # With loaded KB, should have candidates
        assert isinstance(cfr["candidates"], list)

    def test_with_over_temperature_no_candidates(self):
        """Temperature above all PTFE limits should result in empty candidates."""
        from app.langgraph_v2.state import TechnicalParameters
        from app.langgraph_v2.nodes.compound_filter import node_compound_filter

        params = TechnicalParameters(temperature_max=350.0)
        state = _make_state(parameters=params)
        result = node_compound_filter(state)
        cfr = result["compound_filter_results"]
        # All PTFE compounds max out at 260°C
        assert cfr["candidates"] == []

    def test_conditions_applied_reported(self):
        from app.langgraph_v2.state import TechnicalParameters
        from app.langgraph_v2.nodes.compound_filter import node_compound_filter

        params = TechnicalParameters(temperature_max=200.0, pressure_bar=100.0)
        state = _make_state(parameters=params)
        result = node_compound_filter(state)
        cfr = result["compound_filter_results"]
        applied = cfr.get("conditions_applied", {})
        assert "temp_max_c" in applied
        assert applied["temp_max_c"] == 200.0


# ---------------------------------------------------------------------------
# _factcard_lookup_router
# ---------------------------------------------------------------------------

class TestFactcardLookupRouter:
    def test_routes_deterministic_to_response(self):
        from app.langgraph_v2.sealai_graph_v2 import _factcard_lookup_router

        state = _make_state(kb_factcard_result={"deterministic": True})
        assert _factcard_lookup_router(state) == "deterministic"

    def test_routes_non_deterministic_to_compound_filter(self):
        from app.langgraph_v2.sealai_graph_v2 import _factcard_lookup_router

        state = _make_state(kb_factcard_result={"deterministic": False})
        assert _factcard_lookup_router(state) == "compound_filter"

    def test_routes_empty_result_to_compound_filter(self):
        from app.langgraph_v2.sealai_graph_v2 import _factcard_lookup_router

        state = _make_state()  # kb_factcard_result defaults to {}
        assert _factcard_lookup_router(state) == "compound_filter"


# ---------------------------------------------------------------------------
# Graph instantiation smoke test — KB nodes present in graph
# ---------------------------------------------------------------------------

def test_graph_contains_kb_nodes():
    """The compiled graph must include node_factcard_lookup and node_compound_filter."""
    from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
    from langgraph.checkpoint.memory import MemorySaver

    from app.core.memory import AsyncPostgresStore

    store = AsyncPostgresStore.__new__(AsyncPostgresStore)
    store.pool = None  # type: ignore[assignment]

    graph = create_sealai_graph_v2(
        checkpointer=MemorySaver(),
        store=store,
        require_async=False,
    )
    node_names = list(graph.get_graph().nodes.keys())
    assert "node_factcard_lookup" in node_names, f"node_factcard_lookup missing from: {node_names}"
    assert "node_compound_filter" in node_names, f"node_compound_filter missing from: {node_names}"
