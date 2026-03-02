from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.langgraph_v2.nodes.nodes_resume import resume_router_node
from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
from app.langgraph_v2.state import SealAIState


def test_resume_router_fallback_to_frontdoor() -> None:
    state = SealAIState.model_construct(
        awaiting_user_confirmation=True,
        confirm_decision="approve",
        phase="some_unknown_phase",
    )
    updates = resume_router_node(state)
    assert updates["phase"] == "confirm"

    # We use a fresh builder to inspect the topology as configured in create_sealai_graph_v2
    builder = create_sealai_graph_v2(
        checkpointer=MemorySaver(), 
        store=InMemoryStore(), 
        require_async=False, 
        return_builder=True
    )
    
    # In StateGraph builder, edges are stored in a way we can inspect.
    # We look for the conditional edges from 'resume_router_node'
    mapping = {}
    # builder.branches is a dict: {node_name: {branch_id: Branch}}
    for source, branches in builder.branches.items():
        if source == "resume_router_node":
            for branch_id, branch in branches.items():
                mapping.update(branch.ends)
            
    # Fallback path is explicitly "frontdoor" to ensure re-classification
    assert mapping["frontdoor"] == "frontdoor_discovery_node"
