# backend/app/api/v1/endpoints/ai.py
from __future__ import annotations

import os
import re
import json
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState
from pydantic import BaseModel, Field
from redis import Redis

# Nur die Consult-Funktion nutzen; Checkpointer wird im Consult-Modul intern gehandhabt.
from app.services.langgraph.graph.consult.io import invoke_consult as _invoke_consult

log = logging.getLogger("uvicorn.error")

# ─────────────────────────────────────────────────────────────
# ENV / Redis STM (Short-Term Memory)
# ─────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STM_PREFIX = os.getenv("STM_PREFIX", "chat:stm")
STM_TTL_SEC = int(os.getenv("STM_TTL_SEC", "604800"))  # 7 Tage
WS_AUTH_OPTIONAL = os.getenv("WS_AUTH_OPTIONAL", "1") == "1"

def _stm_key(thread_id: str) -> str:
    return f"{STM_PREFIX}:{thread_id}"

def _get_redis() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)

def _set_stm(thread_id: str, key: str, value: str) -> None:
    r = _get_redis()
    skey = _stm_key(thread_id)
    r.hset(skey, key, value)
    r.expire(skey, STM_TTL_SEC)

def _get_stm(thread_id: str, key: str) -> Optional[str]:
    r = _get_redis()
    skey = _stm_key(thread_id)
    v = r.hget(skey, key)
    return v if (isinstance(v, str) and v.strip()) else None

# ─────────────────────────────────────────────────────────────
# Intent: “merke dir … / remember …” (optional)
# ─────────────────────────────────────────────────────────────
RE_REMEMBER_NUM  = re.compile(r"\b(merke\s*dir|merk\s*dir|remember)\b[^0-9\-+]*?(-?\d+(?:[.,]\d+)?)", re.I)
RE_REMEMBER_FREE = re.compile(r"\b(merke\s*dir|merk\s*dir|remember)\b[:\s]+(.+)$", re.I)
RE_ASK_NUMBER    = re.compile(r"\b(welche\s+zahl\s+meinte\s+ich|what\s+number\s+did\s+i\s+mean)\b", re.I)
RE_ASK_FREE      = re.compile(r"\b(woran\s+erinn?erst\s+du\s+dich|what\s+did\s+you\s+remember)\b", re.I)

def _normalize_num_str(s: str) -> str:
    return (s or "").replace(",", ".")

def _maybe_handle_memory_intent(text: str, thread_id: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None

    m = RE_REMEMBER_NUM.search(t)
    if m:
        raw = m.group(2)
        norm = _normalize_num_str(raw)
        _set_stm(thread_id, "last_number", norm)
        return f"Alles klar – ich habe mir **{raw}** gemerkt."

    m2 = RE_REMEMBER_FREE.search(t)
    if m2 and not m:
        val = (m2.group(2) or "").strip()
        if val:
            _set_stm(thread_id, "last_note", val)
            return "Notiert. 👍"

    if RE_ASK_NUMBER.search(t):
        v = _get_stm(thread_id, "last_number")
        return f"Du meintest **{v}**." if v else "Ich habe dazu noch keine Zahl gespeichert."

    if RE_ASK_FREE.search(t):
        v = _get_stm(thread_id, "last_note")
        return f"Ich habe mir gemerkt: “{v}”." if v else "Ich habe dazu noch nichts gespeichert."

    return None

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _extract_text_from_consult_out(out: Dict[str, Any]) -> str:
    # 1) letzte Assistant-Message
    msgs = out.get("messages") or []
    if msgs:
        last = msgs[-1]
        # LangChain-Objekt oder dict
        content = getattr(last, "content", None)
        if isinstance(last, dict):
            content = last.get("content", content)
        if isinstance(content, str) and content.strip():
            return content.strip()
    # 2) strukturierte Felder (JSON/Explain)
    for k in ("answer", "explanation", "text", "response"):
        v = out.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "OK."

# ─────────────────────────────────────────────────────────────
# API (HTTP)
# ─────────────────────────────────────────────────────────────
router = APIRouter()  # KEIN prefix hier – der übergeordnete Router hängt '/ai' an.

class ChatRequest(BaseModel):
    chat_id: str = Field(default="default", description="Konversations-ID")
    input_text: str = Field(..., description="Nutzertext")

class ChatResponse(BaseModel):
    text: str

@router.post("/beratung", response_model=ChatResponse)
async def beratung(request: Request, payload: ChatRequest) -> ChatResponse:
    """
    Einstieg in den Consult-Flow.
    """
    user_text = (payload.input_text or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="input_text empty")

    thread_id = f"api:{payload.chat_id}"

    # 1) Memory-Intents kurz-circuited beantworten
    mem = _maybe_handle_memory_intent(user_text, thread_id)
    if mem:
        return ChatResponse(text=mem)

    # 2) Consult-Flow korrekt mit State aufrufen
    state = {
        "messages": [{"role": "user", "content": user_text}],
        "input": user_text,
        "chat_id": thread_id,
    }
    try:
        out = _invoke_consult(state)  # returns dict-like ConsultState
    except Exception as e:
        log.exception("consult invoke failed: %r", e)
        raise HTTPException(status_code=500, detail="consult_failed")

    return ChatResponse(text=_extract_text_from_consult_out(out))

# ─────────────────────────────────────────────────────────────
# API (WebSocket) – zuerst accept(), dann prüfen/antworten
# ─────────────────────────────────────────────────────────────
@router.websocket("/ws")
@router.websocket("/chat/ws")
@router.websocket("/v1/ws")
@router.websocket("/ws_chat")   # Backwards-compat
@router.websocket("/api/v1/ai/ws")  # aktueller Pfad im Frontend
async def chat_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    Robuster WS-Handler:
      - Erst 'accept()', dann (optionale) Token/Origin-Prüfung
      - Erwartet Textframes mit JSON wie: {"chat_id":"default","input":"hallo","mode":"graph"}
    """
    await websocket.accept()

    try:
        if not WS_AUTH_OPTIONAL and not token:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_text('{"error":"unauthorized"}')
            await websocket.close(code=1008)
            return

        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except Exception:
                data = {"input": msg}

            if isinstance(data, dict) and data.get("type") == "ping":
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text('{"type":"pong"}')
                continue

            chat_id = (data.get("chat_id") or "default") if isinstance(data, dict) else "default"
            user_input = (data.get("input") or "").strip() if isinstance(data, dict) else str(data)
            thread_id = f"api:{chat_id}"

            if not user_input:
                continue

            mem = _maybe_handle_memory_intent(user_input, thread_id)
            if mem:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text(json.dumps({"event": "final", "text": mem}))
                continue

            # Consult-Flow korrekt mit State aufrufen
            state = {
                "messages": [{"role": "user", "content": user_input}],
                "input": user_input,
                "chat_id": thread_id,
            }
            try:
                out = _invoke_consult(state)
                out_text = _extract_text_from_consult_out(out)
            except Exception as e:
                log.exception("consult error: %r", e)
                out_text = "Entschuldige, da ist gerade ein Fehler passiert."

            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_text(json.dumps({"event": "final", "text": out_text}))

    except WebSocketDisconnect:
        log.info("ws: client disconnected")
    except Exception as e:
        log.exception("ws_chat error: %r", e)
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_text('{"error":"internal"}')
                await websocket.close(code=1011)
        except Exception:
            pass
