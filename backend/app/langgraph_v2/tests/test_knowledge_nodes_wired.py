from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node
from app.langgraph_v2.state import Intent, SealAIState


def test_knowledge_nodes_are_wired():
    graph = create_sealai_graph_v2(checkpointer=MemorySaver())
    compiled = graph.get_graph()
    edges = list(compiled.edges)
    assert any(
        edge.source == "autonomous_supervisor_node" and edge.target == "knowledge_entry_node"
        for edge in edges
    )


def test_supervisor_routes_knowledge_intent():
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison", key="knowledge_material", knowledge_type="material"),
    )
    patch = supervisor_policy_node(state)
    assert patch.get("next_action") == "RUN_KNOWLEDGE"
