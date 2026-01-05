# MIGRATION: Phase-2 - Debate Subgraph

from langgraph.graph import StateGraph

from ...state import SealAIState
from .nodes.debate_agent import debate_agent

def create_debate_subgraph():
    graph = StateGraph(SealAIState)
    graph.add_node("debate_agent", debate_agent)
    graph.set_entry_point("debate_agent")
    # debate_agent sends to resolver
    return graph.compile()
