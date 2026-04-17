# backend/app/api/v1/schemas/case_workspace.py
"""Case Workspace Projection — UI-facing read model for a single engineering case.

This DTO is a controlled projection of the internal 4-pillar SealAIState.
It exposes only what the frontend needs to render a case workspace, without
leaking internal orchestration details, prompt traces, or raw LLM artifacts.

Deliberately NOT exposed:
- messages / transcript (separate chat-history endpoint)
- prompt_traces, tool_call_records, evidence_bundle internals
- working_memory, plan, budget, round_index (orchestration internals)
- raw parameter_provenance / identity records (too granular for UI)
- draft_text, preview_text, final_prompt (LLM intermediates)
- confirm_checkpoint / confirm_edits (HITL internals)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Literal


RequestType = Literal[
    "new_design",
    "retrofit",
    "rca_failure_analysis",
    "validation_check",
    "spare_part_identification",
    "quick_engineering_check",
]

EngineeringPath = Literal[
    "ms_pump",
    "rwdr",
    "static",
    "labyrinth",
    "hyd_pneu",
    "unclear_rotary",
]


class CaseSummary(BaseModel):
    thread_id: Optional[str] = None
    user_id: Optional[str] = None
    phase: Optional[str] = None
    intent_goal: Optional[str] = None
    application_category: Optional[str] = None
    seal_family: Optional[str] = None
    motion_type: Optional[str] = None
    user_persona: Optional[str] = None
    turn_count: int = 0
    max_turns: int = 12

    model_config = ConfigDict(extra="forbid")


class CompletenessStatus(BaseModel):
    coverage_score: float = 0.0
    coverage_gaps: List[str] = Field(default_factory=list)
    completeness_depth: str = "precheck"
    missing_critical_parameters: List[str] = Field(default_factory=list)
    discovery_missing: List[str] = Field(default_factory=list)
    analysis_complete: bool = False
    recommendation_ready: bool = False

    model_config = ConfigDict(extra="forbid")


class GovernanceStatus(BaseModel):
    release_status: str = "inadmissible"
    scope_of_validity: List[str] = Field(default_factory=list)
    assumptions_active: List[str] = Field(default_factory=list)
    unknowns_release_blocking: List[str] = Field(default_factory=list)
    unknowns_manufacturer_validation: List[str] = Field(default_factory=list)
    gate_failures: List[str] = Field(default_factory=list)
    governance_notes: List[str] = Field(default_factory=list)
    required_disclaimers: List[str] = Field(default_factory=list)
    verification_passed: bool = True

    model_config = ConfigDict(extra="forbid")


class ElevationHint(BaseModel):
    """Patch C4: Structured hint for specificity elevation."""
    label: str
    field_key: Optional[str] = None
    reason: str = ""
    priority: int = 1
    action_type: str = "provide_data"

    model_config = ConfigDict(extra="forbid")


class SpecificityInfo(BaseModel):
    material_specificity_required: str = "family_only"
    completeness_depth: str = "precheck"
    elevation_possible: bool = False
    elevation_hints: List[ElevationHint] = Field(default_factory=list)
    elevation_target: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class CandidateClusterSummary(BaseModel):
    plausibly_viable: List[Dict[str, Any]] = Field(default_factory=list)
    manufacturer_validation_required: List[Dict[str, Any]] = Field(default_factory=list)
    inadmissible_or_excluded: List[Dict[str, Any]] = Field(default_factory=list)
    total_candidates: int = 0

    model_config = ConfigDict(extra="forbid")


class ConflictSummary(BaseModel):
    total: int = 0
    open: int = 0
    resolved: int = 0
    by_severity: Dict[str, int] = Field(default_factory=dict)
    items: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ClaimItem(BaseModel):
    value: Optional[str] = None
    claim_type: str = "unknown"
    claim_origin: str = "unknown"

    model_config = ConfigDict(extra="forbid")


class ClaimsSummary(BaseModel):
    total: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_origin: Dict[str, int] = Field(default_factory=dict)
    items: List[ClaimItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class EvidenceSummary(BaseModel):
    evidence_present: bool = False
    evidence_count: int = 0
    trusted_sources_present: bool = False
    evidence_supported_topics: List[str] = Field(default_factory=list)
    source_backed_findings: List[str] = Field(default_factory=list)
    deterministic_findings: List[str] = Field(default_factory=list)
    assumption_based_findings: List[str] = Field(default_factory=list)
    unresolved_open_points: List[str] = Field(default_factory=list)
    evidence_gaps: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ManufacturerQuestions(BaseModel):
    mandatory: List[str] = Field(default_factory=list)
    open_questions: List[Dict[str, Any]] = Field(default_factory=list)
    total_open: int = 0

    model_config = ConfigDict(extra="forbid")


class RFQStatus(BaseModel):
    admissibility_status: str = "inadmissible"
    release_status: str = "inadmissible"
    rfq_confirmed: bool = False
    rfq_ready: bool = False
    handover_ready: bool = False
    handover_initiated: bool = False
    blockers: List[str] = Field(default_factory=list)
    open_points: List[str] = Field(default_factory=list)
    has_pdf: bool = False
    has_html_report: bool = False

    model_config = ConfigDict(extra="forbid")


class ArtifactStatus(BaseModel):
    has_answer_contract: bool = False
    contract_id: Optional[str] = None
    contract_obsolete: bool = False
    has_verification_report: bool = False
    has_sealing_requirement_spec: bool = False
    has_rfq_draft: bool = False
    has_recommendation: bool = False
    has_live_calc_tile: bool = False
    live_calc_status: str = "insufficient_data"

    model_config = ConfigDict(extra="forbid")


class RFQPackageSummary(BaseModel):
    """RFQ Package read model — what would go into an outward-facing RFQ package.

    Surfaces the redacted operating context, mandatory questions, and
    buyer assumptions from the internal RFQDraft artifact.  Read-only.
    """
    has_draft: bool = False
    rfq_id: Optional[str] = None
    rfq_basis_status: str = "inadmissible"
    operating_context_redacted: Dict[str, Any] = Field(default_factory=dict)
    manufacturer_questions_mandatory: List[str] = Field(default_factory=list)
    conflicts_visible_count: int = 0
    buyer_assumptions_acknowledged: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class FactVariant(BaseModel):
    """Patch C2: A variant value for a grounded fact from a different source."""
    value: str
    source: str
    source_rank: float = 0.0

    model_config = ConfigDict(extra="forbid")


class GroundedFact(BaseModel):
    """Patch C1a: Typed grounding for technical material facts."""
    name: str
    value: str
    unit: Optional[str] = None
    source: str
    source_rank: float = 0.0
    grounding_basis: str = "metadata"
    
    # Patch C2: Divergence detection
    is_divergent: bool = False
    variants: List[FactVariant] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MaterialFitItem(BaseModel):
    """A single candidate material's manufacturer fit assessment."""
    material: str = ""
    cluster: str = "viable"
    specificity: str = "family_only"
    requires_validation: bool = False
    fit_basis: str = ""
    grounded_facts: List[GroundedFact] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class PartnerMatchingSummary(BaseModel):
    """Manufacturer fit / partner matching read model.

    Derived deterministically from candidate clusters and governance signals.
    data_source indicates the actual basis — 'candidate_derived' when no
    real partner database is connected, 'partner_db' when a live catalog exists.
    """
    matching_ready: bool = False
    shortlist_ready: bool = False
    inquiry_ready: bool = False
    not_ready_reasons: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    material_fit_items: List[MaterialFitItem] = Field(default_factory=list)
    open_manufacturer_questions: List[str] = Field(default_factory=list)
    selected_partner_id: Optional[str] = None
    data_source: str = "candidate_derived"

    model_config = ConfigDict(extra="forbid")


class CommunicationContext(BaseModel):
    """Small additive communication layer for the canonical workspace read model."""

    conversation_phase: Optional[str] = None
    turn_goal: Optional[str] = None
    primary_question: Optional[str] = None
    supporting_reason: Optional[str] = None
    response_mode: Optional[str] = None
    confirmed_facts_summary: List[str] = Field(default_factory=list)
    open_points_summary: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MediumContextSummary(BaseModel):
    medium_label: Optional[str] = None
    status: str = "unavailable"
    scope: str = "orientierend"
    summary: Optional[str] = None
    properties: List[str] = Field(default_factory=list)
    challenges: List[str] = Field(default_factory=list)
    followup_points: List[str] = Field(default_factory=list)
    confidence: Optional[str] = None
    source_type: Optional[str] = None
    not_for_release_decisions: bool = True
    disclaimer: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class MediumCaptureSummary(BaseModel):
    raw_mentions: List[str] = Field(default_factory=list)
    primary_raw_text: Optional[str] = None
    source_turn_ref: Optional[str] = None
    source_turn_index: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class MediumClassificationSummary(BaseModel):
    canonical_label: Optional[str] = None
    family: str = "unknown"
    confidence: str = "low"
    status: str = "unavailable"
    normalization_source: Optional[str] = None
    mapping_confidence: Optional[str] = None
    matched_alias: Optional[str] = None
    source_registry_key: Optional[str] = None
    followup_question: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class TechnicalDerivationItem(BaseModel):
    calc_type: str = "unknown"
    status: str = "insufficient_data"
    v_surface_m_s: Optional[float] = None
    pv_value_mpa_m_s: Optional[float] = None
    dn_value: Optional[float] = None
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CycleInfo(BaseModel):
    current_assertion_cycle_id: int = 0
    state_revision: int = 0
    asserted_profile_revision: int = 0
    derived_artifacts_stale: bool = False
    stale_reason: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


CockpitSectionId = Literal[
    "core_intake",
    "failure_drivers",
    "geometry_fit",
    "rfq_liability",
]


class CockpitProperty(BaseModel):
    key: str
    label: str
    value: Any = None
    unit: Optional[str] = None
    origin: Optional[str] = None
    confidence: Optional[str] = None
    is_confirmed: bool = False
    is_mandatory: bool = False

    model_config = ConfigDict(extra="forbid")


class CockpitSectionCompletion(BaseModel):
    mandatory_present: int = 0
    mandatory_total: int = 0
    percent: int = 0

    model_config = ConfigDict(extra="forbid")


class CockpitSection(BaseModel):
    section_id: CockpitSectionId
    title: str
    completion: CockpitSectionCompletion = Field(default_factory=CockpitSectionCompletion)
    properties: List[CockpitProperty] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CockpitRoutingMetadata(BaseModel):
    phase: Optional[str] = None
    last_node: Optional[str] = None
    routing: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class CockpitReadinessSummary(BaseModel):
    status: str = "preliminary"
    is_rfq_ready: bool = False
    release_status: str = "inadmissible"
    coverage_score: float = 0.0

    model_config = ConfigDict(extra="forbid")


class EngineeringCheckResult(BaseModel):
    calc_id: str
    label: str
    formula_version: str
    required_inputs: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    valid_paths: List[EngineeringPath] = Field(default_factory=list)
    output_key: str
    unit: Optional[str] = None
    status: str = "insufficient_data"
    value: Any = None
    fallback_behavior: str = "insufficient_data_when_required_inputs_missing"
    guardrails: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class EngineeringCockpitView(BaseModel):
    request_type: Optional[RequestType] = None
    engineering_path: Optional[EngineeringPath] = None
    routing_metadata: CockpitRoutingMetadata = Field(default_factory=CockpitRoutingMetadata)
    sections: List[CockpitSection] = Field(default_factory=list)
    checks: List[EngineeringCheckResult] = Field(default_factory=list)
    missing_mandatory_keys: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    readiness: CockpitReadinessSummary = Field(default_factory=CockpitReadinessSummary)

    model_config = ConfigDict(extra="forbid")


class CaseWorkspaceProjection(BaseModel):
    """Top-level UI-facing read model for a single engineering case."""
    request_type: Optional[RequestType] = None
    engineering_path: Optional[EngineeringPath] = None
    cockpit_view: EngineeringCockpitView = Field(default_factory=EngineeringCockpitView)
    case_summary: CaseSummary = Field(default_factory=CaseSummary)
    completeness: CompletenessStatus = Field(default_factory=CompletenessStatus)
    governance_status: GovernanceStatus = Field(default_factory=GovernanceStatus)
    specificity: SpecificityInfo = Field(default_factory=SpecificityInfo)
    candidate_clusters: CandidateClusterSummary = Field(default_factory=CandidateClusterSummary)
    conflicts: ConflictSummary = Field(default_factory=ConflictSummary)
    claims_summary: ClaimsSummary = Field(default_factory=ClaimsSummary)
    evidence_summary: EvidenceSummary = Field(default_factory=EvidenceSummary)
    manufacturer_questions: ManufacturerQuestions = Field(default_factory=ManufacturerQuestions)
    rfq_status: RFQStatus = Field(default_factory=RFQStatus)
    artifact_status: ArtifactStatus = Field(default_factory=ArtifactStatus)
    rfq_package: RFQPackageSummary = Field(default_factory=RFQPackageSummary)
    partner_matching: PartnerMatchingSummary = Field(default_factory=PartnerMatchingSummary)
    communication_context: CommunicationContext = Field(default_factory=CommunicationContext)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    medium_capture: MediumCaptureSummary = Field(default_factory=MediumCaptureSummary)
    medium_classification: MediumClassificationSummary = Field(default_factory=MediumClassificationSummary)
    medium_context: MediumContextSummary = Field(default_factory=MediumContextSummary)
    technical_derivations: List[TechnicalDerivationItem] = Field(default_factory=list)
    cycle_info: CycleInfo = Field(default_factory=CycleInfo)

    model_config = ConfigDict(extra="forbid")
