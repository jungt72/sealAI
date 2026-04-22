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
        name = str(material.get("grade_name") or material.get("material_family") or "").strip()
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
    if state.governance.requirement_class is not None and state.governance.gov_class in {"A", "B"}:
        return "governed"
    if state.asserted.assertions:
        return "draft"
    return "pending"


async def norm_node(state: GraphState) -> GraphState:
    """Derive the bounded SealAI norm object from the current governed state."""
    requirement_class = state.rfq.requirement_class or state.dispatch.requirement_class or state.governance.requirement_class
    material_family = _material_family(state)

    sealai_norm = SealaiNormState(
        status=_norm_status(state),
        identity=SealaiNormIdentity(
            sealai_request_id=_session_request_id(state),
            norm_version="sealai_norm_v1",
            requirement_class_id=requirement_class.class_id if requirement_class is not None else None,
            engineering_path=derive_engineering_path(
                engineering_path=_asserted_value(state, "engineering_path"),
            ),
            seal_family=requirement_class.seal_type if requirement_class is not None else None,
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
        assumptions=[assumption.description for assumption in state.normalized.assumptions],
        validity_limits=list(state.governance.validity_limits),
        open_validation_points=list(state.governance.open_validation_points),
        manufacturer_validation_required=bool(state.governance.open_validation_points),
    )

    log.debug(
        "[norm_node] status=%s requirement_class=%s geometry=%d assumptions=%d",
        sealai_norm.status,
        sealai_norm.identity.requirement_class_id,
        len(sealai_norm.geometry),
        len(sealai_norm.assumptions),
    )

    return state.model_copy(update={"sealai_norm": sealai_norm})
