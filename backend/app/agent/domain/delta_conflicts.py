"""Conflict projection for proposed deltas versus governed case state."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.agent.state.models import GovernedSessionState, ProposedCaseDeltaField


def _canonical_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace(",", ".")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return " ".join(text.split())
    normalized = number.normalize()
    return format(normalized, "f").rstrip("0").rstrip(".") or "0"


def _format_value(value: Any, unit: str | None = None) -> str:
    rendered = str(value).strip()
    unit_text = str(unit or "").strip()
    return f"{rendered} {unit_text}".strip()


def _proposal_source_label(event_type: str, field: ProposedCaseDeltaField) -> str:
    if event_type == "document_delta_proposed" or field.provenance == "documented":
        return "document"
    if field.provenance == "user_stated":
        return "chat"
    return str(field.provenance or "proposal")


def _decided_source_event_ids(state: GovernedSessionState) -> set[str]:
    decided: set[str] = set()
    for event in state.case_events:
        if event.event_type not in {"case_delta_accepted", "case_delta_rejected"}:
            continue
        for payload in list(event.accepted_delta.values()) + list(event.rejected_delta.values()):
            if isinstance(payload, dict) and payload.get("source_event_id"):
                decided.add(str(payload["source_event_id"]))
    return decided


def build_governed_conflict_items(state: GovernedSessionState) -> list[dict[str, Any]]:
    """Expose unresolved normalized and proposed-delta conflicts for workspace UI."""
    items: list[dict[str, Any]] = []

    for conflict in state.normalized.conflicts:
        items.append(
            {
                "conflict_type": "PARAMETER_CONFLICT",
                "field_name": conflict.field_name,
                "severity": conflict.severity,
                "summary": conflict.description,
                "resolution_status": "open",
                "sources": ["observed_extractions"],
            }
        )

    decided_event_ids = _decided_source_event_ids(state)
    parameters = state.normalized.parameters
    for event in state.case_events:
        if event.event_type not in {"assistant_delta_proposed", "document_delta_proposed"}:
            continue
        if event.event_id in decided_event_ids:
            continue
        proposal_source = event.proposed_case_delta.source
        for field in event.proposed_case_delta.fields:
            if field.status != "proposed":
                continue
            existing = parameters.get(field.field_name)
            if existing is None:
                continue
            if _canonical_value(existing.value) == _canonical_value(field.proposed_value):
                continue
            source_label = _proposal_source_label(event.event_type, field)
            items.append(
                {
                    "conflict_type": "DELTA_SOURCE_CONFLICT",
                    "field_name": field.field_name,
                    "severity": "blocking" if proposal_source == "document" else "warning",
                    "summary": (
                        f"{field.field_name}: aktueller Case-Wert "
                        f"{_format_value(existing.value, existing.unit)} widerspricht "
                        f"{source_label}-Vorschlag {_format_value(field.proposed_value, field.unit)}."
                    ),
                    "resolution_status": "open",
                    "sources": [str(existing.source or "case_state"), source_label],
                    "source_event_id": event.event_id,
                }
            )

    return items


def build_governed_conflict_summary(state: GovernedSessionState) -> dict[str, Any]:
    items = build_governed_conflict_items(state)
    by_severity: dict[str, int] = {}
    open_count = 0
    resolved_count = 0
    for item in items:
        severity = str(item.get("severity") or "warning")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        if item.get("resolution_status") == "resolved":
            resolved_count += 1
        else:
            open_count += 1
    return {
        "total": len(items),
        "open": open_count,
        "resolved": resolved_count,
        "by_severity": by_severity,
        "items": items,
    }
