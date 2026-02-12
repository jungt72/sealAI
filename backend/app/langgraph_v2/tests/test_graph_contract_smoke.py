from __future__ import annotations

"""Offline smoke tests for the current LangGraph v2 contract."""

from langgraph.checkpoint.memory import MemorySaver

from app.api.v1.endpoints.langgraph_v2 import _build_state_update_payload
from app.langgraph_v2.nodes.nodes_supervisor import ACTION_ASK_USER, ACTION_RUN_KNOWLEDGE, supervisor_policy_node
from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.tests.graph_contract_spec import (
    ALLOWED_SUPERVISOR_INBOUND,
    FORBIDDEN_EDGES,
    MANDATORY_EDGES,
    MANDATORY_NODES,
    edge_tuples,
)


def test_graph_contract_smoke_compiled_graph_matches_contract_spec() -> None:
    compiled = create_sealai_graph_v2(checkpointer=MemorySaver()).get_graph()
    nodes = set(compiled.nodes)
    edges = edge_tuples(compiled.edges)

    assert MANDATORY_NODES.issubset(nodes)
    assert MANDATORY_EDGES.issubset(edges)
    assert edges.isdisjoint(FORBIDDEN_EDGES)

    inbound_supervisor = {src for src, dst in edges if dst == "supervisor_policy_node"}
    assert inbound_supervisor == ALLOWED_SUPERVISOR_INBOUND


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
