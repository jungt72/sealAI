"""
dispatch_contract_node — Phase I.1

Deterministic connector-ready handover contract.

Responsibility:
    Build a stable, systemneutral dispatch contract from the bounded dispatch,
    norm, export profile, and manufacturer mapping layers without introducing
    connector-specific IDs or transport internals.
"""
from __future__ import annotations

import logging

from app.agent.graph import GraphState
from app.agent.state.models import DispatchContractState

log = logging.getLogger(__name__)


def _contract_unresolved_points(state: GraphState) -> list[str]:
    unresolved: list[str] = []
    for item in (
        list(state.export_profile.unresolved_points)
        + list(state.manufacturer_mapping.unresolved_mapping_points)
        + list(state.governance.open_validation_points)
    ):
        text = str(item or "").strip()
        if text and text not in unresolved:
            unresolved.append(text)
    return unresolved


def _mapping_summary(state: GraphState) -> str | None:
    parts: list[str] = []
    mapping = state.manufacturer_mapping
    if mapping.mapped_product_family:
        parts.append(f"product_family={mapping.mapped_product_family}")
    if mapping.mapped_material_family:
        parts.append(f"material_family={mapping.mapped_material_family}")
    if mapping.geometry_export_hint:
        parts.append(f"geometry_hint={mapping.geometry_export_hint}")
    return "; ".join(parts) or None


def _contract_status(state: GraphState, unresolved_points: list[str]) -> str:
    if (
        state.dispatch.dispatch_ready
        and state.rfq.rfq_ready
        and state.export_profile.selected_manufacturer
        and state.export_profile.recipient_refs
    ):
        return "ready"
    if (
        state.sealai_norm.identity.sealai_request_id
        or state.export_profile.selected_manufacturer
        or state.manufacturer_mapping.mapped_material_family
    ):
        return "partial" if unresolved_points else "not_ready"
    return "pending"


def _handover_notes(state: GraphState) -> list[str]:
    notes: list[str] = []
    for note in (
        list(state.export_profile.export_notes)
        + list(state.manufacturer_mapping.mapping_notes)
    ):
        text = str(note or "").strip()
        if text and text not in notes:
            notes.append(text)
    return notes


async def dispatch_contract_node(state: GraphState) -> GraphState:
    """Derive the connector-ready contract from bounded layers."""
    unresolved_points = _contract_unresolved_points(state)
    contract = DispatchContractState(
        status=_contract_status(state, unresolved_points),
        contract_version="dispatch_contract_v1",
        sealai_request_id=state.sealai_norm.identity.sealai_request_id,
        selected_manufacturer=state.export_profile.selected_manufacturer,
        recipient_refs=list(state.export_profile.recipient_refs),
        requirement_class_id=state.sealai_norm.identity.requirement_class_id,
        application_summary=state.export_profile.application_summary or state.sealai_norm.application_summary,
        material_summary=state.export_profile.material_summary,
        dimensions_summary=list(state.export_profile.dimensions_summary),
        rfq_ready=state.rfq.rfq_ready,
        dispatch_ready=state.dispatch.dispatch_ready,
        unresolved_points=unresolved_points,
        mapping_summary=_mapping_summary(state),
        handover_notes=_handover_notes(state),
    )

    log.debug(
        "[dispatch_contract_node] status=%s manufacturer=%s recipients=%d",
        contract.status,
        contract.selected_manufacturer,
        len(contract.recipient_refs),
    )

    return state.model_copy(update={"dispatch_contract": contract})
