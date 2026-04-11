"""
Unit tests for Phase 0A.3 — Graph-level Guidance / Qualification split.

Tests cover:
1. route_by_policy() — the conditional entry edge
2. fast_guidance_node() — lightweight fast-path node
3. reasoning_node() — structured path untouched (smoke-test the signature)
4. Integration: graph invoked with policy_path "fast" uses fast_guidance_node
5. Integration: graph invoked with policy_path "structured" uses reasoning_node
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.agent.graph import (
    fast_guidance_node,
    reasoning_node,
    route_by_policy,
)
from app.agent.agent.policy import ResultForm, RoutingPath
from app.agent.agent.state import AgentState
from app.agent.agent.prompts import build_fast_guidance_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides) -> dict:
    """Minimal valid-ish AgentState dict for testing."""
    base: dict[str, Any] = {
        "messages": [],
        "sealing_state": {
            "observed": {"observed_inputs": [], "raw_parameters": {}},
            "normalized": {"identity_records": {}, "normalized_parameters": {}},
            "asserted": {
                "medium_profile": {},
                "machine_profile": {},
                "installation_profile": {},
                "operating_conditions": {},
                "sealing_requirement_spec": {},
            },
            "governance": {
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "scope_of_validity": [],
                "assumptions_active": [],
                "gate_failures": [],
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": [],
                "conflicts": [],
            },
            "cycle": {
                "analysis_cycle_id": "test-1",
                "snapshot_parent_revision": 0,
                "superseded_by_cycle": None,
                "contract_obsolete": False,
                "contract_obsolete_reason": None,
                "state_revision": 0,
            },
            "selection": {
                "selection_status": "pending",
                "candidates": [],
                "viable_candidate_ids": [],
                "blocked_candidates": [],
                "winner_candidate_id": None,
                "recommendation_artifact": None,
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
            },
        },
        "relevant_fact_cards": [],
        "working_profile": {},
        "tenant_id": "test-tenant",
    }
    base.update(overrides)
    return base


def _mock_policy_route_for_query(query: str) -> str:
    """Deterministic routing stub for tests that should not hit the real LLM."""
    normalized = query.lower()
    if "was ist" in normalized or "welche dichtung" in normalized:
        return "Fast"
    return "Structured"


# ---------------------------------------------------------------------------
# 1. route_by_policy — conditional entry edge
# ---------------------------------------------------------------------------

class TestRouteByPolicy:
    def test_fast_path_routes_to_fast_guidance_node(self):
        state = _make_state(policy_path="fast")
        assert route_by_policy(state) == "fast_guidance_node"

    def test_structured_path_routes_to_reasoning_node(self):
        state = _make_state(policy_path="structured")
        assert route_by_policy(state) == "reasoning_node"

    def test_missing_policy_path_defaults_to_reasoning_node(self):
        """Safe default: unknown policy → structured (never lose qualification coverage)."""
        state = _make_state()
        assert route_by_policy(state) == "reasoning_node"

    def test_none_policy_path_defaults_to_reasoning_node(self):
        state = _make_state(policy_path=None)
        assert route_by_policy(state) == "reasoning_node"

    def test_unknown_policy_path_defaults_to_reasoning_node(self):
        state = _make_state(policy_path="unknown_future_value")
        assert route_by_policy(state) == "reasoning_node"

    # Phase 0D paths
    def test_meta_path_routes_to_meta_response_node(self):
        state = _make_state(policy_path="meta")
        assert route_by_policy(state) == "meta_response_node"

    def test_blocked_path_routes_to_blocked_node(self):
        state = _make_state(policy_path="blocked")
        assert route_by_policy(state) == "blocked_node"

    def test_greeting_path_routes_to_greeting_node(self):
        state = _make_state(policy_path="greeting")
        assert route_by_policy(state) == "greeting_node"

    @pytest.mark.parametrize("result_form, expected_path", [
        (ResultForm.DIRECT_ANSWER.value, RoutingPath.FAST_PATH.value),
        (ResultForm.GUIDED_RECOMMENDATION.value, RoutingPath.FAST_PATH.value),
        (ResultForm.DETERMINISTIC_RESULT.value, RoutingPath.STRUCTURED_PATH.value),
        (ResultForm.QUALIFIED_CASE.value, RoutingPath.STRUCTURED_PATH.value),
    ])
    def test_policy_decides_routing_for_all_result_forms(self, result_form, expected_path):
        """Verify policy_path values that come from each ResultForm route correctly."""
        from app.agent.agent.interaction_policy import evaluate_policy
        from app.agent.agent.policy import RoutingPath

        # Build a query that produces the right result form, then simulate routing
        form_to_query = {
            ResultForm.DIRECT_ANSWER.value: "Was ist FKM?",
            ResultForm.GUIDED_RECOMMENDATION.value: "Welche Dichtung für meine Pumpe?",
            # These two use numeric+unit patterns — deterministically upgraded to Structured
            # regardless of LLM classification (see _fast_path_upgrade_to_structured).
            ResultForm.DETERMINISTIC_RESULT.value: "Berechne RWDR 50mm 1500 rpm",
            ResultForm.QUALIFIED_CASE.value: "FDA-konforme Applikation 80°C 10 bar",
        }
        with patch(
            "app.agent.runtime.interaction_policy._call_routing_llm",
            side_effect=_mock_policy_route_for_query,
        ):
            decision = evaluate_policy(form_to_query[result_form])
        state = _make_state(policy_path=decision.path.value)
        route = route_by_policy(state)

        if expected_path == RoutingPath.FAST_PATH.value:
            assert route == "fast_guidance_node"
        else:
            assert route == "reasoning_node"


# ---------------------------------------------------------------------------
# 2. fast_guidance_node — node contract
# ---------------------------------------------------------------------------

class TestFastGuidanceNode:
    @pytest.fixture
    def mock_llm_response(self):
        from langchain_core.messages import AIMessage
        response = AIMessage(content="FKM ist ein Fluorelastomer mit hoher Chemikalienbeständigkeit.")
        llm_mock = AsyncMock()
        llm_mock.ainvoke = AsyncMock(return_value=response)
        return llm_mock

    @pytest.mark.asyncio
    async def test_returns_ai_message(self, mock_llm_response):
        from langchain_core.messages import AIMessage, HumanMessage

        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist FKM?")],
        )
        with patch("app.agent.agent.graph.get_llm", return_value=mock_llm_response), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        assert "messages" in result
        assert isinstance(result["messages"][0], AIMessage)
        assert len(result["messages"][0].content) > 0

    @pytest.mark.asyncio
    async def test_does_not_modify_sealing_state(self, mock_llm_response):
        """Fast path must NOT write to sealing_state."""
        from langchain_core.messages import HumanMessage

        state = _make_state(
            policy_path="fast",
            result_form="guided_recommendation",
            messages=[HumanMessage(content="Welche Dichtung für Hydrauliköl?")],
        )
        with patch("app.agent.agent.graph.get_llm", return_value=mock_llm_response), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        assert "sealing_state" not in result, (
            "fast_guidance_node must not write sealing_state (no qualification in fast path)"
        )

    @pytest.mark.asyncio
    async def test_does_not_modify_working_profile(self, mock_llm_response):
        """Fast path must NOT call extract_parameters / update working_profile."""
        from langchain_core.messages import HumanMessage

        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist NBR?")],
        )
        with patch("app.agent.agent.graph.get_llm", return_value=mock_llm_response), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        assert "working_profile" not in result, (
            "fast_guidance_node must not write working_profile (no heuristic extraction)"
        )

    @pytest.mark.asyncio
    async def test_llm_called_without_tools(self, mock_llm_response):
        """Fast-path LLM must not have tools bound (no submit_claim)."""
        from langchain_core.messages import HumanMessage

        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist PTFE?")],
        )
        with patch("app.agent.agent.graph.get_llm", return_value=mock_llm_response), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            await fast_guidance_node(state)

        # ainvoke is called directly on the LLM (not on llm.bind_tools(...))
        assert mock_llm_response.ainvoke.called
        # bind_tools should NOT have been called
        assert not mock_llm_response.bind_tools.called


# ---------------------------------------------------------------------------
# 3. Prompt builder — result_form adaptation
# ---------------------------------------------------------------------------

class TestFastGuidancePrompt:
    def test_direct_answer_mode_in_prompt(self):
        prompt = build_fast_guidance_prompt("some context", "direct_answer")
        assert "Direkte Antwort" in prompt
        assert "some context" in prompt

    def test_guided_recommendation_mode_in_prompt(self):
        prompt = build_fast_guidance_prompt("ctx", "guided_recommendation")
        assert "Orientierende Einschätzung" in prompt

    def test_unknown_result_form_falls_back_gracefully(self):
        prompt = build_fast_guidance_prompt("ctx", "unknown_form")
        assert "Direkte Antwort" in prompt  # fallback default


# ---------------------------------------------------------------------------
# 3b. greeting_node — deterministic, no LLM, no RAG
# ---------------------------------------------------------------------------

class TestGreetingNode:
    def test_returns_ai_message_with_greeting(self):
        from app.agent.agent.graph import greeting_node
        from langchain_core.messages import AIMessage, HumanMessage
        state = _make_state(
            messages=[HumanMessage(content="Hallo!")],
            policy_path="greeting",
        )
        result = greeting_node(state)
        msgs = result["messages"]
        assert len(msgs) == 1
        assert isinstance(msgs[0], AIMessage)
        assert "SealAI" in msgs[0].content
        assert "Betriebsparameter" in msgs[0].content

    def test_does_not_modify_working_profile(self):
        from app.agent.agent.graph import greeting_node
        from langchain_core.messages import HumanMessage
        state = _make_state(
            messages=[HumanMessage(content="Hi")],
            policy_path="greeting",
        )
        result = greeting_node(state)
        assert "working_profile" not in result
        assert "sealing_state" not in result


# ---------------------------------------------------------------------------
# 4. Integration: graph topology is correct
# ---------------------------------------------------------------------------

class TestGraphTopology:
    def test_graph_has_fast_guidance_node(self):
        from app.agent.agent.graph import app as compiled_graph
        assert "fast_guidance_node" in compiled_graph.nodes

    def test_graph_has_reasoning_node(self):
        from app.agent.agent.graph import app as compiled_graph
        assert "reasoning_node" in compiled_graph.nodes

    def test_graph_has_both_structured_path_nodes(self):
        from app.agent.agent.graph import app as compiled_graph
        nodes = compiled_graph.nodes
        assert "evidence_tool_node" in nodes
        assert "selection_node" in nodes
        assert "final_response_node" in nodes

    def test_graph_has_greeting_node(self):
        from app.agent.agent.graph import app as compiled_graph
        assert "greeting_node" in compiled_graph.nodes

    def test_graph_has_eight_user_nodes(self):
        """Exactly the expected nodes after Phase 0D+ (greeting added) — no accidental extras."""
        from app.agent.agent.graph import app as compiled_graph
        user_nodes = {n for n in compiled_graph.nodes if not n.startswith("__")}
        assert user_nodes == {
            # Fast path
            "fast_guidance_node",
            # Phase 0D+: deterministic paths (no LLM)
            "meta_response_node",
            "blocked_node",
            "greeting_node",
            # Structured path
            "reasoning_node",
            "evidence_tool_node",
            "selection_node",
            "final_response_node",
        }


# ---------------------------------------------------------------------------
# 5. Router: policy_path is injected before execute_agent (smoke test)
# ---------------------------------------------------------------------------

class TestRouterPolicyInjection:
    def test_fast_path_decision_sets_policy_path_fast(self):
        from app.agent.agent.interaction_policy import evaluate_policy
        from app.agent.agent.policy import RoutingPath

        with patch(
            "app.agent.runtime.interaction_policy._call_routing_llm",
            side_effect=_mock_policy_route_for_query,
        ):
            decision = evaluate_policy("Was ist FKM?")
        assert decision.path == RoutingPath.FAST_PATH
        assert decision.path.value == "fast"

    def test_structured_path_decision_sets_policy_path_structured(self):
        from app.agent.agent.interaction_policy import evaluate_policy
        from app.agent.agent.policy import RoutingPath

        with patch(
            "app.agent.runtime.interaction_policy._call_routing_llm",
            side_effect=_mock_policy_route_for_query,
        ):
            decision = evaluate_policy("FDA Freigabe benötigt")
        assert decision.path == RoutingPath.STRUCTURED_PATH
        assert decision.path.value == "structured"


# ---------------------------------------------------------------------------
# 6. Versioning — run_meta in state after node execution (Phase 0A.5)
# ---------------------------------------------------------------------------

class TestRunMetaVersioning:
    """Verify that terminal nodes write run_meta with required version fields."""

    _REQUIRED_META_KEYS = {"model_id", "prompt_version", "prompt_hash", "policy_version", "path"}

    @pytest.mark.asyncio
    async def test_fast_guidance_node_writes_run_meta(self):
        from langchain_core.messages import AIMessage, HumanMessage

        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist FKM?")],
        )
        llm_mock = MagicMock()
        response = AIMessage(content="FKM ist ein Fluorelastomer.")
        llm_mock.ainvoke = AsyncMock(return_value=response)

        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        assert "run_meta" in result, "fast_guidance_node must write run_meta"
        meta = result["run_meta"]
        for key in self._REQUIRED_META_KEYS:
            assert key in meta, f"run_meta missing '{key}'"

    @pytest.mark.asyncio
    async def test_fast_guidance_node_run_meta_path_is_fast(self):
        from langchain_core.messages import AIMessage, HumanMessage

        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist NBR?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(return_value=AIMessage(content="NBR ist..."))

        with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
             patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        assert result["run_meta"]["path"] == "fast"

    def test_fast_guidance_node_run_meta_model_id_matches_graph_constant(self):
        from app.agent.agent.graph import _GRAPH_MODEL_ID
        from app.agent.agent.prompts import FAST_GUIDANCE_PROMPT_VERSION

        # Run synchronously via asyncio to keep test simple
        import asyncio
        from langchain_core.messages import AIMessage, HumanMessage
        from unittest.mock import patch, AsyncMock, MagicMock

        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist PTFE?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(return_value=AIMessage(content="PTFE ist..."))

        async def _run():
            with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
                 patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
                return await fast_guidance_node(state)

        result = asyncio.run(_run())
        assert result["run_meta"]["model_id"] == _GRAPH_MODEL_ID
        assert result["run_meta"]["prompt_version"] == FAST_GUIDANCE_PROMPT_VERSION

    def test_policy_version_in_run_meta_matches_policy_constant(self):
        """policy_version in run_meta must equal INTERACTION_POLICY_VERSION."""
        import asyncio
        from langchain_core.messages import AIMessage, HumanMessage
        from unittest.mock import patch, AsyncMock, MagicMock
        from app.agent.agent.policy import INTERACTION_POLICY_VERSION

        state = _make_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="FKM vs NBR?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(return_value=AIMessage(content="FKM hat ..."))

        async def _run():
            with patch("app.agent.agent.graph.get_llm", return_value=llm_mock), \
                 patch("app.agent.agent.graph._fetch_rag_cards", return_value=([], "stub")):
                return await fast_guidance_node(state)

        result = asyncio.run(_run())
        assert result["run_meta"]["policy_version"] == INTERACTION_POLICY_VERSION
