from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
from app.langgraph_v2.tests.graph_contract_spec import MANDATORY_EDGES, edge_tuples


def test_rag_support_node_is_supervisor_gated() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver())
    compiled = graph.get_graph()
    edges = edge_tuples(compiled.edges)
    # Knowledge flow is gated by supervisor policy routing.
    assert ("supervisor_policy_node", "knowledge_entry_node") in edges
    assert ("supervisor_policy_node", "knowledge_entry_node") in MANDATORY_EDGES

    # Ensure no direct shortcuts from material comparison
    assert ("material_comparison_node", "knowledge_entry_node") not in edges
