# backend/app/services/memory/conversation_memory.py
"""
Conversation STM (Short-Term Memory) auf Redis
----------------------------------------------
- Speichert JEDE Chatnachricht (user|assistant|system) chronologisch.
- Ring-Buffer per LTRIM (STM_MAX_MSG).
- TTL wird bei jedem Push erneuert (STM_TTL_SEC).
"""

from __future__ import annotations
import json
import os
from typing import Any, Dict, List

from redis import Redis

from app.services.redis_client import make_redis_client


STM_PREFIX = os.getenv("STM_PREFIX", "chat:stm")
STM_MAX_MSG = int(os.getenv("STM_MAX_MSG", "50"))
STM_TTL_SEC = int(os.getenv("STM_TTL_SEC", "604800"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_LAST_AGENT_SUFFIX = "last_agent"


def _redis() -> Redis:
    return make_redis_client(REDIS_URL, decode_responses=True)


def _normalize_user_id(user_id: str | None) -> str | None:
    if user_id is None:
        return None
    user_id = str(user_id).strip()
    return user_id or None


def _stm_key(user_id: str | None, chat_id: str) -> str | None:
    normalized_user = _normalize_user_id(user_id)
    if not normalized_user or not chat_id:
        return None
    return f"{STM_PREFIX}:{normalized_user}:{chat_id}"


def _last_agent_key(user_id: str | None, chat_id: str) -> str | None:
    base = _stm_key(user_id, chat_id)
    if not base:
        return None
    return f"{base}:{_LAST_AGENT_SUFFIX}"


def add_message(user_id: str | None, chat_id: str, role: str, content: str) -> None:
    entry = json.dumps({"role": role, "content": content})
    try:
        r = _redis()
        key = _stm_key(user_id, chat_id)
        if not key:
            return
        r.rpush(key, entry)
        r.ltrim(key, -STM_MAX_MSG, -1)
        r.expire(key, STM_TTL_SEC)
    except Exception:
        return


def get_history(user_id: str | None, chat_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        r = _redis()
        key = _stm_key(user_id, chat_id)
        if not key:
            return []
        entries = r.lrange(key, -limit, -1)
        history: List[Dict[str, Any]] = []
        for entry in entries:
            try:
                parsed = json.loads(entry)
                if isinstance(parsed, dict):
                    history.append(parsed)
            except json.JSONDecodeError:
                continue
        return history
    except Exception:
        return []


def set_last_agent(user_id: str | None, chat_id: str, agent: str) -> None:
    """Persist the last selected agent for a chat thread.

    The value is stored with the same TTL as the STM messages so that it
    expires automatically when the conversation history is purged.
    """

    if not chat_id or not agent:
        return
    try:
        r = _redis()
        key = _last_agent_key(user_id, chat_id)
        if not key:
            return
        r.set(key, agent, ex=STM_TTL_SEC)
    except Exception:
        return


def get_last_agent(user_id: str | None, chat_id: str) -> str | None:
    """Return the previously stored agent identifier, if available."""

    if not chat_id:
        return None
    try:
        r = _redis()
        key = _last_agent_key(user_id, chat_id)
        if not key:
            return None
        value = r.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
    except Exception:
        return None


def clear_last_agent(user_id: str | None, chat_id: str) -> None:
    """Remove the cached agent hint for the given chat thread."""

    if not chat_id:
        return
    try:
        r = _redis()
        key = _last_agent_key(user_id, chat_id)
        if not key:
            return
        r.delete(key)
    except Exception:
        return
