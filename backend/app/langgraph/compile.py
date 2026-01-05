# backend/app/langgraph/compile.py
# MIGRATION: Phase-2 - Hauptgraph kompilieren, Checkpointer setzen
from __future__ import annotations
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage, HumanMessage
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
from .nodes.memory_bridge import memory_bridge_node
from .state import MetaInfo, Routing, SealAIState

logger = logging.getLogger(__name__)
_CHECKPOINTER = make_checkpointer()
_ASYNC_CHECKPOINTER = make_checkpointer(require_async=True)

_TECHNICAL_DOMAINS: Set[str] = {"sealing", "dichtungstechnik"}
_NON_TECHNICAL_KINDS: Set[str] = {"smalltalk", "greeting", "meta", "other"}
_TECHNICAL_CONFIDENCE_THRESHOLD = 0.7


def _is_technical_consulting(intent: Optional[dict]) -> bool:
    if not isinstance(intent, dict):
        return False
    domain = str(intent.get("domain") or "").strip().lower()
    if domain not in _TECHNICAL_DOMAINS:
        return False
    kind = str(intent.get("kind") or "").strip().lower()
    if kind in _NON_TECHNICAL_KINDS:
        return False
    try:
        confidence = float(intent.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return confidence >= _TECHNICAL_CONFIDENCE_THRESHOLD


def _route_after_intent(state: SealAIState) -> str:
    slots = state.get("slots") or {}
    intent = state.get("intent")
    if _is_technical_consulting(intent):
        if slots.get("rapport_phase_done"):
            return "warmup_agent"
        return "rapport_agent"
    return "context_retrieval"


_GRAPH_CACHE: Optional[CompiledStateGraph] = None


def ensure_main_graph() -> CompiledStateGraph:
    if _GRAPH_CACHE is None:
        raise RuntimeError("Main graph not initialized.")
    return _GRAPH_CACHE


def _resolve_graph_inputs(payload: Dict[str, Any], request: Request) -> Tuple[str, str, str]:
    user_input = str(
        payload.get("input")
        or payload.get("text")
        or payload.get("query")
        or payload.get("message")
        or ""
    ).strip()

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
    return user_input, chat_id, user_id


def _format_sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def build_initial_state(
    payload: Dict[str, Any],
    *,
    chat_id: str,
    user_id: str,
    user_input: str,
) -> SealAIState:
    return {
        "messages": [HumanMessage(content=user_input)],
        "meta": {"thread_id": chat_id, "user_id": user_id},
        "slots": {"user_query": user_input},
        "routing": {},
        "context_refs": [],
    }


def build_stream_config(*, thread_id: str, user_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": thread_id, "user_id": user_id}}


def _extract_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("content") or value.get("text")
    return getattr(value, "content", None)


async def iter_langgraph_payloads(
    graph: Any,
    state: SealAIState,
    config: Dict[str, Any],
) -> AsyncIterator[Dict[str, Any]]:
    async for event in graph.astream_events(state, config=config, version="v1"):
        kind = str(event.get("event") or "").strip()
        data = event.get("data")
        if kind in {"on_chat_model_stream", "on_llm_stream"}:
            chunk = None
            if isinstance(data, dict):
                chunk = data.get("chunk") or data.get("delta")
            else:
                chunk = data
            text = _extract_text(chunk)
            if text:
                yield {"type": "token", "event": "token", "text": text}
        elif kind == "messages":
            messages = data if isinstance(data, list) else []
            for message in messages:
                text = _extract_text(message)
                if text:
                    yield {"type": "message", "event": "message", "text": text}
        elif kind == "on_graph_end":
            yield {"type": "done", "event": "done", "data": data}
            break


async def run_langgraph_stream(request: Request) -> StreamingResponse:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid_json: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")

    user_input, chat_id, user_id = _resolve_graph_inputs(payload, request)
    if not user_input:
        raise HTTPException(status_code=400, detail="missing_input")

    graph = ensure_main_graph()
    state: SealAIState = {
        "messages": [{"role": "user", "content": user_input}],
        "meta": {"thread_id": chat_id, "user_id": user_id},
    }
    config = {"configurable": {"thread_id": chat_id, "user_id": user_id}}

    async def _stream() -> AsyncIterator[str]:
        done_sent = False
        async for event in graph.astream_events(state, config=config, version="v1"):
            kind = str(event.get("event") or "").strip()
            data = event.get("data")
            if kind == "messages":
                messages = []
                if isinstance(data, list):
                    messages = data
                elif isinstance(data, dict):
                    messages = data.get("messages") or data.get("data") or []
                for message in messages:
                    text = None
                    if isinstance(message, dict):
                        text = message.get("text") or message.get("content")
                    else:
                        text = getattr(message, "content", None)
                    if text:
                        yield _format_sse("message", {"text": text})
            elif kind == "on_graph_end":
                final_state = {}
                if isinstance(data, dict):
                    final_state = data.get("state") or data.get("output") or {}
                slots = final_state.get("slots") if isinstance(final_state, dict) else {}
                if isinstance(slots, dict):
                    final_answer = slots.get("final_answer") or slots.get("candidate_answer")
                    if final_answer:
                        yield _format_sse("message", {"text": str(final_answer)})
                yield _format_sse("done", {"state": final_state})
                done_sent = True
                break
        if not done_sent:
            yield _format_sse("done", {"state": {}})

    return StreamingResponse(_stream(), media_type="text/event-stream")


__all__ = [
    "run_langgraph_stream",
    "ensure_main_graph",
    "memory_bridge_node",
    "_route_after_intent",
    "build_initial_state",
    "build_stream_config",
    "iter_langgraph_payloads",
]
