# MIGRATION: Phase-2 - Subgraph kompilieren (eigener Checkpointer optional)

from langgraph.graph import StateGraph

from .state import SealAIState
from .nodes.material_agent import material_agent
from .nodes.rag_select import rag_select
# from .nodes.tools_node import tool_node  # ToolNode not available
from .nodes.synthesis import synthesis

def create_material_subgraph():
    graph = StateGraph(SealAIState)
    # Add nodes
    graph.add_node("material_agent", material_agent)
    graph.add_node("rag_select", rag_select)
    # graph.add_node("tools_node", tool_node)  # ToolNode not available
    graph.add_node("synthesis", synthesis)
    # Edges
    graph.set_entry_point("material_agent")
    graph.add_edge("material_agent", "rag_select")
    graph.add_edge("rag_select", "synthesis")
    # synthesis sends to resolver in main graph
    return graph.compile()
