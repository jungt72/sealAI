# backend/app/api/v1/endpoints/ai.py
from __future__ import annotations

import os
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from redis import Redis

# Nur die Consult-Funktion nutzen; Checkpointer holen wir aus app.state
from app.services.langgraph.graph.consult.io import invoke_consult as _invoke_consult

# ─────────────────────────────────────────────────────────────
# ENV / Redis STM (Short-Term Memory)
# ─────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STM_PREFIX = os.getenv("STM_PREFIX", "chat:stm")
STM_TTL_SEC = int(os.getenv("STM_TTL_SEC", "604800"))  # 7 Tage

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
# API
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
    Einstieg in den Consult-Flow. Nutzt (falls vorhanden) den Checkpointer aus app.state.
    Zusätzlich: einfache STM-Merkfunktion (merke dir … / welche Zahl …?).
    """
    user_text = (payload.input_text or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="input_text empty")

    thread_id = f"api:{payload.chat_id}"

    # 1) Memory-Intents kurz-circuited beantworten
    mem = _maybe_handle_memory_intent(user_text, thread_id)
    if mem:
        return ChatResponse(text=mem)

    # 2) Consult-Flow aufrufen (mit optionalem Checkpointer)
    checkpointer = getattr(request.app.state, "swarm_checkpointer", None)
    out = _invoke_consult(user_text, thread_id=thread_id, checkpointer=checkpointer)
    return ChatResponse(text=out)
