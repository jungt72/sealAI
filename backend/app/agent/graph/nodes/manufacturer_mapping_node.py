"""
manufacturer_mapping_node — Phase H.3

Deterministic bounded manufacturer mapping derived from the export profile.

Responsibility:
    Add a first manufacturer-facing mapping layer without changing the
    manufacturer-neutral norm core or the neutral export profile.
"""
from __future__ import annotations

import logging

from app.agent.domain.governed_data import get_default_domain_data_provider
from app.agent.graph import GraphState
from app.agent.state.models import ManufacturerMappingState

log = logging.getLogger(__name__)


def _geometry_export_hint(state: GraphState) -> str | None:
    dimensions = list(state.export_profile.dimensions_summary)
    if dimensions:
        return ", ".join(dimensions)
    return None


def _mapped_product_family(state: GraphState) -> str | None:
    seal_family = state.sealai_norm.identity.seal_family
    if seal_family:
        return seal_family
    return None


def _catalog_backed_material_family(state: GraphState) -> tuple[str | None, list[str]]:
    selected = str(state.export_profile.selected_manufacturer or "").strip()
    material_family = str(state.sealai_norm.material.material_family or "").strip()
    notes: list[str] = []
    if not selected or not material_family:
        return (material_family or None, notes)

    provider = get_default_domain_data_provider()
    for record in provider.list_material_records():
        if record.manufacturer_name != selected:
            continue
        if record.material_family != material_family:
            continue
        notes.append("Manufacturer mapping is backed by the governed material catalog.")
        if record.is_demo_only:
            notes.append("Current mapping uses demo catalog data and remains category-level only.")
        return record.material_family, notes
    return material_family, notes


def _unresolved_mapping_points(
    *,
    selected_manufacturer: str | None,
    mapped_product_family: str | None,
    mapped_material_family: str | None,
    geometry_export_hint: str | None,
) -> list[str]:
    unresolved: list[str] = []
    if not selected_manufacturer:
        unresolved.append("selected_manufacturer_missing")
    if not mapped_product_family:
        unresolved.append("product_family_hint_missing")
    if not mapped_material_family:
        unresolved.append("material_family_mapping_missing")
    if not geometry_export_hint:
        unresolved.append("geometry_export_hint_missing")
    return unresolved


def _mapping_status(
    *,
    selected_manufacturer: str | None,
    mapped_product_family: str | None,
    mapped_material_family: str | None,
    geometry_export_hint: str | None,
    sealai_request_id: str | None,
) -> str:
    if not sealai_request_id and not selected_manufacturer and not mapped_material_family:
        return "pending"
    if selected_manufacturer and mapped_material_family and (mapped_product_family or geometry_export_hint):
        return "mapped"
    if selected_manufacturer or mapped_material_family or mapped_product_family:
        return "partial"
    return "not_ready"


async def manufacturer_mapping_node(state: GraphState) -> GraphState:
    """Derive a bounded manufacturer mapping from export_profile + catalog."""
    selected_manufacturer = str(state.export_profile.selected_manufacturer or "").strip() or None
    mapped_product_family = _mapped_product_family(state)
    mapped_material_family, catalog_notes = _catalog_backed_material_family(state)
    geometry_export_hint = _geometry_export_hint(state)
    unresolved = _unresolved_mapping_points(
        selected_manufacturer=selected_manufacturer,
        mapped_product_family=mapped_product_family,
        mapped_material_family=mapped_material_family,
        geometry_export_hint=geometry_export_hint,
    )
    notes = list(catalog_notes)
    if not notes:
        notes.append("Mapping remains category-level only; no SKU or compound code is inferred.")

    manufacturer_mapping = ManufacturerMappingState(
        status=_mapping_status(
            selected_manufacturer=selected_manufacturer,
            mapped_product_family=mapped_product_family,
            mapped_material_family=mapped_material_family,
            geometry_export_hint=geometry_export_hint,
            sealai_request_id=state.export_profile.sealai_request_id,
        ),
        mapping_version="manufacturer_mapping_v1",
        selected_manufacturer=selected_manufacturer,
        mapped_product_family=mapped_product_family,
        mapped_material_family=mapped_material_family,
        geometry_export_hint=geometry_export_hint,
        unresolved_mapping_points=unresolved,
        mapping_notes=notes,
    )

    log.debug(
        "[manufacturer_mapping_node] status=%s manufacturer=%s material=%s",
        manufacturer_mapping.status,
        manufacturer_mapping.selected_manufacturer,
        manufacturer_mapping.mapped_material_family,
    )

    return state.model_copy(update={"manufacturer_mapping": manufacturer_mapping})
