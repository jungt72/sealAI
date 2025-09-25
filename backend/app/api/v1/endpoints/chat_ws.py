# backend/app/api/v1/endpoints/chat_ws.py
# backend/app/api/v1/endpoints/chat_ws.py
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

from app.api.v1.dependencies.auth import guard_websocket  # ⬅️ Token & Origin prüfen
from app.services.langgraph.llm_factory import get_llm as make_llm
from app.services.langgraph.redis_lifespan import get_redis_checkpointer
from app.services.langgraph.prompt_registry import get_agent_prompt
from langchain_core.language_models.chat_models import BaseChatModel

from app.services.langgraph.graph.consult.memory_utils import (
    read_history as stm_read_history,
    write_message as stm_write_message,
)

from app.services.langgraph.tools import long_term_memory as ltm

router = APIRouter()

COALESCE_MIN_CHARS      = int(os.getenv("WS_COALESCE_MIN_CHARS", "24"))
COALESCE_MAX_LAT_MS     = float(os.getenv("WS_COALESCE_MAX_LAT_MS", "60"))
IDLE_TIMEOUT_SEC        = int(os.getenv("WS_IDLE_TIMEOUT_SEC", "20"))
FIRST_TOKEN_TIMEOUT_MS  = int(os.getenv("WS_FIRST_TOKEN_TIMEOUT_MS", "5000"))
WS_INPUT_MAX_CHARS      = int(os.getenv("WS_INPUT_MAX_CHARS", "4000"))
WS_RATE_LIMIT_PER_MIN   = int(os.getenv("WS_RATE_LIMIT_PER_MIN", "30"))
MICRO_CHUNK_CHARS       = int(os.getenv("WS_MICRO_CHUNK_CHARS", "0"))
EMIT_FINAL_TEXT         = os.getenv("WS_EMIT_FINAL_TEXT", "0") == "1"
DEBUG_EVENTS            = os.getenv("WS_DEBUG_EVENTS", "1") == "1"
DEFAULT_ROUTE           = os.getenv("WS_DEFAULT_ROUTE", "supervisor").strip().lower()

FLUSH_ENDINGS: Tuple[str, ...] = (". ", "? ", "! ", "\n\n", ":", ";", "…", ", ", ") ", "] ", " }")

def _env_stream_nodes() -> set[str]:
    raw = os.getenv("WS_STREAM_NODES", "*").strip()
    if not raw or raw in {"*", "all"}:
        return {"*"}
    return {x.strip().lower() for x in raw.split(",") if x.strip()}

STREAM_NODES = _env_stream_nodes()

def _truthy(v: Optional[str]) -> bool:
    if v is None: return False
    v = str(v).strip().strip('\'"').lower()
    return v in ("1","true","yes","on")

def _get_rl_redis(app) -> Optional[redis.Redis]:
    # singleton redis client für Rate-Limit
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
            yield c; return
        d = chunk.get("delta")
        if isinstance(d, str) and d:
            yield d; return
    content = getattr(chunk, "content", None)
    if isinstance(content, str) and content:
        yield content; return
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

_BOUNDARY_RX = re.compile(r"[ \n\t.,;:!?…)\]}]")

def _micro_chunks(s: str) -> Iterable[str]:
    n = MICRO_CHUNK_CHARS
    if n <= 0 or len(s) <= n:
        yield s; return
    i = 0; L = len(s)
    while i < L:
        j = min(i + n, L); k = j
        if j < L:
            m = _BOUNDARY_RX.search(s, j, min(L, j + 40))
            if m: k = m.end()
        yield s[i:k]; i = k

def _is_relevant_node(ev: Dict) -> bool:
    if "*" in STREAM_NODES or "all" in STREAM_NODES:
        return True
    meta = ev.get("metadata") or {}; run  = ev.get("run") or {}
    node = str(meta.get("langgraph_node") or "").lower()
    run_name = str(run.get("name") or meta.get("run_name") or "").lower()
    return (node in STREAM_NODES) or (run_name in STREAM_NODES)

def _last_ai_text_from_result_like(obj: Dict[str, Any]) -> str:
    if not isinstance(obj, dict):
        return ""
    msgs = obj.get("messages")
    if isinstance(msgs, list):
        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                c = getattr(m, "content", "")
                if isinstance(c, str) and c:
                    return c.strip()
    resp = obj.get("response")
    if isinstance(resp, str) and resp.strip():
        return resp.strip()
    for key in ("output", "state", "final_state"):
        sub = obj.get(key)
        if isinstance(sub, dict):
            t = _last_ai_text_from_result_like(sub)
            if t:
                return t
    return ""

# --- Heuristik: RWDR-/Maß-Erkennung toleranter; erlaubt x, ×, / und optionalen Bindestrich vor der letzten Zahl
CONSULT_RX  = re.compile(
    r"\b(rwdr|wellendichtring|bauform\s*[A-Z0-9]{1,4}|\d{1,3}\s*[x×/]\s*\d{1,3}\s*[x×/\-]?\s*\d{1,3})\b",
    re.I
)
GREETING_RX = re.compile(r"^(hi|hallo|hey|guten\s+tag|moin|servus)\b", re.I)
REMEMBER_RX = re.compile(r"^\s*(?:!remember|remember|merke(?:\s*dir)?|speicher(?:e)?)\s*[:\-]?\s*(.+)$", re.I)

def _is_greeting_only(text: str) -> bool:
    """Nur reiner Gruß (z. B. 'Hallo', 'Moin!'). Gruß + Fachinhalt zählt NICHT als reiner Gruß."""
    t = (text or "").strip()
    m = GREETING_RX.match(t)
    if not m:
        return False
    rest = t[m.end():].strip(" .,!?:;—–-")
    return rest == ""

GRAPH_BUILDER = os.getenv("GRAPH_BUILDER", "supervisor").lower()

def _ensure_graph(app) -> None:
    if getattr(app.state, "graph_async", None) is not None or getattr(app.state, "graph_sync", None) is not None:
        return
    if GRAPH_BUILDER == "supervisor":
        from app.services.langgraph.supervisor_graph import build_supervisor_graph as build_graph
    else:
        from app.services.langgraph.graph.consult.build import build_consult_graph as build_graph
    saver = None
    try:
        saver = get_redis_checkpointer(app)
    except Exception:
        saver = None
    def _force_streaming_on_llms(obj) -> None:
        """Ensure every BaseChatModel in the graph streams tokens."""
        seen: set[int] = set()
        stack = [obj]
        while stack:
            cur = stack.pop()
            if not cur:
                continue
            ident = id(cur)
            if ident in seen:
                continue
            seen.add(ident)

            if isinstance(cur, BaseChatModel):
                for attr in ("stream", "streaming", "_stream", "_streaming"):
                    if hasattr(cur, attr):
                        try:
                            setattr(cur, attr, True)
                        except Exception:
                            pass

            if isinstance(cur, dict):
                stack.extend(cur.values())
            elif isinstance(cur, (list, tuple, set)):
                stack.extend(cur)
            else:
                for value in getattr(cur, "__dict__", {}).values():
                    if isinstance(value, (dict, list, tuple, set)) or hasattr(value, "__dict__"):
                        stack.append(value)

    build_kwargs = {}
    shared_llm = getattr(app.state, "llm", None)
    if isinstance(shared_llm, BaseChatModel):
        build_kwargs.setdefault("llm", shared_llm)

    def _invoke_builder(**extra):
        try:
            return build_graph(**extra)
        except TypeError:
            return build_graph()

    g = None
    try:
        if build_kwargs:
            g = _invoke_builder(**build_kwargs)
        else:
            g = _invoke_builder(streaming=True)
    except Exception:
        g = build_graph()

    _force_streaming_on_llms(g)
    try:
        compiled = g.compile(checkpointer=saver) if saver else g.compile()
    except Exception:
        compiled = g.compile()
    app.state.graph_async = compiled
    app.state.graph_sync  = compiled

def _choose_subprotocol(ws: WebSocket) -> Optional[str]:
    raw = ws.headers.get("sec-websocket-protocol")
    if not raw:
        return None
    return raw.split(",")[0].strip() or None

async def _send_json_safe(ws: WebSocket, payload: Dict) -> bool:
    try:
        await ws.send_json(payload); return True
    except WebSocketDisconnect:
        return False
    except Exception:
        return False

async def _stream_llm_direct(ws: WebSocket, llm, *, user_input: str, thread_id: str):
    """LLM-Direktmodus – jetzt IMMER mit Supervisor-Systemprompt als erste Message."""
    def cancelled() -> bool:
        flags = getattr(ws.app.state, "ws_cancel_flags", {})
        return bool(flags.get(thread_id))

    history = stm_read_history(thread_id, limit=80)
    if cancelled():
        return

    loop = asyncio.get_event_loop()
    buf: List[str] = []; accum: List[str] = []; last_flush = [loop.time()]

    async def flush():
        if not buf or cancelled():
            return
        chunk = "".join(buf); buf.clear(); last_flush[0] = loop.time()
        accum.append(chunk)
        await _send_json_safe(ws, {"event": "token", "delta": chunk, "thread_id": thread_id})

    sys_msg = SystemMessage(content=get_agent_prompt("supervisor"))

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
        try: await agen.aclose()
        except Exception: pass
        if text and not cancelled():
            await _send_json_safe(ws, {"event": "token", "delta": text, "thread_id": thread_id})
            try: stm_write_message(thread_id=thread_id, role="assistant", content=text)
            except Exception: pass
        if EMIT_FINAL_TEXT and not cancelled():
            await _send_json_safe(ws, {"event": "final", "text": text, "thread_id": thread_id})
        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
        return
    except Exception:
        try: await agen.aclose()
        except Exception: pass
        return

    if cancelled():
        try: await agen.aclose()
        except Exception: pass
        return

    txt = (_piece_from_llm_chunk(first) or "")
    if txt and not cancelled():
        for seg in _micro_chunks(txt):
            buf.append(seg); await flush()

    try:
        async for chunk in agen:
            if cancelled(): break
            for piece in _iter_text_from_chunk(chunk):
                if not piece or cancelled(): continue
                for seg in _micro_chunks(piece):
                    buf.append(seg)
                    enough  = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                    natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                    too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                    if enough or natural or too_old:
                        await flush()
        await flush()
    finally:
        try: await agen.aclose()
        except Exception: pass

    if cancelled():
        return

    final_text = ("".join(accum)).strip()
    if final_text:
        try: stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
        except Exception: pass
    if EMIT_FINAL_TEXT:
        await _send_json_safe(ws, {"event": "final", "text": final_text, "thread_id": thread_id})
    await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})

async def _stream_supervised(ws: WebSocket, *, app, user_input: str, thread_id: str, params_patch: Optional[Dict]=None):
    def cancelled() -> bool:
        flags = getattr(ws.app.state, "ws_cancel_flags", {})
        return bool(flags.get(thread_id))

    if cancelled():
        return

    try:
        _ensure_graph(app)
    except Exception as e:
        if EMIT_FINAL_TEXT and not cancelled():
            await _send_json_safe(ws, {"event": "final", "text": "", "thread_id": thread_id, "error": f"graph_build_failed: {e!r}"})
        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
        return

    g_async = getattr(app.state, "graph_async", None)
    g_sync  = getattr(app.state, "graph_sync", None)

    history = stm_read_history(thread_id, limit=80)
    sys_msg = SystemMessage(content=get_agent_prompt("supervisor"))
    initial: Dict[str, Any] = {"messages": [sys_msg] + history + [HumanMessage(content=user_input)], "chat_id": thread_id, "input": user_input}
    if isinstance(params_patch, dict) and params_patch:
        initial["params"] = params_patch

    cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": getattr(app.state, "checkpoint_ns", None)}}

    loop = asyncio.get_event_loop()
    buf: List[str] = []; last_flush = [loop.time()]; streamed_any = False
    final_tail: str = ""; accum: List[str] = []

    async def flush():
        nonlocal streamed_any
        if not buf or cancelled(): return
        chunk = "".join(buf); buf.clear(); last_flush[0] = loop.time()
        streamed_any = True; accum.append(chunk)
        if not await _send_json_safe(ws, {"event": "token", "delta": chunk, "thread_id": thread_id}):
            raise WebSocketDisconnect()

    def _emit_ui_event_if_any(ev_data: Any) -> bool:
        if not isinstance(ev_data, dict):
            return False
        ui_ev = ev_data.get("ui_event")
        if isinstance(ui_ev, dict):
            # zusätzlich "event": "ui_action" mitsenden, damit das Frontend eindeutig routen kann
            payload = {**ui_ev, "event": "ui_action", "thread_id": thread_id}
            return asyncio.create_task(_send_json_safe(ws, payload)) is not None
        for key in ("output", "state", "final_state", "result"):
            sub = ev_data.get(key)
            if isinstance(sub, dict) and isinstance(sub.get("ui_event"), dict):
                u = {**sub["ui_event"], "event": "ui_action", "thread_id": thread_id}
                return asyncio.create_task(_send_json_safe(ws, u)) is not None
        return False

    if g_async is not None and not cancelled():
        for ver in ("v2", "v1"):
            try:
                async for ev in g_async.astream_events(initial, config=cfg, version=ver):
                    if cancelled(): return

                    if DEBUG_EVENTS:
                        await _send_json_safe(ws, {"event": "dbg", "meta": ev.get("metadata"), "name": ev.get("event")})

                    ev_name = ev.get("event") if isinstance(ev, dict) else None

                    if ev_name in ("on_chat_model_stream", "on_llm_stream") and _is_relevant_node(ev):
                        chunk = (ev.get("data") or {}).get("chunk") if isinstance(ev.get("data"), dict) else None
                        if not chunk: continue
                        for piece in _iter_text_from_chunk(chunk):
                            if not piece or cancelled(): continue
                            for seg in _micro_chunks(piece):
                                buf.append(seg)
                                enough  = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                                natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                                too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                                if enough or natural or too_old:
                                    await flush()

                    if ev_name in ("on_node_end", "on_chain_end", "on_graph_end"):
                        _emit_ui_event_if_any(ev.get("data"))

                    if ev_name in ("on_chain_end", "on_graph_end"):
                        data   = ev.get("data") or {}
                        output = data.get("output") if isinstance(data, dict) else {}
                        output = output or (data.get("state") if isinstance(data, dict) else {})
                        output = output or (data.get("final_state") if isinstance(data, dict) else {})
                        t = _last_ai_text_from_result_like(output) or ""
                        if t: final_tail = t
                await flush(); break
            except Exception:
                continue

    if cancelled():
        return

    if final_tail:
        if not streamed_any:
            accum.append(final_tail)
            if not await _send_json_safe(ws, {"event": "token", "delta": final_tail, "thread_id": thread_id}):
                return
        assistant_text = final_tail
    elif not streamed_any:
        try:
            if g_sync is not None:
                def _run_sync(): return g_sync.invoke(initial, config=cfg)
                result = await asyncio.get_event_loop().run_in_executor(None, _run_sync)
            else:
                result = await g_async.ainvoke(initial, config=cfg)  # type: ignore
            final_text = _last_ai_text_from_result_like(result) or ""
            assistant_text = final_text
            if final_text and not cancelled():
                accum.append(final_text)
                if not await _send_json_safe(ws, {"event": "token", "delta": final_text, "thread_id": thread_id}):
                    return
        except Exception:
            assistant_text = ""
    else:
        assistant_text = "".join(accum)

    if cancelled():
        return

    final_text = (assistant_text or "".join(accum)).strip()
    try:
        if final_text:
            stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
    except Exception:
        pass

    if EMIT_FINAL_TEXT:
        await _send_json_safe(ws, {"event": "final", "text": final_text, "thread_id": thread_id})
    await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})

@router.websocket("/ai/ws")
async def ws_chat(ws: WebSocket):
    # ⛔ Erst authentifizieren/origin prüfen, dann accept()
    try:
        _ = await guard_websocket(ws)
    except Exception:
        return

    await ws.accept(subprotocol=_choose_subprotocol(ws))

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
            raw = await ws.receive_text()
            # 1) Rohgrößen-Guard (DoS/Fehleingaben)
            if isinstance(raw, str) and WS_INPUT_MAX_CHARS > 0 and len(raw) > (WS_INPUT_MAX_CHARS * 2):
                await _send_json_safe(ws, {
                    "event": "error",
                    "code": "input_oversize",
                    "message": f"payload too large (>{WS_INPUT_MAX_CHARS*2} chars)",
                })
                await _send_json_safe(ws, {"event": "done", "thread_id": "ws"})
                continue
            try:
                data = json.loads(raw)
            except Exception:
                await _send_json_safe(ws, {"event": "error", "message": "invalid_json"}); continue

            typ = (data.get("type") or "").strip().lower()
            if typ == "ping":
                await _send_json_safe(ws, {"event": "pong", "ts": data.get("ts")}); continue
            if typ == "cancel":
                tid = (data.get("thread_id") or f"api:{(data.get('chat_id') or 'default').strip()}").strip()
                app.state.ws_cancel_flags[tid] = True
                await _send_json_safe(ws, {"event": "done", "thread_id": tid}); continue

            chat_id    = (data.get("chat_id") or "").strip() or "default"
            thread_id  = f"api:{chat_id}"
            payload    = ws.scope.get("user") or {}
            user_id    = str(payload.get("sub") or payload.get("email") or chat_id)

            # 2) Rate-Limit (pro User/Thread), 30 req/min Default
            rl = _get_rl_redis(app)
            if rl and WS_RATE_LIMIT_PER_MIN > 0:
                key = f"ws:ratelimit:{user_id}:{chat_id}"
                try:
                    cur = rl.incr(key)
                    if cur == 1:
                        rl.expire(key, 60)  # Fenster 60s
                    if cur > WS_RATE_LIMIT_PER_MIN:
                        await _send_json_safe(ws, {
                            "event": "error",
                            "code": "rate_limited",
                            "message": "Too many requests, slow down.",
                            "retry_after_sec": int(rl.ttl(key) or 60)
                        })
                        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                        continue
                except Exception:
                    pass

            params_patch = data.get("params") or data.get("params_patch")
            if not isinstance(params_patch, dict):
                params_patch = None

            user_input = (data.get("input") or data.get("text") or data.get("query") or "").strip()
            # 3) Input-Längen-Guard
            if user_input and WS_INPUT_MAX_CHARS > 0 and len(user_input) > WS_INPUT_MAX_CHARS:
                await _send_json_safe(ws, {
                    "event": "error",
                    "code": "input_too_long",
                    "message": f"input exceeds {WS_INPUT_MAX_CHARS} chars"
                })
                await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                continue

            if not user_input and not params_patch:
                await _send_json_safe(ws, {"event": "error", "message": "missing input", "thread_id": thread_id}); continue

            try: app.state.ws_cancel_flags.pop(thread_id, None)
            except Exception: pass

            if user_input:
                try: stm_write_message(thread_id=thread_id, role="user", content=user_input)
                except Exception: pass

            m = REMEMBER_RX.match(user_input or "")
            if m:
                note = m.group(1).strip(); ok = False
                try:
                    _ = ltm.upsert_memory(user=thread_id, chat_id=thread_id, text=note, kind="note"); ok = True
                except Exception: ok = False
                msg = "✅ Gespeichert." if ok else "⚠️ Konnte nicht speichern."
                await _send_json_safe(ws, {"event": "token", "delta": msg, "thread_id": thread_id})
                if EMIT_FINAL_TEXT:
                    await _send_json_safe(ws, {"event": "final", "text": msg, "thread_id": thread_id})
                await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                try: stm_write_message(thread_id=thread_id, role="assistant", content=msg)
                except Exception: pass
                continue

            # Routing:
            # 1) Immer Supervisor, wenn Formular-Parameter gepatcht werden
            # 2) Supervisor bei RWDR/Abmessungen im Text
            # 3) Nur Gruß -> LLM
            # 4) Sonst auf DEFAULT_ROUTE zurückfallen
            if params_patch:
                route = "supervisor"; reason = "params_patch"
            elif user_input and CONSULT_RX.search(user_input):
                route = "supervisor"; reason = "consult_rx"
            elif _is_greeting_only(user_input):
                route = "llm"; reason = "greeting_only"
            else:
                route = DEFAULT_ROUTE; reason = "fallback_default"

            await _send_json_safe(ws, {"phase": "starting", "thread_id": thread_id, "route_guess": route, "reason": reason})

            if route == "supervisor":
                await _stream_supervised(ws, app=app, user_input=(user_input or "📝 form patch"), thread_id=thread_id, params_patch=params_patch)
            else:
                await _stream_llm_direct(ws, app.state.llm, user_input=(user_input or ""), thread_id=thread_id)

            try: app.state.ws_cancel_flags.pop(thread_id, None)
            except Exception: pass

    except WebSocketDisconnect:
        return
    except Exception as e:
        if EMIT_FINAL_TEXT:
            await _send_json_safe(ws, {"event": "final", "text": "", "error": f"ws_internal_error: {e!r}"})
        await _send_json_safe(ws, {"event": "done", "thread_id": "ws"})
