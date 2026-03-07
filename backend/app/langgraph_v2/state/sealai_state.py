# path: backend/app/langgraph_v2/state/sealai_state.py
"""Strict Pydantic state definition for SealAI LangGraph v2 (4-pillar architecture)."""

from __future__ import annotations

import operator
import re
from typing import Annotated, Any, Dict, List, Optional, TypeVar

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator
from typing_extensions import Literal

try:
    from app.services.rag.state import ErrorInfo as LegacyErrorInfo
    from app.services.rag.state import WorkingProfile as LegacyWorkingProfile
except Exception:
    class LegacyWorkingProfile(BaseModel):
        """Fallback for environments where legacy WorkingProfile is unavailable."""

        model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

        def as_dict(self) -> Dict[str, Any]:
            return self.model_dump(exclude_none=True)

    class LegacyErrorInfo(BaseModel):
        """Fallback for environments where legacy ErrorInfo is unavailable."""

        model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

from app.langgraph_v2.io import AskMissingRequest, CoverageAnalysis, ParameterProfile
from app.langgraph_v2.state.audit import EvidenceBundle, SourceRefPayload, ToolCallRecord
from app.langgraph_v2.types import (
    IntentKey,
    KnowledgeType,
    PhaseLiteral,
    normalize_knowledge_type,
)

AskMissingScope = Literal["discovery", "technical"]


IntentGoal = Literal[
    "smalltalk",
    "design_recommendation",
    "explanation_or_comparison",
    "troubleshooting_leakage",
    "out_of_scope",
]


class Intent(BaseModel):
    goal: IntentGoal = "design_recommendation"
    domain: Literal["sealing_technology"] | str = "sealing_technology"
    confidence: float = 0.0
    high_impact_gaps: List[str] = Field(default_factory=list)

    # legacy compatibility
    key: Optional[IntentKey] = None
    knowledge_type: Optional[KnowledgeType] = None
    routing_hint: Optional[str] = None
    complexity: Optional[str] = None
    needs_sources: bool = False
    need_sources: bool = False
    seeded_parameters: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")

    @field_validator("knowledge_type", mode="before")
    @classmethod
    def _normalize_knowledge_type(cls, value: Any) -> Any:
        return normalize_knowledge_type(value)


class SealAIExtractedParameters(BaseModel):
    pressure_bar: Optional[float] = None
    temperature_c: Optional[float] = None
    medium: Optional[str] = None
    quantity: Optional[int] = None
    sku: Optional[str] = None
    shaft_diameter: Optional[float] = None
    speed_rpm: Optional[float] = None
    housing_bore: Optional[float] = None

    model_config = ConfigDict(extra="forbid")


class SealAIIntentOutput(BaseModel):
    intent_category: Literal[
        "CHIT_CHAT",
        "GENERAL_KNOWLEDGE",
        "MATERIAL_RESEARCH",
        "COMMERCIAL",
        "ENGINEERING_CALCULATION",
    ]
    is_safety_critical: bool
    requires_rag: bool
    needs_pricing: bool
    extracted_parameters: SealAIExtractedParameters = Field(default_factory=SealAIExtractedParameters)
    reasoning: str

    model_config = ConfigDict(extra="forbid")


class RenderedPrompt(BaseModel):
    template_name: str
    version: str
    rendered_text: str
    hash_sha256: str

    model_config = ConfigDict(extra="forbid")


_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def take_last_non_null(left: Any, right: Any) -> Any:
    """Reducer for concurrent writes: keep newest non-null value."""
    return right if right is not None else left


def resolve_last_node(left: Optional[str], right: Optional[str]) -> Optional[str]:
    """Reducer for concurrent writes to last_node: prefer the newest (right) value."""
    return right if right is not None else left


def _deep_merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        left_value = merged.get(key)
        if isinstance(left_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(left_value, value)
        else:
            merged[key] = value
    return merged


def merge_dicts(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Reducer for concurrent dict writes: deep-merge right over left."""
    if right is None:
        return dict(left or {})
    if left is None:
        return dict(right or {})
    return _deep_merge_dicts(dict(left), dict(right))


def _dedupe_list(values: List[Any]) -> List[Any]:
    try:
        return list(set(values))
    except TypeError:
        deduped: List[Any] = []
        for item in values:
            if item in deduped:
                continue
            deduped.append(item)
        return deduped


def merge_working_profile(
    left: Optional[LegacyWorkingProfile],
    right: Optional[LegacyWorkingProfile],
) -> LegacyWorkingProfile:
    """Deep-merge reducer for legacy engineering WorkingProfile patches."""
    if left is None and right is None:
        return LegacyWorkingProfile()

    base: Dict[str, Any] = {}
    if left is not None:
        base = left.model_dump(exclude_none=False)

    if right is None:
        return LegacyWorkingProfile.model_validate(base)

    patch = right.model_dump(exclude_unset=True, exclude_none=True)
    if not patch and left is not None:
        return left

    for key, value in patch.items():
        left_value = base.get(key)
        if isinstance(left_value, list) and isinstance(value, list):
            base[key] = _dedupe_list(list(left_value) + list(value))
        elif isinstance(left_value, dict) and isinstance(value, dict):
            merged = dict(left_value)
            merged.update(value)
            base[key] = merged
        else:
            base[key] = value

    return LegacyWorkingProfile.model_validate(base)


class CalcResults(BaseModel):
    safety_factor: Optional[float] = None
    temperature_margin: Optional[float] = None
    pressure_margin: Optional[float] = None
    v_surface_m_s: Optional[float] = None
    pv_value_mpa_m_s: Optional[float] = None
    friction_power_watts: Optional[float] = None
    hrc_warning: Optional[bool] = None
    notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class LiveCalcTile(BaseModel):
    v_surface_m_s: Optional[float] = None
    pv_value_mpa_m_s: Optional[float] = None
    p_v_limit_check: Optional[str] = None
    hrc_value: Optional[float] = None
    hrc_warning: bool = False
    runout_warning: bool = False
    pv_warning: bool = False
    friction_power_watts: Optional[float] = None
    dry_running_risk: bool = False
    clearance_gap_mm: Optional[float] = None
    extrusion_risk: bool = False
    requires_backup_ring: bool = False
    compression_ratio_pct: Optional[float] = None
    groove_fill_pct: Optional[float] = None
    stretch_pct: Optional[float] = None
    geometry_warning: bool = False
    thermal_expansion_mm: Optional[float] = None
    shrinkage_risk: bool = False
    chem_warning: bool = False
    chem_message: Optional[str] = None
    status: Literal["ok", "warning", "critical", "insufficient_data"] = "insufficient_data"
    parameters: Dict[str, str | int | float] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class Recommendation(BaseModel):
    seal_family: Optional[str] = None
    material: Optional[str] = None
    profile: Optional[str] = None
    summary: str = ""
    rationale: str = ""
    risk_hints: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class Source(BaseModel):
    snippet: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class GovernanceMetadata(BaseModel):
    scope_of_validity: List[str] = Field(default_factory=list)
    assumptions_active: List[str] = Field(default_factory=list)
    unknowns_release_blocking: List[str] = Field(default_factory=list)
    unknowns_manufacturer_validation: List[str] = Field(default_factory=list)
    gate_failures: List[str] = Field(default_factory=list)
    governance_notes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RequirementSpec(BaseModel):
    """Neutral requirement space for technical constraints and operational window.
    
    This model decouples technical needs from candidate choices or LLM-resolved 
    parameters, acting as the 'Source of Truth' for what the application requires.
    """
    operating_conditions: Dict[str, Any] = Field(default_factory=dict)
    missing_critical_parameters: List[str] = Field(default_factory=list)
    exclusion_criteria: List[str] = Field(default_factory=list)
    unknowns_release_blocking: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class AnswerContract(BaseModel):
    # Cycle binding — set to "cycle_{session_id}_{cycle_id}" when the contract is built.
    # Used to detect staleness when the assertion cycle advances.
    analysis_cycle_id: Optional[str] = None
    resolved_parameters: Dict[str, Any] = Field(default_factory=dict)
    requirement_spec: Optional[RequirementSpec] = None
    calc_results: Dict[str, Any] = Field(default_factory=dict)
    selected_fact_ids: List[str] = Field(default_factory=list)
    candidate_semantics: List[Dict[str, Any]] = Field(default_factory=list)
    # Three-cluster grouping derived deterministically from candidate_semantics.
    # Keys: plausibly_viable, viable_only_with_manufacturer_validation, inadmissible_or_excluded.
    candidate_clusters: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    governance_metadata: GovernanceMetadata = Field(default_factory=GovernanceMetadata)
    required_disclaimers: List[str] = Field(default_factory=list)
    respond_with_uncertainty: bool = False

    model_config = ConfigDict(extra="forbid")


class ConflictRecord(BaseModel):
    # Blueprint v1.2 — 9 conflict types
    conflict_type: Literal[
        "FALSE_CONFLICT",
        "SOURCE_CONFLICT",
        "SCOPE_CONFLICT",
        "CONDITION_CONFLICT",
        "COMPOUND_SPECIFICITY_CONFLICT",
        "ASSUMPTION_CONFLICT",
        "TEMPORAL_VALIDITY_CONFLICT",
        "PARAMETER_CONFLICT",
        "UNKNOWN",
    ] = "UNKNOWN"
    # Blueprint v1.2 — 6 severity levels
    # BLOCKING_UNKNOWN / RESOLUTION_REQUIRES_MANUFACTURER_SCOPE are governance-level severities
    # that signal incompleteness requiring external validation, not necessarily a hard failure.
    severity: Literal[
        "INFO",
        "WARNING",
        "HARD",
        "CRITICAL",
        "BLOCKING_UNKNOWN",
        "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE",
    ] = "WARNING"
    summary: str = ""
    sources_involved: List[str] = Field(default_factory=list)
    scope_note: str = ""
    resolution_status: Literal["OPEN", "RESOLVED", "DISMISSED"] = "OPEN"

    model_config = ConfigDict(extra="forbid")


class VerificationReport(BaseModel):
    contract_hash: str
    draft_hash: str
    status: Literal["pass", "fail"]
    failure_type: Optional[str] = None
    failed_claim_spans: List[Dict[str, Any]] = Field(default_factory=list)
    conflicts: List[ConflictRecord] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RFQAdmissibilityContract(BaseModel):
    status: Literal["inadmissible", "provisional", "ready"] = "inadmissible"
    # Blueprint-konformer 4-Wert Release-Status — additiv zu status, nicht als Ersatz.
    # Wird deterministisch aus Governance-Signalen abgeleitet:
    #   inadmissible                   — blockers nicht leer
    #   precheck_only                  — open_points nicht leer oder requires_human_review, keine Blocker
    #   manufacturer_validation_required — unknowns_manufacturer_validation nicht leer, keine Blocker
    #   rfq_ready                      — governed_ready=True, status=="ready", blockers leer
    release_status: Literal[
        "inadmissible",
        "precheck_only",
        "manufacturer_validation_required",
        "rfq_ready",
    ] = "inadmissible"
    reason: Optional[str] = "rfq_contract_missing"
    open_points: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    manufacturer_validation_items: List[str] = Field(default_factory=list)
    governed_ready: bool = False
    derived_from_assertion_cycle_id: Optional[int] = None
    derived_from_assertion_revision: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class ParameterIdentityRecord(BaseModel):
    raw_value: Any = None
    normalized_value: Any = None
    identity_class: Literal["confirmed", "probable", "family_only", "unresolved"] = "unresolved"
    normalization_notes: List[str] = Field(default_factory=list)
    normalization_source: Optional[str] = None
    lookup_allowed: bool = False
    promotion_allowed: bool = False

    model_config = ConfigDict(extra="forbid")


class QuestionItem(BaseModel):
    id: str
    question: str
    reason: str
    priority: Literal["high", "medium", "low"] = "medium"
    status: Literal["open", "answered", "deferred"] = "open"
    source: str = "derived"

    model_config = ConfigDict(extra="forbid")


class FactItem(BaseModel):
    value: Any = None
    source: str = "panel"
    confidence: float = 0.0
    evidence_refs: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CandidateItem(BaseModel):
    kind: str
    value: str
    rationale: str = ""
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    specificity: Literal["compound_specific", "family_level", "material_class", "document_hit", "unresolved"] = "unresolved"
    source_kind: str = "unknown"
    governed: bool = False
    # Deterministic gate exclusion — set by chemical_resistance or material_limits checks.
    # A non-None value routes this candidate to inadmissible_or_excluded cluster.
    excluded_by_gate: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class DecisionEntry(BaseModel):
    round: int = 0
    action: str = ""
    reason: str = ""
    cost: int = 0
    confidence: float = 0.0
    open_questions_summary: str = ""

    model_config = ConfigDict(extra="forbid")


class Budget(BaseModel):
    remaining: int = 8
    spent: int = 0

    model_config = ConfigDict(extra="forbid")


class WorkingMemory(BaseModel):
    supervisor_decision: Optional[str] = None
    retries: int = 0
    material_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    material_requirements: RequirementSpec = Field(default_factory=RequirementSpec)
    material_recommendation: Dict[str, Any] = Field(default_factory=dict)
    knowledge_material: Optional[str] = None
    knowledge_lifetime: Optional[str] = None
    knowledge_generic: Optional[str] = None
    response_text: Optional[str] = None
    response_kind: Optional[str] = None
    technical_profile: Dict[str, Any] = Field(default_factory=dict)

    frontdoor_reply: Optional[str] = None
    design_notes: Dict[str, Any] = Field(default_factory=dict)
    comparison_notes: Dict[str, Any] = Field(default_factory=dict)
    troubleshooting_notes: Dict[str, Any] = Field(default_factory=dict)
    diagnostic_data: Dict[str, Any] = Field(default_factory=dict)

    panel_calculator: Dict[str, Any] = Field(default_factory=dict)
    panel_material: Dict[str, Any] = Field(default_factory=dict)
    panel_norms_rag: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


def merge_working_memory(
    left: Optional["WorkingMemory"] | Dict[str, Any],
    right: Optional["WorkingMemory"] | Dict[str, Any],
) -> "WorkingMemory":
    """Reducer for concurrent WorkingMemory updates in the same graph step."""
    if right is None:
        if isinstance(left, WorkingMemory):
            return left
        return WorkingMemory.model_validate(left or {})

    if left is None:
        if isinstance(right, WorkingMemory):
            return right
        return WorkingMemory.model_validate(right or {})

    left_dict = (
        left.model_dump(exclude_defaults=True, exclude_none=True)
        if isinstance(left, WorkingMemory)
        else dict(left or {})
    )
    right_dict = (
        right.model_dump(exclude_defaults=True, exclude_none=True)
        if isinstance(right, WorkingMemory)
        else dict(right or {})
    )
    merged = _deep_merge_dicts(left_dict, right_dict)
    return WorkingMemory.model_validate(merged)


ModelT = TypeVar("ModelT", bound=BaseModel)


def _merge_model(model_cls: type[ModelT], left: Any, right: Any) -> ModelT:
    if right is None:
        if isinstance(left, model_cls):
            return left
        return model_cls.model_validate(left or {})
    if left is None:
        if isinstance(right, model_cls):
            return right
        return model_cls.model_validate(right or {})

    left_dict = left.model_dump(exclude_defaults=True, exclude_none=True) if isinstance(left, BaseModel) else dict(left or {})
    right_dict = right.model_dump(exclude_defaults=True, exclude_none=True) if isinstance(right, BaseModel) else dict(right or {})
    merged = _deep_merge_dicts(left_dict, right_dict)
    return model_cls.model_validate(merged)


class ConversationState(BaseModel):
    """Pillar 1: chat transcript and user intent context only."""

    messages: Annotated[List[BaseMessage], add_messages] = Field(default_factory=list)
    user_id: Optional[str] = None
    thread_id: Optional[str] = None
    user_context: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None  # legacy RAGState

    router_classification: Optional[
        Literal["new_case", "follow_up", "clarification", "rfq_trigger", "resume", "ask_user"]
    ] = None
    intent: Optional[Intent] = None
    knowledge_type: Optional[KnowledgeType] = None
    use_case_raw: Optional[str] = None
    application_category: Optional[str] = None
    motion_type: Optional[str] = None
    seal_family: Optional[str] = None
    user_persona: Optional[str] = None

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    @field_validator("knowledge_type", mode="before")
    @classmethod
    def _normalize_state_knowledge_type(cls, value: Any) -> Any:
        return normalize_knowledge_type(value)

    @field_validator("intent", mode="before")
    @classmethod
    def _normalize_state_intent(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
        if normalized in {"smalltalk", "chit_chat", "chitchat", "greeting"}:
            return {"goal": "smalltalk", "routing_hint": "CHIT_CHAT"}
        if normalized in {"engineering", "engineering_calculation"}:
            return {"goal": "design_recommendation", "routing_hint": "ENGINEERING_CALCULATION"}
        return value


def merge_conversation_state(left: Any, right: Any) -> ConversationState:
    return _merge_model(ConversationState, left, right)


class WorkingProfile(BaseModel):
    """Pillar 2: digital twin for deterministic engineering parameters and results."""

    engineering_profile: Annotated[LegacyWorkingProfile, merge_working_profile] = Field(default_factory=LegacyWorkingProfile)
    profile: Optional[LegacyWorkingProfile] = None  # legacy RAGState profile mirror

    parameter_profile: Optional[ParameterProfile] = None
    medium: Annotated[Optional[str], take_last_non_null] = None
    temperature_c: Annotated[Optional[float], take_last_non_null] = None
    pressure_bar: Annotated[Optional[float], take_last_non_null] = None

    extracted_params: Dict[str, Any] = Field(default_factory=dict)
    derived_from_assertion_cycle_id: Optional[int] = None
    derived_from_assertion_revision: Optional[int] = None
    derived_artifacts_stale: bool = False
    derived_artifacts_stale_reason: Optional[str] = None
    calculation_result: Optional[Dict[str, Any]] = None
    is_critical_application: bool = False
    live_calc_tile: LiveCalcTile = Field(default_factory=LiveCalcTile)
    tradeoff_options: List[Dict[str, Any]] = Field(default_factory=list)
    capability_requirements: Dict[str, Any] = Field(default_factory=dict)

    dp_dt_bar_per_s: Optional[float] = None
    side_load_kn: Optional[float] = None
    aed_required: Optional[bool] = None
    medium_additives: Optional[str] = None
    fluid_contamination_iso: Optional[str] = None
    surface_hardness_hrc: Optional[float] = None
    pressure_spike_factor: Optional[float] = None
    dynamic_type: Optional[str] = None

    analysis_complete: bool = False
    calc_results_ok: bool = False
    calc_results: Optional[CalcResults] = None
    compliance_results: Optional[Dict[str, Any]] = None
    recommendation: Optional[Recommendation] = None

    material_choice: Dict[str, Any] = Field(default_factory=dict)
    profile_choice: Dict[str, Any] = Field(default_factory=dict)
    factcard_matches: List[Dict[str, Any]] = Field(default_factory=list)

    sealing_type_results: List[Any] = Field(default_factory=list)  # legacy RAGState

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def as_dict(self) -> Dict[str, Any]:
        profile_data: Dict[str, Any] = {}
        if hasattr(self.engineering_profile, "as_dict"):
            profile_data = self.engineering_profile.as_dict()  # type: ignore[assignment]
        elif hasattr(self.engineering_profile, "model_dump"):
            profile_data = self.engineering_profile.model_dump(exclude_none=True)
        return dict(profile_data or {})


def merge_pillar_working_profile(left: Any, right: Any) -> WorkingProfile:
    return _merge_model(WorkingProfile, left, right)


class ReasoningState(BaseModel):
    """Pillar 3: routing/orchestration logic and in-flight reasoning state."""

    phase: Annotated[Optional[PhaseLiteral], take_last_non_null] = None
    last_node: Annotated[Optional[str], resolve_last_node] = None

    discovery_summary: Optional[str] = None
    discovery_coverage: Optional[float] = None
    discovery_missing: List[str] = Field(default_factory=list)
    coverage_score: float = 0.0
    coverage_gaps: List[str] = Field(default_factory=list)
    recommendation_ready: bool = False
    recommendation_go: bool = False
    gap_report: Dict[str, Any] = Field(default_factory=dict)

    parameter_provenance: Dict[str, str] = Field(default_factory=dict)
    extracted_parameter_provenance: Dict[str, str] = Field(default_factory=dict)
    extracted_parameter_identity: Dict[str, ParameterIdentityRecord] = Field(default_factory=dict)
    parameter_versions: Dict[str, int] = Field(default_factory=dict)
    parameter_updated_at: Dict[str, float] = Field(default_factory=dict)
    current_assertion_cycle_id: int = 0
    state_revision: int = 0
    asserted_profile_revision: int = 0
    snapshot_parent_revision: int = 0
    last_assertion_changed_at: Optional[float] = None
    derived_artifacts_stale: bool = False
    derived_artifacts_stale_reason: Optional[str] = None
    missing_params: List[str] = Field(default_factory=list)
    coverage_analysis: Optional[CoverageAnalysis] = None
    ask_missing_request: Optional[AskMissingRequest] = None
    ask_missing_scope: Optional[AskMissingScope] = None
    awaiting_user_input: bool = False
    streaming_complete: bool = False

    critique_log: List[str] = Field(default_factory=list)
    qgate_has_blockers: bool = False
    qgate_result: Optional[Dict[str, Any]] = None

    # TODO: Deprecated in v13. Legacy procurement payload container; kept for API compatibility.
    procurement_result: Optional[Dict[str, Any]] = None
    # TODO: Deprecated in v13. Legacy RFQ artifact payload; kept for API compatibility.
    rfq_payload: Dict[str, Any] = Field(default_factory=dict)
    rfq_ready: bool = False
    missing_fields: List[str] = Field(default_factory=list)

    kb_factcard_result: Dict[str, Any] = Field(default_factory=dict)
    compound_filter_results: Dict[str, Any] = Field(default_factory=dict)
    coverage_disclosure_ready: bool = False

    plan: Dict[str, Any] = Field(default_factory=dict)
    working_memory: Annotated[WorkingMemory, merge_working_memory] = Field(default_factory=WorkingMemory)

    need_sources: bool = False
    requires_rag: bool = False
    retrieval_meta: Optional[Dict[str, Any]] = None
    context: Optional[str] = None

    flags: Dict[str, Any] = Field(
        default_factory=lambda: {
            "parameters_complete_for_material": False,
            "parameters_complete_for_profile": False,
        }
    )
    validation: Dict[str, Any] = Field(default_factory=lambda: {"status": None, "issues": []})
    critical: Dict[str, Any] = Field(
        default_factory=lambda: {
            "status": None,
            "target": None,
            "next_step": None,
            "iteration_count": 0,
        }
    )
    products: Dict[str, Any] = Field(
        default_factory=lambda: {
            "manufacturer": None,
            "matches": [],
            "match_quality": None,
        }
    )
    troubleshooting: Dict[str, Any] = Field(
        default_factory=lambda: {
            "symptoms": [],
            "hypotheses": [],
            "pattern_match": None,
            "done": False,
        }
    )
    diagnostic_data: Annotated[Dict[str, Any], merge_dicts] = Field(default_factory=dict)
    diagnostic_complete: bool = False

    open_questions: List[QuestionItem] = Field(default_factory=list)
    facts: Dict[str, FactItem] = Field(default_factory=dict)
    candidates: List[CandidateItem] = Field(default_factory=list)
    decision_log: List[DecisionEntry] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    confidence: float = 0.0
    round_index: int = 0
    turn_count: int = 0
    max_turns: int = 12
    knowledge_coverage: str = "limited"
    output_blocked: bool = False
    output_blocked_reason: Optional[str] = None
    rag_turn_count: int = 0
    next_action: Optional[str] = None

    ui_state: Dict[str, Any] = Field(default_factory=lambda: {"current_step": None, "current_label": None})

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


def merge_reasoning_state(left: Any, right: Any) -> ReasoningState:
    return _merge_model(ReasoningState, left, right)


class SystemState(BaseModel):
    """Pillar 4: system metadata, safety controls, audit traces, and outputs."""

    run_id: Optional[str] = None
    prompt_traces: Annotated[List[RenderedPrompt], operator.add] = Field(default_factory=list)
    tool_call_records: Annotated[List[ToolCallRecord], operator.add] = Field(default_factory=list)
    source_ref_payloads: Annotated[List[SourceRefPayload], operator.add] = Field(default_factory=list)
    evidence_bundle: Optional[EvidenceBundle] = None
    evidence_bundle_hash: Optional[str] = None

    tenant_id: Optional[str] = None
    requires_human_review: bool = False
    safety_class: Optional[str] = None

    sources: List[Source] = Field(default_factory=list)

    rfq_pdf_base64: Optional[str] = None
    rfq_pdf_url: Optional[str] = None
    rfq_html_report: Optional[str] = None
    # TODO: Deprecated in v13. Historical plaintext RFQ export field.
    rfq_pdf_text: Optional[str] = None

    error: Optional[str] = None
    rfq_admissibility: RFQAdmissibilityContract = Field(default_factory=RFQAdmissibilityContract)
    preview_text: Optional[str] = None
    governed_output_text: Optional[str] = None
    governed_output_status: Optional[str] = None
    governed_output_ready: bool = False
    governance_metadata: GovernanceMetadata = Field(default_factory=GovernanceMetadata)
    final_text: Annotated[Optional[str], take_last_non_null] = None
    final_answer: Annotated[Optional[str], take_last_non_null] = None
    final_prompt: Optional[str] = None
    final_prompt_metadata: Dict[str, Any] = Field(default_factory=dict)
    answer_contract: Optional[AnswerContract] = None
    draft_text: Optional[str] = None
    draft_base_hash: Optional[str] = None
    verification_report: Optional[VerificationReport] = None

    verification_passed: bool = True
    verification_error: Optional[Dict[str, Any]] = None
    derived_from_assertion_cycle_id: Optional[int] = None
    derived_from_assertion_revision: Optional[int] = None
    derived_artifacts_stale: bool = False
    derived_artifacts_stale_reason: Optional[str] = None

    pending_action: Optional[str] = None
    confirmed_actions: List[str] = Field(default_factory=list)
    awaiting_user_confirmation: bool = False
    confirm_checkpoint_id: Optional[str] = None
    confirm_checkpoint: Dict[str, Any] = Field(default_factory=dict)
    confirm_status: Optional[Literal["pending", "resolved"]] = None
    confirm_resolved_at: Optional[str] = None
    confirm_decision: Optional[str] = None
    confirm_edits: Dict[str, Any] = Field(default_factory=dict)

    errors: List[Any] = Field(default_factory=list)  # legacy RAGState
    error_state: Optional[LegacyErrorInfo] = None  # legacy RAGState

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


def merge_system_state(left: Any, right: Any) -> SystemState:
    return _merge_model(SystemState, left, right)


_CONVERSATION_FIELDS = {
    "messages",
    "user_id",
    "thread_id",
    "user_context",
    "session_id",
    "router_classification",
    "intent",
    "knowledge_type",
    "use_case_raw",
    "application_category",
    "motion_type",
    "seal_family",
    "user_persona",
}

_WORKING_PROFILE_FIELDS = {
    "working_profile",  # legacy flat field -> working_profile.engineering_profile
    "profile",  # legacy RAGState profile
    "parameter_profile",
    "medium",
    "temperature_c",
    "pressure_bar",
    "extracted_params",
    "calculation_result",
    "is_critical_application",
    "live_calc_tile",
    "tradeoff_options",
    "capability_requirements",
    "dp_dt_bar_per_s",
    "side_load_kn",
    "aed_required",
    "medium_additives",
    "fluid_contamination_iso",
    "surface_hardness_hrc",
    "pressure_spike_factor",
    "dynamic_type",
    "analysis_complete",
    "calc_results_ok",
    "calc_results",
    "compliance_results",
    "recommendation",
    "material_choice",
    "profile_choice",
    "factcard_matches",
    "sealing_type_results",
}

_REASONING_FIELDS = {
    "phase",
    "last_node",
    "discovery_summary",
    "discovery_coverage",
    "discovery_missing",
    "coverage_score",
    "coverage_gaps",
    "recommendation_ready",
    "recommendation_go",
    "gap_report",
    "parameter_provenance",
    "extracted_parameter_provenance",
    "extracted_parameter_identity",
    "parameter_versions",
    "parameter_updated_at",
    "missing_params",
    "coverage_analysis",
    "ask_missing_request",
    "ask_missing_scope",
    "awaiting_user_input",
    "streaming_complete",
    "critique_log",
    "qgate_has_blockers",
    "qgate_result",
    "procurement_result",
    "rfq_payload",
    "rfq_ready",
    "missing_fields",
    "kb_factcard_result",
    "compound_filter_results",
    "coverage_disclosure_ready",
    "plan",
    "working_memory",
    "need_sources",
    "requires_rag",
    "retrieval_meta",
    "context",
    "flags",
    "validation",
    "critical",
    "products",
    "troubleshooting",
    "diagnostic_data",
    "diagnostic_complete",
    "open_questions",
    "facts",
    "candidates",
    "decision_log",
    "budget",
    "confidence",
    "round_index",
    "turn_count",
    "max_turns",
    "knowledge_coverage",
    "output_blocked",
    "output_blocked_reason",
    "rag_turn_count",
    "next_action",
    "ui_state",
}

_SYSTEM_FIELDS = {
    "run_id",
    "prompt_traces",
    "tool_call_records",
    "source_ref_payloads",
    "evidence_bundle",
    "evidence_bundle_hash",
    "tenant_id",
    "rfq_pdf_base64",
    "rfq_pdf_url",
    "rfq_html_report",
    "rfq_pdf_text",
    "requires_human_review",
    "safety_class",
    "sources",
    "error",
    "rfq_admissibility",
    "preview_text",
    "governed_output_text",
    "governed_output_status",
    "governed_output_ready",
    "final_text",
    "final_answer",
    "final_prompt",
    "final_prompt_metadata",
    "answer_contract",
    "draft_text",
    "draft_base_hash",
    "verification_report",
    "verification_passed",
    "verification_error",
    "pending_action",
    "confirmed_actions",
    "awaiting_user_confirmation",
    "confirm_checkpoint_id",
    "confirm_checkpoint",
    "confirm_status",
    "confirm_resolved_at",
    "confirm_decision",
    "confirm_edits",
    "errors",
    "error_state",
}


def _build_flat_field_map() -> Dict[str, tuple[str, str]]:
    mapping: Dict[str, tuple[str, str]] = {}
    mapping.update({name: ("conversation", name) for name in _CONVERSATION_FIELDS})
    mapping.update({name: ("working_profile", name) for name in _WORKING_PROFILE_FIELDS if name != "working_profile"})
    mapping.update({name: ("reasoning", name) for name in _REASONING_FIELDS})
    mapping.update({name: ("system", name) for name in _SYSTEM_FIELDS})
    mapping["working_profile"] = ("working_profile", "engineering_profile")
    return mapping


_FLAT_FIELD_TO_PILLAR = _build_flat_field_map()


def _value_to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=False)
    return {}


def _looks_like_new_working_profile_payload(value: Any) -> bool:
    if isinstance(value, WorkingProfile):
        return True
    if not isinstance(value, dict):
        return False
    marker_keys = {
        "engineering_profile",
        "parameter_profile",
        "extracted_params",
        "live_calc_tile",
        "recommendation",
    }
    return bool(marker_keys & set(value.keys()))


class SealAIState(BaseModel):
    """Root state composed of exactly four nested pillars."""

    conversation: Annotated[ConversationState, merge_conversation_state] = Field(default_factory=ConversationState)
    working_profile: Annotated[WorkingProfile, merge_pillar_working_profile] = Field(default_factory=WorkingProfile)
    reasoning: Annotated[ReasoningState, merge_reasoning_state] = Field(default_factory=ReasoningState)
    system: Annotated[SystemState, merge_system_state] = Field(default_factory=SystemState)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    _flat_field_to_pillar: Dict[str, tuple[str, str]] = PrivateAttr(
        default_factory=lambda: dict(_FLAT_FIELD_TO_PILLAR)
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_flat_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        sanitized_value = {k: v for k, v in value.items() if k != "_flat_field_to_pillar"}

        nested_payload: Dict[str, Any] = {
            "conversation": _value_to_dict(sanitized_value.get("conversation")),
            "working_profile": _value_to_dict(sanitized_value.get("working_profile"))
            if _looks_like_new_working_profile_payload(sanitized_value.get("working_profile"))
            else {},
            "reasoning": _value_to_dict(sanitized_value.get("reasoning")),
            "system": _value_to_dict(sanitized_value.get("system")),
        }

        has_nested_shape = any(
            key in sanitized_value for key in ("conversation", "working_profile", "reasoning", "system")
        )
        consumed_flat = False
        passthrough: Dict[str, Any] = {}

        for key, raw in sanitized_value.items():
            if key in ("conversation", "working_profile", "reasoning", "system"):
                if key == "working_profile" and not _looks_like_new_working_profile_payload(raw):
                    nested_payload["working_profile"]["engineering_profile"] = raw
                    consumed_flat = True
                continue

            route = _FLAT_FIELD_TO_PILLAR.get(key)
            if route is None:
                passthrough[key] = raw
                continue

            pillar_name, pillar_field = route
            nested_payload[pillar_name][pillar_field] = raw
            consumed_flat = True

        if not (has_nested_shape or consumed_flat):
            return sanitized_value

        return {
            "conversation": nested_payload["conversation"],
            "working_profile": nested_payload["working_profile"],
            "reasoning": nested_payload["reasoning"],
            "system": nested_payload["system"],
            **passthrough,
        }

    @property
    def engineering_profile(self) -> LegacyWorkingProfile:
        """Compatibility alias for direct access to legacy engineering profile."""
        return self.working_profile.engineering_profile

    def compute_knowledge_coverage(self, intent: str) -> str:
        """Deterministic helper retained for compatibility with legacy callers."""
        if intent in ("greeting", "smalltalk", "info"):
            return "full"

        profile = self.working_profile
        critical = [
            profile.medium,
            profile.pressure_bar,
            profile.temperature_c,
            profile.dynamic_type,
        ]
        if not all(critical):
            return "limited"

        if intent in ("complex", "safety_critical"):
            dynamic = [
                profile.dp_dt_bar_per_s,
                profile.aed_required,
                profile.medium_additives,
            ]
            if sum(1 for field in dynamic if field is None) > 1:
                return "partial"
        return "full"


__all__ = [
    "Intent",
    "IntentGoal",
    "SealAIExtractedParameters",
    "SealAIIntentOutput",
    "RenderedPrompt",
    "ToolCallRecord",
    "SourceRefPayload",
    "EvidenceBundle",
    "CalcResults",
    "LiveCalcTile",
    "Recommendation",
    "Source",
    "AnswerContract",
    "RequirementSpec",
    "ConflictRecord",
    "VerificationReport",
    "QuestionItem",
    "FactItem",
    "CandidateItem",
    "DecisionEntry",
    "Budget",
    "merge_working_profile",
    "ConversationState",
    "WorkingProfile",
    "ReasoningState",
    "SystemState",
    "SealAIState",
    "AskMissingScope",
    "WorkingMemory",
]
