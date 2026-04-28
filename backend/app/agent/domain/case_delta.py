"""v0.4 Structured Double Output and CaseEvent helpers.

The LLM-facing extraction layer may propose deltas. This module deliberately
keeps them non-authoritative until a backend acceptance path applies them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from app.agent.state.models import (
    CaseEvent,
    ConfidenceLevel,
    EngineeringValue,
    GovernedPersistenceMarker,
    ObservedExtraction,
    GovernedSessionState,
    ProposedCaseDelta,
    ProposedCaseDeltaField,
)
from app.agent.domain.normalization import (
    MappingConfidence,
    normalize_critical_field_value,
)
from app.domain.critical_field_contract import CRITICAL_CASE_FIELDS, PRESSURE_FIELDS

_ALLOWED_DELTA_FIELDS: frozenset[str] = CRITICAL_CASE_FIELDS | frozenset(
    {
        "medium",
        "geometry_context",
        "geometry",
        "sealing_type",
        "pressure_direction",
        "duty_profile",
        "installation",
        "contamination",
        "counterface_surface",
        "tolerances",
        "industry",
        "compliance",
        "medium_qualifiers",
        "material",
    }
)


def confidence_from_extraction(value: float | str | None) -> ConfidenceLevel:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in {"confirmed", "estimated", "inferred", "requires_confirmation"}:
            return normalized  # type: ignore[return-value]
    try:
        numeric = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return "requires_confirmation"
    if numeric >= 0.9:
        return "estimated"
    if numeric >= 0.7:
        return "inferred"
    return "requires_confirmation"


def proposed_case_delta_from_extractions(
    extractions: Iterable[ObservedExtraction],
    *,
    turn_index: int,
) -> ProposedCaseDelta:
    fields: list[ProposedCaseDeltaField] = []
    seen: set[str] = set()
    for extraction in extractions:
        if extraction.turn_index != turn_index:
            continue
        field_name = str(extraction.field_name or "").strip()
        if field_name not in _ALLOWED_DELTA_FIELDS or field_name in seen:
            continue
        if extraction.raw_value in (None, "", []):
            continue
        confidence = confidence_from_extraction(extraction.confidence)
        engineering_value = None
        confirmation_required = confidence == "requires_confirmation"
        normalized = normalize_critical_field_value(
            field_name,
            extraction.raw_value,
            unit=extraction.raw_unit,
        )
        if normalized is not None:
            engineering_value = EngineeringValue(**normalized.as_engineering_value_dict())
            if normalized.confidence == MappingConfidence.REQUIRES_CONFIRMATION:
                confidence = "requires_confirmation"
                confirmation_required = True
            else:
                confirmation_required = False
        seen.add(field_name)
        fields.append(
            ProposedCaseDeltaField(
                field_name=field_name,
                proposed_value=extraction.raw_value,
                unit=extraction.raw_unit,
                provenance="user_stated" if extraction.source in {"llm", "user"} else "inferred",
                confidence=confidence,
                engineering_value=engineering_value,
                confirmation_required=confirmation_required,
                source_turn_index=extraction.turn_index,
                status="proposed",
            )
        )
    return ProposedCaseDelta(fields=fields, source="llm")


def _revision_before(marker: GovernedPersistenceMarker | None) -> int:
    if marker is None:
        return 0
    return int(marker.postgres_case_revision or marker.postgres_snapshot_revision or 0)


def build_assistant_delta_event(
    *,
    case_id: str,
    turn_index: int,
    assistant_message: str,
    delta: ProposedCaseDelta,
    persistence_marker: GovernedPersistenceMarker | None = None,
) -> CaseEvent:
    before = _revision_before(persistence_marker)
    now = datetime.now(timezone.utc).isoformat()
    return CaseEvent(
        case_id=case_id,
        turn_id=f"turn-{turn_index}",
        actor="assistant",
        actor_type="assistant",
        event_type="assistant_delta_proposed",
        assistant_message=assistant_message,
        source_turn_id=f"turn-{turn_index}",
        proposed_case_delta=delta,
        accepted_delta={},
        rejected_delta={},
        state_revision_before=before,
        state_revision_after=before + 1 if before >= 0 else 0,
        created_at=now,
    )


def build_document_delta_event(
    *,
    case_id: str,
    document_id: str,
    filename: str | None,
    delta: ProposedCaseDelta,
    persistence_marker: GovernedPersistenceMarker | None = None,
) -> CaseEvent:
    """Build an append-only document proposal without accepting any value."""
    before = _revision_before(persistence_marker)
    now = datetime.now(timezone.utc).isoformat()
    label = filename or document_id
    return CaseEvent(
        case_id=case_id,
        turn_id=f"document-{document_id}",
        actor="system",
        actor_type="system",
        event_type="document_delta_proposed",
        assistant_message=f"Document input proposed case fields from {label}.",
        source_document_id=document_id,
        proposed_case_delta=delta,
        accepted_delta={},
        rejected_delta={},
        state_revision_before=before,
        state_revision_after=before + 1 if before >= 0 else 0,
        created_at=now,
    )


def latest_proposed_delta_event(state: GovernedSessionState) -> CaseEvent | None:
    """Return the newest proposal with at least one proposed field."""
    for event in reversed(state.case_events):
        if event.event_type not in {"assistant_delta_proposed", "document_delta_proposed"}:
            continue
        if event.proposed_case_delta.fields:
            return event
    return None


def select_delta_fields(
    delta: ProposedCaseDelta,
    *,
    field_names: Iterable[str] | None = None,
) -> list[ProposedCaseDeltaField]:
    requested = {str(name).strip() for name in field_names or [] if str(name).strip()}
    selected: list[ProposedCaseDeltaField] = []
    seen: set[str] = set()
    for field in delta.fields:
        if field.status != "proposed":
            continue
        if requested and field.field_name not in requested:
            continue
        if field.field_name in seen:
            continue
        seen.add(field.field_name)
        selected.append(field)
    return selected


def _acceptance_block_reason(field: ProposedCaseDeltaField) -> str | None:
    if field.field_name not in PRESSURE_FIELDS:
        return None
    engineering_value = field.engineering_value
    interpretation = (
        str(engineering_value.interpretation or "").strip()
        if engineering_value is not None
        else ""
    )
    if interpretation in {"", "unknown"}:
        return "pressure interpretation requires confirmation before acceptance"
    return None


def build_case_delta_decision_event(
    *,
    case_id: str,
    action: str,
    fields: Iterable[ProposedCaseDeltaField],
    source_event_id: str | None = None,
    persistence_marker: GovernedPersistenceMarker | None = None,
) -> CaseEvent:
    """Build an append-only user decision event for proposed case delta fields."""
    before = _revision_before(persistence_marker)
    now = datetime.now(timezone.utc).isoformat()
    accepted: dict[str, Any] = {}
    rejected: dict[str, Any] = {}
    event_type = "case_delta_accepted" if action == "accept" else "case_delta_rejected"
    status = "accepted" if action == "accept" else "rejected"
    for field in fields:
        if action == "accept":
            block_reason = _acceptance_block_reason(field)
            if block_reason is not None:
                raise ValueError(
                    f"{field.field_name} cannot be accepted: {block_reason}"
                )
        payload = field.model_copy(update={"status": status}).model_dump(mode="json")
        payload["source_event_id"] = source_event_id
        if action == "accept":
            accepted[field.field_name] = payload
        else:
            rejected[field.field_name] = payload

    return CaseEvent(
        case_id=case_id,
        actor="user",
        actor_type="user",
        event_type=event_type,
        source_turn_id=source_event_id,
        proposed_case_delta=ProposedCaseDelta(fields=[]),
        accepted_delta=accepted,
        rejected_delta=rejected,
        state_revision_before=before,
        state_revision_after=before + 1 if before >= 0 else 0,
        created_at=now,
    )
