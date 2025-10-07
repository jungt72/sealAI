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

# Consult-Graph API (synchrone + Streaming-Variante)
from app.services.langgraph.graph.consult.io import (
    invoke_consult as _invoke_consult,
    stream_consult as _stream_consult,
)

log = logging.getLogger("uvicorn.error")

# ─────────────────────────────────────────────────────────────
# Konfiguration / Redis Short-Term Memory (STM)
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
# Leichte Memory-Intents (“merke dir …”, “welche Zahl …?”)
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
def _message_to_text(message: Any) -> str:
    """
    Extrahiert Text aus LangChain/LangGraph-Messageobjekten (oder dict/list).
    """
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

def _extract_text_from_consult_out(out: Dict[str, Any]) -> str:
    # 1) letzte Assistant-Message
    msgs = out.get("messages") or []
    if isinstance(msgs, list) and msgs:
        for candidate in reversed(msgs):
            text = _message_to_text(candidate)
            if text:
                return text
    # 2) strukturierte Felder
    for key in ("answer", "explanation", "text", "response", "summary_text"):
        value = out.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "OK."

# ─────────────────────────────────────────────────────────────
# API (HTTP)
# ─────────────────────────────────────────────────────────────
router = APIRouter()  # KEIN prefix hier – der übergeordnete Router hängt '/ai' an.

class ChatRequest(BaseModel):
    chat_id: str = Field(default="default", description="Konversations-/Thread-ID")
    input_text: str = Field(..., description="Nutzertext")

class ChatResponse(BaseModel):
    text: str

@router.post("/beratung", response_model=ChatResponse)
async def beratung(_req: Request, payload: ChatRequest) -> ChatResponse:
    """
    Einstieg in den Consult-Flow über HTTP.
    """
    user_text = (payload.input_text or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="input_text empty")

    thread_id = f"api:{payload.chat_id}"

    # 1) Memory-Intents ggf. direkt beantworten (kein Graph-Call)
    mem = _maybe_handle_memory_intent(user_text, thread_id)
    if mem:
        return ChatResponse(text=mem)

    # 2) Consult-Flow mit State aufrufen
    state: Dict[str, Any] = {
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
# API (WebSocket)
# ─────────────────────────────────────────────────────────────
@router.websocket("/ws")
@router.websocket("/chat/ws")
@router.websocket("/v1/ws")
@router.websocket("/ws_chat")          # Backwards-compat
@router.websocket("/api/v1/ai/ws")     # aktueller Pfad im Frontend
async def chat_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    Robuster WS-Handler:
      • Erst accept(), dann (optionale) Token/Origin-Prüfung
      • Erwartet Textframes mit JSON wie:
        {"chat_id":"default","input":"hallo","mode":"graph"}
    """
    await websocket.accept()

    async def _send_json(payload: Dict[str, Any]) -> None:
        if websocket.application_state != WebSocketState.CONNECTED:
            return
        try:
            await websocket.send_json(payload)
        except Exception:
            # Verbindung evtl. weg – bewusst “schlucken” für Robustheit
            pass

    try:
        if not WS_AUTH_OPTIONAL and not token:
            await _send_json({"error": "unauthorized"})
            await websocket.close(code=1008)
            return

        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except Exception:
                data = {"input": msg}

            # Ping/Pong
            if isinstance(data, dict) and data.get("type") == "ping":
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text('{"type":"pong"}')
                continue

            chat_id = (data.get("chat_id") or "default") if isinstance(data, dict) else "default"
            user_input = (data.get("input") or "").strip() if isinstance(data, dict) else str(data)
            thread_id = f"api:{chat_id}"
            if not user_input:
                continue

            # Frontend erwartet ein "starting"-Signal pro Anfrage.
            await _send_json({"event": "starting", "phase": "starting", "thread_id": thread_id})

            # Memory-Intent?
            mem = _maybe_handle_memory_intent(user_input, thread_id)
            if mem:
                await _send_json(
                    {"event": "final", "thread_id": thread_id, "text": mem, "final": {"text": mem}}
                )
                await _send_json({"event": "done", "thread_id": thread_id})
                continue

            # Consult-Flow korrekt mit State aufrufen
            state: Dict[str, Any] = {
                "messages": [{"role": "user", "content": user_input}],
                "input": user_input,
                "chat_id": thread_id,
            }
            streamed_chunks: list[str] = []
            last_messages: List[Any] = []
            last_ui_serialized: Optional[str] = None
            out: Optional[Dict[str, Any]] = None

            async def _maybe_emit_ui(candidate: Dict[str, Any]) -> None:
                nonlocal last_ui_serialized
                if not isinstance(candidate, dict):
                    return
                ui_event = candidate.get("ui_event")
                if not isinstance(ui_event, dict) or not ui_event:
                    return
                try:
                    serialized = json.dumps(ui_event, sort_keys=True, ensure_ascii=False)
                except Exception:
                    serialized = None
                if serialized and serialized == last_ui_serialized:
                    return
                last_ui_serialized = serialized
                payload = {"event": "ui_action", "thread_id": thread_id, "ui_event": ui_event}
                if isinstance(ui_event.get("ui_action"), str):
                    payload["ui_action"] = ui_event["ui_action"]
                await _send_json(payload)

            async def _handle_stream_event(event: Dict[str, Any]) -> None:
                nonlocal out
                if not isinstance(event, dict):
                    return
                ev_name = str(event.get("event") or "")

                # vereinheitlichte Text-Streams
                if ev_name == "on_custom_event":
                    data = event.get("data")
                    name = str(event.get("name") or "").lower()
                    if name == "stream_text" and isinstance(data, dict):
                        text_piece = data.get("text")
                        if isinstance(text_piece, str) and text_piece:
                            streamed_chunks.append(text_piece)
                            await _send_json(
                                {
                                    "event": "stream",
                                    "thread_id": thread_id,
                                    "text": text_piece,
                                    "node": data.get("node") or data.get("source"),
                                }
                            )
                        return
                    if isinstance(data, dict) and str(data.get("type") or "").lower() == "stream_text":
                        text_piece = data.get("text")
                        if isinstance(text_piece, str) and text_piece:
                            streamed_chunks.append(text_piece)
                            await _send_json(
                                {
                                    "event": "stream",
                                    "thread_id": thread_id,
                                    "text": text_piece,
                                    "node": data.get("node") or data.get("source"),
                                }
                            )
                    return

                if ev_name in {"on_node_end", "on_chain_end", "on_graph_end", "on_execution_end"}:
                    data = event.get("data")
                    candidate: Optional[Dict[str, Any]] = None
                    if isinstance(data, dict):
                        output = data.get("output")
                        result = data.get("result")
                        if isinstance(output, dict):
                            candidate = output
                        elif isinstance(result, dict):
                            candidate = result
                        elif any(k in data for k in ("messages", "ui_event", "answer")):
                            candidate = data
                    if isinstance(candidate, dict):
                        out = candidate
                        msgs_candidate = candidate.get("messages")
                        if isinstance(msgs_candidate, list) and msgs_candidate:
                            last_messages = msgs_candidate
                        await _maybe_emit_ui(candidate)

            stream_failed = False
            try:
                async for stream_event in _stream_consult(state):
                    await _handle_stream_event(stream_event)
            except Exception as stream_exc:  # robustes Fallback
                stream_failed = True
                log.exception("consult stream error: %r", stream_exc)

            if out is None or stream_failed:
                try:
                    out = _invoke_consult(state)
                except Exception as e:
                    log.exception("consult error: %r", e)
                    out = {"error": str(e)}
                await _maybe_emit_ui(out)
                if isinstance(out, dict):
                    fallback_msgs = out.get("messages")
                    if isinstance(fallback_msgs, list) and fallback_msgs:
                        last_messages = fallback_msgs

            out = out or {}
            if last_messages and not out.get("messages"):
                out = {**out, "messages": last_messages}
            aggregated_text = "".join(chunk for chunk in streamed_chunks if isinstance(chunk, str))
            out_text = _extract_text_from_consult_out(out) or aggregated_text or ""

            await _send_json(
                {"event": "final", "thread_id": thread_id, "text": out_text, "final": {"text": out_text}}
            )
            await _send_json({"event": "done", "thread_id": thread_id})

    except Exception as e:
        log.exception("ws_chat error: %r", e)
        try:
            await _send_json({"error": "internal"})
            await websocket.close(code=1011)
        except Exception:
            pass
