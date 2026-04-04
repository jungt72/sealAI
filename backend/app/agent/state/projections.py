"""
state/projections.py — Phase F-C.3

UI tile projections derived from GovernedSessionState.

Tiles are outward-facing representations, not state shortcuts. This module is
pure: no state mutation, no I/O, no LLM calls.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent.runtime.clarification_priority import prioritized_open_point_labels
from app.agent.services.medium_context import MediumContext
from app.agent.state.models import GovernedSessionState


class ParameterEntry(BaseModel):
    """One outward-facing parameter row."""

    field_name: str
    value: Any
    unit: str | None = None
    confidence: str = "confirmed"


class AssumptionEntry(BaseModel):
    """One outward-facing assumption or open-point row."""

    kind: str
    text: str


class ParameterTileProjection(BaseModel):
    parameters: list[ParameterEntry] = Field(default_factory=list)
    parameter_count: int = 0
    needs_confirmation: bool = False


class AssumptionTileProjection(BaseModel):
    items: list[AssumptionEntry] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)
    has_open_points: bool = False


class RecommendationTileProjection(BaseModel):
    scope_status: str = "pending"
    rfq_admissible: bool = False
    requirement_class: str | None = None
    requirement_summary: str | None = None
    validity_notes: list[str] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)


class ComputeResultProjection(BaseModel):
    calc_type: str = "unknown"
    status: str = "insufficient_data"
    v_surface_m_s: float | None = None
    pv_value_mpa_m_s: float | None = None
    dn_value: float | None = None
    notes: list[str] = Field(default_factory=list)


class ComputeTileProjection(BaseModel):
    items: list[ComputeResultProjection] = Field(default_factory=list)


class MatchingTileProjection(BaseModel):
    status: str = "pending"
    selected_manufacturer: str | None = None
    manufacturer_count: int = 0
    manufacturers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RfqTileProjection(BaseModel):
    status: str = "pending"
    rfq_ready: bool = False
    rfq_admissible: bool = False
    selected_manufacturer: str | None = None
    recipient_count: int = 0
    qualified_material_count: int = 0
    requirement_class: str | None = None
    dispatch_ready: bool = False
    dispatch_status: str = "pending"
    notes: list[str] = Field(default_factory=list)


class NormTileProjection(BaseModel):
    status: str = "pending"
    norm_version: str | None = None
    sealai_request_id: str | None = None
    requirement_class: str | None = None
    seal_family: str | None = None
    application_summary: str | None = None
    material_family: str | None = None
    qualified_material_count: int = 0
    open_points: list[str] = Field(default_factory=list)
    validity_notes: list[str] = Field(default_factory=list)


class ExportProfileTileProjection(BaseModel):
    status: str = "pending"
    export_profile_version: str | None = None
    sealai_request_id: str | None = None
    selected_manufacturer: str | None = None
    recipient_count: int = 0
    requirement_class: str | None = None
    application_summary: str | None = None
    dimensions_summary: list[str] = Field(default_factory=list)
    material_summary: str | None = None
    rfq_ready: bool = False
    dispatch_ready: bool = False
    unresolved_points: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ManufacturerMappingTileProjection(BaseModel):
    status: str = "pending"
    mapping_version: str | None = None
    selected_manufacturer: str | None = None
    mapped_product_family: str | None = None
    mapped_material_family: str | None = None
    geometry_export_hint: str | None = None
    unresolved_mapping_points: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DispatchContractTileProjection(BaseModel):
    status: str = "pending"
    contract_version: str | None = None
    sealai_request_id: str | None = None
    selected_manufacturer: str | None = None
    recipient_count: int = 0
    requirement_class: str | None = None
    application_summary: str | None = None
    material_summary: str | None = None
    dimensions_summary: list[str] = Field(default_factory=list)
    rfq_ready: bool = False
    dispatch_ready: bool = False
    unresolved_points: list[str] = Field(default_factory=list)
    mapping_summary: str | None = None
    handover_notes: list[str] = Field(default_factory=list)


class MediumContextTileProjection(BaseModel):
    medium_label: str | None = None
    status: str = "unavailable"
    scope: str = "orientierend"
    summary: str | None = None
    properties: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    followup_points: list[str] = Field(default_factory=list)
    confidence: str | None = None
    source_type: str | None = None
    not_for_release_decisions: bool = True
    disclaimer: str | None = None


class MediumClassificationTileProjection(BaseModel):
    canonical_label: str | None = None
    family: str = "unknown"
    confidence: str = "low"
    status: str = "unavailable"
    normalization_source: str | None = None
    mapping_confidence: str | None = None
    matched_alias: str | None = None
    source_registry_key: str | None = None
    followup_question: str | None = None
    primary_raw_text: str | None = None
    raw_mentions: list[str] = Field(default_factory=list)


class UiProjection(BaseModel):
    parameter: ParameterTileProjection
    assumption: AssumptionTileProjection
    recommendation: RecommendationTileProjection
    compute: ComputeTileProjection
    matching: MatchingTileProjection
    rfq: RfqTileProjection
    medium_classification: MediumClassificationTileProjection
    medium_context: MediumContextTileProjection
    norm: NormTileProjection
    export_profile: ExportProfileTileProjection
    manufacturer_mapping: ManufacturerMappingTileProjection
    dispatch_contract: DispatchContractTileProjection


_SCOPE_STATUS: dict[str | None, str] = {
    "A": "complete",
    "B": "partial",
    "C": "clarification",
    "D": "out_of_scope",
    None: "pending",
}


def _coerce_state(state: GovernedSessionState | None) -> GovernedSessionState:
    return state if isinstance(state, GovernedSessionState) else GovernedSessionState()


def _sanitize_public_notes(notes: list[str]) -> list[str]:
    blocked_fragments = (
        "transport",
        "bridge",
        "handoff",
        "dry-run",
        "internal trigger",
        "sender/connector",
        "connector consumption",
        "envelope",
    )
    public_notes: list[str] = []
    for note in notes:
        text = str(note or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if any(fragment in lowered for fragment in blocked_fragments):
            continue
        if text not in public_notes:
            public_notes.append(text)
    return public_notes


def _build_parameter_tile(state: GovernedSessionState) -> ParameterTileProjection:
    params = state.normalized.parameters
    entries = [
        ParameterEntry(
            field_name=parameter.field_name,
            value=parameter.value,
            unit=parameter.unit,
            confidence=parameter.confidence,
        )
        for parameter in params.values()
    ]
    return ParameterTileProjection(
        parameters=entries,
        parameter_count=len(entries),
        needs_confirmation=any(
            parameter.confidence == "requires_confirmation"
            for parameter in params.values()
        ),
    )


def _build_assumption_tile(state: GovernedSessionState) -> AssumptionTileProjection:
    items = [
        AssumptionEntry(kind="assumption", text=assumption.description)
        for assumption in state.normalized.assumptions
    ]
    open_points = prioritized_open_point_labels(state, state.governance.open_validation_points)
    items.extend(
        AssumptionEntry(kind="open_point", text=open_point)
        for open_point in open_points
    )
    return AssumptionTileProjection(
        items=items,
        open_points=open_points,
        has_open_points=bool(open_points),
    )


def _build_recommendation_tile(state: GovernedSessionState) -> RecommendationTileProjection:
    governance = state.governance
    requirement_class = None
    requirement_summary = None
    if governance.requirement_class is not None:
        requirement_class = governance.requirement_class.class_id or None
        requirement_summary = governance.requirement_class.description or None

    return RecommendationTileProjection(
        scope_status=_SCOPE_STATUS.get(governance.gov_class, "pending"),
        rfq_admissible=governance.rfq_admissible,
        requirement_class=requirement_class,
        requirement_summary=requirement_summary,
        validity_notes=list(governance.validity_limits),
        open_points=prioritized_open_point_labels(state, governance.open_validation_points),
    )


def _build_compute_tile(state: GovernedSessionState) -> ComputeTileProjection:
    items: list[ComputeResultProjection] = []
    for result in list(getattr(state, "compute_results", []) or []):
        if not isinstance(result, dict):
            continue
        items.append(
            ComputeResultProjection(
                calc_type=str(result.get("calc_type") or "unknown"),
                status=str(result.get("status") or "insufficient_data"),
                v_surface_m_s=result.get("v_surface_m_s"),
                pv_value_mpa_m_s=result.get("pv_value_mpa_m_s"),
                dn_value=result.get("dn_value"),
                notes=[str(item) for item in list(result.get("notes") or []) if item],
            )
        )
    return ComputeTileProjection(items=items)


def _build_matching_tile(state: GovernedSessionState) -> MatchingTileProjection:
    selected = state.matching.selected_manufacturer_ref
    manufacturers = [
        ref.manufacturer_name
        for ref in state.matching.manufacturer_refs
        if ref.manufacturer_name
    ]
    if not state.matching.manufacturer_refs and state.matching.status == "pending":
        return MatchingTileProjection(status="pending")
    return MatchingTileProjection(
        status=state.matching.status,
        selected_manufacturer=selected.manufacturer_name if selected is not None else None,
        manufacturer_count=len(state.matching.manufacturer_refs),
        manufacturers=manufacturers,
        notes=list(state.matching.matching_notes),
    )


def _build_rfq_tile(state: GovernedSessionState) -> RfqTileProjection:
    requirement_class = state.rfq.requirement_class
    selected = state.rfq.selected_manufacturer_ref
    if (
        state.rfq.status == "pending"
        and not state.rfq.rfq_ready
        and not state.rfq.recipient_refs
        and not state.rfq.qualified_material_ids
        and not state.rfq.notes
    ):
        return RfqTileProjection(
            status="pending",
            rfq_admissible=state.governance.rfq_admissible,
        )
    return RfqTileProjection(
        status=state.rfq.status,
        rfq_ready=state.rfq.rfq_ready,
        rfq_admissible=state.rfq.rfq_admissible or state.governance.rfq_admissible,
        selected_manufacturer=selected.manufacturer_name if selected is not None else None,
        recipient_count=len(state.rfq.recipient_refs),
        qualified_material_count=len(state.rfq.qualified_material_ids),
        requirement_class=requirement_class.class_id if requirement_class is not None else None,
        dispatch_ready=state.dispatch.dispatch_ready,
        dispatch_status=state.dispatch.dispatch_status,
        notes=_sanitize_public_notes(list(state.rfq.notes)),
    )


def _build_norm_tile(state: GovernedSessionState) -> NormTileProjection:
    norm = state.sealai_norm
    if (
        norm.status == "pending"
        and norm.identity.sealai_request_id is None
        and norm.identity.requirement_class_id is None
        and not norm.geometry
        and not norm.material.qualified_materials
        and not norm.open_validation_points
        and not norm.validity_limits
    ):
        return NormTileProjection(status="pending", norm_version=norm.identity.norm_version)
    return NormTileProjection(
        status=norm.status,
        norm_version=norm.identity.norm_version,
        sealai_request_id=norm.identity.sealai_request_id,
        requirement_class=norm.identity.requirement_class_id,
        seal_family=norm.identity.seal_family,
        application_summary=norm.application_summary,
        material_family=norm.material.material_family,
        qualified_material_count=len(norm.material.qualified_materials),
        open_points=list(norm.open_validation_points),
        validity_notes=list(norm.validity_limits),
    )


def _build_export_profile_tile(state: GovernedSessionState) -> ExportProfileTileProjection:
    export_profile = state.export_profile
    if (
        export_profile.status == "pending"
        and export_profile.sealai_request_id is None
        and export_profile.selected_manufacturer is None
        and export_profile.requirement_class_id is None
        and not export_profile.dimensions_summary
        and export_profile.material_summary is None
        and not export_profile.unresolved_points
        and not export_profile.export_notes
    ):
        return ExportProfileTileProjection(
            status="pending",
            export_profile_version=export_profile.export_profile_version,
        )
    return ExportProfileTileProjection(
        status=export_profile.status,
        export_profile_version=export_profile.export_profile_version,
        sealai_request_id=export_profile.sealai_request_id,
        selected_manufacturer=export_profile.selected_manufacturer,
        recipient_count=len(export_profile.recipient_refs),
        requirement_class=export_profile.requirement_class_id,
        application_summary=export_profile.application_summary,
        dimensions_summary=list(export_profile.dimensions_summary),
        material_summary=export_profile.material_summary,
        rfq_ready=export_profile.rfq_ready,
        dispatch_ready=export_profile.dispatch_ready,
        unresolved_points=list(export_profile.unresolved_points),
        notes=_sanitize_public_notes(list(export_profile.export_notes)),
    )


def _build_manufacturer_mapping_tile(state: GovernedSessionState) -> ManufacturerMappingTileProjection:
    mapping = state.manufacturer_mapping
    if (
        mapping.status == "pending"
        and mapping.selected_manufacturer is None
        and mapping.mapped_product_family is None
        and mapping.mapped_material_family is None
        and mapping.geometry_export_hint is None
        and not mapping.unresolved_mapping_points
        and not mapping.mapping_notes
    ):
        return ManufacturerMappingTileProjection(
            status="pending",
            mapping_version=mapping.mapping_version,
        )
    return ManufacturerMappingTileProjection(
        status=mapping.status,
        mapping_version=mapping.mapping_version,
        selected_manufacturer=mapping.selected_manufacturer,
        mapped_product_family=mapping.mapped_product_family,
        mapped_material_family=mapping.mapped_material_family,
        geometry_export_hint=mapping.geometry_export_hint,
        unresolved_mapping_points=list(mapping.unresolved_mapping_points),
        notes=list(mapping.mapping_notes),
    )


def _build_dispatch_contract_tile(state: GovernedSessionState) -> DispatchContractTileProjection:
    contract = state.dispatch_contract
    if (
        contract.status == "pending"
        and contract.sealai_request_id is None
        and contract.selected_manufacturer is None
        and contract.requirement_class_id is None
        and contract.application_summary is None
        and contract.material_summary is None
        and not contract.dimensions_summary
        and not contract.unresolved_points
        and contract.mapping_summary is None
        and not contract.handover_notes
    ):
        return DispatchContractTileProjection(
            status="pending",
            contract_version=contract.contract_version,
        )
    return DispatchContractTileProjection(
        status=contract.status,
        contract_version=contract.contract_version,
        sealai_request_id=contract.sealai_request_id,
        selected_manufacturer=contract.selected_manufacturer,
        recipient_count=len(contract.recipient_refs),
        requirement_class=contract.requirement_class_id,
        application_summary=contract.application_summary,
        material_summary=contract.material_summary,
        dimensions_summary=list(contract.dimensions_summary),
        rfq_ready=contract.rfq_ready,
        dispatch_ready=contract.dispatch_ready,
        unresolved_points=list(contract.unresolved_points),
        mapping_summary=contract.mapping_summary,
        handover_notes=_sanitize_public_notes(list(contract.handover_notes)),
    )


def _build_medium_context_tile(state: GovernedSessionState) -> MediumContextTileProjection:
    medium_context = state.medium_context if isinstance(state.medium_context, MediumContext) else MediumContext()
    if medium_context.status != "available" or not str(medium_context.medium_label or "").strip():
        return MediumContextTileProjection()
    return MediumContextTileProjection(
        medium_label=medium_context.medium_label,
        status=medium_context.status,
        scope=medium_context.scope,
        summary=medium_context.summary,
        properties=list(medium_context.properties),
        challenges=list(medium_context.challenges),
        followup_points=list(medium_context.followup_points),
        confidence=medium_context.confidence,
        source_type=medium_context.source_type,
        not_for_release_decisions=medium_context.not_for_release_decisions,
        disclaimer=medium_context.disclaimer,
    )


def _build_medium_classification_tile(state: GovernedSessionState) -> MediumClassificationTileProjection:
    classification = state.medium_classification
    if isinstance(classification, dict):
        classification = MediumClassificationTileProjection.model_validate(classification)
    capture = state.medium_capture
    if isinstance(capture, dict):
        capture = type("CaptureProxy", (), {
            "primary_raw_text": capture.get("primary_raw_text"),
            "raw_mentions": capture.get("raw_mentions") or [],
        })()
    return MediumClassificationTileProjection(
        canonical_label=classification.canonical_label,
        family=classification.family,
        confidence=classification.confidence,
        status=classification.status,
        normalization_source=classification.normalization_source,
        mapping_confidence=classification.mapping_confidence,
        matched_alias=classification.matched_alias,
        source_registry_key=classification.source_registry_key,
        followup_question=classification.followup_question,
        primary_raw_text=capture.primary_raw_text,
        raw_mentions=list(capture.raw_mentions),
    )


def project_for_ui(state: GovernedSessionState | None) -> UiProjection:
    """Project the outward UI tiles from the governed state."""
    coerced = _coerce_state(state)
    return UiProjection(
        parameter=_build_parameter_tile(coerced),
        assumption=_build_assumption_tile(coerced),
        recommendation=_build_recommendation_tile(coerced),
        compute=_build_compute_tile(coerced),
        matching=_build_matching_tile(coerced),
        rfq=_build_rfq_tile(coerced),
        medium_classification=_build_medium_classification_tile(coerced),
        medium_context=_build_medium_context_tile(coerced),
        norm=_build_norm_tile(coerced),
        export_profile=_build_export_profile_tile(coerced),
        manufacturer_mapping=_build_manufacturer_mapping_tile(coerced),
        dispatch_contract=_build_dispatch_contract_tile(coerced),
    )
