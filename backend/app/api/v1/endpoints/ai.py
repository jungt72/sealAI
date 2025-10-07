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
# Graph-Adapter (bereitgestellt in backend/app/langgraph/graph_chat.py)
#   → stream_consult(state): async generator[dict]
#   → invoke_consult(state): dict
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
# Pydantic-Schemas
# ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    chat_id: str = Field(default="default")
    input: str = Field(..., min_length=1)
    params: Dict[str, Any] | None = None


class ChatResponse(BaseModel):
    text: str


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
        # nimm erstes Text-Element, falls vorhanden
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"].strip()

    return ""


def _extract_text(graph_out: Dict[str, Any]) -> str:
    # unterstützt sowohl {"final":{"text":..}} als auch {"message":{...}}
    if isinstance(graph_out, dict):
        if isinstance(graph_out.get("final"), dict):
            t = graph_out["final"].get("text")
            if isinstance(t, str) and t.strip():
                return t.strip()
        if isinstance(graph_out.get("message"), dict):
            return _msg_text(graph_out["message"])
    return ""


# ─────────────────────────────────────────────────────────────
# Auth-Helper: Bearer aus Header ODER Query akzeptieren
# ─────────────────────────────────────────────────────────────
_BEARER_RE = re.compile(r"^\s*Bearer\s+(.+?)\s*$", re.IGNORECASE)


def _extract_token_from_headers(ws: WebSocket) -> str | None:
    """Liest ggf. "Authorization: Bearer <token>" aus dem WS-Handshake."""
    try:
        header_val = ws.headers.get("authorization")
        if not header_val:
            return None
        m = _BEARER_RE.match(header_val)
        return m.group(1) if m else None
    except Exception:
        return None


def _resolve_ws_token(ws: WebSocket, query_token: str | None) -> str | None:
    # Priorität: Query-Param > Authorization-Header
    if query_token:
        return query_token
    return _extract_token_from_headers(ws)


router = APIRouter()


# ─────────────────────────────────────────────────────────────
# REST: /api/v1/ai/beratung  (synchrone Variante)
# ─────────────────────────────────────────────────────────────
@router.post("/beratung", response_model=ChatResponse)
async def beratung(_req: Request, payload: ChatRequest) -> ChatResponse:
    """
    Synchrone Beratung:
      - nimmt chat_id, input, params entgegen
      - löst leichte Memory-Intents lokal auf
      - ruft invoke_consult(...) mit *params* auf (Fix!)
    """
    # Thread-Namespace angleichen
    thread_id = f"api:{payload.chat_id or 'default'}"

    # Memory-Intents (leicht & synchron)
    mi = _memory_intent(payload.input, thread_id)
    if mi:
        return ChatResponse(text=mi)

    # WICHTIG: params wirklich an invoke_consult weiterreichen
    state: Dict[str, Any] = {
        "chat_id": thread_id,
        "input": payload.input,
        "params": payload.params or {},  # <── Fix gegenüber vorher
        "messages": [{"role": "user", "content": payload.input}],
    }

    try:
        out = invoke_consult(state)
    except Exception as e:
        log.exception("consult invoke failed: %r", e)
        raise HTTPException(status_code=500, detail="consult_failed")

    return ChatResponse(text=_extract_text(out))


# ─────────────────────────────────────────────────────────────
# WebSocket API – abgestimmt auf dein Frontend/useChatWs:
#   start → { event:"start", thread_id }
#   token → { event:"token", delta:"…" }
#   final → { event:"final", text:"…" }
#   done  → { event:"done" }
#   ui_action → { event:"ui_action", ui_action:"open_form"/"calc_snapshot", ... }
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
        # Header- oder Query-Token akzeptieren
        effective_token = _resolve_ws_token(websocket, token)
        if not WS_AUTH_OPTIONAL and not effective_token:
            await _send({"event": "error", "message": "unauthorized"})
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
            params = data.get("params") or {}  # <── WS: params werden unterstützt
            thread_id = f"api:{chat_id}"
            if not user_input and not params:
                continue

            # Memory-Intents (leicht & lokal)
            mi = _memory_intent(user_input, thread_id)
            if mi:
                await _send({"event": "token", "delta": mi})
                await _send({"event": "final", "text": mi})
                await _send({"event": "done", "thread_id": thread_id})
                continue

            # Graph streamen
            state = {
                "chat_id": thread_id,
                "input": user_input,
                "params": params,
                "messages": [{"role": "user", "content": user_input}],
            }

            async for ev in stream_consult(state):
                await _send(ev)

    except Exception as e:
        log.exception("ws_endpoint error: %r", e)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
