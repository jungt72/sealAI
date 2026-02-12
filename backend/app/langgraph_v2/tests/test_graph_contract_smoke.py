from __future__ import annotations

"""Offline smoke tests for the current LangGraph v2 contract."""

from langchain_core.messages import HumanMessage

from app.api.v1.endpoints.langgraph_v2 import _build_state_update_payload
from app.langgraph_v2.nodes.nodes_discovery import confirm_gate_node
from app.langgraph_v2.nodes.nodes_supervisor import ACTION_ASK_USER, ACTION_RUN_KNOWLEDGE, supervisor_policy_node
from app.langgraph_v2.sealai_graph_v2 import _frontdoor_router, knowledge_entry_node
from app.langgraph_v2.state import Intent, SealAIState


def test_graph_contract_smoke_frontdoor_smalltalk_routes_to_finalize() -> None:
    state = SealAIState(intent=Intent(goal="smalltalk"))
    assert _frontdoor_router(state) == "finalize"


def test_graph_contract_smoke_knowledge_entry_sets_last_node() -> None:
    state = SealAIState(intent=Intent(goal="explanation_or_comparison"))
    patch = knowledge_entry_node(state)
    patched = state.model_copy(update=patch, deep=True)
    assert patched.last_node == "knowledge_entry_node"


def test_graph_contract_smoke_confirm_gate_design_triggers_ask_missing() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation", confidence=0.9),
        messages=[HumanMessage(content="Bitte lege eine Dichtung aus")],
    )
    patch = confirm_gate_node(state)
    assert patch.get("awaiting_user_input") is True
    assert patch.get("ask_missing_request") is not None


def test_graph_contract_smoke_state_update_payload_contract() -> None:
    state = SealAIState(
        phase="validation",
        last_node="assumption_lock_node",
        awaiting_user_input=True,
        recommendation_ready=False,
        coverage_score=0.6,
        coverage_gaps=["pressure_bar"],
        missing_params=["pressure_bar"],
        pending_action=ACTION_RUN_KNOWLEDGE,
    )
    payload = _build_state_update_payload(state)
    assert payload["type"] == "state_update"
    assert payload["last_node"] == "assumption_lock_node"
    assert payload["awaiting_user_input"] is True
    assert payload["coverage_gaps"] == ["pressure_bar"]
    assert payload["missing_params"] == ["pressure_bar"]


def test_graph_contract_smoke_supervisor_missing_params_asks_user() -> None:
    state = SealAIState(missing_params=["pressure_bar"])
    patch = supervisor_policy_node(state)
    assert patch["next_action"] in {ACTION_ASK_USER, "ASK_USER"}
