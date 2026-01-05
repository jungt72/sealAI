# backend/app/services/chat/ws_streaming.py
"""Chat streaming helpers (legacy v1 removed)."""
from __future__ import annotations

import os
from typing import Any, Iterable, List

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


async def stream_langgraph(_ws, _payload):
    """Legacy v1 streaming removed; use /api/v1/langgraph/chat/v2 SSE instead."""
    raise RuntimeError(
        "Legacy LangGraph v1 WebSocket streaming removed; use /api/v1/langgraph/chat/v2 (SSE)."
    )


__all__ = ["_truncate_history_for_prompt", "stream_langgraph", "FLUSH_MAX_LATENCY_SEC"]
