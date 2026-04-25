"""v0.4 dependency graph and stale handling for derived engineering values."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.agent.state.models import DerivedState, DerivedValue

RULESET_VERSION = "v0.4-mvp-2026-04-25"

CRITICAL_INPUT_FIELDS: frozenset[str] = frozenset(
    {
        "asset_type",
        "seal_location",
        "motion_type",
        "medium_name",
        "temperature_min",
        "temperature_max",
        "pressure_nominal",
        "pressure_peak",
        "speed_rpm",
        "shaft_diameter",
        "housing_bore",
        "installation_width",
        "shaft_material",
        "surface_finish",
        "food_contact",
        "atex_relevance",
        # legacy/current aliases used by the existing runtime
        "medium",
        "temperature_c",
        "pressure_bar",
        "shaft_diameter_mm",
        "movement_type",
        "geometry_context",
        "counterface_surface",
        "atex",
    }
)

DEPENDENCY_GRAPH: dict[str, tuple[str, ...]] = {
    "circumferential_speed": ("shaft_diameter", "shaft_diameter_mm", "speed_rpm"),
    "pv_load": ("pressure_nominal", "pressure_bar", "circumferential_speed"),
    "temperature_risk": ("temperature_max", "temperature_c", "candidate_materials", "medium_name", "medium"),
    "material_direction": ("medium_name", "medium", "temperature_max", "temperature_c", "motion_type", "movement_type", "pressure_nominal", "pressure_bar", "speed_rpm"),
    "readiness_level": ("asset_type", "seal_location", "motion_type", "movement_type", "medium_name", "medium", "operating_conditions", "geometry", "geometry_context", "conflicts", "blocking_unknowns"),
    "rwdr_pv_precheck": ("pressure_nominal", "pressure_bar", "shaft_diameter", "shaft_diameter_mm", "speed_rpm"),
    "rwdr_dn_value": ("shaft_diameter", "shaft_diameter_mm", "speed_rpm"),
    "rwdr_circumferential_speed": ("shaft_diameter", "shaft_diameter_mm", "speed_rpm"),
}

_ALIAS_GROUPS: tuple[set[str], ...] = (
    {"medium", "medium_name"},
    {"temperature_c", "temperature_max"},
    {"pressure_bar", "pressure_nominal"},
    {"shaft_diameter_mm", "shaft_diameter"},
    {"movement_type", "motion_type"},
    {"geometry_context", "seal_location", "geometry"},
    {"counterface_surface", "surface_finish"},
    {"atex", "atex_relevance"},
)


def expand_changed_fields(fields: Iterable[str]) -> set[str]:
    expanded = {str(field).strip() for field in fields if str(field).strip()}
    changed = True
    while changed:
        changed = False
        for group in _ALIAS_GROUPS:
            if expanded.intersection(group) and not group.issubset(expanded):
                expanded.update(group)
                changed = True
    return expanded


def dependent_derived_value_ids(changed_fields: Iterable[str]) -> list[str]:
    changed = expand_changed_fields(changed_fields)
    result: list[str] = []
    known_inputs = set(changed)
    graph_remaining = dict(DEPENDENCY_GRAPH)
    progressed = True
    while progressed:
        progressed = False
        for value_id, dependencies in list(graph_remaining.items()):
            if set(dependencies).intersection(known_inputs):
                result.append(value_id)
                known_inputs.add(value_id)
                del graph_remaining[value_id]
                progressed = True
    return result


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
