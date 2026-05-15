from __future__ import annotations

import logging
from typing import Any

from langgraph.config import get_stream_writer

from app.agent.capability_registry.contracts import CapabilityId
from app.agent.capability_registry.registry import build_default_capability_registry
from app.agent.graph import GraphState

log = logging.getLogger(__name__)


def _asserted_value(state: GraphState, field_name: str) -> Any:
    claim = (state.asserted.assertions or {}).get(field_name)
    if claim is None:
        return None
    return getattr(claim, "asserted_value", None)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _medium_query(state: GraphState) -> str:
    return (
        _optional_text(_asserted_value(state, "medium"))
        or _optional_text(state.medium_classification.canonical_label)
        or _optional_text(state.medium_capture.primary_raw_text)
        or ""
    )


def _application_context(state: GraphState) -> str | None:
    parts = [
        _optional_text(_asserted_value(state, "application")),
        _optional_text(_asserted_value(state, "sealing_type")),
        _optional_text(_asserted_value(state, "motion_type")),
        _optional_text(state.application_hint.label),
        _optional_text(state.motion_hint.label),
    ]
    return "; ".join(part for part in parts if part) or None


def _emit_medium_intelligence_event(payload: dict[str, Any]) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    except Exception:  # noqa: BLE001
        return
    try:
        writer(
            {
                "event_type": "medium_intelligence_ready",
                "validation_status": payload.get("validation_status"),
                "confidence": payload.get("confidence"),
                "candidate_fact_count": len(payload.get("candidate_facts") or {}),
                "risk_note_count": len(payload.get("risk_notes") or []),
                "missing_field_hints": list(payload.get("missing_field_hints") or []),
            }
        )
    except Exception:  # noqa: BLE001
        return


async def medium_intelligence_node(state: GraphState) -> GraphState:
    """Run the registered Medium Intelligence capability as a native graph step.

    The capability is read-only and deterministic. It writes bounded candidate
    facts and risk notes with provenance into the state; it never creates an
    approval, material release, compound release, or manufacturer decision.
    """

    payload = {
        "medium_query": _medium_query(state),
        "temperature_c": _optional_float(_asserted_value(state, "temperature_c")),
        "application_context": _application_context(state),
    }
    try:
        result = build_default_capability_registry().invoke(
            CapabilityId.MEDIUM_INTELLIGENCE,
            payload,
        )
        result_payload = result.as_dict()
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[medium_intelligence_node] skipped (%s: %s)",
            type(exc).__name__,
            exc,
        )
        result_payload = {
            "capability_id": CapabilityId.MEDIUM_INTELLIGENCE.value,
            "validation_status": "error",
            "confidence": "low",
            "risk_notes": ("medium_intelligence_unavailable",),
            "missing_field_hints": (),
            "candidate_facts": {},
        }

    _emit_medium_intelligence_event(result_payload)
    return state.model_copy(update={"medium_intelligence": result_payload})
