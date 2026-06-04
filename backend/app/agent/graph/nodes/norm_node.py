"""
norm_node — Phase H.1

Deterministic SealAI norm-object derivation for the governed path.

Responsibility:
    Build a bounded, versioned, manufacturer-neutral SealAI norm request from
    the productive governed state after governance, matching, RFQ, and dispatch
    have completed.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.graph import GraphState
from app.agent.state.models import (
    SealaiNormIdentity,
    SealaiNormMaterial,
    SealaiNormOperatingConditions,
    SealaiNormState,
)
from app.domain.engineering_path import derive_engineering_path
from app.domain.sealing_material_family import derive_sealing_material_family
from app.services.norm_modules import (
    EscalationPolicy,
    NormCheckResult,
    build_default_registry,
)

log = logging.getLogger(__name__)


def _asserted_value(state: GraphState, field_name: str) -> Any:
    claim = state.asserted.assertions.get(field_name)
    return None if claim is None else claim.asserted_value


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _session_request_id(state: GraphState) -> str | None:
    if not state.session_id:
        return None
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", state.session_id).strip("-")
    return f"sealai-{token}" if token else None


def _material_family(state: GraphState) -> str | None:
    direct = _asserted_value(state, "material")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    qualified = state.rfq.qualified_materials
    if qualified:
        family = qualified[0].get("material_family")
        if isinstance(family, str) and family.strip():
            return family.strip()
    return None


def _qualified_material_names(state: GraphState) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for material in state.rfq.qualified_materials:
        name = str(
            material.get("grade_name") or material.get("material_family") or ""
        ).strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def _application_summary(state: GraphState) -> str | None:
    parts: list[str] = []
    medium = _asserted_value(state, "medium")
    temperature_c = _as_float(_asserted_value(state, "temperature_c"))
    pressure_bar = _as_float(_asserted_value(state, "pressure_bar"))
    if medium:
        parts.append(str(medium))
    if temperature_c is not None:
        parts.append(f"{temperature_c:g}°C")
    if pressure_bar is not None:
        parts.append(f"{pressure_bar:g} bar")
    return ", ".join(parts) or None


def _norm_status(state: GraphState) -> str:
    if state.rfq.rfq_ready:
        return "rfq_ready"
    if (
        state.governance.requirement_class is not None
        and state.governance.gov_class in {"A", "B"}
    ):
        return "governed"
    if state.asserted.assertions:
        return "draft"
    return "pending"


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _dimension_value(state: GraphState, *field_names: str) -> Any:
    for field_name in field_names:
        value = _asserted_value(state, field_name)
        if value is not None and value != "":
            return value
        value = state.rfq.dimensions.get(field_name)
        if value is not None and value != "":
            return value
    return None


def _norm_context(
    state: GraphState, *, engineering_path: str | None, material_family: str | None
) -> dict[str, Any]:
    requirement_class = (
        state.rfq.requirement_class
        or state.dispatch.requirement_class
        or state.governance.requirement_class
    )
    material = derive_sealing_material_family(
        asserted_material=_asserted_value(state, "material"),
        sealai_norm_material_family=material_family,
        qualified_materials=state.rfq.qualified_materials,
    )
    return {
        "engineering_path": engineering_path,
        "seal_kind": _first_value(
            _asserted_value(state, "sealing_type"), _asserted_value(state, "seal_kind")
        ),
        "seal_type_family": _first_value(
            _asserted_value(state, "seal_family"),
            requirement_class.seal_type if requirement_class else None,
        ),
        "motion_type": _asserted_value(state, "motion_type"),
        "shaft_diameter_mm": _dimension_value(
            state, "shaft_diameter_mm", "shaft_diameter", "diameter"
        ),
        "housing_bore_diameter_mm": _dimension_value(
            state, "housing_bore_diameter_mm", "housing_diameter_mm", "bore_diameter_mm"
        ),
        "seal_width_mm": _dimension_value(state, "seal_width_mm", "width_mm"),
        "seal_type": _asserted_value(state, "seal_type"),
        "pressure_bar": _asserted_value(state, "pressure_bar"),
        "temperature_c": _asserted_value(state, "temperature_c"),
        "shaft_surface_finish": _asserted_value(state, "shaft_surface_finish"),
        "medium_name": _asserted_value(state, "medium"),
        "sealing_material_family": material,
        "material_name": _first_value(
            _asserted_value(state, "material_name"),
            _asserted_value(state, "material"),
            material_family,
        ),
        "cleaning_regime": _asserted_value(state, "cleaning_regime"),
        "food_contact_region": _asserted_value(state, "food_contact_region"),
        "intended_us_market": _asserted_value(state, "intended_us_market"),
        "certification_records": _asserted_value(state, "certification_records"),
        "manufacturer_declaration_present": _asserted_value(
            state, "manufacturer_declaration_present"
        ),
        "traceability_present": _asserted_value(state, "traceability_present"),
        "migration_test_available": _asserted_value(state, "migration_test_available"),
    }


def _norm_check_payload(result: NormCheckResult) -> dict[str, Any]:
    return {
        "module_id": result.module_id,
        "version": result.version,
        "status": result.status.value,
        "applies": result.applies,
        "missing_required_fields": list(result.missing_required_fields),
        "escalation": result.escalation.value,
        "references": list(result.references),
        "findings": [
            {
                "code": finding.code,
                "message": finding.message,
                "severity": finding.severity,
                "field": finding.field,
            }
            for finding in result.findings
        ],
    }


def _run_norm_checks(
    context: dict[str, Any],
) -> tuple[list[NormCheckResult], list[dict[str, Any]]]:
    try:
        return build_default_registry().run_checks(context), []
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log.warning("[norm_node] norm registry unavailable: %s", exc, exc_info=True)
        return [], [
            {
                "module_id": "norm_registry",
                "version": None,
                "status": "unavailable",
                "applies": False,
                "missing_required_fields": [],
                "escalation": EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW.value,
                "references": [],
                "findings": [
                    {
                        "code": "norm_registry_unavailable",
                        "message": "Norm module registry could not be evaluated; manufacturer review remains required.",
                        "severity": "review",
                        "field": None,
                    }
                ],
            }
        ]


async def norm_node(state: GraphState) -> GraphState:
    """Derive the bounded SealAI norm object from the current governed state."""
    requirement_class = (
        state.rfq.requirement_class
        or state.dispatch.requirement_class
        or state.governance.requirement_class
    )
    material_family = _material_family(state)
    engineering_path = derive_engineering_path(
        engineering_path=_asserted_value(state, "engineering_path"),
    )
    norm_results, registry_failures = _run_norm_checks(
        _norm_context(
            state, engineering_path=engineering_path, material_family=material_family
        )
    )
    norm_checks = [
        _norm_check_payload(result) for result in norm_results
    ] + registry_failures
    open_validation_points = list(state.governance.open_validation_points)
    for result in norm_results:
        for field_name in result.missing_required_fields:
            point = f"{result.module_id}:{field_name}"
            if point not in open_validation_points:
                open_validation_points.append(point)
        if result.escalation is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW:
            point = f"{result.module_id}:manufacturer_review_required"
            if point not in open_validation_points:
                open_validation_points.append(point)
    for failure in registry_failures:
        point = str(failure["findings"][0]["code"])
        if point not in open_validation_points:
            open_validation_points.append(point)
    manufacturer_validation_required = bool(open_validation_points) or any(
        result.has_blocking_issue
        or result.escalation is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW
        for result in norm_results
    )

    sealai_norm = SealaiNormState(
        status=_norm_status(state),
        identity=SealaiNormIdentity(
            sealai_request_id=_session_request_id(state),
            norm_version="sealai_norm_v1",
            requirement_class_id=requirement_class.class_id
            if requirement_class is not None
            else None,
            engineering_path=engineering_path,
            seal_family=requirement_class.seal_type
            if requirement_class is not None
            else None,
        ),
        application_summary=_application_summary(state),
        operating_conditions=SealaiNormOperatingConditions(
            medium=_asserted_value(state, "medium"),
            temperature_c=_as_float(_asserted_value(state, "temperature_c")),
            pressure_bar=_as_float(_asserted_value(state, "pressure_bar")),
            dynamic_type=_asserted_value(state, "dynamic_type"),
        ),
        geometry=dict(state.rfq.dimensions),
        material=SealaiNormMaterial(
            material_family=material_family,
            sealing_material_family=derive_sealing_material_family(
                asserted_material=_asserted_value(state, "material"),
                sealai_norm_material_family=material_family,
                qualified_materials=state.rfq.qualified_materials,
            ),
            qualified_materials=_qualified_material_names(state),
        ),
        assumptions=[
            assumption.description for assumption in state.normalized.assumptions
        ],
        validity_limits=list(state.governance.validity_limits),
        open_validation_points=open_validation_points,
        norm_checks=norm_checks,
        manufacturer_validation_required=manufacturer_validation_required,
    )

    log.debug(
        "[norm_node] status=%s requirement_class=%s geometry=%d assumptions=%d",
        sealai_norm.status,
        sealai_norm.identity.requirement_class_id,
        len(sealai_norm.geometry),
        len(sealai_norm.assumptions),
    )

    return state.model_copy(update={"sealai_norm": sealai_norm})
