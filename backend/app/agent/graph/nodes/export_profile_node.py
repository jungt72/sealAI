"""
export_profile_node — Phase H.2

Deterministic export-profile derivation for the governed path.

Responsibility:
    Build a bounded export profile from the SealAI norm core plus matching,
    RFQ, and dispatch readiness without introducing manufacturer-specific
    codes, connector details, or transport internals.
"""
from __future__ import annotations

import logging

from app.agent.graph import GraphState
from app.agent.state.models import ExportProfileState

log = logging.getLogger(__name__)


def _dimension_summary(state: GraphState) -> list[str]:
    return [
        f"{key}={value}"
        for key, value in sorted(state.sealai_norm.geometry.items())
        if value is not None
    ]


def _material_summary(state: GraphState) -> str | None:
    material_family = state.sealai_norm.material.material_family
    qualified = state.sealai_norm.material.qualified_materials
    if material_family and qualified:
        return f"{material_family} ({len(qualified)} qualified material candidates)"
    if material_family:
        return material_family
    if qualified:
        return qualified[0]
    return None


def _recipient_refs(state: GraphState) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for ref in state.rfq.recipient_refs:
        name = str(ref.manufacturer_name or "").strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def _unresolved_points(state: GraphState) -> list[str]:
    points: list[str] = []
    for item in (
        list(state.asserted.blocking_unknowns)
        + list(state.asserted.conflict_flags)
        + list(state.governance.open_validation_points)
    ):
        text = str(item or "").strip()
        if text and text not in points:
            points.append(text)
    return points


def _export_status(state: GraphState, recipients: list[str], unresolved_points: list[str]) -> str:
    if state.dispatch.dispatch_ready and state.rfq.rfq_ready and recipients:
        return "ready"
    if state.sealai_norm.identity.requirement_class_id or state.sealai_norm.application_summary:
        return "partial" if unresolved_points else "not_ready"
    if state.sealai_norm.status != "pending":
        return "not_ready"
    return "pending"


def _export_notes(state: GraphState) -> list[str]:
    notes: list[str] = []
    for note in list(state.rfq.notes) + list(state.dispatch.dispatch_notes):
        text = str(note or "").strip()
        if text and text not in notes:
            notes.append(text)
    return notes


async def export_profile_node(state: GraphState) -> GraphState:
    """Derive the bounded export profile from norm + commercial readiness."""
    selected = state.rfq.selected_manufacturer_ref or state.dispatch.selected_manufacturer_ref or state.matching.selected_manufacturer_ref
    recipients = _recipient_refs(state)
    unresolved_points = _unresolved_points(state)
    export_profile = ExportProfileState(
        status=_export_status(state, recipients, unresolved_points),
        export_profile_version="sealai_export_profile_v1",
        sealai_request_id=state.sealai_norm.identity.sealai_request_id,
        selected_manufacturer=selected.manufacturer_name if selected is not None else None,
        recipient_refs=recipients,
        requirement_class_id=state.sealai_norm.identity.requirement_class_id,
        application_summary=state.sealai_norm.application_summary,
        dimensions_summary=_dimension_summary(state),
        material_summary=_material_summary(state),
        rfq_ready=state.rfq.rfq_ready,
        dispatch_ready=state.dispatch.dispatch_ready,
        unresolved_points=unresolved_points,
        export_notes=_export_notes(state),
    )

    log.debug(
        "[export_profile_node] status=%s requirement_class=%s recipients=%d",
        export_profile.status,
        export_profile.requirement_class_id,
        len(export_profile.recipient_refs),
    )

    return state.model_copy(update={"export_profile": export_profile})
