from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.langgraph_v2.nodes.nodes_resume import resume_router_node
from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
from app.langgraph_v2.state import SealAIState


def test_resume_router_default_mapping_safe_fallback() -> None:
    state = SealAIState.model_construct(
        awaiting_user_confirmation=True,
        confirm_decision="approve",
        phase="some_unknown_phase",
    )
    updates = resume_router_node(state)
    assert updates["phase"] == "confirm"

    graph = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore())
    compiled = graph.get_graph()
    edges = [
        edge
        for edge in compiled.edges
        if edge.source == "resume_router_node" and edge.conditional
    ]
    mapping = {edge.data: edge.target for edge in edges}

    assert mapping["default"] == "response_node"
    assert mapping["frontdoor"] == "frontdoor_discovery_node"
