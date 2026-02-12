from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2
from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node
from app.langgraph_v2.state import Intent, SealAIState
from app.langgraph_v2.tests.graph_contract_spec import MANDATORY_EDGES, edge_tuples


def test_knowledge_nodes_are_wired():
    graph = create_sealai_graph_v2(checkpointer=MemorySaver())
    compiled = graph.get_graph()
    edges = edge_tuples(compiled.edges)
    assert ("supervisor_policy_node", "knowledge_entry_node") in edges
    assert ("supervisor_policy_node", "knowledge_entry_node") in MANDATORY_EDGES


def test_supervisor_routes_knowledge_intent():
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison", key="knowledge_material", knowledge_type="material"),
    )
    patch = supervisor_policy_node(state)
    assert patch.get("next_action") == "RUN_KNOWLEDGE"
