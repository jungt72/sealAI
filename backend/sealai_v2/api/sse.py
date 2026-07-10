"""SSE framing for POST /api/v2/chat/stream (P4a — stage progress, zero new LLM calls).

Doctrine (AGENTS.md § Safety Boundaries + the P4 line): stage frames carry ONLY
``{stage, status}``; the ANSWER crosses the wire exactly once, as the complete gated /chat
payload (`event: result`), after verify + cite; `event: error` carries a FIXED message,
never exception detail. The generator owns pipeline-task cancellation: a client disconnect
makes Starlette close the generator, and the ``finally`` cancels the in-flight run —
the provider call of a gone user is stopped, not orphaned.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

HEARTBEAT_SECONDS = (
    10.0  # < nginx default proxy_read_timeout (60s); keeps long stages alive
)
STREAM_SCHEMA_VERSION = "1"

_TERMINAL = {"result", "error"}


def format_frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_frames(
    queue: asyncio.Queue,
    task: asyncio.Task,
    *,
    heartbeat_s: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Yield SSE frames from ``queue`` until the terminal frame (result/error), emitting a
    ``: keepalive`` comment during silence. Always cancels an unfinished pipeline task on
    exit (disconnect or terminal frame — cancelling a done task is a no-op)."""
    try:
        while True:
            try:
                kind, data = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield format_frame(kind, data)
            if kind in _TERMINAL:
                return
    finally:
        if not task.done():
            task.cancel()
