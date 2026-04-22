# backend/app/api/v1/projections/workspace_routing.py
"""Deterministic workspace request/path routing helpers.

This module is part of the SSoT workspace projection. It owns only routing
classification, not state mutation or UI rendering.
"""

from __future__ import annotations

from typing import Any, Dict

from app.api.v1.schemas.case_workspace import (
    EngineeringPath as WorkspaceEngineeringPath,
    RequestType as WorkspaceRequestType,
)

_REQUEST_TYPE_VALUES: frozenset[str] = frozenset(
    {
        "new_design",
        "retrofit",
        "rca_failure_analysis",
        "validation_check",
        "spare_part_identification",
        "quick_engineering_check",
    }
)

_ENGINEERING_PATH_VALUES: frozenset[str] = frozenset(
    {
        "ms_pump",
        "rwdr",
        "static",
        "labyrinth",
        "hyd_pneu",
        "unclear_rotary",
    }
)


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _has_marker(texts: list[str], markers: tuple[str, ...]) -> bool:
    return any(marker in text for text in texts for marker in markers)


def _coerce_request_type(value: Any) -> WorkspaceRequestType | None:
    text = _normalize_text(value)
    if text in _REQUEST_TYPE_VALUES:
        return text  # type: ignore[return-value]
    return None


def _coerce_engineering_path(value: Any) -> WorkspaceEngineeringPath | None:
    text = _normalize_text(value)
    if text in _ENGINEERING_PATH_VALUES:
        return text  # type: ignore[return-value]
    return None


def _derive_request_type(
    *,
    profile: Dict[str, Any],
    system: Dict[str, Any],
    reasoning: Dict[str, Any],
) -> WorkspaceRequestType | None:
    explicit_request_type = (
        _coerce_request_type(system.get("request_type"))
        or _coerce_request_type(_d(system.get("routing")).get("request_type"))
        or _coerce_request_type(reasoning.get("request_type"))
    )
    if explicit_request_type is not None:
        return explicit_request_type

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in (
            "geometry_locked",
            "old_part_known",
            "old_part_dimensions",
            "allowed_changes",
            "available_radial_space_mm",
            "available_axial_space_mm",
            "cavity_standard_known",
        )
    ):
        return "retrofit"

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in (
            "symptom_class",
            "failure_timing",
            "damage_pattern",
            "leakage_pattern",
            "runtime_to_failure",
            "runtime_to_failure_hours",
            "operating_phase_of_failure",
            "inspection_findings",
        )
    ):
        return "rca_failure_analysis"

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in (
            "validation_target",
            "validation_basis",
            "existing_design_reference",
        )
    ):
        return "validation_check"

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in (
            "part_number",
            "old_part_number",
            "manufacturer_part_number",
            "spare_part_reference",
        )
    ):
        return "spare_part_identification"

    if any(
        profile.get(key) not in (None, "", [], {})
        for key in ("requested_check", "calc_id", "target_formula")
    ):
        return "quick_engineering_check"

    return None


def _derive_engineering_path(
    *,
    profile: Dict[str, Any],
    system: Dict[str, Any],
    reasoning: Dict[str, Any],
) -> WorkspaceEngineeringPath | None:
    explicit_path = (
        _coerce_engineering_path(system.get("engineering_path"))
        or _coerce_engineering_path(_d(system.get("routing")).get("path"))
        or _coerce_engineering_path(reasoning.get("engineering_path"))
        or _coerce_engineering_path(profile.get("engineering_path"))
        or _coerce_engineering_path(profile.get("path"))
        or _coerce_engineering_path(profile.get("routing_path"))
    )
    if explicit_path is not None:
        return explicit_path

    motion_type = _normalize_text(
        profile.get("movement_type") or profile.get("motion_type")
    )
    texts = [
        _normalize_text(profile.get("installation")),
        _normalize_text(profile.get("application_context")),
        _normalize_text(profile.get("application_category")),
        _normalize_text(profile.get("geometry_context")),
        _normalize_text(profile.get("sealing_type")),
        _normalize_text(
            _d(system.get("answer_contract")).get("requirement_class_hint")
        ),
        _normalize_text(
            _d(_d(system.get("answer_contract")).get("requirement_class")).get(
                "seal_type"
            )
        ),
    ]
    texts = [text for text in texts if text]

    if _has_marker(texts, ("labyrinth",)):
        return "labyrinth"

    if motion_type == "static" or _has_marker(
        texts, ("static_sealing", "housing_sealing", "flachdichtung", "static seal")
    ):
        return "static"

    if _has_marker(
        texts,
        (
            "rwdr",
            "wellendichtring",
            "radialwellendichtring",
            "radial shaft",
            "simmerring",
            "lip seal",
        ),
    ):
        return "rwdr"

    if _has_marker(
        texts, ("hydraul", "pneumat", "zylinder", "cylinder", "rod", "kolbenstange")
    ):
        return "hyd_pneu"

    if motion_type == "rotary":
        if _has_marker(
            texts,
            ("pump", "kreiselpumpe", "mechanical_seal", "mechanical seal", "gleitring"),
        ):
            return "ms_pump"
        if _has_marker(
            texts,
            (
                "rwdr",
                "wellendichtring",
                "radial shaft",
                "radialwellendichtring",
                "simmerring",
                "gearbox",
                "lip seal",
            ),
        ):
            return "rwdr"
        return "unclear_rotary"

    return None
