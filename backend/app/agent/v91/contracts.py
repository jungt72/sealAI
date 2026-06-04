from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


V91_POLICY_VERSION = "sealai_v9_1_policy_v1"


class SemanticIntent(str, Enum):
    SMALLTALK = "smalltalk"
    PROCESS_OR_META = "process_or_meta"
    GENERAL_KNOWLEDGE = "general_knowledge"
    MATERIAL_OR_MEDIUM_KNOWLEDGE = "material_or_medium_knowledge"
    MATERIAL_COMPARISON = "material_comparison"
    CASE_INTAKE = "case_intake"
    PENDING_SLOT_ANSWER = "pending_slot_answer"
    ACTIVE_CASE_SIDE_QUESTION = "active_case_side_question"
    CORRECTION = "correction"
    CONCRETE_SUITABILITY = "concrete_suitability"
    RFQ_OR_EXPORT = "rfq_or_export"
    SAFETY_OR_COMPLIANCE = "safety_or_compliance"
    NON_SEALING_UTILITY = "non_sealing_utility"
    LOW_SIGNAL = "low_signal"
    BLOCKED = "blocked"
    UNCLEAR = "unclear"


class DomainRelevance(str, Enum):
    IRRELEVANT = "irrelevant"
    LOW = "low"
    SEALING_RELATED = "sealing_related"
    CONCRETE_SEALING_CASE = "concrete_sealing_case"
    SAFETY_OR_COMPLIANCE = "safety_or_compliance"


class CaseBinding(str, Enum):
    NONE = "none"
    ACTIVE_CASE_CONTEXT = "active_case_context"
    NEW_CASE_CANDIDATE = "new_case_candidate"
    CASE_MUTATION_CANDIDATE = "case_mutation_candidate"
    UNKNOWN = "unknown"


class LLMFreedomLevel(str, Enum):
    FREE_EXPLANATION = "free_explanation"
    GUIDED_EXPLANATION = "guided_explanation"
    RESTRICTED_CASE_CLAIMS = "restricted_case_claims"
    BLOCKED_OR_REFUSAL = "blocked_or_refusal"


class RedFlagType(str, Enum):
    FINAL_SUITABILITY = "final_suitability"
    FINAL_RELEASE = "final_release"
    COMPLIANCE_OR_CERTIFICATION = "compliance_or_certification"
    SAFETY_CRITICAL = "safety_critical"
    RFQ_EXPORT_OR_DISPATCH = "rfq_export_or_dispatch"
    CASE_STATE_MUTATION = "case_state_mutation"
    DOCUMENT_BASED_CLAIM = "document_based_claim"
    NUMERIC_LIMIT_CLAIM = "numeric_limit_claim"
    MANUFACTURER_OR_ARTICLE_EQUIVALENCE = "manufacturer_or_article_equivalence"


class ResponseAction(str, Enum):
    ANSWER_ONLY = "answer_only"
    ANSWER_THEN_RESUME = "answer_then_resume"
    ROUTE_SLOT_CANDIDATE = "route_slot_candidate"
    ENTER_GOVERNED_GRAPH = "enter_governed_graph"
    SHOW_RFQ_READINESS = "show_rfq_readiness"
    ANSWER_RFQ_STATUS = "answer_rfq_status"
    BUILD_RFQ_PREVIEW = "build_rfq_preview"
    DEFER_RFQ_UNTIL_REQUIRED_FIELDS = "defer_rfq_until_required_fields"
    WAIT_FOR_USER = "wait_for_user"
    BLOCK = "block"


class KnowledgeRagPolicy(str, Enum):
    NOT_NEEDED = "not_needed"
    OPTIONAL = "optional"
    REQUIRED = "required"
    DISALLOWED = "disallowed"
    MISSING_MUST_DEFER = "missing_must_defer"


class AnswerDepth(str, Enum):
    SHORT = "short"
    NORMAL = "normal"
    DEEP = "deep"


class ResponseMove(str, Enum):
    ACKNOWLEDGE = "acknowledge"
    ANSWER = "answer"
    EXPLAIN = "explain"
    COMPARE = "compare"
    CHALLENGE = "challenge"
    CLARIFY = "clarify"
    JUSTIFY_QUESTION = "justify_question"
    SUMMARIZE_STATE = "summarize_state"
    CONFIRM_UPDATE = "confirm_update"
    MENTION_TAB_UPDATE = "mention_tab_update"
    DISCLOSE_SOURCE = "disclose_source"
    BOUNDARY = "boundary"
    EMPATHIZE = "empathize"
    RECOVER = "recover"
    REDIRECT = "redirect"
    OFFER_UI_ACTION = "offer_ui_action"
    ESCALATE = "escalate"
    SMALLTALK_BRIDGE = "smalltalk_bridge"


class SemanticBoundaryDecision(BaseModel):
    intent: SemanticIntent
    domain_relevance: DomainRelevance
    case_binding: CaseBinding = CaseBinding.UNKNOWN
    active_case_exists: bool = False
    should_mutate_case: bool = False
    graph_candidate: bool = False
    source: Literal["deterministic_adapter_v1", "llm_router_v1"] = "deterministic_adapter_v1"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = ""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class RedFlag(BaseModel):
    type: RedFlagType
    severity: Literal["low", "medium", "high", "blocking"] = "medium"
    reason: str = ""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class LLMFreedomDecision(BaseModel):
    level: LLMFreedomLevel
    red_flags: list[RedFlag] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    reason: str = ""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @model_validator(mode="after")
    def _blocked_requires_forbidden_action(self) -> "LLMFreedomDecision":
        level = getattr(self.level, "value", self.level)
        if level == LLMFreedomLevel.BLOCKED_OR_REFUSAL.value and not self.forbidden_actions:
            raise ValueError("blocked freedom decisions require forbidden_actions")
        return self


class ResponsePolicy(BaseModel):
    action: ResponseAction
    answer_depth: AnswerDepth = AnswerDepth.NORMAL
    graph_allowed: bool = False
    answer_first: bool = False
    max_primary_questions: int = Field(default=1, ge=0, le=1)
    must_explain_uncertainty: bool = True
    must_resume_primary_task: bool = False
    reason: str = ""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @model_validator(mode="after")
    def _graph_allowed_only_for_graph_action(self) -> "ResponsePolicy":
        action = getattr(self.action, "value", self.action)
        if self.graph_allowed and action != ResponseAction.ENTER_GOVERNED_GRAPH.value:
            raise ValueError("graph_allowed requires action=enter_governed_graph")
        return self


class KnowledgePolicy(BaseModel):
    rag_policy: KnowledgeRagPolicy
    can_use_general_model_knowledge: bool = True
    requires_evidence_for_case_claims: bool = True
    fallback_allowed: bool = False
    source_scope: Literal[
        "none",
        "general_orientation",
        "case_orientation",
        "documented_evidence",
    ] = "general_orientation"
    reason: str = ""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class CandidateFact(BaseModel):
    field_id: str
    value: Any
    unit: str | None = None
    source_message_id: str | None = None
    source_quote: str | None = None
    extraction_method: Literal["llm", "regex", "form", "document", "manual"] = "llm"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_user_confirmation: bool = True

    model_config = ConfigDict(extra="forbid")


class FieldGovernanceDecision(BaseModel):
    field_id: str
    candidate_value: Any = None
    candidate_unit: str | None = None
    source_message_id: str | None = None
    source_quote: str | None = None
    decision: Literal[
        "observed_only",
        "normalized_candidate",
        "accepted_to_case_state",
        "conflict_requires_confirmation",
        "held_for_confirmation",
    ] = "observed_only"
    provenance: Literal[
        "user_stated",
        "documented",
        "calculated",
        "inferred",
        "confirmed",
        "missing",
    ] = "inferred"
    normalized_status: str | None = None
    case_status: str | None = None
    case_revision_event_type: Literal[
        "none",
        "new_value",
        "correction",
        "conflict",
        "document_override",
    ] = "none"
    requires_user_confirmation: bool = True
    requires_recompute: bool = False
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class QuestionNeed(BaseModel):
    need_id: str
    target_field: str | None = None
    blocker_addressed: str
    why_it_matters: str
    priority: int = Field(default=1, ge=1, le=5)
    expected_answer_type: str = "text"

    model_config = ConfigDict(extra="forbid")


class QuestionPlan(BaseModel):
    primary_question: str | None = None
    question_need: QuestionNeed | None = None
    ask_now: bool = False
    max_questions_policy: Literal["ask_one_highest_leverage_question"] = (
        "ask_one_highest_leverage_question"
    )
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class CommunicationPlan(BaseModel):
    goal: Literal[
        "answer",
        "answer_and_clarify",
        "clarify_only",
        "boundary",
        "recover",
        "summarize",
        "redirect",
        "escalate",
    ] = "answer"
    response_mode: Literal[
        "direct_answer",
        "guided_explanation",
        "case_challenge",
        "clarification",
        "boundary_refusal",
    ] = "guided_explanation"
    response_moves: list[ResponseMove] = Field(
        default_factory=lambda: [ResponseMove.ACKNOWLEDGE, ResponseMove.ANSWER]
    )
    response_depth: Literal["micro", "short", "standard", "deep", "dossier"] = "standard"
    answer_depth: AnswerDepth = AnswerDepth.NORMAL
    answer_first: bool = False
    ask_user_question: bool = False
    max_new_questions: int = Field(default=1, ge=0, le=1)
    question_justification_required: bool = False
    include_boundary_notice: bool = True
    include_tab_update_notice: bool = False
    tab_update_visibility: Literal["silent", "concise", "explicit"] = "silent"
    source_disclosure_mode: Literal["none", "on_claims", "on_request", "always"] = "none"
    user_question_must_be_answered: bool = False
    max_findings_to_mention: int = Field(default=2, ge=0, le=8)
    primary_question: str | None = None
    primary_question_reason: str | None = None
    must_mention: list[str] = Field(default_factory=list)
    may_mention: list[str] = Field(default_factory=list)
    must_not_mention: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    allowed_claim_level: str = "general_orientation"

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ConversationTaskState(BaseModel):
    active_intent: str | None = None
    last_asked_question: str | None = None
    open_side_topics: list[str] = Field(default_factory=list)
    answer_depth: AnswerDepth = AnswerDepth.NORMAL
    user_preference_notes: list[str] = Field(default_factory=list)
    pause_resume_status: Literal["active", "waiting_for_user", "paused"] = "active"
    source: str = "v91_conversation_task_adapter_v1"

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class DialogueDebt(BaseModel):
    pending_questions: list[str] = Field(default_factory=list)
    pending_explanations: list[str] = Field(default_factory=list)
    pending_conflicts: list[str] = Field(default_factory=list)
    pending_tab_updates: list[str] = Field(default_factory=list)
    last_asked_question_id: str | None = None
    repeated_question_count: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class FinalAnswerContext(BaseModel):
    semantic_boundary: SemanticBoundaryDecision
    freedom_decision: LLMFreedomDecision
    response_policy: ResponsePolicy
    knowledge_policy: KnowledgePolicy
    question_plan: QuestionPlan | None = None
    communication_plan: CommunicationPlan | None = None
    allowed_claim_levels: list[str] = Field(default_factory=list)
    evidence_ref_ids: list[str] = Field(default_factory=list)
    risk_claims: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class IntelligenceSlice(BaseModel):
    slice_id: Literal[
        "medium",
        "material",
        "challenge",
        "document",
        "rfq",
    ]
    status: str = "not_available"
    claim_level: Literal[
        "general_orientation",
        "screening",
        "case_projection",
        "manufacturer_review",
    ] = "screening"
    summary: str = ""
    signals: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    evidence_ref_ids: list[str] = Field(default_factory=list)
    not_for_release_decisions: bool = True
    source: str = "workspace_projection_v9_1"

    model_config = ConfigDict(extra="forbid")


class IntelligenceState(BaseModel):
    schema_version: str = "sealing_intelligence_v9_1"
    case_revision: int = 0
    overall_status: Literal[
        "empty",
        "intake",
        "screening",
        "review_needed",
        "rfq_basis",
    ] = "empty"
    medium: IntelligenceSlice = Field(
        default_factory=lambda: IntelligenceSlice(slice_id="medium")
    )
    material: IntelligenceSlice = Field(
        default_factory=lambda: IntelligenceSlice(slice_id="material")
    )
    challenge: IntelligenceSlice = Field(
        default_factory=lambda: IntelligenceSlice(slice_id="challenge")
    )
    document: IntelligenceSlice = Field(
        default_factory=lambda: IntelligenceSlice(slice_id="document")
    )
    rfq: IntelligenceSlice = Field(
        default_factory=lambda: IntelligenceSlice(slice_id="rfq")
    )

    model_config = ConfigDict(extra="forbid")


class TabState(BaseModel):
    tab_id: Literal[
        "overview",
        "parameters",
        "medium",
        "material",
        "challenge",
        "documents",
        "rfq",
    ]
    label: str
    status: str = "not_available"
    source_slice_id: str
    summary: str = ""
    primary_items: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str | None = None
    evidence_ref_ids: list[str] = Field(default_factory=list)
    not_for_release_decisions: bool = True

    model_config = ConfigDict(extra="forbid")


class V91WorkspaceProjection(BaseModel):
    intelligence_state: IntelligenceState = Field(default_factory=IntelligenceState)
    tab_state: list[TabState] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class GuardResult(BaseModel):
    passed: bool
    findings: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class V91TurnPolicyBundle(BaseModel):
    policy_version: str = V91_POLICY_VERSION
    semantic_boundary: SemanticBoundaryDecision
    freedom_decision: LLMFreedomDecision
    response_policy: ResponsePolicy
    knowledge_policy: KnowledgePolicy
    question_plan: QuestionPlan | None = None
    communication_plan: CommunicationPlan | None = None

    model_config = ConfigDict(extra="forbid")

    def as_trace(self) -> dict[str, Any]:
        red_flags = [
            str(getattr(flag.type, "value", flag.type)) for flag in self.freedom_decision.red_flags
        ]
        return {
            "v91_policy_version": self.policy_version,
            "v91_semantic_intent": self.semantic_boundary.intent,
            "v91_domain_relevance": self.semantic_boundary.domain_relevance,
            "v91_case_binding": self.semantic_boundary.case_binding,
            "v91_active_case_exists": self.semantic_boundary.active_case_exists,
            "v91_should_mutate_case": self.semantic_boundary.should_mutate_case,
            "v91_graph_candidate": self.semantic_boundary.graph_candidate,
            "v91_freedom_level": self.freedom_decision.level,
            "v91_red_flags": red_flags,
            "v91_response_action": self.response_policy.action,
            "v91_response_answer_depth": self.response_policy.answer_depth,
            "v91_response_graph_allowed": self.response_policy.graph_allowed,
            "v91_knowledge_rag_policy": self.knowledge_policy.rag_policy,
            "v91_knowledge_source_scope": self.knowledge_policy.source_scope,
            "v91_max_primary_questions": self.response_policy.max_primary_questions,
            "v91_question_plan_present": self.question_plan is not None,
            "v91_communication_plan_present": self.communication_plan is not None,
        }
