from __future__ import annotations

import threading
from typing import Any, Dict

_STORE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def get_context_state(user_id: str) -> Dict[str, Any]:
    """
    Liefert den aktuell bekannten Kontext-Status des Nutzers.
    """
    with _LOCK:
        return dict(_STORE.get(user_id, {}))


def merge_context_state(user_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merged neue Kontextdaten in den gespeicherten Zustand.
    """
    if not user_id:
        user_id = "api_user"
    sanitized_patch = patch if isinstance(patch, dict) else {}
    with _LOCK:
        current = dict(_STORE.get(user_id, {}))
        current.update(sanitized_patch)
        _STORE[user_id] = current
        return dict(current)
