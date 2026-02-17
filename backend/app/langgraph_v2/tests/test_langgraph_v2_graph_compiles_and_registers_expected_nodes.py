from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.contracts import STABLE_V2_NODE_CONTRACT, get_compiled_graph_node_names
from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2


def test_graph_registers_rag_support_node() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver())
    compiled = graph.get_graph()
    assert "rag_support_node" in compiled.nodes


def test_graph_registers_stable_v2_contract_nodes() -> None:
    graph = create_sealai_graph_v2(checkpointer=MemorySaver())
    node_names = get_compiled_graph_node_names(graph)
    assert STABLE_V2_NODE_CONTRACT.issubset(node_names)
