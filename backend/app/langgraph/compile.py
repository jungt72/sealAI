# backend/app/langgraph/compile.py
# MIGRATION: Phase-2 - Hauptgraph kompilieren, Checkpointer setzen
from __future__ import annotations
import json
from typing import Any, AsyncIterator, Dict, Optional
from uuid import uuid4
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from .checkpointer import make_checkpointer
from .constants import CHECKPOINTER_NAMESPACE_MAIN
from .nodes.confirm_gate import confirm_gate
from .nodes.discovery_intake import discovery_intake
from .nodes.entry_frontend import entry_frontend
from .nodes.exit_response import exit_response
from .nodes.intent_projector import intent_projector
from .nodes.resolver import resolver
from .nodes.supervisor import supervisor
from .state import MetaInfo, Routing, SealAIState
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
    builder.add_node("resolver", resolver)
    builder.add_node("exit_response", exit_response)
    # Edges
    builder.add_edge(START, "entry_frontend")
    builder.add_edge("entry_frontend", "discovery_intake")
    builder.add_edge("discovery_intake", "confirm_gate")
    builder.add_edge("confirm_gate", "intent_projector")
    builder.add_edge("intent_projector", "supervisor")
    builder.add_edge("supervisor", "resolver")
    builder.add_edge("resolver", "exit_response")
    builder.add_edge("exit_response", END)
    if checkpointer is None:
        checkpointer = _ASYNC_CHECKPOINTER if require_async else _CHECKPOINTER
    elif require_async:
        checkpointer = _ensure_async_ready(checkpointer)
    return builder.compile(checkpointer=checkpointer)
_GRAPH_CACHE: Optional[CompiledStateGraph] = None
def _ensure_main_graph() -> CompiledStateGraph:
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        _GRAPH_CACHE = create_main_graph(require_async=True)
    return _GRAPH_CACHE
def _message_text(message: Any) -> Optional[str]:
    if isinstance(message, BaseMessage):
        content = message.content
        return content if isinstance(content, str) else str(content)
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if content is not None:
            return str(content)
    return None
async def _request_payload(request: Request) -> Dict[str, Any]:
    cached = getattr(request.state, "langgraph_payload", None)
    if isinstance(cached, dict):
        return dict(cached)
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            data = await request.json()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return dict(request.query_params)
def _build_initial_state(payload: Dict[str, Any], *, chat_id: str, user_id: str, user_input: str) -> SealAIState:
    return SealAIState(
        messages=[],
        slots={"user_query": user_input},
        routing=Routing(),
        context_refs=[],
        meta=MetaInfo(thread_id=chat_id, user_id=user_id, trace_id=str(uuid4())),
    )
async def _sse_events(graph: CompiledStateGraph, state: SealAIState, config: Dict[str, Any]) -> AsyncIterator[str]:
    async for event in graph.astream_events(state, config=config, stream_mode="messages"):
        kind = event.get("event")
        if kind == "messages":
            for message in event.get("data", []):
                text = _message_text(message)
                if text:
                    payload = json.dumps({"text": text}, ensure_ascii=False)
                    yield f"event: message\ndata: {payload}\n\n"
        elif kind == "end":
            yield "event: done\ndata: {}\n\n"
            return
async def run_langgraph_stream(request: Request):
    payload = await _request_payload(request)
    user_input = str(
        payload.get("input")
        or payload.get("input_text")
        or payload.get("text")
        or payload.get("query")
        or payload.get("message")
        or ""
    ).strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="input empty")
    chat_id = str(
        payload.get("chat_id")
        or payload.get("thread_id")
        or payload.get("chatId")
        or request.path_params.get("chat_id")
        or "default"
    ).strip() or "default"
    user_id = str(
        payload.get("user_id")
        or getattr(getattr(request.state, "user", None), "id", None)
        or request.headers.get("x-user-id")
        or "api_user"
    )
    graph = _ensure_main_graph()
    initial_state = _build_initial_state(payload, chat_id=chat_id, user_id=user_id, user_input=user_input)
    config = {
        "configurable": {
            "thread_id": chat_id,
            "user_id": user_id,
            "checkpoint_ns": CHECKPOINTER_NAMESPACE_MAIN,
        }
    }
    accepts = request.headers.get("accept", "")
    if request.url.path.endswith("/chat/stream") or "text/event-stream" in accepts:
        return StreamingResponse(_sse_events(graph, initial_state, config), media_type="text/event-stream")
    final_text = ""
    async for event in graph.astream_events(initial_state, config=config, stream_mode="messages"):
        if event.get("event") == "messages":
            for message in event.get("data", []):
                text = _message_text(message)
                if text:
                    final_text = text
        elif event.get("event") == "end":
            break
    return {"text": final_text or "", "chat_id": chat_id}
__all__ = ["create_main_graph", "run_langgraph_stream"]
