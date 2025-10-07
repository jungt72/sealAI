"""Discovery intake node for the unified IO pipeline."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.langgraph.io.schema import SCHEMA_VERSION
from app.langgraph.io.validation import ensure_discovery
from .base import IOValidatedNode


def _coalesce_goal(payload: Dict[str, Any]) -> str:
    for key in ("ziel", "goal", "objective", "auftrag"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    message = payload.get("messages")
    if isinstance(message, list):
        for item in reversed(message):
            text = None
            if isinstance(item, dict):
                text = item.get("content") or item.get("text")
            elif hasattr(item, "content"):
                text = getattr(item, "content")
            if isinstance(text, str) and text.strip():
                return text.strip()[:280]
    return "Beratung starten"


def _coalesce_summary(payload: Dict[str, Any], fallback: str) -> str:
    for key in ("zusammenfassung", "summary", "beschreibung", "context"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _collect_missing(payload: Dict[str, Any]) -> List[str]:
    candidates: Iterable[Any] = payload.get("missing") or payload.get("fehlende_parameter") or payload.get("required") or []
    missing: List[str] = []
    for item in candidates:
        if isinstance(item, str) and item.strip():
            candidate = item.strip()
        elif isinstance(item, dict):
            candidate = str(item.get("name") or item.get("key") or "").strip()
        else:
            continue
        if candidate and candidate not in missing:
            missing.append(candidate)
        if len(missing) >= 3:
            break
    return missing


def _ready_flag(payload: Dict[str, Any], missing: List[str]) -> bool:
    if isinstance(payload.get("ready_to_route"), bool):
        return payload["ready_to_route"]
    if isinstance(payload.get("force_ready"), bool):
        return payload["force_ready"]
    return len(missing) == 0


class DiscoveryIntakeNode(IOValidatedNode):
    """Collects initial metadata and missing parameters from raw discovery payloads."""

    _out_validator = ensure_discovery

    def _run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        goal = _coalesce_goal(payload)
        summary = _coalesce_summary(payload, goal)
        missing = _collect_missing(payload)
        ready = _ready_flag(payload, missing)

        return {
            "schema_version": SCHEMA_VERSION,
            "ziel": goal,
            "zusammenfassung": summary,
            "fehlende_parameter": missing,
            "ready_to_route": ready,
        }


__all__ = ["DiscoveryIntakeNode"]
