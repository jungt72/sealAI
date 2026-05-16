"""V9.2 governed engineering models.

These models are additive to the V9.1 runtime. They make the engineering
boundary explicit without changing the existing conversation contracts:
free text may explain, deterministic services calculate, and only evidence-
bounded claims may leave the system.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ClaimLevel = Literal[
    "L0_raw",
    "L1_normalized",
    "L2_screening",
    "L3_deterministic_calculation",
    "L4_source_backed_screening",
    "L5_document_backed",
    "L6_expert_approved",
    "L3_reviewed",
]
CalculationValidityStatus = Literal[
    "valid_for_screening",
    "valid_with_assumptions",
    "input_missing",
    "out_of_scope",
    "stale",
    "requires_expert_review",
]
ReadinessBand = Literal[
    "intake_started",
    "screening_possible",
    "engineering_checks_partial",
    "review_ready_with_open_items",
    "rfq_ready_for_expert_review",
    "blocked_missing_core_data",
    "blocked_safety_or_compliance",
    "not_ready",
]
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
    risk_findings: list["EngineeringRiskFinding"] = Field(default_factory=list)
    completeness_matrix: Optional["CompletenessMatrix"] = None
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
    units: dict[str, str] = Field(default_factory=dict)
    formula_refs: list[str] = Field(default_factory=list)
    assumptions: list[dict[str, Any]] = Field(default_factory=list)
    output_snapshot_hash: str = ""
    validity_status: CalculationValidityStatus = "input_missing"
    engineering_signals: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    guardrail_violations: list[str] = Field(default_factory=list)


class CalculationGuardResult(BaseModel):
    calculation_id: str
    calculator_exists: bool = True
    required_inputs_present: bool = False
    units_normalized: bool = False
    formula_version_present: bool = False
    output_units_present: bool = False
    assumptions_marked: bool = True
    stale_inputs_detected: bool = False
    no_final_claim_from_calculation: bool = True
    allowed_user_facing: bool = False
    violations: list[str] = Field(default_factory=list)


class CalculationState(BaseModel):
    """CalculationGuard-owned V9.2 calculation ledger."""

    schema_version: str = "calculation_state_v9_2"
    status: V92Status = "pending"
    input_snapshot: Optional[CalculationInputSnapshot] = None
    results: list[CalculationResult] = Field(default_factory=list)
    stale_result_ids: list[str] = Field(default_factory=list)
    blocked_calculations: list[str] = Field(default_factory=list)
    guardrail_violations: list[str] = Field(default_factory=list)
    guard_results: list[CalculationGuardResult] = Field(default_factory=list)


class StandardsRegistryEntry(BaseModel):
    standard_id: str
    title: str
    publisher: str = "unknown"
    version: str = "metadata_only"
    edition: Optional[str] = None
    publication_date: Optional[str] = None
    region: Optional[str] = None
    scope: str = ""
    lifecycle: str = "active_or_unknown"
    applies_to_seal_types: list[str] = Field(default_factory=list)
    relevant_fields: list[str] = Field(default_factory=list)
    license_boundary: str = "metadata_only_no_norm_text"
    licensed_content_available: bool = False
    license_constraints: list[str] = Field(default_factory=lambda: ["metadata_only_no_norm_text"])
    internal_rule_refs: list[str] = Field(default_factory=list)
    review_owner: Optional[str] = None
    next_review_due: Optional[str] = None
    source_url: Optional[str] = None
    source_checked_at: Optional[str] = None
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
    applicability: Literal[
        "direct",
        "indirect",
        "unknown",
        "general_background",
        "material_family_level",
        "compound_level",
        "product_level",
        "case_specific",
        "not_applicable",
    ] = "unknown"
    source_owner: Optional[str] = None
    version: Optional[str] = None
    issue_date: Optional[str] = None
    valid_until: Optional[str] = None
    retrieved_at: Optional[str] = None
    region: Optional[str] = None
    manufacturer: Optional[str] = None
    compound_id: Optional[str] = None
    source_scope: Optional[str] = None
    permitted_claim_levels: list[ClaimLevel] = Field(default_factory=lambda: ["L2_screening"])
    confidence: Optional[float] = None
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
    medium_exposures: list[dict[str, Any]] = Field(default_factory=list)
    candidate_facts: list[dict[str, Any]] = Field(default_factory=list)
    supported_document_types: list[str] = Field(
        default_factory=lambda: ["drawing", "datasheet", "sds", "certificate", "standard_metadata"]
    )
    prompt_injection_findings: list[str] = Field(default_factory=list)
    sds_limitations: list[str] = Field(default_factory=list)
    extraction_gaps: list[str] = Field(default_factory=list)
    boundary_notice: str = "Document data remains evidence until accepted into governed fields."


class FailureObservationState(BaseModel):
    schema_version: str = "failure_observation_v9_2"
    status: V92Status = "pending"
    morphology_indicators: list[str] = Field(default_factory=list)
    morphology_tags: list[dict[str, Any]] = Field(default_factory=list)
    possible_causes: list[str] = Field(default_factory=list)
    required_diagnostics: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(
        default_factory=lambda: [
            "definitive_root_cause",
            "final_failure_cause_from_image",
            "warranty_or_liability_decision",
        ]
    )
    image_claim_boundary: str = (
        "Images and descriptions may indicate failure morphology, not prove root cause."
    )


class ReviewState(BaseModel):
    schema_version: str = "expert_review_v9_2"
    status: ReviewDecision = "not_started"
    reviewer_id: Optional[str] = None
    scope: list[str] = Field(default_factory=list)
    required_review_types: list[str] = Field(default_factory=list)
    review_guard_notes: list[str] = Field(default_factory=list)
    dossier_modules: list[str] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    override_log_required: bool = True
    approved_claim_level: Optional[ClaimLevel] = None
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
    case_revision: int = 0
    seal_system_summary: dict[str, Any] = Field(default_factory=dict)
    facts: list[dict[str, Any]] = Field(default_factory=list)
    calculations: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    material_family_candidates: list[dict[str, Any]] = Field(default_factory=list)
    compound_candidates: list[dict[str, Any]] = Field(default_factory=list)
    product_candidates: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    risk_findings: list[dict[str, Any]] = Field(default_factory=list)
    document_refs: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: list[dict[str, Any]] = Field(default_factory=list)
    standards_refs: list[dict[str, Any]] = Field(default_factory=list)
    compliance_notes: list[dict[str, Any]] = Field(default_factory=list)
    expert_review_status: str = "not_started"
    allowed_claims: list[str] = Field(default_factory=list)
    readiness_band: ReadinessBand = "not_ready"
    allowed_next_actions: list[str] = Field(default_factory=list)
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


class EngineeringRiskFinding(BaseModel):
    finding_id: str
    category: Literal[
        "medium",
        "material",
        "compound",
        "geometry",
        "motion",
        "pressure",
        "temperature",
        "surface",
        "environment",
        "compliance",
        "evidence",
        "document",
        "failure",
    ]
    severity: Literal["low", "medium", "high", "blocking"] = "medium"
    title: str
    technical_reason: str
    user_facing_reason: str
    affected_calculations: list[str] = Field(default_factory=list)
    affected_claims: list[str] = Field(default_factory=list)
    required_next_evidence: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class CompletenessMatrix(BaseModel):
    seal_type: str
    required_fields: list[dict[str, Any]] = Field(default_factory=list)
    present_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    blocking_missing_fields: list[str] = Field(default_factory=list)
    optional_but_useful_fields: list[str] = Field(default_factory=list)
    readiness_band: ReadinessBand = "not_ready"
    next_best_blocker: Optional[str] = None
