from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from redis import Redis
from starlette.websockets import WebSocketState

from app.services.chat.ws_commons import choose_subprotocol, send_json_safe
from app.services.chat.ws_streaming import stream_langgraph

log = logging.getLogger("uvicorn.error")

ENABLE_LANGGRAPH = os.getenv("ENABLE_LANGGRAPH_V06", "false").lower() in ("true", "1", "yes")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STM_PREFIX = os.getenv("STM_PREFIX", "chat:stm")
STM_TTL_SEC = int(os.getenv("STM_TTL_SEC", "604800"))
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
    value = r.hget(_stm_key(thread_id), key)
    return value if isinstance(value, str) and value.strip() else None


RE_REMEMBER_NUM = re.compile(r"\b(merke\s*dir|merk\s*dir|remember)\b[^0-9\-+]*?(-?\d+(?:[.,]\d+)?)", re.I)
RE_REMEMBER_FREE = re.compile(r"\b(merke\s*dir|merk\s*dir|remember)\b[:\s]+(.+)$", re.I)
RE_ASK_NUMBER = re.compile(r"\b(welche\s+zahl\s+meinte\s+ich|what\s+number\s+did\s+i\s+mean)\b", re.I)
RE_ASK_FREE = re.compile(r"\b(woran\s+erinn?erst\s+du\s+dich|what\s+did\s+you\s+remember)\b", re.I)


def _norm_num(value: str) -> str:
    return (value or "").replace(",", ".")


def _memory_intent(text: str, thread_id: str) -> Optional[str]:
    content = (text or "").strip()
    if not content:
        return None

    match_number = RE_REMEMBER_NUM.search(content)
    if match_number:
        raw = match_number.group(2)
        _stm_set(thread_id, "last_number", _norm_num(raw))
        return f"Alles klar – ich habe mir **{raw}** gemerkt."

    match_free = RE_REMEMBER_FREE.search(content)
    if match_free and not match_number:
        value = (match_free.group(2) or "").strip()
        if value:
            _stm_set(thread_id, "last_note", value)
            return "Notiert. 👍"

    if RE_ASK_NUMBER.search(content):
        remembered = _stm_get(thread_id, "last_number")
        return f"Du meintest **{remembered}**." if remembered else "Ich habe dazu noch keine Zahl gespeichert."

    if RE_ASK_FREE.search(content):
        remembered = _stm_get(thread_id, "last_note")
        return f"Ich habe mir gemerkt: “{remembered}”." if remembered else "Ich habe dazu noch nichts gespeichert."

    return None


class ChatRequest(BaseModel):
    chat_id: str = Field(default="default")
    input: str
    params: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    text: str


router = APIRouter()

@router.post("/supervisor", response_model=ChatResponse)
async def supervisor_endpoint(payload: ChatRequest) -> ChatResponse:
    user_text = (payload.input or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="input empty")
    log.warning("supervisor_endpoint disabled; legacy supervisor stack removed")
    return ChatResponse(text="Supervisor-Stack wurde deaktiviert. Bitte nutzen Sie den Standard-Chat.")


@router.post("/beratung", response_model=ChatResponse)
async def beratung(_req: Request, payload: ChatRequest) -> ChatResponse:
    user_text = (payload.input or "").strip()
    thread_id = f"api:{payload.chat_id or 'default'}"

    memory_hint = _memory_intent(user_text, thread_id)
    if memory_hint:
        return ChatResponse(text=memory_hint)

    message = (
        "LangGraph wurde entfernt. "
        "Die Beratungskomponente wird neu aufgebaut. "
        "Bitte zu einem späteren Zeitpunkt erneut versuchen."
    )
    if not user_text:
        raise HTTPException(status_code=400, detail="input empty")
    return ChatResponse(text=message)


_BEARER_RE = re.compile(r"^\s*Bearer\s+(.+?)\s*$", re.IGNORECASE)


def _extract_token_from_headers(ws: WebSocket) -> Optional[str]:
    try:
        header_val = ws.headers.get("authorization")
        if not header_val:
            return None
        match = _BEARER_RE.match(header_val)
        return match.group(1) if match else None
    except Exception:
        return None


def _extract_token_from_cookies(ws: WebSocket) -> Optional[str]:
    try:
        cookies = ws.cookies or {}
        return cookies.get("kc_access_token") or cookies.get("access_token") or None
    except Exception:
        return None


def _resolve_ws_token(ws: WebSocket, query_token: Optional[str]) -> Optional[str]:
    return query_token or _extract_token_from_headers(ws) or _extract_token_from_cookies(ws)


@router.websocket("/api/v1/ai/ws")
@router.websocket("/ws")
@router.websocket("/chat/ws")
@router.websocket("/v1/ws")
@router.websocket("/ws_chat")
@router.websocket("/api/v1/ai/ws")
@router.websocket("/ws")
@router.websocket("/chat/ws")
@router.websocket("/v1/ws")
@router.websocket("/ws_chat")
async def ws_endpoint(websocket: WebSocket, token: Optional[str] = Query(default=None)) -> None:
    effective_token = _resolve_ws_token(websocket, token)
    if not WS_AUTH_OPTIONAL and not effective_token:
        try:
            await websocket.close(code=1008)
        finally:
            return

    await websocket.accept(subprotocol=choose_subprotocol(websocket))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                data = {"input": raw}

            if isinstance(data, dict) and data.get("type") == "ping":
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text('{"type":"pong"}')
                continue

            if not isinstance(data, dict):
                data = {"input": str(data)}

            chat_id = data.get("chat_id") or "default"
            user_input = str(data.get("input") or data.get("text") or data.get("query") or "").strip()
            mode = data.get("mode", "default")

            if not user_input:
                continue

            memory_hint = _memory_intent(user_input, f"ws:{chat_id}")
            if memory_hint:
                await send_json_safe(websocket, {"event": "memory", "text": memory_hint})
                continue
            if mode == "graph" and ENABLE_LANGGRAPH:
                await stream_langgraph(websocket, {"input": user_input, "chat_id": chat_id})
                continue

            # Fallback for non-memory messages when LangGraph is disabled
            await send_json_safe(
                websocket,
                {
                    "event": "info",
                    "message": (
                        "LangGraph wurde entfernt. "
                        "Streaming-Antworten stehen vorübergehend nicht zur Verfügung."
                    ),
                },
            )
            await send_json_safe(websocket, {"event": "done"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.exception("ws_endpoint error: %r", exc)
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await send_json_safe(websocket, {"event": "error", "message": "internal_error"})
        finally:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close(code=1011)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.exception("ws_endpoint error: %r", exc)
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await send_json_safe(websocket, {"event": "error", "message": "internal_error"})
        finally:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close(code=1011)
