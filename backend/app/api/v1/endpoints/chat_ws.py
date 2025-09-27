# Generated from the original SealAI code dump with modifications.
# The WebSocket authentication logic now accepts JWT tokens passed via
# Authorization headers, URL query parameters or the Sec-WebSocket-Protocol
# subprotocol list. Additionally, the guard_websocket import is active.

from __future__ import annotations

import os
import re
import json
import asyncio
from typing import Any, Dict, Iterable, List, Optional, Tuple
import redis

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages.ai import AIMessageChunk

from app.api.v1.dependencies.auth import guard_websocket  # activated for WS auth
from app.services.langgraph.llm_factory import get_llm as make_llm
from app.services.langgraph.redis_lifespan import get_redis_checkpointer
from app.services.langgraph.prompt_registry import get_agent_prompt
from app.services.langgraph.graph.consult.memory_utils import (
    read_history as stm_read_history,
    write_message as stm_write_message,
)
from app.services.langgraph.tools import long_term_memory as ltm
from app.services.langgraph.compat import call_with_supported_kwargs


router = APIRouter()

# --- Tunables / Env (engere Defaults für mehr Tempo) ---
COALESCE_MIN_CHARS = int(os.getenv("WS_COALESCE_MIN_CHARS", "24"))
COALESCE_MAX_LAT_MS = float(os.getenv("WS_COALESCE_MAX_LAT_MS", "40"))
IDLE_TIMEOUT_SEC = int(os.getenv("WS_IDLE_TIMEOUT_SEC", "45"))  # 45s, Client heartbeat < 45s
FIRST_TOKEN_TIMEOUT_MS = int(os.getenv("WS_FIRST_TOKEN_TIMEOUT_MS", "2000"))
WS_INPUT_MAX_CHARS = int(os.getenv("WS_INPUT_MAX_CHARS", "4000"))
WS_RATE_LIMIT_PER_MIN = int(os.getenv("WS_RATE_LIMIT_PER_MIN", "30"))
MICRO_CHUNK_CHARS = int(os.getenv("WS_MICRO_CHUNK_CHARS", "0"))
EMIT_FINAL_TEXT = os.getenv("WS_EMIT_FINAL_TEXT", "0") == "1"
DEBUG_EVENTS = os.getenv("WS_DEBUG_EVENTS", "1") == "1"
WS_EVENT_TIMEOUT_SEC = int(os.getenv("WS_EVENT_TIMEOUT_SEC", "25"))
FORCE_SYNC_FALLBACK = os.getenv("WS_FORCE_SYNC", "0") == "1"

FLUSH_ENDINGS: Tuple[str, ...] = (". ", "? ", "! ", "\n\n", ":", ";", "…", ", ", ") ", "] ", " }")


def _env_stream_nodes() -> set[str]:
    raw = os.getenv("WS_STREAM_NODES", "*").strip()
    if not raw or raw in {"*", "all"}:
        return {"*"}
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


STREAM_NODES = _env_stream_nodes()
GRAPH_BUILDER = os.getenv("GRAPH_BUILDER", "supervisor").lower()


def _log(msg: str, **extra) -> None:
    try:
        if extra:
            print(f"[ws] {msg} " + json.dumps(extra, ensure_ascii=False, default=str))
        else:
            print(f"[ws] {msg}")
    except Exception:
        try:
            print(f"[ws] {msg} {extra}")
        except Exception:
            pass


def _get_rl_redis(app) -> Optional[redis.Redis]:
    client = getattr(app.state, "redis_rl", None)
    if client is not None:
        return client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        app.state.redis_rl = client
        return client
    except Exception:
        return None


def _piece_from_llm_chunk(chunk: Any) -> Optional[str]:
    if isinstance(chunk, AIMessageChunk):
        return chunk.content or ""
    txt = getattr(chunk, "content", None)
    if isinstance(txt, str) and txt:
        return txt
    ak = getattr(chunk, "additional_kwargs", None)
    if isinstance(ak, dict):
        for k in ("delta", "content", "text", "token"):
            v = ak.get(k)
            if isinstance(v, str) and v:
                return v
    if isinstance(chunk, dict):
        for k in ("delta", "content", "text", "token"):
            v = chunk.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def _iter_text_from_chunk(chunk) -> Iterable[str]:
    if isinstance(chunk, dict):
        c = chunk.get("content")
        if isinstance(c, str) and c:
            yield c
            return
        d = chunk.get("delta")
        if isinstance(d, str) and d:
            yield d
            return
    content = getattr(chunk, "content", None)
    if isinstance(content, str) and content:
        yield content
        return
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                yield part
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                yield part["text"]
    ak = getattr(chunk, "additional_kwargs", None)
    if isinstance(ak, dict):
        for k in ("delta", "content", "text", "token"):
            v = ak.get(k)
            if isinstance(v, str) and v:
                yield v


_BOUNDARY_RX = re.compile(r"[ \n\t.,;:!?…\)\]}]")


def _micro_chunks(s: str) -> Iterable[str]:
    n = MICRO_CHUNK_CHARS
    if n <= 0 or len(s) <= n:
        yield s
        return
    i = 0
    L = len(s)
    while i < L:
        j = min(i + n, L)
        k = j
        if j < L:
            m = _BOUNDARY_RX.search(s, j, min(L, j + 40))
            if m:
                k = m.end()
        yield s[i:k]
        i = k


def _is_relevant_node(ev: Dict) -> bool:
    if "*" in STREAM_NODES or "all" in STREAM_NODES:
        return True
    meta = ev.get("metadata") or {}
    run = ev.get("run") or {}
    node = str(meta.get("langgraph_node") or "").lower()
    run_name = str(run.get("name") or meta.get("run_name") or "").lower()
    return (node in STREAM_NODES) or (run_name in STREAM_NODES)


def _extract_texts(obj: Any) -> List[str]:
    out: List[str] = []
    if isinstance(obj, str) and obj.strip():
        out.append(obj.strip())
        return out
    if isinstance(obj, dict):
        for k in ("response", "final_text", "text", "answer"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        msgs = obj.get("messages")
        if isinstance(msgs, list):
            for m in msgs:
                if isinstance(m, AIMessage):
                    c = getattr(m, "content", "")
                    if isinstance(c, str) and c.strip():
                        out.append(c.strip())
                elif isinstance(m, dict):
                    c = m.get("content")
                    if isinstance(c, str) and c.strip():
                        out.append(c.strip())
        for k in ("output", "state", "final_state", "result"):
            sub = obj.get(k)
            out.extend(_extract_texts(sub))
    elif isinstance(obj, list):
        for it in obj:
            out.extend(_extract_texts(it))
    return out


def _last_ai_text_from_result_like(obj: Dict[str, Any]) -> str:
    texts = _extract_texts(obj)
    return texts[-1].strip() if texts else ""


REMEMBER_RX = re.compile(r"^\s*(?:!remember|remember|merke(?:\s*dir)?|speicher(?:e)?)\s*[:\-]?\s*(.+)$", re.I)
GREETING_RX = re.compile(r"^(hi|hallo|hello|hey|moin)\b", re.I)


def _ensure_graph(app, builder_name: str | None = None) -> None:
    # Cache per graph name
    want = (builder_name or GRAPH_BUILDER).lower().strip() or "supervisor"
    if (
        getattr(app.state, "graph_name", None) == want
        and (
            getattr(app.state, "graph_async", None) is not None
            or getattr(app.state, "graph_sync", None) is not None
        )
    ):
        return

    if want == "supervisor":
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
        compiled = g.compile(checkpointer=saver) if saver else g.compile()
    except Exception:
        compiled = g.compile()

    app.state.graph_async = compiled
    app.state.graph_sync = compiled
    app.state.graph_name = want


def _choose_subprotocol(ws: WebSocket) -> Optional[str]:
    raw = ws.headers.get("sec-websocket-protocol")
    if not raw:
        return None
    return raw.split(",")[0].strip() or None


async def _send_json_safe(ws: WebSocket, payload: Dict) -> bool:
    try:
        await ws.send_json(payload)
        return True
    except WebSocketDisconnect:
        return False
    except Exception:
        return False


def _get_token(ws: WebSocket) -> Optional[str]:
    """
    Extract the JWT from the WebSocket headers or query parameters.

    Supports three transports:
      * Authorization: Bearer <token>
      * ?token=<token> query parameter
      * Sec-WebSocket-Protocol header: either "bearer,<token>" or a single
        protocol value containing dots (e.g. a JWT)
    """
    auth = ws.headers.get("authorization") or ws.headers.get("Authorization")
    if auth:
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    # query param
    try:
        q = ws.query_params.get("token")
        if q:
            return str(q)
    except Exception:
        pass
    # subprotocol
    sp = ws.headers.get("sec-websocket-protocol") or ws.headers.get("Sec-WebSocket-Protocol")
    if sp:
        protocols = [p.strip() for p in sp.split(",") if p.strip()]
        if protocols:
            first = protocols[0].lower()
            if first in {"bearer", "jwt", "token"} and len(protocols) > 1:
                return protocols[1]
            if len(protocols) == 1 and "." in protocols[0]:
                return protocols[0]
    return None


# ------------------- Streaming helpers -------------------


async def _send_typing_stub(ws: WebSocket, thread_id: str) -> None:
    await _send_json_safe(ws, {"event": "typing", "thread_id": thread_id})


async def _stream_llm_direct(ws: WebSocket, llm, *, user_input: str, thread_id: str) -> None:
    def cancelled() -> bool:
        flags = getattr(ws.app.state, "ws_cancel_flags", {})
        return bool(flags.get(thread_id))

    history = stm_read_history(thread_id, limit=80)
    if cancelled():
        return

    loop = asyncio.get_event_loop()
    buf: List[str] = []
    accum: List[str] = []
    last_flush = [loop.time()]

    async def flush() -> None:
        if not buf or cancelled():
            return
        chunk = "".join(buf)
        buf.clear()
        last_flush[0] = loop.time()
        accum.append(chunk)
        await _send_json_safe(ws, {"event": "token", "delta": chunk, "thread_id": thread_id})

    sys_msg = SystemMessage(content=get_agent_prompt("supervisor"))
    await _send_typing_stub(ws, thread_id)

    agen = llm.astream([sys_msg] + history + [HumanMessage(content=user_input)])
    try:
        first = await asyncio.wait_for(agen.__anext__(), timeout=FIRST_TOKEN_TIMEOUT_MS / 1000.0)
    except asyncio.TimeoutError:
        try:
            if not cancelled():
                resp = await llm.ainvoke([sys_msg] + history + [HumanMessage(content=user_input)])
                text = getattr(resp, "content", "") or ""
            else:
                text = ""
        except Exception:
            text = ""
        try:
            await agen.aclose()
        except Exception:
            pass
        if text and not cancelled():
            await _send_json_safe(ws, {"event": "token", "delta": text, "thread_id": thread_id})
            try:
                stm_write_message(thread_id=thread_id, role="assistant", content=text)
            except Exception:
                pass
        if EMIT_FINAL_TEXT and not cancelled():
            await _send_json_safe(ws, {"event": "final", "text": text, "thread_id": thread_id})
        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
        return
    except Exception:
        try:
            await agen.aclose()
        except Exception:
            pass
        return

    if cancelled():
        try:
            await agen.aclose()
        except Exception:
            pass
        return

    txt = (_piece_from_llm_chunk(first) or "")
    if txt and not cancelled():
        for seg in _micro_chunks(txt):
            buf.append(seg)
            await flush()

    try:
        async for chunk in agen:
            if cancelled():
                break
            for piece in _iter_text_from_chunk(chunk):
                if not piece or cancelled():
                    continue
                for seg in _micro_chunks(piece):
                    buf.append(seg)
                    enough = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                    natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                    too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                    if enough or natural or too_old:
                        await flush()
        await flush()
    finally:
        try:
            await agen.aclose()
        except Exception:
            pass

    if cancelled():
        return

    final_text = ("".join(accum)).strip()
    if final_text:
        try:
            stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
        except Exception:
            pass
    if EMIT_FINAL_TEXT:
        await _send_json_safe(ws, {"event": "final", "text": final_text, "thread_id": thread_id})
    await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})


async def _stream_supervised(
    ws: WebSocket,
    *,
    app,
    user_input: str,
    thread_id: str,
    params_patch: Optional[Dict] = None,
    builder_name: str | None = None,
) -> None:
    def cancelled() -> bool:
        flags = getattr(ws.app.state, "ws_cancel_flags", {})
        return bool(flags.get(thread_id))

    if cancelled():
        return

    try:
        _ensure_graph(app, builder_name=builder_name)
    except Exception as e:
        if EMIT_FINAL_TEXT and not cancelled():
            await _send_json_safe(ws, {"event": "final", "text": "", "thread_id": thread_id, "error": f"graph_build_failed: {e!r}"})
        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
        return

    g_async = getattr(app.state, "graph_async", None)
    g_sync = getattr(app.state, "graph_sync", None)

    _log("graph_ready", builder=GRAPH_BUILDER, has_async=bool(g_async), has_sync=bool(g_sync))

    history = stm_read_history(thread_id, limit=80)
    sys_msg = SystemMessage(content=get_agent_prompt("supervisor"))

    base_msgs: List[Any] = [sys_msg] + history
    if user_input:
        base_msgs.append(HumanMessage(content=user_input))

    initial: Dict[str, Any] = {
        "messages": base_msgs,
        "chat_id": thread_id,
        "input": user_input,
    }
    if isinstance(params_patch, dict) and params_patch:
        initial["params"] = params_patch

    cfg = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": getattr(app.state, "checkpoint_ns", None),
        }
    }

    loop = asyncio.get_event_loop()
    buf: List[str] = []
    last_flush = [loop.time()]
    streamed_any = False
    final_tail: str = ""
    accum: List[str] = []

    async def flush() -> None:
        nonlocal streamed_any
        if not buf or cancelled():
            return
        chunk = "".join(buf)
        buf.clear()
        last_flush[0] = loop.time()
        streamed_any = True
        accum.append(chunk)
        if not await _send_json_safe(ws, {"event": "token", "delta": chunk, "thread_id": thread_id}):
            raise WebSocketDisconnect()

    def _emit_ui_event_if_any(ev_data: Any) -> bool:
        if not isinstance(ev_data, dict):
            return False
        ui_ev = ev_data.get("ui_event")
        if isinstance(ui_ev, dict):
            payload = {**ui_ev, "event": "ui_action", "thread_id": thread_id}
            _log("emit_ui_event", payload=payload)
            return asyncio.create_task(_send_json_safe(ws, payload)) is not None
        for key in ("output", "state", "final_state", "result"):
            sub = ev_data.get(key)
            if isinstance(sub, dict) and isinstance(sub.get("ui_event"), dict):
                u = {**sub["ui_event"], "event": "ui_action", "thread_id": thread_id}
                _log("emit_ui_event_nested", payload=u)
                return asyncio.create_task(_send_json_safe(ws, u)) is not None
        return False

    def _maybe_emit_ask_missing_fallback(ev_data: Any) -> bool:
        try:
            meta = (ev_data or {}).get("metadata") or {}
            node = str(meta.get("langgraph_node") or meta.get("node") or "").lower()
        except Exception:
            node = ""
        out = (ev_data or {}).get("output") or ev_data or {}
        phase = str(out.get("phase") or "").lower()
        if node == "ask_missing" or phase == "ask_missing":
            payload = {
                "event": "ui_action",
                "ui_action": "open_form",
                "thread_id": thread_id,
                "source": "ws_fallback",
            }
            _log("emit_ui_event_fallback", node=node, phase=phase, payload=payload)
            asyncio.create_task(_send_json_safe(ws, payload))
            return True
        return False

    def _try_stream_text_from_node(data: Any) -> None:
        texts = _extract_texts(data)
        if not texts:
            return
        joined = "\n".join([t for t in texts if isinstance(t, str)])
        for seg in _micro_chunks(joined):
            buf.append(seg)

    await _send_typing_stub(ws, thread_id)

    async def _run_stream(version: str) -> None:
        nonlocal final_tail
        if g_async is None:
            return
        astream_method = getattr(g_async, "astream_events", None)
        if not callable(astream_method):
            return
        astream = call_with_supported_kwargs(
            astream_method,
            initial,
            config=cfg,
            version=version,
        )
        async for ev in astream:  # type: ignore[misc]
            if cancelled():
                return
            ev_name = ev.get("event") if isinstance(ev, dict) else None
            data = ev.get("data") if isinstance(ev, dict) else None
            meta = ev.get("metadata") if isinstance(ev, dict) else None
            node_name = ""
            try:
                if isinstance(meta, dict):
                    node_name = str(meta.get("langgraph_node") or meta.get("node") or "")
            except Exception:
                node_name = ""

            if DEBUG_EVENTS and ev_name in ("on_node_start", "on_node_end"):
                _log("node_event", event=ev_name, node=node_name)

            if isinstance(data, dict) and str(data.get("type") or "").lower() == "stream_text":
                text_piece = data.get("text")
                if isinstance(text_piece, str) and text_piece:
                    for seg in _micro_chunks(text_piece):
                        buf.append(seg)
                        enough = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                        natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                        too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                        if enough or natural or too_old:
                            await flush()
                    await flush()
                continue

            if ev_name in ("on_chat_model_stream", "on_llm_stream") and _is_relevant_node(ev):
                chunk = (data or {}).get("chunk") if isinstance(data, dict) else None
                if chunk:
                    for piece in _iter_text_from_chunk(chunk):
                        if not piece or cancelled():
                            continue
                        for seg in _micro_chunks(piece):
                            buf.append(seg)
                            enough = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                            natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                            too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                            if enough or natural or too_old:
                                await flush()

            if ev_name in ("on_node_end",):
                if isinstance(data, dict):
                    _try_stream_text_from_node(data.get("output") or data)
                await flush()
                emitted = _emit_ui_event_if_any(data)
                if not emitted:
                    _maybe_emit_ask_missing_fallback(data)

            if ev_name in ("on_chain_end", "on_graph_end"):
                if isinstance(data, dict):
                    _emit_ui_event_if_any(data)
                    final_tail = _last_ai_text_from_result_like(data) or final_tail

        await flush()

    timed_out = False
    if FORCE_SYNC_FALLBACK:
        timed_out = True
    elif g_async is not None and not cancelled():
        try:
            await asyncio.wait_for(_run_stream("v2"), timeout=WS_EVENT_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            timed_out = True
        except Exception:
            try:
                await asyncio.wait_for(_run_stream("v1"), timeout=WS_EVENT_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                timed_out = True
            except Exception:
                pass

    if cancelled():
        return

    assistant_text: str = ""
    if final_tail:
        if not streamed_any:
            accum.append(final_tail)
        assistant_text = final_tail
    elif (not streamed_any) or timed_out:
        try:
            result: Any = None
            if g_sync is not None:
                def _run_sync() -> Any:
                    return call_with_supported_kwargs(g_sync.invoke, initial, config=cfg)

                result = await asyncio.get_event_loop().run_in_executor(None, _run_sync)
            elif g_async is not None:
                result = await call_with_supported_kwargs(g_async.ainvoke, initial, config=cfg)  # type: ignore[arg-type]

            if isinstance(result, dict):
                emitted = _emit_ui_event_if_any(result)
                if not emitted:
                    _maybe_emit_ask_missing_fallback(result)

            final_text = _last_ai_text_from_result_like(result or {}) or ""
            assistant_text = final_text
            if final_text:
                accum.append(final_text)
        except Exception:
            assistant_text = ""
        if not assistant_text:
            try:
                llm = getattr(app.state, "llm", make_llm(streaming=False))
                resp = await llm.ainvoke(
                    [SystemMessage(content=get_agent_prompt("supervisor"))] + history + [HumanMessage(content=user_input)]
                )
                assistant_text = (getattr(resp, "content", "") or "").strip()
            except Exception:
                assistant_text = ""
    else:
        assistant_text = "".join(accum)

    if cancelled():
        return

    final_text = (assistant_text or "".join(accum)).strip()

    already = "".join(accum).strip()
    if final_text and (not already or already != final_text):
        if not await _send_json_safe(ws, {"event": "token", "delta": final_text, "thread_id": thread_id}):
            return

    try:
        if final_text:
            stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
    except Exception:
        pass

    if EMIT_FINAL_TEXT:
        await _send_json_safe(ws, {"event": "final", "text": final_text, "thread_id": thread_id})
    await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})


@router.websocket("/ai/ws")
async def ws_chat(ws: WebSocket) -> None:
    # One‑time tolerant handshake including subprotocol negotiation
    await ws.accept(subprotocol=_choose_subprotocol(ws))
    """
    Robust handshake & tolerant auth:
    """

    # Soft‑Auth (Keycloak optional); on failure close connection
    user_payload: Dict[str, Any] = {}
    try:
        # Validate origin and token via guard_websocket
        user_payload = await guard_websocket(ws)
    except Exception:
        # no valid token → close and return
        await _send_json_safe(ws, {"event": "error", "message": "unauthorized"})
        await ws.close(code=1008)
        return

    try:
        ws.scope["user"] = user_payload
    except Exception:
        pass

    # Lazy init shared state
    app = ws.app
    if not getattr(app.state, "llm", None):
        app.state.llm = make_llm(streaming=True)
    try:
        ltm.prewarm_ltm()
    except Exception:
        pass
    if not hasattr(app.state, "ws_cancel_flags"):
        app.state.ws_cancel_flags = {}

    try:
        while True:
            # Heartbeat / idle detection
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=IDLE_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                await _send_json_safe(ws, {"event": "idle", "ts": int(asyncio.get_event_loop().time())})
                continue

            # Logging / short preview of raw message
            try:
                short = raw if len(raw) < 256 else raw[:252] + "...}"
                _log("RX_raw", raw=short)
            except Exception:
                pass

            if isinstance(raw, str) and WS_INPUT_MAX_CHARS > 0 and len(raw) > (WS_INPUT_MAX_CHARS * 2):
                await _send_json_safe(ws, {
                    "event": "error",
                    "code": "input_oversize",
                    "message": f"payload too large (>{WS_INPUT_MAX_CHARS * 2} chars)",
                })
                await _send_json_safe(ws, {"event": "done", "thread_id": "ws"})
                continue

            try:
                data = json.loads(raw)
            except Exception:
                await _send_json_safe(ws, {"event": "error", "message": "invalid_json"})
                continue

            # Control messages
            typ = (data.get("type") or "").strip().lower()
            if typ == "ping":
                await _send_json_safe(ws, {"event": "pong", "ts": data.get("ts")})
                continue
            if typ == "cancel":
                tid = (data.get("thread_id") or f"api:{(data.get('chat_id') or 'default').strip()}").strip()
                ws.app.state.ws_cancel_flags[tid] = True
                await _send_json_safe(ws, {"event": "done", "thread_id": tid})
                continue

            # Context / limits
            chat_id = (data.get("chat_id") or "").strip() or "default"
            thread_id = f"api:{chat_id}"
            payload = ws.scope.get("user") or {}
            user_id = str(payload.get("sub") or payload.get("email") or chat_id)

            rl = _get_rl_redis(app)
            if rl and WS_RATE_LIMIT_PER_MIN > 0:
                key = f"ws:ratelimit:{user_id}:{chat_id}"
                try:
                    cur = rl.incr(key)
                    if cur == 1:
                        rl.expire(key, 60)
                    if cur > WS_RATE_LIMIT_PER_MIN:
                        await _send_json_safe(ws, {
                            "event": "error",
                            "code": "rate_limited",
                            "message": "Too many requests, slow down.",
                            "retry_after_sec": int(rl.ttl(key) or 60),
                        })
                        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                        continue
                except Exception:
                    pass

            params_patch = data.get("params") or data.get("params_patch")
            if not isinstance(params_patch, dict):
                params_patch = None

            user_input = (data.get("input") or data.get("text") or data.get("query") or "").strip()
            if user_input and WS_INPUT_MAX_CHARS > 0 and len(user_input) > WS_INPUT_MAX_CHARS:
                await _send_json_safe(ws, {
                    "event": "error",
                    "code": "input_too_long",
                    "message": f"input exceeds {WS_INPUT_MAX_CHARS} chars",
                })
                await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                continue

            if not user_input and not params_patch:
                await _send_json_safe(ws, {"event": "error", "message": "missing_input", "thread_id": thread_id})
                continue

            try:
                app.state.ws_cancel_flags.pop(thread_id, None)
            except Exception:
                pass

            if user_input:
                try:
                    stm_write_message(thread_id=thread_id, role="user", content=user_input)
                except Exception:
                    pass

            # Short command "remember ..."
            m = REMEMBER_RX.match(user_input or "")
            if m:
                note = m.group(1).strip()
                ok = False
                try:
                    _ = ltm.upsert_memory(user=thread_id, chat_id=thread_id, text=note, kind="note")
                    ok = True
                except Exception:
                    ok = False
                msg = "✅ Gespeichert." if ok else "⚠️ Konnte nicht speichern."
                await _send_json_safe(ws, {"event": "token", "delta": msg, "thread_id": thread_id})
                await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                try:
                    stm_write_message(thread_id=thread_id, role="assistant", content=msg)
                except Exception:
                    pass
                continue

            # Trivial greetings → direct LLM stream
            if user_input and not params_patch and GREETING_RX.match(user_input):
                llm = getattr(app.state, "llm", make_llm(streaming=True))
                await _stream_llm_direct(ws, llm, user_input=user_input, thread_id=thread_id)
                try:
                    app.state.ws_cancel_flags.pop(thread_id, None)
                except Exception:
                    pass
                continue

            # Start event + routing
            mode = (data.get("mode") or os.getenv("WS_MODE", "graph")).strip().lower()
            graph_name = (data.get("graph") or os.getenv("GRAPH_BUILDER", "supervisor")).strip().lower()
            await _send_json_safe(ws, {"event": "start", "thread_id": thread_id, "route": mode, "graph": graph_name})

            # Execute stream
            if mode == "llm":
                llm = getattr(app.state, "llm", make_llm(streaming=True))
                await _stream_llm_direct(ws, llm, user_input=(user_input or ""), thread_id=thread_id)
            else:
                effective_input = user_input if user_input else ""
                _log("route", mode=mode, graph=graph_name, thread_id=thread_id, params_present=bool(params_patch), input_len=len(user_input))
                await _stream_supervised(
                    ws,
                    app=app,
                    user_input=effective_input,
                    thread_id=thread_id,
                    params_patch=params_patch,
                    builder_name=graph_name,
                )

            try:
                app.state.ws_cancel_flags.pop(thread_id, None)
            except Exception:
                pass

    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            print(f"[ws_chat] error: {e!r}")
        except Exception:
            pass
        await _send_json_safe(ws, {"event": "done", "thread_id": "ws"})
