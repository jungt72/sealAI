import app.langgraph_v2.sealai_graph_v2  # noqa: F401

from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node
from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
from app.langgraph_v2.state import Intent, SealAIState, TechnicalParameters


def test_graph_entry_routes_to_supervisor_policy_node() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver())
    compiled = graph.get_graph()
    entry_edges = [
        edge for edge in compiled.edges if edge.source == "frontdoor_discovery_node"
    ]
    assert len(entry_edges) == 1
    assert entry_edges[0].target == "supervisor_policy_node"


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
    patch = supervisor_policy_node(state)
    assert patch["missing_params"] == ["speed_rpm"]
    assert patch["coverage_gaps"] == ["speed_rpm"]
    assert patch["coverage_score"] == 0.8
    assert patch["recommendation_ready"] is True
