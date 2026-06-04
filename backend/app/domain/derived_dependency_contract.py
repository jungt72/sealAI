"""Shared dependency/stale contract for derived engineering values."""
from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from typing import Any

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
        "rpm",
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
    "circumferential_speed": (
        "shaft_diameter",
        "shaft_diameter_mm",
        "speed_rpm",
        "rpm",
    ),
    "pv_load": (
        "pressure_nominal",
        "pressure_bar",
        "pressure_peak",
        "circumferential_speed",
    ),
    "temperature_risk": (
        "temperature_max",
        "temperature_c",
        "candidate_materials",
        "medium_name",
        "medium",
    ),
    "material_direction": (
        "medium_name",
        "medium",
        "temperature_max",
        "temperature_c",
        "motion_type",
        "movement_type",
        "pressure_nominal",
        "pressure_bar",
        "speed_rpm",
    ),
    "readiness_level": (
        "asset_type",
        "seal_location",
        "motion_type",
        "movement_type",
        "medium_name",
        "medium",
        "operating_conditions",
        "geometry",
        "geometry_context",
        "conflicts",
        "blocking_unknowns",
    ),
    "rwdr_pv_precheck": (
        "pressure_nominal",
        "pressure_bar",
        "pressure_peak",
        "shaft_diameter",
        "shaft_diameter_mm",
        "speed_rpm",
        "rpm",
    ),
    "rwdr_dn_value": ("shaft_diameter", "shaft_diameter_mm", "speed_rpm", "rpm"),
    "rwdr_circumferential_speed": (
        "shaft_diameter",
        "shaft_diameter_mm",
        "speed_rpm",
        "rpm",
    ),
}

_ALIAS_GROUPS: tuple[set[str], ...] = (
    {"medium", "medium_name"},
    {"temperature_c", "temperature_max"},
    {"pressure_bar", "pressure_nominal", "pressure_peak"},
    {"speed_rpm", "rpm"},
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


def mark_stale_snapshot_derived_values(
    state_json: dict[str, Any],
    *,
    changed_fields: Iterable[str],
    new_revision: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Return a snapshot dict with dependent derived values marked stale."""
    impacted = dependent_derived_value_ids(changed_fields)
    if not impacted:
        return state_json

    updated = deepcopy(state_json)
    stale_reason = reason or "accepted_input_changed"

    top_level_derived_values = updated.get("derived_values")
    has_top_level_derived_values = isinstance(top_level_derived_values, dict)
    derived = updated.get("derived")
    has_nested_derived_values = (
        isinstance(derived, dict) and isinstance(derived.get("derived_values"), dict)
    )

    if has_nested_derived_values or not has_top_level_derived_values:
        nested_derived = _dict_child(updated, "derived")
        _mark_derived_value_mapping_stale(
            _dict_child(nested_derived, "derived_values"),
            field_status=_dict_child(nested_derived, "field_status"),
            stale_ids=_list_child(nested_derived, "stale_derived_value_ids"),
            impacted=impacted,
            new_revision=new_revision,
            stale_reason=stale_reason,
            create_missing=True,
        )

    if has_top_level_derived_values:
        _mark_derived_value_mapping_stale(
            top_level_derived_values,
            field_status=_dict_child(updated, "field_status"),
            stale_ids=_list_child(updated, "stale_derived_value_ids"),
            impacted=impacted,
            new_revision=new_revision,
            stale_reason=stale_reason,
            create_missing=False,
        )

    return updated


def _mark_derived_value_mapping_stale(
    derived_values: dict[str, Any],
    *,
    field_status: dict[str, Any],
    stale_ids: list[Any],
    impacted: list[str],
    new_revision: int,
    stale_reason: str,
    create_missing: bool,
) -> None:
    for value_id in impacted:
        current = derived_values.get(value_id)
        if not isinstance(current, dict):
            if not create_missing:
                continue
            current = {
                "value": None,
                "derived_from_fields": list(DEPENDENCY_GRAPH.get(value_id, ())),
                "derived_from_revision": max(new_revision - 1, 0),
                "calculation_id": value_id,
                "ruleset_version": RULESET_VERSION,
            }
        else:
            current = dict(current)
            current.setdefault(
                "derived_from_fields",
                list(DEPENDENCY_GRAPH.get(value_id, ())),
            )
            current.setdefault("derived_from_revision", max(new_revision - 1, 0))
            current.setdefault("calculation_id", value_id)
            current.setdefault("ruleset_version", RULESET_VERSION)

        current["status"] = "stale"
        current["stale_reason"] = stale_reason
        derived_values[value_id] = current
        field_status[value_id] = "stale"
        if value_id not in stale_ids:
            stale_ids.append(value_id)


def _dict_child(parent: dict[str, Any], key: str) -> dict[str, Any]:
    child = parent.get(key)
    if isinstance(child, dict):
        return child
    child = {}
    parent[key] = child
    return child


def _list_child(parent: dict[str, Any], key: str) -> list[Any]:
    child = parent.get(key)
    if isinstance(child, list):
        return child
    child = []
    parent[key] = child
    return child
