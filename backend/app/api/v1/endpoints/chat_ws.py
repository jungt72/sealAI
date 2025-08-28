from __future__ import annotations
import os, re, json, asyncio
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages.ai import AIMessageChunk

from app.services.llm.llm_factory import get_llm as make_llm
from app.services.langgraph.graph.intent_router import classify_intent
from app.services.langgraph.redis_lifespan import get_redis_checkpointer
from redis import Redis

router = APIRouter()

# ─────────────────────────────────────────────────────────────
# Redis STM
# ─────────────────────────────────────────────────────────────
def _redis() -> Redis:
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return Redis.from_url(url, decode_responses=True)

def _conv_key(thread_id: str) -> str:
    return f"chat:stm:{thread_id}:messages"

def write_memory_message(*, thread_id: str, role: str, content: str) -> None:
    if not content:
        return
    r = _redis()
    key = _conv_key(thread_id)
    item = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.lpush(key, item)
    pipe.ltrim(key, 0, int(os.getenv("STM_MAX_ITEMS", "200")) - 1)
    pipe.expire(key, int(os.getenv("STM_TTL_SEC", "604800")))
    pipe.execute()

def read_memory_messages(thread_id: str) -> List[SystemMessage | HumanMessage | AIMessage]:
    try:
        raw = _redis().lrange(_conv_key(thread_id), 0, int(os.getenv("STM_MAX_ITEMS", "200")) - 1)
    except Exception:
        return []
    out: List[SystemMessage | HumanMessage | AIMessage] = []
    for s in reversed(raw):  # oldest first
        try:
            obj = json.loads(s)
            role = (obj.get("role") or "").strip().lower()
            content = obj.get("content") or ""
            if role == "user":
                out.append(HumanMessage(content=content))
            elif role in ("assistant", "ai", "model"):
                out.append(AIMessage(content=content))
            elif role == "system":
                out.append(SystemMessage(content=content))
        except Exception:
            continue
    return out

# ─────────────────────────────────────────────────────────────
# Streaming tuning
# ─────────────────────────────────────────────────────────────
COALESCE_MIN_CHARS = int(os.getenv("WS_COALESCE_MIN_CHARS", "24"))
COALESCE_MAX_LAT_MS = float(os.getenv("WS_COALESCE_MAX_LAT_MS", "60"))
IDLE_TIMEOUT_SEC = int(os.getenv("WS_IDLE_TIMEOUT_SEC", "20"))
FIRST_TOKEN_TIMEOUT_MS = int(os.getenv("WS_FIRST_TOKEN_TIMEOUT_MS", "900"))
FLUSH_ENDINGS: Tuple[str, ...] = (". ", "? ", "! ", "\n\n", ":", ";", "…", ", ", ") ", "] ", " }")

def _env_stream_nodes() -> set[str]:
    raw = os.getenv("WS_STREAM_NODES", "*").strip()
    if not raw or raw in {"*", "all"}:
        return {"*"}
    return {x.strip().lower() for x in raw.split(",") if x.strip()}

STREAM_NODES = _env_stream_nodes()

# ─────────────────────────────────────────────────────────────
# Chunk helpers
# ─────────────────────────────────────────────────────────────
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

def _is_relevant_node(ev: Dict) -> bool:
    if "*" in STREAM_NODES or "all" in STREAM_NODES:
        return True
    meta = ev.get("metadata") or {}
    run  = ev.get("run") or {}
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

# expliziter Triggertext für Consult
CONSULT_RX = re.compile(r"\b(optimal\w*\s+(dichtung|empfehlung|lösung|auswahl)|optimale\s+dichtungsempfehlung|rwdr|wellendichtring|25x\d+x\d+)\b", re.I)

# ─────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────
def _ensure_graph(app) -> None:
    if getattr(app.state, "graph_async", None) is not None or getattr(app.state, "graph_sync", None) is not None:
        return
    from app.services.langgraph.graph.consult.build import build_consult_graph
    saver = None
    try:
        saver = get_redis_checkpointer(app)
    except Exception:
        saver = None
    g = build_consult_graph()
    try:
        compiled = g.compile(checkpointer=saver) if saver else g.compile()
    except Exception:
        compiled = g.compile()
    app.state.graph_async = compiled
    app.state.graph_sync = compiled

# ─────────────────────────────────────────────────────────────
# WS utils
# ─────────────────────────────────────────────────────────────
from fastapi import WebSocket
def _choose_subprotocol(ws: WebSocket) -> Optional[str]:
    raw = ws.headers.get("sec-websocket-protocol")
    if not raw:
        return None
    return raw.split(",")[0].strip() or None

# ─────────────────────────────────────────────────────────────
# WebSocket endpoint
# ─────────────────────────────────────────────────────────────
@router.websocket("/ai/ws")
async def ws_chat(ws: WebSocket):
    await ws.accept(subprotocol=_choose_subprotocol(ws))

    app = ws.app
    llm = getattr(app.state, "llm", None) or make_llm(streaming=True)

    async def stream_llm(user_input: str, thread_id: str):
        history = read_memory_messages(thread_id)
        loop = asyncio.get_event_loop()
        buf: List[str] = []
        accum: List[str] = []
        last_flush = [loop.time()]

        async def flush():
            if not buf:
                return
            chunk = "".join(buf)
            buf.clear()
            last_flush[0] = loop.time()
            accum.append(chunk)
            await ws.send_json({"delta": chunk, "thread_id": thread_id})

        async def _idle_guard():
            await asyncio.sleep(IDLE_TIMEOUT_SEC)
            raise asyncio.TimeoutError("idle timeout")

        agen = llm.astream(history + [HumanMessage(content=user_input)])
        try:
            first = await asyncio.wait_for(agen.__anext__(), timeout=FIRST_TOKEN_TIMEOUT_MS / 1000.0)
        except Exception:
            try:
                await agen.aclose()
            except Exception:
                pass
            await ws.send_json({"final": {"text": ""}, "thread_id": thread_id})
            await ws.send_json({"event": "done", "thread_id": thread_id})
            return

        p = _piece_from_llm_chunk(first)
        if p:
            buf.append(p)
            await flush()

        guard = asyncio.create_task(_idle_guard())
        try:
            async for chunk in agen:
                piece = _piece_from_llm_chunk(chunk)
                if not piece:
                    continue
                buf.append(piece)
                if guard.done():
                    break
                guard.cancel()
                guard = asyncio.create_task(_idle_guard())

                enough = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                if enough or natural or too_old:
                    await flush()
            await flush()
        finally:
            guard.cancel()
            try:
                await agen.aclose()
            except Exception:
                pass

        final_text = "".join(accum).strip()
        try:
            if final_text:
                write_memory_message(thread_id=thread_id, role="assistant", content=final_text)
        except Exception:
            pass

        await ws.send_json({"final": {"text": final_text}, "thread_id": thread_id})
        await ws.send_json({"event": "done", "thread_id": thread_id})

    async def stream_graph(user_input: str, thread_id: str):
        try:
            _ensure_graph(app)
        except Exception as e:
            await ws.send_json({"error": f"graph_build_failed: {e!r}", "thread_id": thread_id})
            await ws.send_json({"final": {"text": ""}, "thread_id": thread_id})
            await ws.send_json({"event": "done", "thread_id": thread_id})
            return

        g_async = getattr(app.state, "graph_async", None)
        g_sync = getattr(app.state, "graph_sync", None)

        history = read_memory_messages(thread_id)
        initial = {
            "messages": history + [HumanMessage(content=user_input)],
            "chat_id": thread_id,
            "input": user_input,
        }
        cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": getattr(app.state, "checkpoint_ns", None)}}

        loop = asyncio.get_event_loop()
        buf: List[str] = []
        last_flush = [loop.time()]
        streamed_any = False
        final_tail: str = ""
        accum: List[str] = []

        async def flush():
            nonlocal streamed_any
            if not buf:
                return
            chunk = "".join(buf)
            buf.clear()
            last_flush[0] = loop.time()
            streamed_any = True
            accum.append(chunk)
            await ws.send_json({"delta": chunk, "thread_id": thread_id})

        if g_async is not None:
            for ver in ("v2", "v1"):
                try:
                    async for ev in g_async.astream_events(initial, config=cfg, version=ver):
                        ev_name = ev.get("event")
                        if ev_name in ("on_chat_model_stream", "on_llm_stream") and _is_relevant_node(ev):
                            chunk = (ev.get("data") or {}).get("chunk")
                            if not chunk:
                                continue
                            for piece in _iter_text_from_chunk(chunk):
                                if not piece:
                                    continue
                                buf.append(piece)
                                enough = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                                natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                                too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                                if enough or natural or too_old:
                                    await flush()
                        if ev_name in ("on_chain_end", "on_graph_end"):
                            data = ev.get("data") or {}
                            output = data.get("output") or data.get("state") or data.get("final_state") or {}
                            t = _last_ai_text_from_result_like(output) or ""
                            if t:
                                final_tail = t
                    await flush()
                    break
                except Exception:
                    continue

        if final_tail:
            if not streamed_any:
                accum.append(final_tail)
                await ws.send_json({"delta": final_tail, "thread_id": thread_id})
            assistant_text = final_tail
        elif not streamed_any:
            try:
                if g_sync is not None:
                    def _run_sync():
                        return g_sync.invoke(initial, config=cfg)
                    result = await loop.run_in_executor(None, _run_sync)
                else:
                    result = await g_async.ainvoke(initial, config=cfg)  # type: ignore
                final_text = _last_ai_text_from_result_like(result) or ""
                assistant_text = final_text
                if final_text:
                    accum.append(final_text)
                    await ws.send_json({"delta": final_text, "thread_id": thread_id})
            except Exception as e:
                await ws.send_json({"error": f"fallback_failed: {e!r}", "thread_id": thread_id})
                assistant_text = ""
        else:
            assistant_text = "".join(accum)

        final_text = (assistant_text or "".join(accum)).strip()
        try:
            if final_text:
                write_memory_message(thread_id=thread_id, role="assistant", content=final_text)
        except Exception:
            pass

        await ws.send_json({"final": {"text": final_text}, "thread_id": thread_id})
        await ws.send_json({"event": "done", "thread_id": thread_id})

    # Main loop
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                await ws.send_json({"error": "invalid_json"})
                continue

            chat_id = (data.get("chat_id") or "").strip() or "ws"
            thread_id = f"api:{chat_id}"

            user_input = (data.get("input") or data.get("text") or data.get("query") or "").strip()
            if not user_input:
                await ws.send_json({"error": "missing input", "thread_id": thread_id})
                continue

            force_consult = bool(data.get("force_consult"))
            try:
                write_memory_message(thread_id=thread_id, role="user", content=user_input)
            except Exception:
                pass

            if force_consult or CONSULT_RX.search(user_input):
                route = "consult"; reason = "force|regex" if force_consult else "regex"
            else:
                if len(user_input.split()) <= 3:
                    route, reason = "chitchat", "short_utterance"
                elif re.search(r"^(hi|hallo|hey|guten\s+tag|moin)\b", user_input, re.I):
                    route, reason = "chitchat", "greeting"
                else:
                    try:
                        intent = classify_intent(llm, [HumanMessage(content=user_input)])
                        route = "consult" if intent == "consult" else "chitchat"
                        reason = "router"
                    except Exception:
                        route = "consult"; reason = "router_fail"

            await ws.send_json({"phase": "starting", "thread_id": chat_id, "route_guess": route, "reason": reason})

            if route == "consult":
                await stream_graph(user_input, thread_id)
            else:
                await stream_llm(user_input, thread_id)

    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_json({"error": f"ws_internal_error: {e!r}"})
            await ws.send_json({"final": {"text": ""}})
            await ws.send_json({"event": "done", "thread_id": "ws"})
        except Exception:
            pass
