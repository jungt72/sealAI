from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncGenerator, Dict, Iterable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.langgraph.llm_factory import get_llm as make_llm
from app.services.langgraph.redis_lifespan import get_redis_checkpointer
from app.services.langgraph.prompt_registry import get_agent_prompt
from app.services.langgraph.graph.consult.memory_utils import (
    read_history as stm_read_history,
    write_message as stm_write_message,
)
from app.services.langgraph.compat import call_with_supported_kwargs

router = APIRouter()

# Tunables
SSE_MIN_CHARS      = int(os.getenv("SSE_COALESCE_MIN_CHARS", "24"))
SSE_MAX_LAT_MS     = float(os.getenv("SSE_COALESCE_MAX_LAT_MS", "60"))
SSE_EVENT_TIMEOUT  = int(os.getenv("SSE_EVENT_TIMEOUT_SEC", "60"))
SSE_INPUT_MAX      = int(os.getenv("SSE_INPUT_MAX_CHARS", "4000"))
GRAPH_BUILDER      = os.getenv("GRAPH_BUILDER", "supervisor").lower()

# Helpers
def _iter_text_from_chunk(chunk: Any) -> Iterable[str]:
    if isinstance(chunk, dict):
        for k in ("content", "delta", "text", "token"):
            v = chunk.get(k)
            if isinstance(v, str) and v:
                yield v
    c = getattr(chunk, "content", None)
    if isinstance(c, str) and c:
        yield c
    if isinstance(c, list):
        for part in c:
            if isinstance(part, str) and part:
                yield part

def _last_ai_text_from_result_like(obj: Dict[str, Any]) -> str:
    def _collect(x: Any, out: list[str]):
        if isinstance(x, str) and x.strip():
            out.append(x.strip()); return
        if isinstance(x, dict):
            for k in ("response", "final_text", "text", "answer"):
                v = x.get(k)
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
            msgs = x.get("messages")
            if isinstance(msgs, list):
                for m in msgs:
                    if isinstance(m, dict):
                        c = m.get("content")
                        if isinstance(c, str) and c.strip():
                            out.append(c.strip())
            for k in ("output", "state", "final_state", "result"):
                _collect(x.get(k), out)
        elif isinstance(x, list):
            for it in x:
                _collect(it, out)
    tmp: list[str] = []
    _collect(obj, tmp)
    return tmp[-1].strip() if tmp else ""

def _build_graph(app):
    # Gleiche Logik wie WS: Supervisor bevorzugen, sonst Consult
    if GRAPH_BUILDER == "supervisor":
        from app.services.langgraph.supervisor_graph import build_supervisor_graph as build_graph
    else:
        from app.services.langgraph.graph.consult.build import build_consult_graph as build_graph
    saver = None
    try:
        saver = get_redis_checkpointer(app)
    except Exception:
        saver = None
    g = build_graph()
    try:
        return g.compile(checkpointer=saver) if saver else g.compile()
    except Exception:
        return g.compile()

def _sse(event: str, data: Any) -> bytes:
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")

@router.post("/chat/stream")
async def chat_stream(request: Request) -> StreamingResponse:
    """
    Input (JSON):
      { "chat_id": "default", "input_text": "..." }
    Output: text/event-stream mit Events: token, final, done
    """
    body = await request.json()
    chat_id   = (body.get("chat_id") or body.get("chatId") or "default").strip() or "default"
    user_text = (body.get("input_text") or body.get("input") or body.get("message") or "").strip()
    if not user_text:
        async def bad() -> AsyncGenerator[bytes, None]:
            yield _sse("error", {"error": "input_empty"}); yield _sse("done", {"done": True})
        return StreamingResponse(bad(), media_type="text/event-stream")
    if SSE_INPUT_MAX > 0 and len(user_text) > SSE_INPUT_MAX:
        async def too_long() -> AsyncGenerator[bytes, None]:
            yield _sse("error", {"error": f"input exceeds {SSE_INPUT_MAX} chars"}); yield _sse("done", {"done": True})
        return StreamingResponse(too_long(), media_type="text/event-stream")

    async def gen() -> AsyncGenerator[bytes, None]:
        app = request.app
        # LLM fallback für Notfälle bereitstellen
        if not getattr(app.state, "llm", None):
            app.state.llm = make_llm(streaming=True)

        # History
        thread_id = f"api:{chat_id}"
        history = stm_read_history(thread_id, limit=80)
        sys_msg = SystemMessage(content=get_agent_prompt("supervisor"))

        # Graph vorbereiten (wie WS)
        if not getattr(app.state, "graph_async", None):
            app.state.graph_async = _build_graph(app)
            app.state.graph_sync  = app.state.graph_async

        g_async = app.state.graph_async
        initial = {
            "messages": [sys_msg] + history + [HumanMessage(content=user_text)],
            "chat_id": thread_id,
            "input": user_text,
        }
        cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": getattr(app.state, "checkpoint_ns", None)}}

        loop = asyncio.get_event_loop()
        buf: list[str] = []
        last_flush = [loop.time()]
        accum: list[str] = []
        final_tail = ""

        async def flush():
            if not buf:
                return
            chunk = "".join(buf); buf.clear(); last_flush[0] = loop.time()
            accum.append(chunk)
            yield_bytes = _sse("token", {"delta": chunk})
            # yield innerhalb Hilfsfunktion geht nicht; zurückgeben
            return yield_bytes

        # Sofortiges Lebenszeichen
        yield _sse("token", {"delta": "…"})
        # Stream
        async def run_stream(version: str):
            nonlocal final_tail
            if g_async is None:
                return
            astream_method = getattr(g_async, "astream_events", None)
            if not callable(astream_method):
                return
            agen = call_with_supported_kwargs(
                astream_method,
                initial,
                config=cfg,
                version=version,
            )
            async for ev in agen:  # type: ignore[misc]
                ev_name = ev.get("event"); data = ev.get("data")
                if ev_name in ("on_chat_model_stream", "on_llm_stream"):
                    chunk = (data or {}).get("chunk") if isinstance(data, dict) else None
                    if chunk:
                        for piece in _iter_text_from_chunk(chunk):
                            if not piece:
                                continue
                            buf.append(piece)
                            enough  = sum(len(x) for x in buf) >= SSE_MIN_CHARS
                            too_old = (loop.time() - last_flush[0]) * 1000.0 >= SSE_MAX_LAT_MS
                            if enough or too_old:
                                y = await flush()
                                if y: yield y
                if ev_name in ("on_node_end",):
                    y = await flush()
                    if y: yield y
                if ev_name in ("on_chain_end", "on_graph_end"):
                    if isinstance(data, dict):
                        final_tail = _last_ai_text_from_result_like(data) or final_tail
            y = await flush()
            if y: yield y

        timed_out = False
        try:
            async for y in asyncio.wait_for(run_stream("v2").__aiter__(), timeout=SSE_EVENT_TIMEOUT):  # type: ignore
                if y:
                    yield y
        except asyncio.TimeoutError:
            timed_out = True
        except Exception:
            # v1 Fallback
            try:
                async for y in asyncio.wait_for(run_stream("v1").__aiter__(), timeout=SSE_EVENT_TIMEOUT):  # type: ignore
                    if y:
                        yield y
            except Exception:
                pass

        final_text = final_tail or "".join(accum).strip()
        if not final_text:
            # Notfall: einmalig synchron antworten
            try:
                resp = await app.state.llm.ainvoke([sys_msg] + history + [HumanMessage(content=user_text)])
                final_text = (getattr(resp, "content", "") or "").strip()
            except Exception:
                final_text = ""
        if final_text:
            try: stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
            except Exception: pass
        if final_text:
            yield _sse("final", {"final": {"text": final_text}})
        else:
            yield _sse("final", {"final": {"text": ""}})
        yield _sse("done", {"done": True})

    return StreamingResponse(gen(), media_type="text/event-stream")
