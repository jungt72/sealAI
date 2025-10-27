# backend/app/services/chat/ws_streaming.py
"""Chat streaming helpers with LangGraph integration."""
from __future__ import annotations

import os
import traceback
from typing import Any, Iterable, List
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.services.chat.ws_commons import send_json_safe

FLUSH_MAX_LATENCY_SEC = float(os.getenv("WS_STREAM_MAX_LATENCY_SEC", "1.0"))


def _truncate_history_for_prompt(system_prompt: str, history: Iterable[Any], max_chars: int = 4000) -> List[Any]:
    keep: List[Any] = []
    remaining = max(max_chars - len(system_prompt or ""), 0)
    for message in reversed(list(history)):
        text = (getattr(message, "content", None) or getattr(message, "text", None) or "")
        if len(text) > remaining and keep:
            break
        keep.append(message)
        remaining -= len(text)
    keep.reverse()
    return keep


async def stream_langgraph(ws, payload):
    """Stream LangGraph responses over WebSocket."""
    try:
        from app.langgraph.compile import create_main_graph
        from app.langgraph.constants import CHECKPOINTER_NAMESPACE_MAIN
        from app.langgraph.state import MetaInfo, Routing, SealAIState

        graph = await create_main_graph()

        user_input = (payload.get("input") or "").strip()
        chat_id = (payload.get("chat_id") or "default").strip()
        user_id = payload.get("user_id") or "ws_user"

        initial_state = SealAIState(
            messages=[],
            slots={"user_query": user_input},
            routing=Routing(),
            context_refs=[],
            meta=MetaInfo(thread_id=chat_id, user_id=user_id, trace_id=str(uuid4())),
        )

        config = {
            "configurable": {
                "thread_id": chat_id,
                "user_id": user_id,
                "checkpoint_ns": CHECKPOINTER_NAMESPACE_MAIN,
            }
        }

        async for event in graph.astream_events(initial_state, config=config, stream_mode="messages"):
            kind = event.get("event")
            if kind == "messages":
                for message in event.get("data", []):
                    await _send_stream_chunk(ws, message)
            elif kind == "end":
                await send_json_safe(ws, {"event": "done"})
                return

        await send_json_safe(ws, {"event": "done"})

    except ImportError as e:
        await send_json_safe(ws, {"event": "error", "message": f"LangGraph import error: {str(e)}"})
        await send_json_safe(ws, {"event": "done"})
    except Exception as e:  # pragma: no cover - defensive
        await send_json_safe(
            ws,
            {"event": "error", "message": f"LangGraph error: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"},
        )
        await send_json_safe(ws, {"event": "done"})


async def _send_stream_chunk(ws, message: BaseMessage) -> None:
    if isinstance(message, AIMessage):
        await send_json_safe(ws, {"event": "text", "text": message.content})
    elif isinstance(message, ToolMessage):
        await send_json_safe(
            ws,
            {
                "event": "tool",
                "tool_call_id": getattr(message, "tool_call_id", None),
                "payload": message.content,
            },
        )


__all__ = ["_truncate_history_for_prompt", "stream_langgraph", "FLUSH_MAX_LATENCY_SEC"]
