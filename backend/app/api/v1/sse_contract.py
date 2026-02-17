from __future__ import annotations

from typing import Any, Dict, Iterable


ALLOWED_EVENT_NAMES = {
    "token",
    "state_update",
    "retrieval.results",
    "retrieval.skipped",
    "decision.supervisor",
    "decision.knowledge_target",
    "trace",
    "checkpoint_required",
    "resync_required",
    "error",
    "done",
}


REQUIRED_KEYS_BY_EVENT = {
    "token": ("type", "text"),
    "state_update": ("type",),
    "retrieval.results": (),
    "retrieval.skipped": ("reason",),
    "decision.supervisor": ("action", "reason", "chat_id"),
    "decision.knowledge_target": ("target", "chat_id"),
    "trace": ("type",),
    "checkpoint_required": ("checkpoint_id", "action"),
    "resync_required": ("reason",),
    "error": ("type",),
    "done": ("type", "chat_id"),
}


def _require_keys(payload: Dict[str, Any], keys: Iterable[str], *, event_name: str) -> None:
    for key in keys:
        if key not in payload:
            raise AssertionError(f"missing required key '{key}' for event '{event_name}'")


def validate_event(event_name: str, payload: Dict[str, Any]) -> None:
    if event_name not in ALLOWED_EVENT_NAMES:
        raise AssertionError(f"unknown SSE event '{event_name}'")
    _require_keys(payload, REQUIRED_KEYS_BY_EVENT.get(event_name, ()), event_name=event_name)

