# backend/app/langgraph/compile.py
# MIGRATION: Phase-2 - Hauptgraph kompilieren, Checkpointer setzen

import os

from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from .constants import CHECKPOINTER_NAMESPACE_MAIN, REDIS_URL
from .nodes.confirm_gate import confirm_gate
from .nodes.discovery_intake import discovery_intake
from .nodes.entry_frontend import entry_frontend
from .nodes.exit_response import exit_response
from .nodes.intent_projector import intent_projector
from .nodes.resolver import resolver
from .nodes.supervisor import supervisor
from .state import SealAIState
from .subgraphs.debate.compile import create_debate_subgraph
from .subgraphs.material.compile import create_material_subgraph
from .utils.checkpointer import make_redis_checkpointer


def supervisor_condition(state):
    domains = state.get("routing", {}).get("domains", [])
    if "material" in domains:
        return "material_subgraph"
    return "resolver"


async def create_main_graph() -> CompiledStateGraph:
    redis_url = os.getenv("REDIS_URL", REDIS_URL)
    graph = StateGraph(SealAIState)

    # Nodes
    graph.add_node("entry_frontend", entry_frontend)
    graph.add_node("discovery_intake", discovery_intake)
    graph.add_node("confirm_gate", confirm_gate)
    graph.add_node("intent_projector", intent_projector)
    graph.add_node("supervisor", supervisor)
    graph.add_compiled_graph("material_subgraph", create_material_subgraph())
    graph.add_compiled_graph("debate_subgraph", create_debate_subgraph())
    graph.add_node("resolver", resolver)
    graph.add_node("exit_response", exit_response)

    # Edges
    graph.set_entry_point("entry_frontend")
    graph.add_edge("entry_frontend", "discovery_intake")
    graph.add_edge("discovery_intake", "confirm_gate")
    graph.add_edge("confirm_gate", "intent_projector")
    graph.add_edge("intent_projector", "supervisor")
    graph.add_edge("material_subgraph", "resolver")
    graph.add_conditional_edges(
        "supervisor",
        supervisor_condition,
        {"material_subgraph": "material_subgraph", "resolver": "resolver"},
    )
    graph.add_edge("resolver", "exit_response")
    graph.add_edge("exit_response", END)

    # Versionssicherer Redis-Checkpointer
    checkpointer = await make_redis_checkpointer(redis_url, CHECKPOINTER_NAMESPACE_MAIN)
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
    compiled: CompiledStateGraph = graph.compile(checkpointer=checkpointer)
    return compiled
