import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.langgraph_v2.nodes.nodes_supervisor import supervisor_logic_node
from app.langgraph_v2.sealai_graph_v2 import _reducer_router, create_sealai_graph_v2
from app.langgraph_v2.nodes.route_after_frontdoor import route_after_frontdoor_node
from app.langgraph_v2.state import Intent, SealAIState, TechnicalParameters


def test_graph_entry_routes_to_kb_lookup_or_smalltalk() -> None:
    """Frontdoor should route through dedicated route_after_frontdoor node."""
    graph = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore())
    compiled = graph.get_graph()
    entry_edges = [
        edge for edge in compiled.edges if edge.source == "frontdoor_discovery_node"
    ]
    targets = {edge.target for edge in entry_edges}
    assert "route_after_frontdoor" in targets

    route_edges = [
        edge for edge in compiled.edges if edge.source == "frontdoor_parallel_fanout_node"
    ]
    route_targets = {edge.target for edge in route_edges}
    assert "node_factcard_lookup_parallel" in route_targets
    assert "node_compound_filter_parallel" in route_targets

    # supervisor_policy_node is reached via node_merge_deterministic or direct route_after path
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


def test_route_after_frontdoor_prioritizes_task_intents_over_social_opening() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        flags={
            "frontdoor_bypass_supervisor": True,
            "frontdoor_social_opening": True,
            "frontdoor_task_intents": ["engineering_calculation"],
        }
    )
    assert route_after_frontdoor_node(state).goto == "node_p1_context"


def test_route_after_frontdoor_routes_social_opening_without_task_intents_to_smalltalk() -> None:
    state = SealAIState(
        intent=Intent(goal="smalltalk"),
        flags={
            "frontdoor_social_opening": True,
            "frontdoor_task_intents": [],
            "frontdoor_bypass_supervisor": False,
        }
    )
    assert route_after_frontdoor_node(state).goto == "smalltalk_node"


def test_route_after_frontdoor_routes_comparison_goal_to_supervisor() -> None:
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        flags={
            "frontdoor_intent_category": "GENERAL_KNOWLEDGE",
            "frontdoor_social_opening": False,
            "frontdoor_task_intents": ["general_knowledge"],
        }
    )
    assert route_after_frontdoor_node(state).goto == "supervisor_policy_node"


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
