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

from app.agent.v91.contracts import V91WorkspaceProjection
from app.domain.case_type import CaseType
from app.domain.seal_type import SealFamily, SealType
from app.domain.source_validation import SourceType, ValidationStatus


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
    coverage_percent: int = 0
    coverage_gaps: List[str] = Field(default_factory=list)
    completeness_depth: str = "precheck"
    missing_critical_parameters: List[str] = Field(default_factory=list)
    required_total: int = 0
    required_known: int = 0
    required_missing: List[str] = Field(default_factory=list)
    required_invalid: List[str] = Field(default_factory=list)
    required_fields: List[Dict[str, Any]] = Field(default_factory=list)
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
    validation_status: Optional[str] = None
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


class MaterialIntelligenceSafety(BaseModel):
    mutates_case_state: bool = False
    creates_engineering_truth: bool = False
    final_approval_claim_allowed: bool = False
    dispatch_allowed: bool = False
    external_contact_allowed: bool = False
    export_allowed: bool = False

    model_config = ConfigDict(extra="forbid")


class MaterialIntelligenceInputSummary(BaseModel):
    medium: Optional[str] = None
    medium_family: str = "unknown"
    known_material: Optional[str] = None
    temperature_c: Optional[float] = None
    pressure_bar: Optional[float] = None
    seal_type: Optional[str] = None
    motion_type: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class MaterialCandidateProjection(BaseModel):
    material_key: str
    label: str
    family: str
    status: str
    status_label: str
    confidence: str = "low"
    plausibility: str = "low"
    plausibility_score: int = 0
    plausibility_label: str = "nicht bewertet"
    score_drivers: List[str] = Field(default_factory=list)
    score_cautions: List[str] = Field(default_factory=list)
    why_considered: List[str] = Field(default_factory=list)
    limits: List[str] = Field(default_factory=list)
    blocking_unknowns: List[str] = Field(default_factory=list)
    counterindicators: List[str] = Field(default_factory=list)
    required_checks: List[str] = Field(default_factory=list)
    allowed_claim: str = "vorlaeufige Pruefhypothese"
    forbidden_claims: List[str] = Field(default_factory=list)
    rfq_relevance: str = ""
    evidence_ref_ids: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MaterialAlternativeProjection(BaseModel):
    from_material: str
    to_material: str
    comparison: str
    tradeoffs: List[str] = Field(default_factory=list)
    missing_for_decision: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MaterialEvidenceProjection(BaseModel):
    id: str
    source_type: str = "deterministic"
    validation_status: str = "system_derived"
    title: str
    excerpt: str = ""
    confidence: str = "low"

    model_config = ConfigDict(extra="forbid")


class MaterialIntelligenceProjection(BaseModel):
    capability_id: str = "material_seal_type_context"
    status: str = "insufficient_context"
    input_summary: MaterialIntelligenceInputSummary = Field(
        default_factory=MaterialIntelligenceInputSummary
    )
    candidate_materials: List[MaterialCandidateProjection] = Field(default_factory=list)
    alternatives: List[MaterialAlternativeProjection] = Field(default_factory=list)
    missing_field_hints: List[str] = Field(default_factory=list)
    rfq_relevance_notes: List[str] = Field(default_factory=list)
    evidence: List[MaterialEvidenceProjection] = Field(default_factory=list)
    safety: MaterialIntelligenceSafety = Field(
        default_factory=MaterialIntelligenceSafety
    )
    not_for_release_decisions: bool = True
    disclaimer: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ChallengeFindingProjection(BaseModel):
    finding_id: str
    kind: str
    severity: str = "watch"
    status: str = "open"
    title: str
    summary: str
    rfq_relevance: str = ""
    related_fields: List[str] = Field(default_factory=list)
    evidence_ref_ids: List[str] = Field(default_factory=list)
    action_mode: str = "RUN_RISK_COMPLETENESS"
    claim_id: Optional[str] = None
    claim_type: str = "context_advisory"
    subject_field: str = ""
    evidence_fields: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    allowed_user_wording: str = ""
    forbidden_user_wording: List[str] = Field(default_factory=list)
    source: str = "challenge_engine_v9"

    model_config = ConfigDict(extra="forbid")


class SolutionHypothesisProjection(BaseModel):
    hypothesis_id: str
    label: str
    plausibility_class: str = "low"
    status: str = "active"
    basis: List[str] = Field(default_factory=list)
    counterindicators: List[str] = Field(default_factory=list)
    blocking_unknowns: List[str] = Field(default_factory=list)
    required_checks: List[str] = Field(default_factory=list)
    rfq_relevance: str = ""
    forbidden_claims: List[str] = Field(default_factory=list)
    source: str = "challenge_engine_v9"

    model_config = ConfigDict(extra="forbid")


class ChallengeNextBestQuestionProjection(BaseModel):
    question: str
    reason: str
    focus_key: str
    priority: int = 1
    expected_answer_type: str = "text"
    closes_findings: List[str] = Field(default_factory=list)
    source: str = "challenge_engine_v9"
    max_questions_policy: str = "ask_one_highest_leverage_question"

    model_config = ConfigDict(extra="forbid")


class ChallengeIntelligenceProjection(BaseModel):
    schema_version: str = "challenge_engine_v9.0"
    status: str = "not_run"
    findings: List[ChallengeFindingProjection] = Field(default_factory=list)
    hypotheses: List[SolutionHypothesisProjection] = Field(default_factory=list)
    next_best_question: Optional[ChallengeNextBestQuestionProjection] = None
    action_modes_run: List[str] = Field(default_factory=list)
    boundary_notice: str = (
        "Pruefhypothesen dienen der technischen Vorqualifikation; keine "
        "Freigabe, keine finale Auslegung und keine Materialentscheidung."
    )

    model_config = ConfigDict(extra="forbid")


class TechnicalDerivationItem(BaseModel):
    calc_type: str = "unknown"
    status: str = "insufficient_data"
    v_surface_m_s: Optional[float] = None
    pv_value_mpa_m_s: Optional[float] = None
    dn_value: Optional[float] = None
    temperature_headroom_c: Optional[float] = None
    pressure_window: Optional[str] = None
    value: Any = None
    derived_value_id: Optional[str] = None
    derived_from_fields: List[str] = Field(default_factory=list)
    derived_from_revision: int = 0
    calculation_id: Optional[str] = None
    ruleset_version: Optional[str] = None
    stale_reason: Optional[str] = None
    notes: List[str] = Field(default_factory=list)
    source_type: SourceType = SourceType.deterministic_calculation
    validation_status: ValidationStatus = ValidationStatus.calculated

    model_config = ConfigDict(extra="forbid")


class CycleInfo(BaseModel):
    current_assertion_cycle_id: int = 0
    state_revision: int = 0
    asserted_profile_revision: int = 0
    derived_artifacts_stale: bool = False
    stale_reason: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


CockpitSectionId = Literal[
    "application_function",
    "medium_environment",
    "operating_geometry",
    "risk_readiness",
]

DeepDiveTabId = Literal["analysis", "medium", "material", "seal_type"]


class CockpitProperty(BaseModel):
    key: str
    label: str
    value: Any = None
    unit: Optional[str] = None
    origin: Optional[str] = None
    confidence: Optional[str] = None
    source_type: Optional[SourceType] = None
    validation_status: Optional[ValidationStatus] = None
    is_confirmed: bool = False
    is_mandatory: bool = False

    model_config = ConfigDict(extra="forbid")


class SourceValidationBadgeView(BaseModel):
    """Backend-only source/validation badge contract for future renderers."""

    source_type: SourceType = SourceType.unknown
    validation_status: ValidationStatus = ValidationStatus.unknown
    authoritative: bool = False
    not_for_release_decisions: bool = True
    event_names: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CockpitSectionCompletion(BaseModel):
    mandatory_present: int = 0
    mandatory_total: int = 0
    percent: int = 0

    model_config = ConfigDict(extra="forbid")


class CockpitSection(BaseModel):
    section_id: CockpitSectionId
    title: str
    completion: CockpitSectionCompletion = Field(
        default_factory=CockpitSectionCompletion
    )
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
    readiness_level: int = 0
    readiness_label: str = "no_technical_case_detected"
    missing_required_fields: List[str] = Field(default_factory=list)
    blocking_unknowns: List[str] = Field(default_factory=list)
    recommended_next_question: Optional[str] = None
    rfq_possible: bool = False
    risk_score_max: int = 9
    risk_label_max: str = "unknown"
    ruleset_version: str = "v0.4-mvp-2026-04-25"

    model_config = ConfigDict(extra="forbid")


class RiskEvaluationResult(BaseModel):
    risk_name: str
    score: int
    label: str
    drivers: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    rule_ids: List[str] = Field(default_factory=list)
    explanation_short: str = ""
    confidence: str = "medium"
    ruleset_version: str = "v0.4-mvp-2026-04-25"
    claim_id: Optional[str] = None
    claim_type: str = "context_advisory"
    subject_field: str = ""
    severity: str = "low"
    evidence_fields: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    allowed_user_wording: str = ""
    forbidden_user_wording: List[str] = Field(default_factory=list)
    source: str = "risk_readiness"

    model_config = ConfigDict(extra="forbid")


class CompatibilityEvidenceRef(BaseModel):
    ref_id: Optional[str] = None
    card_id: Optional[str] = None
    material: Optional[str] = None
    medium: Optional[str] = None
    claim_level: Optional[str] = None
    source_type: str = "knowledge_card"
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    excerpt_short: Optional[str] = None
    confidence: Any = None
    limitations: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class EngineeringCheckResult(BaseModel):
    calc_id: str
    check_id: Optional[str] = None
    claim_id: Optional[str] = None
    claim_type: str = "context_advisory"
    compatibility_claim_type: Optional[str] = None
    compatibility_status: Optional[str] = None
    evidence_status: Optional[str] = None
    evidence_refs: List[CompatibilityEvidenceRef] = Field(default_factory=list)
    evidence_summary: str = ""
    evidence_limitations: List[str] = Field(default_factory=list)
    subject_field: str = ""
    label: str
    formula_version: str
    required_inputs: List[str] = Field(default_factory=list)
    required_fields: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    valid_paths: List[EngineeringPath] = Field(default_factory=list)
    output_key: str
    unit: Optional[str] = None
    status: str = "unknown"
    value: Any = None
    fallback_behavior: str = "insufficient_data_when_required_inputs_missing"
    guardrails: List[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None
    blocking_reason: Optional[str] = None
    evidence_fields: List[str] = Field(default_factory=list)
    allowed_user_wording: str = ""
    forbidden_user_wording: List[str] = Field(default_factory=list)
    medium_field: Optional[str] = None
    material_field: Optional[str] = None
    temperature_field: Optional[str] = None
    concentration_field: Optional[str] = None
    ph_field: Optional[str] = None
    ambiguous_fields: List[str] = Field(default_factory=list)
    final_approval_claim_allowed: bool = False
    source: str = "check_registry"
    derived_from: List[str] = Field(default_factory=list)
    severity: str = "screening"
    human_readable_reason: str = ""
    raw_status: Optional[str] = None
    notes: List[str] = Field(default_factory=list)
    requirement_tier: str = "required_for_rwdr_precheck"

    model_config = ConfigDict(extra="forbid")


class CockpitCheckMetrics(BaseModel):
    check_total: int = 0
    check_available_count: int = 0
    check_blocked_count: int = 0
    check_pending_count: int = 0
    check_failed_count: int = 0
    check_passed_count: int = 0
    checks: List[EngineeringCheckResult] = Field(default_factory=list)
    source: str = "backend_check_registry"

    model_config = ConfigDict(extra="forbid")


class CockpitRequiredFieldMetric(BaseModel):
    field_id: str
    label: str
    status: str = "missing"
    value_summary: Optional[str] = None
    provenance_summary: Optional[str] = None
    reason_required: str = ""
    blocks_next_step: bool = True
    requirement_tier: str = "required_for_basic_orientation"

    model_config = ConfigDict(extra="forbid")


class CockpitCompletenessMetrics(BaseModel):
    completeness_percent: int = 0
    required_total: int = 0
    required_known: int = 0
    required_missing: List[str] = Field(default_factory=list)
    required_invalid: List[str] = Field(default_factory=list)
    required_fields: List[CockpitRequiredFieldMetric] = Field(default_factory=list)
    source: str = "backend_required_field_policy"

    model_config = ConfigDict(extra="forbid")


class EngineeringCockpitView(BaseModel):
    request_type: Optional[RequestType] = None
    engineering_path: Optional[EngineeringPath] = None
    routing_metadata: CockpitRoutingMetadata = Field(
        default_factory=CockpitRoutingMetadata
    )
    sections: List[CockpitSection] = Field(default_factory=list)
    checks: List[EngineeringCheckResult] = Field(default_factory=list)
    check_metrics: CockpitCheckMetrics = Field(default_factory=CockpitCheckMetrics)
    completeness_metrics: CockpitCompletenessMetrics = Field(
        default_factory=CockpitCompletenessMetrics
    )
    risk_evaluations: List[RiskEvaluationResult] = Field(default_factory=list)
    missing_mandatory_keys: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    readiness: CockpitReadinessSummary = Field(default_factory=CockpitReadinessSummary)

    model_config = ConfigDict(extra="forbid")


class DeepDiveCard(BaseModel):
    title: str
    body: str
    items: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DeepDiveTabProjection(BaseModel):
    tab_id: DeepDiveTabId
    label: str
    status: str = "available"
    detected: List[str] = Field(default_factory=list)
    relevance: str = ""
    opportunities: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    derived_direction: str = ""
    missing: List[str] = Field(default_factory=list)
    next_action: Optional[str] = None
    return_to_analysis: str = "Zurueck zur Analyse"
    cards: List[DeepDiveCard] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class NeedsAnalysisProjection(BaseModel):
    primary_need: str = "unknown"
    secondary_needs: List[str] = Field(default_factory=list)
    urgency: str = "unknown"
    user_side: Optional[str] = None
    context_side: Optional[str] = None
    confidence: float = 0.0
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CurrentStateAnalysisProjection(BaseModel):
    known_fields: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    uncertain_fields: List[str] = Field(default_factory=list)
    conflicting_fields: List[str] = Field(default_factory=list)
    evidence_backed_fields: List[str] = Field(default_factory=list)
    seal_type_status: str = "unknown"
    readiness_hint: str = "precheck"
    confidence: float = 0.0

    model_config = ConfigDict(extra="forbid")


class NextBestQuestionProjection(BaseModel):
    question: str
    reason: str
    focus_key: str
    priority: int = 1
    expected_answer_type: str = "text"
    applies_to_case_type: CaseType = CaseType.unknown
    applies_to_seal_type: SealType = SealType.unknown_seal
    source: str = "next_best_question_service"
    max_questions_policy: str = "ask_1_to_3_targeted_questions"

    model_config = ConfigDict(extra="forbid")


class CompletenessScoreProjection(BaseModel):
    score: float = 0.0
    missing_critical_count: int = 0
    known_critical_count: int = 0
    uncertainty_count: int = 0
    conflict_count: int = 0
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DecisionUnderstandingProjection(BaseModel):
    case_summary: str = ""
    understood_now: List[str] = Field(default_factory=list)
    technical_meaning: List[str] = Field(default_factory=list)
    plausible_directions: List[str] = Field(default_factory=list)
    not_yet_decidable: List[str] = Field(default_factory=list)
    key_risks: List[str] = Field(default_factory=list)
    confidence_notes: List[str] = Field(default_factory=list)
    next_best_question: Optional[str] = None
    manufacturer_review_needs: List[str] = Field(default_factory=list)
    needs_analysis: NeedsAnalysisProjection = Field(
        default_factory=NeedsAnalysisProjection
    )
    current_state_analysis: CurrentStateAnalysisProjection = Field(
        default_factory=CurrentStateAnalysisProjection
    )
    next_best_questions: List[NextBestQuestionProjection] = Field(default_factory=list)
    completeness_score: CompletenessScoreProjection = Field(
        default_factory=CompletenessScoreProjection
    )

    model_config = ConfigDict(extra="forbid")


class SealApplicationProfileView(BaseModel):
    """Read-only SealType projection for S-SEAL-001.

    This is not authoritative case state and does not mark the seal type as
    user-confirmed. It only exposes deterministic normalization facts and
    type-specific metadata hints.
    """

    seal_family: SealFamily = SealFamily.unknown
    seal_type: SealType = SealType.unknown_seal
    seal_type_confidence: float = 0.1
    confidence_band: str = "low"
    matched_alias: Optional[str] = None
    ambiguous: bool = False
    candidate_types: List[SealType] = Field(default_factory=list)
    application_domain: Optional[str] = None
    motion_type: Optional[str] = None
    standard_refs: List[str] = Field(default_factory=list)
    type_specific_missing_hints: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    source: str = "seal_type_normalizer"

    model_config = ConfigDict(extra="forbid")


class DesignFieldStatusProjection(BaseModel):
    key: str
    label: str
    status: str
    criticality: str
    value: Optional[Any] = None
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class DesignScreeningCheckProjection(BaseModel):
    check_id: str
    label: str
    status: str
    value: Optional[float] = None
    unit: Optional[str] = None
    inputs: List[str] = Field(default_factory=list)
    message: str = ""

    model_config = ConfigDict(extra="forbid")


class DesignEscalationTriggerProjection(BaseModel):
    trigger_id: str
    label: str
    severity: str
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class SealDesignIntakeProjection(BaseModel):
    """Read-only minimum-dataset and screening view for new seal designs.

    This projection exposes backend-derived intake gaps and conservative
    screening hints. It does not confirm a design, select materials, or mark a
    solution as released.
    """

    schema_version: str = "seal_design_intake_v0.8.3"
    status: str = "no_design_dataset"
    known_fields: List[DesignFieldStatusProjection] = Field(default_factory=list)
    missing_fields: List[DesignFieldStatusProjection] = Field(default_factory=list)
    screening_checks: List[DesignScreeningCheckProjection] = Field(default_factory=list)
    escalation_triggers: List[DesignEscalationTriggerProjection] = Field(
        default_factory=list
    )
    next_required_fields: List[str] = Field(default_factory=list)
    boundary_notice: str = ""
    event_names: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CaseWorkspaceProjection(BaseModel):
    """Top-level UI-facing read model for a single engineering case."""

    case_type: CaseType = CaseType.unknown
    request_type: Optional[RequestType] = None
    engineering_path: Optional[EngineeringPath] = None
    seal_application_profile: SealApplicationProfileView = Field(
        default_factory=SealApplicationProfileView
    )
    design_intake: SealDesignIntakeProjection = Field(
        default_factory=SealDesignIntakeProjection
    )
    cockpit_view: EngineeringCockpitView = Field(default_factory=EngineeringCockpitView)
    deep_dive_tabs: List[DeepDiveTabProjection] = Field(default_factory=list)
    decision_understanding: DecisionUnderstandingProjection = Field(
        default_factory=DecisionUnderstandingProjection
    )
    rfq_readiness_projection: Optional[Dict[str, Any]] = None
    needs_analysis: NeedsAnalysisProjection = Field(
        default_factory=NeedsAnalysisProjection
    )
    current_state_analysis: CurrentStateAnalysisProjection = Field(
        default_factory=CurrentStateAnalysisProjection
    )
    next_best_questions: List[NextBestQuestionProjection] = Field(default_factory=list)
    completeness_score: CompletenessScoreProjection = Field(
        default_factory=CompletenessScoreProjection
    )
    case_summary: CaseSummary = Field(default_factory=CaseSummary)
    completeness: CompletenessStatus = Field(default_factory=CompletenessStatus)
    governance_status: GovernanceStatus = Field(default_factory=GovernanceStatus)
    specificity: SpecificityInfo = Field(default_factory=SpecificityInfo)
    candidate_clusters: CandidateClusterSummary = Field(
        default_factory=CandidateClusterSummary
    )
    conflicts: ConflictSummary = Field(default_factory=ConflictSummary)
    claims_summary: ClaimsSummary = Field(default_factory=ClaimsSummary)
    evidence_summary: EvidenceSummary = Field(default_factory=EvidenceSummary)
    manufacturer_questions: ManufacturerQuestions = Field(
        default_factory=ManufacturerQuestions
    )
    rfq_status: RFQStatus = Field(default_factory=RFQStatus)
    artifact_status: ArtifactStatus = Field(default_factory=ArtifactStatus)
    rfq_package: RFQPackageSummary = Field(default_factory=RFQPackageSummary)
    partner_matching: PartnerMatchingSummary = Field(
        default_factory=PartnerMatchingSummary
    )
    communication_context: CommunicationContext = Field(
        default_factory=CommunicationContext
    )
    parameters: Dict[str, Any] = Field(default_factory=dict)
    medium_capture: MediumCaptureSummary = Field(default_factory=MediumCaptureSummary)
    medium_classification: MediumClassificationSummary = Field(
        default_factory=MediumClassificationSummary
    )
    medium_context: MediumContextSummary = Field(default_factory=MediumContextSummary)
    material_intelligence: MaterialIntelligenceProjection = Field(
        default_factory=MaterialIntelligenceProjection
    )
    challenge_intelligence: ChallengeIntelligenceProjection = Field(
        default_factory=ChallengeIntelligenceProjection
    )
    v91_workspace: V91WorkspaceProjection = Field(
        default_factory=V91WorkspaceProjection
    )
    v92_dashboard: Optional[Dict[str, Any]] = None
    technical_derivations: List[TechnicalDerivationItem] = Field(default_factory=list)
    cycle_info: CycleInfo = Field(default_factory=CycleInfo)

    model_config = ConfigDict(extra="forbid")
