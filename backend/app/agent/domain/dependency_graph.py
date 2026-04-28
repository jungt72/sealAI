"""v0.4 dependency graph and stale handling for derived engineering values."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.domain.derived_dependency_contract import (
    CRITICAL_INPUT_FIELDS,
    DEPENDENCY_GRAPH,
    RULESET_VERSION,
    dependent_derived_value_ids,
    expand_changed_fields,
    mark_stale_snapshot_derived_values,
)
from app.agent.state.models import DerivedState, DerivedValue


def mark_stale_derived_values(
    derived: DerivedState,
    *,
    changed_fields: Iterable[str],
    new_revision: int,
    reason: str | None = None,
) -> DerivedState:
    """Return a DerivedState where dependent derived values are marked stale."""
    impacted = dependent_derived_value_ids(changed_fields)
    if not impacted:
        return derived

    stale_reason = reason or "accepted_input_changed"
    values: dict[str, DerivedValue] = dict(derived.derived_values)
    for value_id in impacted:
        current = values.get(value_id)
        if current is None:
            current = DerivedValue(
                value=None,
                status="unknown",
                derived_from_fields=list(DEPENDENCY_GRAPH.get(value_id, ())),
                derived_from_revision=max(new_revision - 1, 0),
                calculation_id=value_id,
                ruleset_version=RULESET_VERSION,
            )
        values[value_id] = current.model_copy(
            update={
                "status": "stale",
                "stale_reason": stale_reason,
                "ruleset_version": current.ruleset_version or RULESET_VERSION,
            }
        )

    field_status = dict(derived.field_status)
    for value_id in impacted:
        field_status[value_id] = "stale"

    stale_ids = list(dict.fromkeys(list(derived.stale_derived_value_ids) + impacted))
    return derived.model_copy(
        update={
            "derived_values": values,
            "stale_derived_value_ids": stale_ids,
            "field_status": field_status,
        }
    )


def derived_values_for_projection(derived: DerivedState) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for value_id, item in derived.derived_values.items():
        items.append(
            {
                "id": value_id,
                "value": item.value,
                "status": item.status,
                "derived_from_fields": list(item.derived_from_fields),
                "derived_from_revision": item.derived_from_revision,
                "calculation_id": item.calculation_id or value_id,
                "ruleset_version": item.ruleset_version,
                "stale_reason": item.stale_reason,
            }
        )
    return items
