# backend/app/langgraph/compile.py
# MIGRATION: Phase-2 - Hauptgraph kompilieren, Checkpointer setzen

from __future__ import annotations

from typing import Optional

from langgraph.graph import START, END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .checkpointer import make_checkpointer
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
from .subgraphs.recommendation.nodes.rag_handoff import rag_handoff

_CHECKPOINTER = make_checkpointer()
_ASYNC_CHECKPOINTER = make_checkpointer(require_async=True)


def _create_recommendation_subgraph() -> CompiledStateGraph:
    # // FIX: Lightweight recommendation subgraph for RAG enrichment.
    subgraph = StateGraph(SealAIState)
    subgraph.add_node("rag_handoff", rag_handoff)
    subgraph.set_entry_point("rag_handoff")
    subgraph.add_edge("rag_handoff", END)
    return subgraph.compile()

def _ensure_compiled(subgraph) -> CompiledStateGraph:
    if isinstance(subgraph, CompiledStateGraph):
        return subgraph
    if isinstance(subgraph, StateGraph):
        return subgraph.compile()
    compile_attr = getattr(subgraph, "compile", None)
    if callable(compile_attr):
        compiled = compile_attr()
        if isinstance(compiled, CompiledStateGraph):
            return compiled
    raise TypeError("Expected a StateGraph or CompiledStateGraph for subgraph nodes")

def _ensure_async_ready(checkpointer: object) -> object:
    """
    Ensure the supplied saver provides async checkpoint primitives.
    Falls back to the async-safe module default otherwise.
    """
    if hasattr(checkpointer, "aget_tuple") and callable(getattr(checkpointer, "aget_tuple")):
        return checkpointer
    return _ASYNC_CHECKPOINTER


def create_main_graph(*, checkpointer: Optional[object] = None, require_async: bool = False) -> CompiledStateGraph:
    builder = StateGraph(SealAIState)

    # Nodes
    builder.add_node("entry_frontend", entry_frontend)
    builder.add_node("discovery_intake", discovery_intake)
    builder.add_node("confirm_gate", confirm_gate)
    builder.add_node("intent_projector", intent_projector)
    builder.add_node("supervisor", supervisor)

    recommendation_subgraph = _ensure_compiled(_create_recommendation_subgraph())
    material_subgraph = _ensure_compiled(create_material_subgraph())
    debate_subgraph = _ensure_compiled(create_debate_subgraph())

    builder.add_node("recommendation", recommendation_subgraph)
    builder.add_node("material_subgraph", material_subgraph)
    builder.add_node("debate_subgraph", debate_subgraph)
    builder.add_node("resolver", resolver)
    builder.add_node("exit_response", exit_response)

    # Edges
    builder.add_edge(START, "entry_frontend")
    builder.add_edge("entry_frontend", "discovery_intake")
    builder.add_edge("discovery_intake", "confirm_gate")
    builder.add_edge("confirm_gate", "intent_projector")
    builder.add_edge("intent_projector", "supervisor")
    builder.add_edge("supervisor", "resolver")
    builder.add_edge("recommendation", "resolver")
    builder.add_edge("material_subgraph", "resolver")
    builder.add_edge("debate_subgraph", "resolver")
    builder.add_edge("resolver", "exit_response")
    builder.add_edge("exit_response", END)

    if checkpointer is None:
        checkpointer = _ASYNC_CHECKPOINTER if require_async else _CHECKPOINTER
    elif require_async:
        checkpointer = _ensure_async_ready(checkpointer)

    return builder.compile(checkpointer=checkpointer)
