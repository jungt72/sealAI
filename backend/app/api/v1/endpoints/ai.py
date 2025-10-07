# backend/app/api/v1/endpoints/ai.py
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, AsyncGenerator

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
        for c in content:
            if isinstance(c, dict):
                t = c.get("text") or c.get("content") or ""
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(p for p in parts if p).strip()

    return ""


def _extract_text(out: Any) -> str:
    """
    Extrahiert bevorzugt `final.text`, fällt zurück auf `message.data.content`,
    dann `message.content`, dann `text`.
    """
    if isinstance(out, dict):
        if isinstance(out.get("final"), dict):
            ft = out["final"].get("text")
            if isinstance(ft, str) and ft.strip():
                return ft.strip()
        # LCEL / LangGraph Messages
        msg = out.get("message") or out.get("messages") or out.get("msg")
        if msg:
            t = _msg_text(msg)
            if t:
                return t
        t2 = out.get("text")
        if isinstance(t2, str) and t2.strip():
            return t2.strip()
    # Fallback: stringifizieren
    try:
        s = str(out)
        return s.strip()
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────
# HTTP-Modelle
# ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    input: str = Field(..., description="User-Eingabe")
    stream: bool = Field(default=True)
    chat_id: Optional[str] = Field(default="default")
    params: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    text: str


# ─────────────────────────────────────────────────────────────
# HTTP-Endpoint (sync invoke) – für Tests/Debug
# ─────────────────────────────────────────────────────────────
router = APIRouter()


@router.post("/beratung", response_model=ChatResponse)
async def beratung(_req: Request, payload: ChatRequest) -> ChatResponse:
    user_text = (payload.input or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="empty_input")

    thread_id = f"api:{payload.chat_id or 'default'}"

    # Leichte Memory-Intents (sofortiges Ergebnis)
    mm = _memory_intent(user_text, thread_id)
    if mm:
        return ChatResponse(text=mm)

    # Graph synchron aufrufen
    state = {
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


# ── Auth-Helper: Bearer aus Header ODER Query akzeptieren ─────────────────────
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
        # Auth: Query (?token=…) oder "Authorization: Bearer …"
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
            params = data.get("params") if isinstance(data, dict) else None
            thread_id = f"api:{chat_id}"
            if not user_input:
                continue

            # Sofort-Intents (Memory)
            mm = _memory_intent(user_input, thread_id)
            if mm:
                await _send({"event": "start", "thread_id": thread_id})
                await _send({"event": "final", "text": mm})
                await _send({"event": "done", "thread_id": thread_id})
                continue

            # Graph-Streaming
            await _send({"event": "start", "thread_id": thread_id})

            state: Dict[str, Any] = {
                "messages": [{"role": "user", "content": user_input}],
                "input": user_input,
                "chat_id": thread_id,
            }
            if isinstance(params, dict) and params:
                state["params"] = params

            async def _emit_stream(gen: AsyncGenerator[Dict[str, Any], None]) -> None:
                """Normalisiert Stream-Frames auf das Frontend-Protokoll."""
                async for frame in gen:
                    if not isinstance(frame, dict):
                        # Rohtext → als Token streamen
                        await _send({"event": "token", "delta": str(frame)})
                        continue

                    # Debug/Node-Events → als dbg weiterreichen (für UI-Triggers)
                    if frame.get("event") == "dbg" or frame.get("type") == "dbg":
                        await _send({"event": "dbg", "meta": frame.get("meta") or {}})
                        # heuristisch: ask_missing → Formular öffnen
                        node = (frame.get("meta", {}).get("langgraph_node") or "").lower()
                        if node == "ask_missing":
                            await _send({"event": "ui_action", "ui_action": "open_form"})
                        continue

                    # UI-Events aus dem Graph direkt durchreichen
                    if frame.get("event") == "ui_action" or frame.get("ui_event") or frame.get("ui_action"):
                        ua = frame.get("ui_event") or frame
                        await _send({"event": "ui_action", **(ua if isinstance(ua, dict) else {"ui_action": str(ua)})})
                        continue

                    # Token / Delta
                    if isinstance(frame.get("delta"), str) and frame["delta"]:
                        await _send({"event": "token", "delta": frame["delta"]})
                        continue

                    # Finaltext
                    if isinstance(frame.get("final"), dict) and isinstance(frame["final"].get("text"), str):
                        await _send({"event": "final", "text": frame["final"]["text"]})
                        continue

                    # LCEL / message(content)
                    msg = frame.get("message") or frame.get("messages") or None
                    if msg:
                        t = _msg_text(msg)
                        if t:
                            await _send({"event": "token", "delta": t})
                            continue

                    # Fallback: text
                    t2 = frame.get("text")
                    if isinstance(t2, str) and t2.strip():
                        await _send({"event": "token", "delta": t2.strip()})
                        continue

                # Ende-Event
                await _send({"event": "done", "thread_id": thread_id})

            # Stream ausführen
            try:
                await _emit_stream(stream_consult(state))
            except Exception as e:
                log.exception("stream_consult failed: %r", e)
                await _send({"event": "error", "message": "stream_failed"})
                # sauberes Done schicken, damit Frontend nicht hängt
                await _send({"event": "done", "thread_id": thread_id})

    except Exception as e:
        # Verbindungs-/Protokollfehler
        try:
            await _send({"event": "error", "message": str(e) or "ws_error"})
        except Exception:
            pass
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close(code=1011)
        except Exception:
            pass
