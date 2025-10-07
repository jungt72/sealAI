"""SSE chat endpoint using the unified LangGraph pipeline."""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:  # optional at import time – tests may not have langchain
    from langchain_core.messages import HumanMessage, SystemMessage
except Exception:  # pragma: no cover - defensive fallback for type checkers
    HumanMessage = SystemMessage = dict  # type: ignore[assignment]

from app.api.routes.chat_utils import ensure_system_prompt  # helper to keep file lean
from app.langgraph.graph_chat import compile_chat_graph
from app.langgraph.io.validation import ensure_parameter_bag
from app.services.auth.dependencies import get_current_request_user
from app.services.langgraph.instrumentation import with_tracing
from app.services.langgraph.redis_lifespan import get_redis_checkpointer

router = APIRouter()


class ParameterItem(BaseModel):
    name: str
    value: int | float | str | bool
    unit: str = Field(default="none")
    source: str = Field(default="user")


class ChatStreamRequest(BaseModel):
    chat_id: str = Field(..., min_length=1)
    input_text: str = Field(..., min_length=1)
    parameters: List[ParameterItem] = Field(default_factory=list)


def _model_dump(model: Any) -> Dict[str, Any]:
    exporter = getattr(model, "model_dump", None)
    if callable(exporter):
        return exporter()
    to_dict = getattr(model, "dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(model, dict):
        return dict(model)
    raise TypeError(f"Cannot serialise model of type {type(model)!r}")


def _parameter_payload(payload: ChatStreamRequest) -> Dict[str, Any]:
    items = [item.model_dump() for item in payload.parameters]
    bag = ensure_parameter_bag({"items": items})
    return _model_dump(bag)


def _sse(event: str, data: Any) -> bytes:
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _ensure_graph(app) -> Any:
    graph = getattr(app.state, "unified_graph", None)
    if graph is not None:
        return graph
    saver = get_redis_checkpointer(app)
    graph = compile_chat_graph(checkpointer=saver)
    app.state.unified_graph = graph
    app.state.unified_graph_cp = saver
    return graph


@router.post("/chat/stream", response_class=StreamingResponse, status_code=status.HTTP_200_OK)
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    username: str = Depends(get_current_request_user),
) -> StreamingResponse:
    text = payload.input_text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input_text empty")

    parameter_bag = _parameter_payload(payload)
    graph = _ensure_graph(request.app)

    system_prompt = ensure_system_prompt()
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=text)]

    thread_id = f"chat:{payload.chat_id.strip()}"

    initial_state = {
        "messages": messages,
        "parameter_bag": parameter_bag,
        "thread_id": thread_id,
        "user_id": username,
    }

    config = with_tracing(
        {
            "configurable": {
                "thread_id": thread_id,
                "user_id": username,
                "checkpoint_ns": getattr(request.app.state, "checkpoint_ns", None),
            }
        },
        run_name="unified_chat",
    )

    async def event_stream() -> AsyncGenerator[bytes, None]:
        result = await graph.ainvoke(initial_state, config=config)
        final_payload = result.get("final") or {}
        yield _sse("final", final_payload)
        yield _sse("done", {"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


__all__ = ["router"]
