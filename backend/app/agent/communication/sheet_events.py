"""Sheet-Chat contract — structured sheet events through the State Gate (Blueprint §9, §29.5).

The four sheet events (``sheet_field_edit``, ``sheet_bulk_input``,
``sheet_conflict_resolution``, ``sheet_to_rfq``) reuse the **same** deterministic
State Gate (``reduce_observed_to_normalized`` → ``reduce_normalized_to_asserted``)
as Patch 5/7 — no second mutation logic. Concurrency rules (§9):

* ``client_event_id`` provides idempotency: a repeated event id does not mutate
  again.
* ``case_revision_seen`` provides stale detection: a stale write degrades to a
  field-level ``warning`` conflict (§12.6) instead of blocking the whole case.

Chat output is produced only when the change is technically relevant (§9.5/§32.11).
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Any, Literal

from app.agent.state.models import (
    ConflictRef,
    GovernedSessionState,
    UserOverride,
)
from app.agent.state.reducers import (
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)
from app.agent.v92.dashboard_contract import extract_case_revision
from pydantic import BaseModel, Field

SheetEventType = Literal[
    "sheet_field_edit",
    "sheet_bulk_input",
    "sheet_conflict_resolution",
    "sheet_to_rfq",
]

# Event type → field provenance stamp (§12.2). A conflict resolution is a
# deliberate single-field edit.
_EVENT_PROVENANCE: dict[str, str] = {
    "sheet_field_edit": "sheet_field_edit",
    "sheet_bulk_input": "sheet_bulk_input",
    "sheet_conflict_resolution": "sheet_field_edit",
}

# Liability-bearing / calculation-relevant fields whose change warrants a chat
# comment (§9.5). Edits outside this set with no conflict stay silent (§9.6).
_RELEVANT_FIELDS: frozenset[str] = frozenset(
    {
        "temperature_c",
        "pressure_bar",
        "pressure_system_bar",
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "speed_rpm",
        "shaft_diameter_mm",
        "medium",
        "material",
        "sealing_type",
    }
)


class SheetFieldValue(BaseModel):
    field_name: str
    value: Any = None
    unit: str | None = None


class SheetEvent(BaseModel):
    event_type: SheetEventType
    fields: list[SheetFieldValue] = Field(default_factory=list)
    client_event_id: str | None = None
    case_revision_seen: int | None = None
    source: str = "cockpit_sheet"
    turn_index: int = 0


@dataclass
class SheetEventResult:
    state: GovernedSessionState
    applied: bool = False
    already_applied: bool = False
    stale: bool = False
    chat_relevant: bool = False
    rfq_requested: bool = False
    conflicts: list[dict[str, Any]] = dataclass_field(default_factory=list)


def _stamp_provenance(container: Any, field_name: str, provenance: str) -> None:
    params = getattr(container, "parameters", None)
    if isinstance(params, dict) and field_name in params:
        param = params[field_name]
        case_field = getattr(param, "case_field", None)
        if case_field is not None:
            case_field.provenance = provenance
        try:
            param.provenance = provenance
        except (AttributeError, ValueError):  # pragma: no cover - defensive
            pass


def _is_stale(state: GovernedSessionState, event: SheetEvent) -> bool:
    if event.case_revision_seen is None:
        return False
    current = extract_case_revision(state)
    return current is not None and event.case_revision_seen < current


def _chat_relevant(
    event: SheetEvent,
    *,
    changed_fields: list[str],
    stale: bool,
    has_conflicts: bool,
) -> bool:
    if event.event_type in {"sheet_conflict_resolution", "sheet_to_rfq"}:
        return True
    if stale or has_conflicts:
        return True
    return any(name in _RELEVANT_FIELDS for name in changed_fields)


def apply_sheet_event(
    state: GovernedSessionState,
    event: SheetEvent,
    *,
    seen_event_ids: set[str] | None = None,
) -> SheetEventResult:
    """Apply a sheet event through the State Gate with idempotency + stale rules.

    ``seen_event_ids`` is the caller-owned set of already-applied
    ``client_event_id`` values; it is updated in place on a fresh apply.
    """
    seen = seen_event_ids if seen_event_ids is not None else set()

    # Idempotency (§9 / §13.4): a repeated client_event_id never mutates twice.
    if event.client_event_id and event.client_event_id in seen:
        return SheetEventResult(state=state, applied=False, already_applied=True)

    # sheet_to_rfq is a readiness trigger, not a mutation (RFQ itself is Patch 9).
    if event.event_type == "sheet_to_rfq":
        if event.client_event_id:
            seen.add(event.client_event_id)
        return SheetEventResult(
            state=state, applied=False, chat_relevant=True, rfq_requested=True
        )

    stale = _is_stale(state, event)

    observed = state.observed
    changed_fields: list[str] = []
    for sheet_field in event.fields:
        name = str(sheet_field.field_name or "").strip()
        if not name:
            continue
        observed = observed.with_override(
            UserOverride(
                field_name=name,
                override_value=sheet_field.value,
                override_unit=sheet_field.unit,
                turn_index=event.turn_index,
            )
        )
        changed_fields.append(name)

    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)

    provenance = _EVENT_PROVENANCE.get(event.event_type, "structured_form_input")
    for name in changed_fields:
        _stamp_provenance(normalized, name, provenance)
        _stamp_provenance(asserted, name, provenance)

    # Stale write degrades to a field-level warning, not a case block (§12.6).
    if stale:
        stale_conflicts = [
            ConflictRef(
                field_name=name,
                description=(
                    f"stale_sheet_write: edited against revision "
                    f"{event.case_revision_seen}, current {extract_case_revision(state)}"
                ),
                severity="warning",
            )
            for name in changed_fields
        ]
        normalized = normalized.model_copy(
            update={"conflicts": list(normalized.conflicts) + stale_conflicts}
        )

    new_state = state.model_copy(
        update={"observed": observed, "normalized": normalized, "asserted": asserted}
    )

    if event.client_event_id:
        seen.add(event.client_event_id)

    conflicts = [conflict.model_dump(mode="json") for conflict in normalized.conflicts]
    chat_relevant = _chat_relevant(
        event,
        changed_fields=changed_fields,
        stale=stale,
        has_conflicts=bool(conflicts),
    )
    return SheetEventResult(
        state=new_state,
        applied=bool(changed_fields),
        stale=stale,
        chat_relevant=chat_relevant,
        conflicts=conflicts,
    )
