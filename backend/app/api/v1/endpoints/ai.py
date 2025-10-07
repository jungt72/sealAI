# backend/app/api/v1/endpoints/ai.py
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from redis import Redis
from starlette.websockets import WebSocketState

# ─────────────────────────────────────────────────────────────
# Graph-Schnittstelle (neues Backend-Layout)
#   → stream_consult(state) : async generator[dict]
#   → invoke_consult(state) : dict
# Passe ggf. den Importweg hier an deinen Tree an.
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
        # liste aus message parts → concat reine strings
        buf: List[str] = []
        for part in content:
            if isinstance(part, str):
                buf.append(part.strip())
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                buf.append(part["text"].strip())
            elif hasattr(part, "text") and isinstance(part.text, str):
                buf.append(part.text.strip())
        return "\n".join([x for x in buf if x])
    return ""


def _extract_text(out: Any) -> str:
    # versucht common Felder
    if isinstance(out, dict):
        if "text" in out and isinstance(out["text"], str):
            return out["text"].strip()
        if "messages" in out:
            msgs = out["messages"]
            if isinstance(msgs, list) and msgs:
                return _msg_text(msgs[-1])
        if "final" in out:
            return _msg_text(out["final"])
    return _msg_text(out)


# ─────────────────────────────────────────────────────────────
# Datamodels
# ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    chat_id: Optional[str] = Field(default="default")
    input: str = Field(default="")
    params: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    text: str


# ─────────────────────────────────────────────────────────────
# REST Endpoint – sync invoke (Debug/Kompat)
# ─────────────────────────────────────────────────────────────
router = APIRouter()


@router.post("/beratung", response_model=ChatResponse)
async def beratung(_req: Request, payload: ChatRequest) -> ChatResponse:
    user_text = (payload.input or "").strip()
    thread_id = f"api:{payload.chat_id or 'default'}"

    # kleine Memory-Intents vorziehen (Qualitäts-of-Life)
    mem = _memory_intent(user_text, thread_id)
    if mem:
        return ChatResponse(text=mem)

    state = {
        "messages": [{"role": "user", "content": user_text}],
        "input": user_text,
        "chat_id": thread_id,
        "params": payload.params or {},
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
    """
    Liest ggf. 'Authorization: Bearer <token>' aus dem WS-Handshake.
    """
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
# Hilfs-Funktion: abgeleitete Kennwerte (UI-Event)
# ─────────────────────────────────────────────────────────────
def _calc_snapshot(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Erzeugt ein leichtes Engineering-Snapshot-Objekt aus RWDR-Parametern.
    """
    try:
        d_mm = float(params.get("wellen_mm") or 0)
        n = float(params.get("drehzahl_u_min") or 0)
        p_bar = float(params.get("druck_bar") or 0)

        # Umfangsgeschwindigkeit v = pi * d * n / 60  (d in m)
        v = 3.141592653589793 * (d_mm / 1000.0) * (n / 60.0)
        omega = 2 * 3.141592653589793 * (n / 60.0)
        pv = p_bar * v
        pv_mpa = (p_bar / 10.0) * v  # 1 bar = 0.1 MPa

        warnings: List[str] = []
        if v > 20:
            warnings.append("Umfangsgeschwindigkeit ungewöhnlich hoch")
        if p_bar > 10:
            warnings.append("Druck > 10 bar – Spezialausführung prüfen")

        return {
            "calculated": {
                "surface_speed_m_s": v,
                "omega_rad_s": omega,
                "pv_bar_ms": pv,
                "p_bar": p_bar,
                "p_mpa": p_bar / 10.0,
                "pv_mpa_ms": pv_mpa,
            },
            "warnings": warnings,
        }
    except Exception:
        return {"calculated": {}, "warnings": ["snapshot_failed"]}


# ─────────────────────────────────────────────────────────────
# WebSocket API – exakt abgestimmt auf Frontend/useChatWs:
#   start → { event:"start", thread_id }
#   token → { event:"token", delta:"…" }
#   final → { event:"final", text:"…" }
#   done  → { event:"done" }
# Plus: UI-Events → { event:"ui_action", ui_action, derived:{…} }
# ─────────────────────────────────────────────────────────────
@router.websocket("/ws")
@router.websocket("/chat/ws")
@router.websocket("/v1/ws")
@router.websocket("/ws_chat")          # Backwards-compat
@router.websocket("/api/v1/ai/ws")     # aktueller Pfad
async def ws_endpoint(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    # ── NEU: Auth vor accept() prüfen, damit Tests einen Fehler beim Connect sehen ──
    effective_token = _resolve_ws_token(websocket, token)
    if not WS_AUTH_OPTIONAL and not effective_token:
        # Handshake ablehnen → TestClient bekommt eine Exception
        try:
            await websocket.close(code=1008)
        finally:
            raise WebSocketDisconnect(code=1008)

    # Ab hier akzeptieren wir die Verbindung
    await websocket.accept()

    async def _send(payload: Dict[str, Any]) -> None:
        if websocket.application_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_json(payload)
            except Exception:
                pass

    try:
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
            params = data.get("params") if isinstance(data, dict) else {}

            # UI: kleiner Live-Snapshot (falls params kommen)
            if isinstance(params, dict) and params:
                await _send({
                    "event": "ui_action",
                    "ui_action": "calc_snapshot",
                    "derived": _calc_snapshot(params),
                })

            # Memory-Intents
            mem = _memory_intent(user_input, thread_id)
            if mem:
                await _send({"event": "final", "text": mem})
                await _send({"event": "done", "thread_id": thread_id})
                continue

            if not user_input:
                continue

            await _send({"event": "start", "thread_id": thread_id})

            # Stream vom Graph
            state = {
                "messages": [{"role": "user", "content": user_input}],
                "input": user_input,
                "chat_id": thread_id,
                "params": params or {},
            }

            final_fragments: List[str] = []
            async for ev in stream_consult(state):
                # Erwartete keys: {"type":"chunk"/"final"/"info", ...}
                if not isinstance(ev, dict):
                    continue
                t = ev.get("type")

                if t == "chunk":
                    delta = _extract_text(ev) or ev.get("delta") or ev.get("text") or ""
                    if delta:
                        final_fragments.append(delta)
                        await _send({"event": "token", "delta": delta})

                elif t == "final":
                    txt = _extract_text(ev) or ""
                    if txt:
                        final_fragments.append(txt)

                elif t == "info":
                    # optional: typing o.ä.
                    if ev.get("info") == "typing":
                        await _send({"event": "typing", "thread_id": thread_id})

            final_text = "".join(final_fragments).strip()
            if final_text:
                await _send({"event": "final", "text": final_text})

            await _send({"event": "done", "thread_id": thread_id})

    except WebSocketDisconnect:
        # sauber beenden
        return
    except Exception as e:
        log.exception("ws_endpoint error: %r", e)
        try:
            await _send({"event": "error", "message": "internal_error"})
            await websocket.close(code=1011)
        except Exception:
            pass
