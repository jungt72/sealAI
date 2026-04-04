from typing import Annotated, Any, Dict, List, Optional, TypedDict, Literal, NotRequired
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

from app.agent.case_state import CaseState

ReleaseStatus = Literal[
    "inadmissible",
    "precheck_only",
    "manufacturer_validation_required",
    "rfq_ready",
    "not_applicable",
]
RFQAdmissibility = Literal["inadmissible", "provisional", "ready", "not_applicable"]
SpecificityLevel = Literal["family_only", "subfamily", "compound_required", "product_family_required"]
IdentityClass = Literal[
    "identity_confirmed",
    "identity_probable",
    "identity_family_only",
    "identity_unresolved",
]


class ObservedInputRecord(TypedDict, total=False):
    """Blueprint v1.2 Section 02: immutable raw intake before normalization."""

    source: str
    raw_text: str
    claim_type: str
    certainty: str
    confirmed: bool
    source_fact_ids: List[str]


class IdentityRecord(TypedDict, total=False):
    """Blueprint v1.2 Section 02: normalized field metadata with identity class."""

    raw_value: Any
    normalized_value: Any
    identity_class: IdentityClass
    normalization_certainty: str
    mapping_reason: str
    source_fact_ids: List[str]
    deterministic_source: str
    evidence_quality: str
    authority_quality: str
    temporal_quality: str

class ObservedLayer(TypedDict):
    """
    Observed Layer (Rohwerte, Units, Originalformulierungen).
    Blueprint Section 02: technisch wirksame Daten starten hier und bleiben roh.
    """
    observed_inputs: List[ObservedInputRecord]
    raw_parameters: Dict[str, Any]

class NormalizedLayer(TypedDict):
    """
    Normalized Layer (Identity Gating).
    Blueprint Section 02 + Section 03: nur deterministisch validierte Normalisierung.
    """
    identity_records: Dict[str, IdentityRecord]
    normalized_parameters: Dict[str, Any]

class AssertedLayer(TypedDict):
    """
    Asserted Layer (Typed Profiles).
    Blueprint Section 02: bindender technischer State nur aus Normalized-Reducer.
    """
    medium_profile: Dict[str, Any]
    machine_profile: Dict[str, Any]
    installation_profile: Dict[str, Any]
    operating_conditions: Dict[str, Any]  # temperature, pressure
    sealing_requirement_spec: Dict[str, Any]

class GovernanceLayer(TypedDict):
    """
    Governance Layer (Compliance & Readiness).
    Blueprint Sections 02, 06, 08: normative Governance-Enumerationen und Gates.
    """
    release_status: ReleaseStatus
    rfq_admissibility: RFQAdmissibility
    specificity_level: SpecificityLevel
    scope_of_validity: List[str]
    assumptions_active: List[str]
    gate_failures: List[str]
    unknowns_release_blocking: List[str]
    unknowns_manufacturer_validation: List[str]
    conflicts: List[Dict[str, Any]]


ReviewState = Literal["none", "pending", "approved", "rejected"]
CriticalReviewStatus = Literal["not_run", "passed", "failed"]


class ReviewLayer(TypedDict, total=False):
    """
    HITL Review Layer — Phase A3.
    Deterministic trigger writes this; frontend/operator resolves it.
    Never populated by the LLM.
    """
    review_required: bool           # True when a human review is mandatory
    review_state: ReviewState       # lifecycle: none → pending → approved | rejected
    review_reason: str              # why the review was triggered (deterministic rule name)
    reviewed_by: Optional[str]      # set by operator after review
    review_decision: Optional[str]  # operator decision text
    review_note: Optional[str]      # optional annotation by reviewer
    critical_review_status: CriticalReviewStatus
    critical_review_passed: bool
    blocking_findings: List[str]
    soft_findings: List[str]
    required_corrections: List[str]

class CycleLayer(TypedDict):
    """
    Cycle Control (Determinismus & Revision).
    Blueprint Section 02 + Section 12: revisionsgebunden und obsoleszenzfähig.
    """
    analysis_cycle_id: str
    snapshot_parent_revision: int
    superseded_by_cycle: Optional[str]
    contract_obsolete: bool
    contract_obsolete_reason: Optional[str]
    state_revision: int

class SelectionCandidate(TypedDict):
    candidate_id: str
    candidate_kind: str
    material_family: str
    filler_hint: Optional[str]
    grade_name: Optional[str]
    manufacturer_name: Optional[str]
    viability_status: str
    block_reason: Optional[str]
    evidence_refs: List[str]

class RecommendationArtifact(TypedDict):
    """
    Non-binding projection artifact.
    Blueprint Section 08: never the source of technical truth or release truth.
    """

    selection_status: str
    winner_candidate_id: Optional[str]
    candidate_projection: Optional[Dict[str, Any]]
    candidate_ids: List[str]
    viable_candidate_ids: List[str]
    blocked_candidates: List[Dict[str, str]]
    evidence_basis: List[str]
    evidence_status: str
    provenance_refs: List[str]
    rationale_basis: List[str]
    conflict_status: str
    integrity_status: str
    domain_scope_status: str
    threshold_status: str
    release_status: ReleaseStatus
    rfq_admissibility: RFQAdmissibility
    specificity_level: SpecificityLevel
    output_blocked: bool
    binding_level: str
    readiness_status: str
    blocking_reason: str
    rationale_summary: str
    trace_provenance_refs: List[str]

class EvidenceProvenanceProjection(TypedDict):
    """
    Deterministic projection of the current evidence/provenance footing.
    """

    status: str
    provenance_refs: List[str]
    evidence_basis: List[str]

class ConflictStatusProjection(TypedDict):
    """
    Deterministic projection of parameter conflict/correction state.
    """

    status: str
    affected_keys: List[str]
    previous_value_summary: str
    current_value_summary: str
    correction_applied: bool
    conflict_still_open: bool

class UnitNormalizationProjection(TypedDict):
    """
    Deterministic projection of normalization/unit plausibility status.
    """

    statuses: Dict[str, str]
    affected_keys: List[str]
    warning_keys: List[str]
    blocking_keys: List[str]

class ParameterIntegrityProjection(TypedDict):
    """
    Compact projection of whether current parameters are usable for structured steps.
    """

    affected_keys: List[str]
    integrity_status: str
    warning_keys: List[str]
    blocking_keys: List[str]
    usable_for_structured_step: bool

class ThresholdProjection(TypedDict):
    """
    Compact projection of triggered deterministic threshold checks.
    """

    triggered_thresholds: List[str]
    warning_thresholds: List[str]
    blocking_thresholds: List[str]
    threshold_status: str
    usable_for_governed_step: bool

class DomainScopeProjection(TypedDict):
    """
    Deterministic domain-scope status for the current structured case.
    """

    status: str
    triggered_thresholds: List[str]
    warning_thresholds: List[str]
    blocking_thresholds: List[str]
    threshold_status: str
    usable_for_governed_step: bool

class CorrectionProjection(TypedDict):
    """
    Compact projection for user-visible correction/conflict state.
    """

    affected_keys: List[str]
    previous_value_summary: str
    current_value_summary: str
    correction_applied: bool
    conflict_still_open: bool

class ReviewEscalationProjection(TypedDict):
    """
    Deterministic projection for the next human-facing step when governed output
    is withheld or requires further validation.
    """

    status: str
    reason: str
    missing_items: List[str]
    ambiguous_candidate_ids: List[str]
    evidence_status: str
    provenance_refs: List[str]
    conflict_status: str
    integrity_status: str
    affected_keys: List[str]
    review_meaningful: bool
    handover_possible: bool
    human_validation_ready: bool

class ClarificationProjection(TypedDict):
    """
    Deterministic clarification projection for incomplete structured cases.
    """

    missing_items: List[str]
    next_question_key: Optional[str]
    next_question_label: Optional[str]
    evidence_status: str
    provenance_refs: List[str]
    conflict_status: str
    integrity_status: str
    affected_keys: List[str]
    clarification_still_meaningful: bool
    reason_if_not: str

class UserFacingOutputProjection(TypedDict):
    """
    Deterministic user-facing result type for the current structured state.
    """

    status: str

class OutputContractProjection(TypedDict):
    """
    Compact output contract for structured user-facing projection.
    """

    output_status: str
    allowed_surface_claims: List[str]
    next_user_action: str
    visible_warning_flags: List[str]
    suppress_recommendation_details: bool

class ProjectionInvariantProjection(TypedDict):
    """
    Explicit projection-invariant status across the structured user-facing slices.
    """

    invariant_ok: bool
    invariant_violations: List[str]

class StateTraceAuditProjection(TypedDict):
    """
    Compact deterministic trace/audit summary for the current structured state.
    """

    primary_status_reason: str
    contributing_reasons: List[str]
    blocking_reasons: List[str]
    trace_flags: List[str]

class CaseSummaryProjection(TypedDict):
    """
    Compact deterministic case summary for the current structured state.
    """

    current_case_status: str
    confirmed_core_fields: List[str]
    missing_core_fields: List[str]
    active_blockers: List[str]
    next_step: str

class ActionabilityProjection(TypedDict):
    """
    Compact deterministic projection of the currently allowed structured action space.
    """

    actionability_status: str
    primary_allowed_action: str
    blocked_actions: List[str]
    next_expected_user_action: str

class StateDeltaProjection(TypedDict):
    """
    Compact deterministic comparison of two structured states.
    """

    changed_keys: List[str]
    changed_statuses: Dict[str, Dict[str, Any]]
    primary_delta_reason: str
    delta_direction: str

class StructuredSnapshotContract(TypedDict):
    """
    Stable compact snapshot of the relevant structured state.
    """

    case_status: str
    output_status: str
    primary_reason: str
    next_step: str
    primary_allowed_action: str
    active_blockers: List[str]

class StructuredSnapshotComparisonContract(TypedDict):
    """
    Stable compact comparison contract between two structured snapshots.
    """

    from_status: str
    to_status: str
    changed_actions: Dict[str, Any]
    changed_blockers: Dict[str, List[str]]
    primary_delta_reason: str
    delta_direction: str

class SelectionLayer(TypedDict):
    """
    Non-binding UI projection only.
    Kept for minimal-diff compatibility with /api/agent responses.
    """

    selection_status: str
    candidates: List[SelectionCandidate]
    viable_candidate_ids: List[str]
    blocked_candidates: List[Dict[str, str]]
    winner_candidate_id: Optional[str]
    recommendation_artifact: Optional[RecommendationArtifact]
    evidence_provenance_projection: NotRequired[Optional[EvidenceProvenanceProjection]]
    conflict_status_projection: NotRequired[Optional[ConflictStatusProjection]]
    unit_normalization_projection: NotRequired[Optional[UnitNormalizationProjection]]
    parameter_integrity_projection: NotRequired[Optional[ParameterIntegrityProjection]]
    threshold_projection: NotRequired[Optional[ThresholdProjection]]
    domain_scope_projection: NotRequired[Optional[DomainScopeProjection]]
    correction_projection: NotRequired[Optional[CorrectionProjection]]
    review_escalation_projection: NotRequired[Optional[ReviewEscalationProjection]]
    clarification_projection: NotRequired[Optional[ClarificationProjection]]
    user_facing_output_projection: NotRequired[Optional[UserFacingOutputProjection]]
    output_contract_projection: NotRequired[Optional[OutputContractProjection]]
    projection_invariant_projection: NotRequired[Optional[ProjectionInvariantProjection]]
    state_trace_audit_projection: NotRequired[Optional[StateTraceAuditProjection]]
    case_summary_projection: NotRequired[Optional[CaseSummaryProjection]]
    actionability_projection: NotRequired[Optional[ActionabilityProjection]]
    structured_snapshot_contract: NotRequired[Optional[StructuredSnapshotContract]]
    candidate_clusters: NotRequired[List[Dict[str, Any]]]
    release_status: ReleaseStatus
    rfq_admissibility: RFQAdmissibility
    specificity_level: SpecificityLevel
    output_blocked: bool

class HandoverLayer(TypedDict, total=False):
    """
    Commercial / Handover Layer — Phase A6.
    Populated deterministically at the end of a qualified structured-path case.
    Contains only clean, ERP-ready order-profile data — no internal governance
    state, no reasoning artefacts, no demo-data flags.
    """
    is_handover_ready: bool            # True only when rfq_ready + no pending HITL review
    handover_status: str               # releasable | handoverable | reviewable | not_handoverable
    handover_reason: str               # deterministic explanation for the status
    target_system: Optional[str]       # e.g. "rfq_portal" | "shop" | None
    handover_payload: Optional[Dict[str, Any]]  # sanitised order-profile for the target system


class OutcomeLayer(TypedDict, total=False):
    """
    Outcome-Feedback Layer.
    Populated asynchronously by external feedback loops after the case is closed.
    NEVER written by the agent graph or LLM during a run.
    All fields are optional — the layer starts empty and is filled post-deployment.
    Schema is defined here so downstream consumers have a stable contract.
    """
    implemented: bool       # Recommendation was implemented as-is
    failed: bool            # Implementation failed in the field
    replaced: bool          # Material was replaced after initial deployment
    review_override: bool   # A human reviewer overrode the governed recommendation
    outcome_note: str       # Free-text field for the operator/engineer feedback note


class SealingAIState(TypedDict):
    """
    Blueprint Section 02 / Phase A1:
    bindender State läuft über Observed -> Normalized -> Asserted -> Governance -> Cycle.
    `selection` bleibt ausschließlich als nicht-bindende Projektion für den Live-Pfad bestehen.
    `review`    trägt den HITL-Status (Phase A3) — niemals LLM-generiert.
    `handover`  trägt den Commercial-Payload (Phase A6) — kein ERP-Call, nur Grenzstruktur.
    `outcome`   trägt das Echtzeit-Feedback nach Deployment (Phase A7) — nur extern befüllt.
    """
    observed: ObservedLayer
    normalized: NormalizedLayer
    asserted: AssertedLayer
    governance: GovernanceLayer
    cycle: CycleLayer
    selection: SelectionLayer
    result_contract: NotRequired[Dict[str, Any]]
    review: NotRequired[ReviewLayer]      # HITL review state (Phase A3)
    handover: NotRequired[HandoverLayer]  # Commercial handover payload (Phase A6)
    outcome: NotRequired[OutcomeLayer]    # Post-deployment outcome feedback (Phase A7)

class AgentState(TypedDict):
    """
    LangGraph Orchestration Layer State.
    Integriert LLM-Kontext (messages) und den aktiven Orchestrierungszustand.

    During the migration, `case_state` is the canonical productive authority for
    persisted governed truth. `sealing_state` and `working_profile` remain as
    orchestration/compat surfaces until the legacy graph-state is collapsed.
    """
    messages: Annotated[List[AnyMessage], add_messages]
    sealing_state: SealingAIState
    relevant_fact_cards: List[Dict[str, Any]]  # Speichert FactCards für Tool-Nodes (Phase H6)
    working_profile: Dict[str, Any]  # Transitional projection / compat slice
    tenant_id: Optional[str]
    owner_id: NotRequired[Optional[str]]
    loaded_state_revision: NotRequired[int]
    case_state: NotRequired[CaseState]  # Canonical productive authority
    result_form: NotRequired[Optional[str]]   # ResultForm value, e.g. "direct_answer"
    policy_path: NotRequired[Optional[str]]   # "fast" | "structured" — set by router (Phase 0A.3)
    run_meta: NotRequired[Optional[Dict[str, Any]]]  # model_id, prompt_version, policy_version (Phase 0A.5)
    # V3 spec fields (Phase 0A QW-2/3/4)
    turn_count: int                           # current turn in this session (hard limit guard)
    max_turns: int                            # hard ceiling — default 12 (CLAUDE.md)
    user_persona: NotRequired[str]            # "erfahrener" | "einsteiger" | "entscheider" | "unknown"
    knowledge_coverage: NotRequired[str]      # "full" | "partial" | "limited"
    inquiry_id: NotRequired[str]              # session_id mirrored for state traceability
