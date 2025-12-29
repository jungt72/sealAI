from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2


def test_rag_support_node_is_supervisor_gated() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver())
    compiled = graph.get_graph()
    sources = [edge.source for edge in compiled.edges if edge.target == "rag_support_node"]
    assert set(sources) == {"confirm_resume_node", "supervisor_policy_node"}

    direct_edges = [
        edge
        for edge in compiled.edges
        if edge.source == "material_comparison_node" and edge.target == "rag_support_node"
    ]
    assert not direct_edges
