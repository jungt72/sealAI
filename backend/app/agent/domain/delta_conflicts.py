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



def detect_delta_conflicts(
    *,
    current_case_state: dict[str, Any],
    accepted_delta_candidate: dict[str, Any],
    field_tolerances: dict[str, float] | None = None,
    provenance_priority: dict[str, int] | None = None,
) -> dict[str, Any]:
    """ADR-005 service contract for deterministic delta conflict detection.

    This function is intentionally independent from the UI projection. It can be
    used before accepting a candidate delta to decide whether to accept, stale
    dependents, or ask a resolution question.
    """
    field_tolerances = dict(field_tolerances or {})
    provenance_priority = dict(provenance_priority or {})
    conflicts: list[dict[str, Any]] = []

    for field_name, candidate_payload in accepted_delta_candidate.items():
        if isinstance(candidate_payload, dict):
            new_value = candidate_payload.get("proposed_value", candidate_payload.get("value"))
            new_provenance = str(candidate_payload.get("provenance") or "unknown")
        else:
            new_value = candidate_payload
            new_provenance = "unknown"

        current_payload = current_case_state.get(field_name)
        if current_payload is None:
            continue
        if isinstance(current_payload, dict):
            old_value = current_payload.get("value", current_payload.get("asserted_value"))
            old_provenance = str(current_payload.get("provenance") or current_payload.get("source") or "case_state")
        else:
            old_value = current_payload
            old_provenance = "case_state"

        old_canonical = _canonical_value(old_value)
        new_canonical = _canonical_value(new_value)
        if old_canonical == new_canonical:
            continue

        tolerance = field_tolerances.get(field_name)
        if tolerance is not None:
            try:
                if abs(float(str(old_value).replace(',', '.')) - float(str(new_value).replace(',', '.'))) <= tolerance:
                    continue
            except (TypeError, ValueError):
                pass

        old_rank = provenance_priority.get(old_provenance, 0)
        new_rank = provenance_priority.get(new_provenance, 0)
        resolution = "accept_new_value_and_invalidate_dependents" if new_rank >= old_rank else "requires_user_resolution"
        severity = "blocking" if resolution == "requires_user_resolution" else "warning"
        conflicts.append(
            {
                "conflict_type": "value_replacement",
                "field": field_name,
                "old_value": old_value,
                "new_value": new_value,
                "old_provenance": old_provenance,
                "new_provenance": new_provenance,
                "resolution": resolution,
                "severity": severity,
            }
        )

    severity_rank = {"none": 0, "warning": 1, "blocking": 2}
    conflict_severity = "none"
    for conflict in conflicts:
        severity = str(conflict.get("severity") or "warning")
        if severity_rank.get(severity, 0) > severity_rank.get(conflict_severity, 0):
            conflict_severity = severity

    suggested_question = None
    blocking = [item for item in conflicts if item.get("severity") == "blocking"]
    if blocking:
        first = blocking[0]
        suggested_question = (
            f"Ich habe fuer {first['field']} zwei unterschiedliche Werte: "
            f"{_format_value(first['old_value'])} und {_format_value(first['new_value'])}. "
            "Welcher Wert soll fuer den Fall gelten?"
        )

    return {
        "conflicts": conflicts,
        "conflict_severity": conflict_severity,
        "suggested_resolution_question": suggested_question,
    }

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
