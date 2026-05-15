"""V9.2 governed engineering models.

These models are additive to the V9.1 runtime. They make the engineering
boundary explicit without changing the existing conversation contracts:
free text may explain, deterministic services calculate, and only evidence-
bounded claims may leave the system.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ClaimLevel = Literal["L0_raw", "L1_normalized", "L2_screening", "L3_reviewed"]
ReviewDecision = Literal["not_started", "pending", "approved_scope", "changes_required", "blocked"]
V92Status = Literal["pending", "partial", "ready", "blocked"]


class SealSystemComponent(BaseModel):
    component_id: str
    role: str
    seal_family: str = "unknown"
    seal_type: str = "unknown_seal"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    known_fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    source: str = "seal_system_graph_v9_2"


class SealSystemState(BaseModel):
    """Formal V9.2 seal-system ontology slice.

    This is the system-neutral authority for what type of sealing problem is
    being discussed. It is not a product recommendation.
    """

    schema_version: str = "seal_system_graph_v9_2"
    status: V92Status = "pending"
    seal_family: str = "unknown"
    seal_type: str = "unknown_seal"
    motion_type: Optional[str] = None
    application_pattern: Optional[str] = None
    components: list[SealSystemComponent] = Field(default_factory=list)
    system_edges: list[dict[str, str]] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    validity_boundaries: list[str] = Field(default_factory=list)


class EngineeringAssumption(BaseModel):
    assumption_id: str
    text: str
    affected_fields: list[str] = Field(default_factory=list)
    invalidates_calculations: list[str] = Field(default_factory=list)
    confirmation_required: bool = True


class EngineeringDecision(BaseModel):
    decision_id: str
    decision_type: str
    status: V92Status = "partial"
    rationale: str = ""
    next_action: str = "collect_missing_inputs"
    blockers: list[str] = Field(default_factory=list)
    related_calculations: list[str] = Field(default_factory=list)


class EngineeringState(BaseModel):
    """V9.2 engineering-orchestrator state.

    It coordinates deterministic calculators, seal-system completeness,
    assumptions and the next technically useful action.
    """

    schema_version: str = "engineering_orchestrator_v9_2"
    status: V92Status = "pending"
    orchestrator_version: str = "engineering_orchestrator_v9_2.0"
    route: str = "unknown"
    decisions: list[EngineeringDecision] = Field(default_factory=list)
    assumptions: list[EngineeringAssumption] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_best_engineering_action: str = "identify_seal_system"


class CalculationInputSnapshot(BaseModel):
    snapshot_hash: str
    case_revision: int = 0
    inputs: dict[str, Any] = Field(default_factory=dict)


class CalculationResult(BaseModel):
    calculation_id: str
    version: str
    calculator: str
    status: Literal["ok", "warning", "insufficient_data", "stale", "blocked"] = "insufficient_data"
    claim_level: ClaimLevel = "L2_screening"
    input_snapshot_hash: str = ""
    outputs: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    guardrail_violations: list[str] = Field(default_factory=list)


class CalculationState(BaseModel):
    """CalculationGuard-owned V9.2 calculation ledger."""

    schema_version: str = "calculation_state_v9_2"
    status: V92Status = "pending"
    input_snapshot: Optional[CalculationInputSnapshot] = None
    results: list[CalculationResult] = Field(default_factory=list)
    stale_result_ids: list[str] = Field(default_factory=list)
    blocked_calculations: list[str] = Field(default_factory=list)
    guardrail_violations: list[str] = Field(default_factory=list)


class StandardsRegistryEntry(BaseModel):
    standard_id: str
    title: str
    version: str = "metadata_only"
    region: Optional[str] = None
    scope: str = ""
    lifecycle: str = "active_or_unknown"
    license_boundary: str = "metadata_only_no_norm_text"
    claim_level: ClaimLevel = "L2_screening"
    conformity_claim_allowed: bool = False
    source_module_id: Optional[str] = None


class StandardsState(BaseModel):
    schema_version: str = "standards_registry_v9_2"
    registry_version: str = "standards_registry_metadata_v1"
    status: V92Status = "pending"
    applicable_entries: list[StandardsRegistryEntry] = Field(default_factory=list)
    check_results: list[dict[str, Any]] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    claim_boundary: str = (
        "Standards are metadata and check references only; no conformity or "
        "certification claim is allowed without licensed review evidence."
    )


class EvidenceGraphNode(BaseModel):
    node_id: str
    evidence_type: str
    title: str
    source_ref: Optional[str] = None
    claim_level: ClaimLevel = "L1_normalized"
    applicability: Literal["direct", "indirect", "unknown"] = "unknown"
    supports: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class EvidenceGraphEdge(BaseModel):
    from_node_id: str
    to_target_id: str
    relationship: Literal["supports", "limits", "contradicts", "requires_review"] = "supports"


class EvidenceGraphState(BaseModel):
    schema_version: str = "evidence_graph_v9_2"
    status: V92Status = "pending"
    nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    edges: list[EvidenceGraphEdge] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    claim_boundary: str = "Evidence may support screening only unless reviewed."


class MaterialFamilyCandidate(BaseModel):
    family: str
    basis: list[str] = Field(default_factory=list)
    claim_level: ClaimLevel = "L2_screening"


class CompoundCandidate(BaseModel):
    compound_id: str
    family: str = ""
    designation: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    claim_level: ClaimLevel = "L2_screening"
    requires_datasheet: bool = True


class ProductCandidate(BaseModel):
    product_id: str
    manufacturer: Optional[str] = None
    article_ref: Optional[str] = None
    compound_id: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    claim_level: ClaimLevel = "L2_screening"
    requires_manufacturer_review: bool = True


class CompoundState(BaseModel):
    schema_version: str = "compound_state_v9_2"
    status: V92Status = "pending"
    material_family_candidates: list[MaterialFamilyCandidate] = Field(default_factory=list)
    compound_candidates: list[CompoundCandidate] = Field(default_factory=list)
    product_candidates: list[ProductCandidate] = Field(default_factory=list)
    separation_violations: list[str] = Field(default_factory=list)
    boundary_notice: str = (
        "Material family, compound and product/article are separate layers. "
        "Family knowledge never creates a compound or product release."
    )


class DocumentEvidenceState(BaseModel):
    schema_version: str = "document_evidence_v9_2"
    status: V92Status = "pending"
    documents_seen: list[dict[str, Any]] = Field(default_factory=list)
    drawing_fields: dict[str, Any] = Field(default_factory=dict)
    sds_fields: dict[str, Any] = Field(default_factory=dict)
    extraction_gaps: list[str] = Field(default_factory=list)
    boundary_notice: str = "Document data remains evidence until accepted into governed fields."


class FailureObservationState(BaseModel):
    schema_version: str = "failure_observation_v9_2"
    status: V92Status = "pending"
    morphology_indicators: list[str] = Field(default_factory=list)
    possible_causes: list[str] = Field(default_factory=list)
    image_claim_boundary: str = (
        "Images and descriptions may indicate failure morphology, not prove root cause."
    )


class ReviewState(BaseModel):
    schema_version: str = "expert_review_v9_2"
    status: ReviewDecision = "not_started"
    reviewer_id: Optional[str] = None
    scope: list[str] = Field(default_factory=list)
    decision_summary: str = ""
    blocking_findings: list[str] = Field(default_factory=list)
    soft_findings: list[str] = Field(default_factory=list)
    required_corrections: list[str] = Field(default_factory=list)
    reviewed_claim_ids: list[str] = Field(default_factory=list)


class DossierSection(BaseModel):
    section_id: str
    title: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class DossierState(BaseModel):
    schema_version: str = "rfq_dossier_v9_2"
    status: V92Status = "pending"
    dossier_id: Optional[str] = None
    facts: list[dict[str, Any]] = Field(default_factory=list)
    calculations: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    allowed_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(
        default_factory=lambda: [
            "freigegeben",
            "geeignet ohne Herstellerprüfung",
            "zertifiziert",
            "konform ohne Normprüfung",
            "finale Auslegung",
        ]
    )
    sections: list[DossierSection] = Field(default_factory=list)
    no_final_technical_release: bool = True
