from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2


def test_knowledge_query_terminates_at_final_answer() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver())
    compiled = graph.get_graph()
    edges = {(edge.source, edge.target) for edge in compiled.edges}

    assert ("knowledge_material_node", "policy_firewall_node") in edges
    assert ("knowledge_lifetime_node", "policy_firewall_node") in edges
    assert ("generic_sealing_qa_node", "policy_firewall_node") in edges
    assert ("final_answer_node", "__end__") in edges
