import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.langgraph_v2.nodes.nodes_supervisor import supervisor_logic_node
from app.langgraph_v2.sealai_graph_v2 import _frontdoor_router, _reducer_router, create_sealai_graph_v2
from app.langgraph_v2.state import Intent, SealAIState, TechnicalParameters


def test_graph_entry_routes_to_kb_lookup_or_smalltalk() -> None:
    """KB Integration: frontdoor now routes via parallel fanout (not directly to supervisor)."""
    graph = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore())
    compiled = graph.get_graph()
    entry_edges = [
        edge for edge in compiled.edges if edge.source == "frontdoor_discovery_node"
    ]
    targets = {edge.target for edge in entry_edges}
    # Post-KB-integration: supervisor path enters the parallel fanout first
    assert "frontdoor_parallel_fanout_node" in targets
    assert "smalltalk_node" in targets
    # supervisor_policy_node is now reached via node_merge_deterministic
    kb_edges = [
        edge for edge in compiled.edges if edge.source == "node_merge_deterministic"
    ]
    assert any(e.target == "supervisor_policy_node" for e in kb_edges)


def test_graph_parallel_worker_edges_route_to_reducer() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore())
    compiled = graph.get_graph()
    node_ids = set(compiled.nodes.keys())
    assert "calculator_agent" in node_ids
    assert "pricing_agent" in node_ids
    assert "safety_agent" in node_ids
    assert "human_review_node" in node_ids


def test_graph_reducer_routes_to_hitl_or_final() -> None:
    assert _reducer_router(SealAIState(requires_human_review=True)) == "human_review"
    assert _reducer_router(SealAIState(requires_human_review=False)) == "standard"


def test_frontdoor_router_prioritizes_task_intents_over_social_opening() -> None:
    state = SealAIState(
        flags={
            "frontdoor_bypass_supervisor": True,
            "frontdoor_social_opening": True,
            "frontdoor_task_intents": ["engineering_calculation"],
        }
    )
    assert _frontdoor_router(state) == "supervisor"


def test_frontdoor_router_routes_social_opening_without_task_intents_to_smalltalk() -> None:
    state = SealAIState(
        flags={
            "frontdoor_social_opening": True,
            "frontdoor_task_intents": [],
            "frontdoor_bypass_supervisor": False,
        }
    )
    assert _frontdoor_router(state) == "smalltalk"


def test_frontdoor_router_routes_chit_chat_category_to_smalltalk() -> None:
    state = SealAIState(
        flags={
            "frontdoor_intent_category": "CHIT_CHAT",
            "frontdoor_social_opening": False,
            "frontdoor_task_intents": [],
        }
    )
    assert _frontdoor_router(state) == "smalltalk"


def test_supervisor_policy_node_sets_coverage_from_missing_params() -> None:
    params = TechnicalParameters(
        medium="Hydraulikoel",
        pressure_bar=10,
        temperature_C=80,
        shaft_diameter=50,
        # speed_rpm missing -> 4/5 coverage == 0.8 => ready True
    )
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        parameters=params,
    )
    patch = supervisor_logic_node(state)
    assert patch["missing_params"] == ["speed_rpm"]
    assert patch["coverage_gaps"] == ["speed_rpm"]
    assert patch["coverage_score"] == 0.8
    assert patch["recommendation_ready"] is True
