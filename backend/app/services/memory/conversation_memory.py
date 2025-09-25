# backend/app/services/memory/conversation_memory.py
"""
Conversation STM (Short-Term Memory) auf Redis
----------------------------------------------
- Speichert JEDE Chatnachricht (user|assistant|system) chronologisch.
- Ring-Buffer per LTRIM (STM_MAX_MSG).
- TTL wird bei jedem Push erneuert (STM_TTL_SEC).
"""

from __future__ import annotations
import os
import json
import time
from typing import Literal, List, Dict, Any
from redis import Redis

# ───────────────────────── Config ──────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TTL_SEC   = int(os.getenv("STM_TTL_SEC", "604800"))           # 7 Tage
MAX_MSG   = int(os.getenv("STM_MAX_MSG", "200"))              # max. Messages/Chat
PREFIX    = os.getenv("STM_PREFIX", "chat:stm")               # Key-Namespace
# ────────────────────────────────────────────────────────────

def _r() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)

def _key(chat_id: str) -> str:
    return f"{PREFIX}:{chat_id}:messages"

def _touch(chat_id: str) -> None:
    _r().expire(_key(chat_id), TTL_SEC)

Role = Literal["user", "assistant", "system"]

def add_message(chat_id: str, role: Role, content: str) -> None:
    """Hängt eine Nachricht an das Chat-Log (Ring-Buffer) an."""
    if not chat_id or not isinstance(content, str) or not content.strip():
        return
    doc: Dict[str, Any] = {
        "role": role,
        "content": content,
        "ts": time.time(),
    }
    r = _r()
    r.rpush(_key(chat_id), json.dumps(doc, ensure_ascii=False))
    r.ltrim(_key(chat_id), -MAX_MSG, -1)  # Ring-Buffer begrenzen
    _touch(chat_id)

def get_history(chat_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Liest die letzten N Nachrichten (chronologisch)."""
    if limit <= 0:
        return []
    r = _r()
    raw = r.lrange(_key(chat_id), -limit, -1)
    out: List[Dict[str, Any]] = []
    for row in raw:
        try:
            out.append(json.loads(row))
        except Exception:
            continue
    return out
