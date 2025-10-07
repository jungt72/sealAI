# backend/app/api/v1/endpoints/ai.py
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field
from redis import Redis
from starlette.websockets import WebSocketState

# ─────────────────────────────────────────────────────────────
# Graph-Schnittstelle (entspricht neuem Backend-Layout)
#   → stream_consult(state) : async generator[dict]
#   → invoke_consult(state) : dict
# Passe den Importweg *hier* an dein Projekt an.
# In deinem Tree existiert `backend/app/langgraph/graph_chat.py`,
# daher importieren wir von dort.
# ─────────────────────────────────────────────────────────────
from app.langgraph.graph_chat import stream_consult, invoke_consult

log = logging.getLogger("uvicorn.error")


# ─────────────────────────────────────────────────────────────
# Redis Short-Term Memory (Small, practical memory)
# ─────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STM_PREFIX = os.getenv("STM_PREFIX", "chat:stm")
STM_TTL_SEC = int(os.getenv("STM_TTL_SEC", "604800"))  # 7 Tage
WS_AUTH_OPTIONAL = os.getenv("WS_AUTH_OPTIONAL", "1") == "1"


def _stm_key(thread_id: str) -> str:
    return f"{STM_PREFIX}:{thread_id}"


def _redis() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def _stm_set(thread_id: str, key: str, value: str) -> None:
    r = _redis()
    skey = _stm_key(thread_id)
    r.hset(skey, key, value)
    r.expire(skey, STM_TTL_SEC)


def _stm_get(thread_id: str, key: str) -> Optional[str]:
    r = _redis()
    skey = _stm_key(thread_id)
    v = r.hget(skey, key)
    return v if (isinstance(v, str) and v.strip()) else None


# ─────────────────────────────────────────────────────────────
# Leichte Memory-Intents (“merke dir …”, “welche Zahl …?”)
# ─────────────────────────────────────────────────────────────
RE_REMEMBER_NUM = re.compile(
    r"\b(merke\s*dir|merk\s*dir|remember)\b[^0-9\-+]*?(-?\d+(?:[.,]\d+)?)",
    re.I,
)
RE_REMEMBER_FREE = re.compile(r"\b(merke\s*dir|merk\s*dir|remember)\b[:\s]+(.+)$", re.I)
RE_ASK_NUMBER = re.compile(
    r"\b(welche\s+zahl\s+meinte\s+ich|what\s+number\s+did\s+i\s+mean)\b", re.I
)
RE_ASK_FREE = re.compile(
    r"\b(woran\s+erinn?erst\s+du\s+dich|what\s+did\s+you\s+remember)\b", re.I
)


def _norm_num(s: str) -> str:
    return (s or "").replace(",", ".")


def _memory_intent(text: str, thread_id: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None

    m = RE_REMEMBER_NUM.search(t)
    if m:
        raw = m.group(2)
        norm = _norm_num(raw)
        _stm_set(thread_id, "last_number", norm)
        return f"Alles klar – ich habe mir **{raw}** gemerkt."

    m2 = RE_REMEMBER_FREE.search(t)
    if m2 and not m:
        val = (m2.group(2) or "").strip()
        if val:
            _stm_set(thread_id, "last_note", val)
            return "Notiert. 👍"

    if RE_ASK_NUMBER.search(t):
        v = _stm_get(thread_id, "last_number")
        return f"Du meintest **{v}**." if v else "Ich habe dazu noch keine Zahl gespeichert."

    if RE_ASK_FREE.search(t):
        v = _stm_get(thread_id, "last_note")
        return f"Ich habe mir gemerkt: “{v}”." if v else "Ich habe dazu noch nichts gespeichert."

    return None


# ─────────────────────────────────────────────────────────────
# Utilities für Text-Extraktion aus Graph-Outputs
# ─────────────────────────────────────────────────────────────
def _msg_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(message, dict):
        content = message.get("content", content)

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: List[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                text = chunk.get("text")
                if isinstance(text, str):
                    parts.append(text)
        joined = "".join(parts).strip()
        if joined:
            return joined
    return ""


def _extract_text(out: Dict[str, Any]) -> str:
    msgs = out.get("messages") or []
    if isinstance(msgs, list) and msgs:
        for candidate in reversed(msgs):
            text = _msg_text(candidate)
            if text:
                return text
    for key in ("answer", "explanation", "text", "response", "summary_text"):
        value = out.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "OK."


# ─────────────────────────────────────────────────────────────
# FastAPI Router
# ─────────────────────────────────────────────────────────────
router = APIRouter()


class ChatRequest(BaseModel):
    chat_id: str = Field(default="default", description="Konversations-/Thread-ID")
    input_text: str = Field(..., description="Nutzertext")


class ChatResponse(BaseModel):
    text: str


@router.post("/beratung", response_model=ChatResponse)
async def beratung(_req: Request, payload: ChatRequest) -> ChatResponse:
    """
    Sync-HTTP für einfache Integrationen.
    """
    user_text = (payload.input_text or "").trim()
    if not user_text:
        raise HTTPException(status_code=400, detail="input_text empty")

    thread_id = f"api:{payload.chat_id}"

    mem = _memory_intent(user_text, thread_id)
    if mem:
        return ChatResponse(text=mem)

    state: Dict[str, Any] = {
        "messages": [{"role": "user", "content": user_text}],
        "input": user_text,
        "chat_id": thread_id,
    }
    try:
        out = invoke_consult(state)
    except Exception as e:
        log.exception("consult invoke failed: %r", e)
        raise HTTPException(status_code=500, detail="consult_failed")

    return ChatResponse(text=_extract_text(out))


# ─────────────────────────────────────────────────────────────
# WebSocket API – exakt abgestimmt auf dein Frontend/useChatWs:
#   start → { event:"start", thread_id }
#   token → { event:"token", delta:"…" }
#   final → { event:"final", text:"…" }
#   done  → { event:"done" }
# Zusätzlich: UI-Events → { event:"ui_action", ui_event:{…}, ui_action?:str }
# ─────────────────────────────────────────────────────────────
@router.websocket("/ws")
@router.websocket("/chat/ws")
@router.websocket("/v1/ws")
@router.websocket("/ws_chat")          # Backwards-compat
@router.websocket("/api/v1/ai/ws")     # aktueller Pfad, den das Frontend nutzt
async def ws_endpoint(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    await websocket.accept()

    async def _send(payload: Dict[str, Any]) -> None:
        if websocket.application_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_json(payload)
            except Exception:
                pass

    try:
        if not WS_AUTH_OPTIONAL and not token:
            await _send({"error": "unauthorized"})
            await websocket.close(code=1008)
            return

        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                data = {"input": raw}

            # Heartbeat
            if isinstance(data, dict) and data.get("type") == "ping":
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text('{"type":"pong"}')
                continue

            chat_id = (data.get("chat_id") or "default") if isinstance(data, dict) else "default"
            user_input = (data.get("input") or "").strip() if isinstance(data, dict) else str(data)
            thread_id = f"api:{chat_id}"
            if not user_input:
                continue

            # Start-Event (Frontend erwartet genau "start")
            await _send({"event": "start", "thread_id": thread_id})

            # Schnelle Memory-Intents ohne Graph
            mem = _memory_intent(user_input, thread_id)
            if mem:
                await _send({"event": "final", "thread_id": thread_id, "text": mem, "final": {"text": mem}})
                await _send({"event": "done", "thread_id": thread_id})
                continue

            # Graph-State vorbereiten
            state: Dict[str, Any] = {
                "messages": [{"role": "user", "content": user_input}],
                "input": user_input,
                "chat_id": thread_id,
            }

            streamed: List[str] = []
            last_messages: List[Any] = []
            last_ui_serialized: Optional[str] = None
            out: Optional[Dict[str, Any]] = None

            async def _maybe_ui(candidate: Dict[str, Any]) -> None:
                nonlocal last_ui_serialized
                if not isinstance(candidate, dict):
                    return
                ui_event = candidate.get("ui_event")
                if not isinstance(ui_event, dict) or not ui_event:
                    return
                try:
                    ser = json.dumps(ui_event, sort_keys=True, ensure_ascii=False)
                except Exception:
                    ser = None
                if ser and ser == last_ui_serialized:
                    return
                last_ui_serialized = ser
                payload = {"event": "ui_action", "thread_id": thread_id, "ui_event": ui_event}
                if isinstance(ui_event.get("ui_action"), str):
                    payload["ui_action"] = ui_event["ui_action"]
                await _send(payload)

            async def _handle_stream(evt: Dict[str, Any]) -> None:
                nonlocal out
                if not isinstance(evt, dict):
                    return
                name = str(evt.get("event") or "")

                # Vereinheitlichte Text-Tokens
                if name == "on_custom_event":
                    data = evt.get("data")
                    custom = str(evt.get("name") or "").lower()
                    # Variante A: {"name": "stream_text", "data":{"text":"..."}}
                    if custom == "stream_text" and isinstance(data, dict):
                        t = data.get("text")
                        if isinstance(t, str) and t:
                            streamed.append(t)
                            await _send({"event": "token", "thread_id": thread_id, "delta": t})
                        return
                    # Variante B: {"data":{"type":"stream_text","text":"..."}}
                    if isinstance(data, dict) and str(data.get("type") or "").lower() == "stream_text":
                        t = data.get("text")
                        if isinstance(t, str) and t:
                            streamed.append(t)
                            await _send({"event": "token", "thread_id": thread_id, "delta": t})
                        return

                # Abschlüsse von Ketten/Nodes/Graph → mögliche finale Outputs sammeln
                if name in {"on_node_end", "on_chain_end", "on_graph_end", "on_execution_end"}:
                    data = evt.get("data")
                    cand: Optional[Dict[str, Any]] = None
                    if isinstance(data, dict):
                        outp = data.get("output")
                        res = data.get("result")
                        if isinstance(outp, dict):
                            cand = outp
                        elif isinstance(res, dict):
                            cand = res
                        elif any(k in data for k in ("messages", "ui_event", "answer", "text", "response")):
                            cand = data
                    if isinstance(cand, dict):
                        out = cand
                        msgs = cand.get("messages")
                        if isinstance(msgs, list) and msgs:
                            last_messages = msgs
                        await _maybe_ui(cand)

            # Primär: Streaming
            stream_failed = False
            try:
                async for ev in stream_consult(state):
                    await _handle_stream(ev)
            except Exception as stream_exc:
                stream_failed = True
                log.exception("consult stream error: %r", stream_exc)

            # Fallback: synchron
            if out is None or stream_failed:
                try:
                    out = invoke_consult(state)
                except Exception as e:
                    log.exception("consult error: %r", e)
                    out = {"error": str(e)}
                await _maybe_ui(out)
                if isinstance(out, dict):
                    msgs = out.get("messages")
                    if isinstance(msgs, list) and msgs:
                        last_messages = msgs

            out = out or {}
            if last_messages and not out.get("messages"):
                out = {**out, "messages": last_messages}

            aggregated = "".join(s for s in streamed if isinstance(s, str))
            final_text = _extract_text(out) or aggregated or ""

            await _send({"event": "final", "thread_id": thread_id, "text": final_text, "final": {"text": final_text}})
            await _send({"event": "done", "thread_id": thread_id})

    except Exception as e:
        log.exception("ws_chat error: %r", e)
        try:
            await _send({"error": "internal"})
            await websocket.close(code=1011)
        except Exception:
            pass
