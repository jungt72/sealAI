from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app._legacy_v2.sealai_graph_v2 import create_sealai_graph_v2


def test_rag_support_node_is_supervisor_gated() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore())
    compiled = graph.get_graph()
    node_ids = set(compiled.nodes.keys())
    assert "rag_support_node" in node_ids
    assert "supervisor_policy_node" in node_ids
    inbound = [edge.source for edge in compiled.edges if edge.target == "rag_support_node"]
    assert inbound == []
