# backend/app/services/memory/conversation_memory.py
"""
Conversation STM (Short-Term Memory) auf Redis
----------------------------------------------
- Speichert JEDE Chatnachricht (user|assistant|system) chronologisch.
- Ring-Buffer per LTRIM (STM_MAX_MSG).
- TTL wird bei jedem Push erneuert (STM_TTL_SEC).
"""

from __future__ import annotations
from typing import List, Dict, Any

# Dieses Modul war historisch eine eigenständige STM-Implementierung.
# Aus Wartbarkeitsgründen delegieren wir die Funktionalität an die
# bereits genutzte Implementation unter `graph.consult.memory_utils`.
from app.services.langgraph.graph.consult import memory_utils as _mu


def add_message(chat_id: str, role: str, content: str) -> None:
    """Backward-compatible wrapper: delegiert an memory_utils.write_message."""
    try:
        _mu.write_message(thread_id=chat_id, role=role, content=content)
    except Exception:
        # Best-effort: swallow errors to avoid breaking callers
        return


def get_history(chat_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Wrapper um die rohen Einträge zu lesen (älteste -> neueste).

    Rückgabe: List[dict] mit mindestens `role` und `content`.
    """
    try:
        return _mu.read_history_raw(chat_id, limit=limit)
    except Exception:
        return []
