"""Typed V9.2 runtime contracts.

These contracts are the public seam between turn routing, deterministic
engineering state, LLM answer composition, final guards and dashboard
projection. They are intentionally additive to the existing V9.1 contracts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TurnRoute = Literal[
    "smalltalk",
    "abusive_or_shit_chat",
    "knowledge_general",
    "knowledge_case_side_question",
    "engineering_case_update",
    "engineering_recommendation",
    "leakage_failure_analysis",
    "standards_or_compliance",
    "rfq_readiness",
    "expert_review_action",
    "unsafe_or_blocked",
]
StateMutationPolicy = Literal[
    "none",
    "observed_only",
    "case_revision_allowed",
    "review_action",
]
StreamingPolicy = Literal[
    "direct_stream_allowed",
    "status_only_until_guarded_final",
    "blocked",
]
GuardDecision = Literal["pass", "revise", "block", "human_review"]
GuardSeverity = Literal["none", "low", "medium", "high", "blocking"]


class PromptTrace(BaseModel):
    prompt_template_id: str
    prompt_template_version: str
    rendered_prompt_hash: str
    input_schema_version: str
    output_schema_version: str
    model_role: str
    case_revision: int | None = None
    trace_id: str

    model_config = ConfigDict(extra="forbid")


class TurnEnvelope(BaseModel):
    turn_id: str
    session_id: str
    case_id: str | None = None
    case_revision_before: int | None = None
    case_revision_after: int | None = None
    user_message: str
    route: TurnRoute
    intent: str
    is_technical: bool
    state_mutation_policy: StateMutationPolicy
    requires_engine: bool
    requires_evidence: bool
    requires_adversarial_review: bool
    requires_final_guard: bool
    streaming_policy: StreamingPolicy
    created_at: str
    trace_id: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _technical_turns_need_guarded_streaming(self) -> "TurnEnvelope":
        if self.is_technical and self.streaming_policy == "direct_stream_allowed":
            raise ValueError("technical turns must not direct-stream draft tokens")
        if self.is_technical and not self.requires_final_guard:
            raise ValueError("technical turns require the final guard")
        return self


class TurnBoundaryDecision(BaseModel):
    route: TurnRoute
    intent: str
    reason: str
    source: str = "turn_boundary_orchestrator_v1"
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    state_mutation_policy: StateMutationPolicy
    requires_engine: bool
    requires_evidence: bool
    requires_adversarial_review: bool
    requires_final_guard: bool = True
    streaming_policy: StreamingPolicy
    graph_required: bool = False
    short_path_allowed: bool = False
    unsafe_instruction_blocked: bool = False
    case_state_may_mutate: bool = False
    trace: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class NonTechnicalAnswerContext(BaseModel):
    turn_id: str
    route: TurnRoute
    intent: str
    user_message: str
    answer_scope: Literal["smalltalk", "knowledge", "process", "safety"] = "knowledge"
    state_mutation_policy: StateMutationPolicy = "none"
    allowed_claim_level: str = "L0_raw"
    forbidden_claims: list[str] = Field(default_factory=list)
    required_warnings: list[str] = Field(default_factory=list)
    dashboard_projection: dict[str, Any] = Field(default_factory=dict)
    guard_trace: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class FinalAnswerContext(BaseModel):
    turn_id: str
    case_id: str | None = None
    case_revision: int | None = None
    route: TurnRoute
    intent: str
    is_technical: bool
    user_message: str
    case_state_summary: dict[str, Any] = Field(default_factory=dict)
    seal_system_summary: dict[str, Any] | None = None
    engineering_outputs: list[dict[str, Any]] = Field(default_factory=list)
    calculation_results: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    standards_summary: dict[str, Any] = Field(default_factory=dict)
    risk_findings: list[dict[str, Any]] = Field(default_factory=list)
    completeness: dict[str, Any] | None = None
    material_candidates: list[dict[str, Any]] = Field(default_factory=list)
    compound_candidates: list[dict[str, Any]] = Field(default_factory=list)
    product_candidates: list[dict[str, Any]] = Field(default_factory=list)
    allowed_claim_level: str = "L2_screening"
    forbidden_claims: list[str] = Field(default_factory=list)
    required_warnings: list[str] = Field(default_factory=list)
    stale_items: list[dict[str, Any]] = Field(default_factory=list)
    review_required: bool = False
    human_review_reasons: list[str] = Field(default_factory=list)
    dashboard_projection: dict[str, Any] = Field(default_factory=dict)
    prompt_trace: dict[str, Any] | PromptTrace | None = None
    guard_trace: dict[str, Any] | None = None
    adversarial_review: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _technical_context_requires_revision_visibility(self) -> "FinalAnswerContext":
        if self.is_technical and self.case_revision is None:
            # Explicit None is allowed for new no-case technical screening, but
            # callers must surface it as missing context for traceability.
            if "case_revision_missing" not in self.human_review_reasons:
                self.human_review_reasons.append("case_revision_missing")
            self.review_required = True
        return self


class AdversarialReviewVerdict(BaseModel):
    decision: GuardDecision = "pass"
    severity: GuardSeverity = "none"
    unsupported_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    stale_state_concerns: list[str] = Field(default_factory=list)
    calculation_concerns: list[str] = Field(default_factory=list)
    evidence_concerns: list[str] = Field(default_factory=list)
    standards_concerns: list[str] = Field(default_factory=list)
    risk_warnings_to_add: list[str] = Field(default_factory=list)
    claims_to_downgrade: list[str] = Field(default_factory=list)
    required_revision_instructions: list[str] = Field(default_factory=list)
    user_visible_challenge_summary: str = ""
    prompt_trace: dict[str, Any] | PromptTrace | None = None

    model_config = ConfigDict(extra="forbid")


class FinalGuardResult(BaseModel):
    decision: GuardDecision = "pass"
    severity: GuardSeverity = "none"
    blocked_reasons: list[str] = Field(default_factory=list)
    required_revisions: list[str] = Field(default_factory=list)
    allowed_claim_level: str = "L2_screening"
    detected_forbidden_claims: list[str] = Field(default_factory=list)
    evidence_failures: list[dict[str, Any]] = Field(default_factory=list)
    calculation_failures: list[dict[str, Any]] = Field(default_factory=list)
    standards_failures: list[dict[str, Any]] = Field(default_factory=list)
    stale_failures: list[dict[str, Any]] = Field(default_factory=list)
    human_review_required: bool = False
    user_visible_limitations: list[str] = Field(default_factory=list)
    final_stream_allowed: bool = True

    model_config = ConfigDict(extra="forbid")


class V92DashboardContract(BaseModel):
    schema_version: str = "v92_dashboard_contract_1"
    case_id: str | None = None
    case_revision: int | None = None
    turn_id: str
    route: TurnRoute
    readiness_band: str = "not_ready"
    seal_system: dict[str, Any] | None = None
    current_facts: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[dict[str, Any]] = Field(default_factory=list)
    blocking_missing_fields: list[dict[str, Any]] = Field(default_factory=list)
    calculations: list[dict[str, Any]] = Field(default_factory=list)
    stale_items: list[dict[str, Any]] = Field(default_factory=list)
    material_family_screening: list[dict[str, Any]] = Field(default_factory=list)
    compound_candidates: list[dict[str, Any]] = Field(default_factory=list)
    product_candidates: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    standards_summary: dict[str, Any] = Field(default_factory=dict)
    risk_matrix: list[dict[str, Any]] = Field(default_factory=list)
    recommendation_card: dict[str, Any] | None = None
    challenge_card: dict[str, Any] | None = None
    review_status: dict[str, Any] = Field(default_factory=dict)
    rfq_dossier_preview: dict[str, Any] | None = None
    allowed_next_actions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
