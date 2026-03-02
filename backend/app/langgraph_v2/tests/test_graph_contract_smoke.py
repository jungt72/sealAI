from __future__ import annotations

"""Offline smoke tests for current LangGraph v2 graph contracts."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.api.v1.endpoints.langgraph_v2 import _build_state_update_payload
from app.langgraph_v2.sealai_graph_v2 import (
    _reducer_router,
    _rfq_validator_router,
    create_sealai_graph_v2,
)
from app.langgraph_v2.state import Intent, SealAIState, TechnicalParameters


def test_graph_contract_smoke_map_reduce_topology_has_required_v2_nodes() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore())
    compiled = graph.get_graph()
    node_ids = set(compiled.nodes.keys())

    required_nodes = {
        "profile_loader_node",
        "combinatorial_chemistry_guard_node",
        "node_router",
        "node_p1_context",
        "rfq_validator_node",
        "frontdoor_discovery_node",
        "supervisor_policy_node",
        "material_agent",
        "pricing_agent",
        "safety_agent",
        "reducer_node",
        "human_review_node",
    }
    assert required_nodes.issubset(node_ids)

    assert _reducer_router(SealAIState(requires_human_review=True)) == "human_review"
    assert _reducer_router(SealAIState(requires_human_review=False)) == "standard"
    assert _reducer_router(
        SealAIState(requires_human_review=False, intent=Intent(goal="explanation_or_comparison"))
    ) == "conversational_rag"
    assert _rfq_validator_router(SealAIState(rfq_ready=True)) == "ready"
    assert _rfq_validator_router(SealAIState(rfq_ready=False)) == "missing"


def test_graph_contract_smoke_sse_state_update_payload_contract() -> None:
    state = SealAIState(
        phase="supervisor",
        last_node="reducer_node",
        awaiting_user_input=True,
        awaiting_user_confirmation=False,
        recommendation_ready=True,
        recommendation_go=False,
        coverage_score=0.8,
        coverage_gaps=["speed_rpm"],
        missing_params=["speed_rpm"],
        parameters=TechnicalParameters(medium="Hydraulikoel", pressure_bar=25.0),
        pending_action="human_review",
        confirm_checkpoint_id="chk_123",
        final_prompt_metadata={"selected_template_name": "final_answer_discovery_v2.j2"},
        live_calc_tile={
            "v_surface_m_s": 3.92,
            "pv_value_mpa_m_s": 1.96,
            "hrc_warning": False,
            "status": "ok",
        },
    )

    payload = _build_state_update_payload(state)

    assert payload["type"] == "state_update"
    assert payload["phase"] == "supervisor"
    assert payload["last_node"] == "reducer_node"
    assert payload["awaiting_user_input"] is True
    assert payload["recommendation_ready"] is True
    assert payload["recommendation_go"] is False
    assert payload["coverage_score"] == 0.8
    assert payload["coverage_gaps"] == ["speed_rpm"]
    assert payload["missing_params"] == ["speed_rpm"]
    assert payload["parameters"]["medium"] == "Hydraulikoel"
    assert payload["parameters"]["pressure_bar"] == 25.0
    assert payload["delta"]["parameters"] == payload["parameters"]
    assert payload["pending_action"] == "human_review"
    assert payload["confirm_checkpoint_id"] == "chk_123"
    assert payload["final_prompt_metadata"]["selected_template_name"] == "final_answer_discovery_v2.j2"
    assert payload["data"]["live_calc_tile"]["v_surface_m_s"] == 3.92
    assert payload["data"]["live_calc_tile"]["pv_value_mpa_m_s"] == 1.96
    assert payload["data"]["live_calc_tile"]["hrc_warning"] is False
    assert payload["data"]["live_calc_tile"]["status"] == "ok"
