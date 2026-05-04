from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TurnKind(str, Enum):
    SMALLTALK = "smalltalk"
    META = "meta"
    KNOWLEDGE = "knowledge"
    CASE_INTAKE = "case_intake"
    PENDING_SLOT_ANSWER = "pending_slot_answer"
    ACTIVE_CASE_SIDE_QUESTION = "active_case_side_question"
    SIDE_TASK_CONTINUATION = "side_task_continuation"
    CORRECTION = "correction"
    MIXED = "mixed"
    UNSAFE = "unsafe"
    UNCLEAR = "unclear"


class AnswerMode(str, Enum):
    SMALLTALK = "smalltalk"
    META_QUESTION = "meta_question"
    NO_CASE_KNOWLEDGE = "no_case_knowledge"
    MATERIAL_COMPARISON = "material_comparison"
    RFQ_READINESS = "rfq_readiness"
    GOVERNED_INTAKE = "governed_intake"
    PENDING_SLOT_ANSWER = "pending_slot_answer"
    ACTIVE_CASE_SIDE_QUESTION = "active_case_side_question"
    ACTIVE_CASE_PROCESS_QUESTION = "active_case_process_question"
    SIDE_TASK_CONTINUATION = "side_task_continuation"
    CORRECTION_EXPLANATION = "correction_explanation"
    SAFETY_BLOCKED = "safety_blocked"
    CLARIFICATION = "clarification"


class MutationPolicy(str, Enum):
    FORBIDDEN = "forbidden"
    PROPOSED = "proposed"
    ALLOWED_BY_VALIDATOR = "allowed_by_validator"
    CORRECTION = "correction"


class ResumeStrategy(str, Enum):
    NONE = "none"
    RESTORE_TO_PENDING_QUESTION_V1 = "restore_to_pending_question_v1"
    REEVALUATE_AFTER_ANSWER = "reevaluate_after_answer"
    PAUSE_PRIMARY_TASK = "pause_primary_task"
    CONTINUE_SIDE_TASK = "continue_side_task"


class CaseRelevance(str, Enum):
    NO_CASE = "no_case"
    ACTIVE_CASE_CONTEXT = "active_case_context"
    NEW_CASE_CANDIDATE = "new_case_candidate"
    UNKNOWN = "unknown"


class ComposerTier(str, Enum):
    TIER_A = "tier_a"
    TIER_B = "tier_b"
    FALLBACK = "fallback"


class ClaimLevel(str, Enum):
    L1_GENERAL = "L1"
    L2_APPLICATION_ORIENTATION = "L2"
    L3_BACKEND_SUPPORTED = "L3"
    L4_FINAL_RELEASE = "L4"


class StateActionType(str, Enum):
    NONE = "none"
    CANDIDATE_FACT = "candidate_fact"
    CONFIRM_FACT = "confirm_fact"
    CORRECT_FACT = "correct_fact"
    CLEAR_PENDING_QUESTION = "clear_pending_question"
    OPEN_SIDE_TASK = "open_side_task"
    CLOSE_SIDE_TASK = "close_side_task"
    BLOCK = "block"


class RuntimeActionType(str, Enum):
    ANSWER_ONLY = "answer_only"
    ANSWER_THEN_RESUME = "answer_then_resume"
    ROUTE_SLOT_CANDIDATE = "route_slot_candidate"
    ENTER_GOVERNED_GRAPH = "enter_governed_graph"
    SHOW_RFQ_READINESS = "show_rfq_readiness"
    ANSWER_RFQ_STATUS = "answer_rfq_status"
    BUILD_RFQ_PREVIEW = "build_rfq_preview"
    DEFER_RFQ_UNTIL_REQUIRED_FIELDS = "defer_rfq_until_required_fields"
    WAIT_FOR_USER = "wait_for_user"


class RuntimeAnswerBuilder(str, Enum):
    NONE = "none"
    FAST_RESPONSE = "fast_response"
    LIGHT_RUNTIME = "light_runtime"
    ACTIVE_CASE_PROCESS = "active_case_process"
    ACTIVE_CASE_SIDE = "active_case_side"
    KNOWLEDGE = "knowledge"
    KNOWLEDGE_OVERRIDE = "knowledge_override"
    RFQ_READINESS = "rfq_readiness"
    GOVERNED_OUTPUT_CONTRACT = "governed_output_contract"


class RouterSignals(BaseModel):
    nano_intent: str | None = None
    nano_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    deterministic_pending_slot_match: bool = False
    deterministic_value_extraction: bool = False
    active_case_exists: bool = False
    safety_blocked: bool = False
    language: str = "de"

    model_config = ConfigDict(extra="forbid")


class ResumeTarget(BaseModel):
    type: Literal["pending_question", "primary_task", "side_task", "none"] = "none"
    target_field: str | None = None
    question_text: str | None = None
    task_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class StateAction(BaseModel):
    type: StateActionType
    mutation_policy: MutationPolicy
    field: str | None = None
    value: Any = None
    source: Literal["user_message", "pending_question", "router_signal", "backend_validator", "system"] = "user_message"
    requires_confirmation: bool = False
    needs_clarification: bool = False
    reason: str = ""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @model_validator(mode="after")
    def _state_mutation_requires_policy(self) -> "StateAction":
        if self.type in {StateActionType.CONFIRM_FACT, StateActionType.CORRECT_FACT} and self.mutation_policy == MutationPolicy.FORBIDDEN:
            raise ValueError("mutating state actions cannot use mutation_policy=forbidden")
        return self


class TaskFrame(BaseModel):
    task_id: str
    type: Literal["governed_seal_design", "active_case_side_question", "no_case_knowledge", "meta"]
    phase: str = "unknown"
    topic: str | None = None
    pending_question: ResumeTarget | None = None
    return_to: ResumeTarget | None = None

    model_config = ConfigDict(extra="forbid")


class TaskStack(BaseModel):
    primary_task: TaskFrame | None = None
    active_side_task: TaskFrame | None = None
    max_side_task_depth: int = 1

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _side_depth_is_bounded(self) -> "TaskStack":
        if self.max_side_task_depth != 1:
            raise ValueError("V7.1 supports max_side_task_depth=1")
        return self


class TurnDecision(BaseModel):
    turn_kind: TurnKind
    primary_interpretation: str
    router_signals: RouterSignals = Field(default_factory=RouterSignals)
    answer_mode: AnswerMode
    mutation_policy: MutationPolicy
    state_actions: list[StateAction] = Field(default_factory=list)
    answer_obligations: list[str] = Field(default_factory=list)
    case_relevance: CaseRelevance = CaseRelevance.UNKNOWN
    resume_strategy: ResumeStrategy = ResumeStrategy.NONE
    resume_target_candidate: ResumeTarget | None = None
    task_stack: TaskStack | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @model_validator(mode="after")
    def _side_questions_do_not_mutate_by_default(self) -> "TurnDecision":
        if self.answer_mode == AnswerMode.ACTIVE_CASE_SIDE_QUESTION and self.mutation_policy == MutationPolicy.ALLOWED_BY_VALIDATOR:
            raise ValueError("active-case side questions may not default to allowed_by_validator")
        return self


class RuntimeAction(BaseModel):
    action_type: RuntimeActionType
    answer_mode: AnswerMode | None = None
    mutation_policy: MutationPolicy | None = None
    graph_allowed: bool = False
    graph_entry_reason: str | None = None
    graph_invocation_skipped_reason: str | None = None
    answer_builder: RuntimeAnswerBuilder = RuntimeAnswerBuilder.NONE
    resume_strategy: ResumeStrategy | None = None
    slot_candidate_detected: bool = False
    next_runtime_action: str | None = None
    reason: str = ""
    decision_source: str = "turn_decision_v7"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rfq_action: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)
    operational_contract_version: Literal["runtime_action_v1"] = "runtime_action_v1"

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @model_validator(mode="after")
    def _only_enter_graph_action_may_allow_graph(self) -> "RuntimeAction":
        if self.graph_allowed and self.action_type != RuntimeActionType.ENTER_GOVERNED_GRAPH:
            raise ValueError("graph_allowed=true requires action_type=enter_governed_graph")
        if self.action_type == RuntimeActionType.ENTER_GOVERNED_GRAPH and not self.graph_allowed:
            raise ValueError("enter_governed_graph requires graph_allowed=true")
        return self

    def as_trace(self) -> dict[str, Any]:
        trace = {
            "runtime_action_built": True,
            "runtime_action_type": _enum_value(self.action_type),
            "runtime_action_reason": self.reason,
            "graph_allowed": bool(self.graph_allowed),
            "graph_entry_reason": self.graph_entry_reason,
            "graph_invocation_skipped_reason": self.graph_invocation_skipped_reason,
            "decision_source": self.decision_source,
            "operational_contract_version": self.operational_contract_version,
            "runtime_answer_builder": _enum_value(self.answer_builder),
            "slot_candidate_detected": bool(self.slot_candidate_detected),
            "next_runtime_action": self.next_runtime_action,
            "runtime_action_answer_mode": _enum_value(self.answer_mode),
            "runtime_action_mutation_policy": _enum_value(self.mutation_policy),
            "runtime_action_resume_strategy": _enum_value(self.resume_strategy),
        }
        if self.confidence is not None:
            trace["runtime_action_confidence"] = self.confidence
        if self.rfq_action:
            trace["rfq_action"] = self.rfq_action
        trace.update(self.trace)
        return trace


def build_runtime_action_from_turn_decision(
    decision: TurnDecision | None,
    *,
    reason: str | None = None,
    decision_source: str = "turn_decision_v7",
) -> RuntimeAction:
    if decision is None:
        return RuntimeAction(
            action_type=RuntimeActionType.ENTER_GOVERNED_GRAPH,
            answer_mode=AnswerMode.GOVERNED_INTAKE,
            mutation_policy=MutationPolicy.PROPOSED,
            graph_allowed=True,
            graph_entry_reason="missing_turn_decision_fail_closed_to_governed_graph",
            answer_builder=RuntimeAnswerBuilder.GOVERNED_OUTPUT_CONTRACT,
            reason=reason or "missing_turn_decision",
            decision_source=decision_source,
        )

    mode = _answer_mode(decision.answer_mode)
    resume_strategy = _resume_strategy(getattr(decision, "resume_strategy", None))
    mutation_policy = _mutation_policy(getattr(decision, "mutation_policy", None))
    confidence = float(getattr(decision, "confidence", 0.0) or 0.0)

    if mode is AnswerMode.ACTIVE_CASE_PROCESS_QUESTION:
        action_type = (
            RuntimeActionType.ANSWER_THEN_RESUME
            if resume_strategy is not ResumeStrategy.NONE
            else RuntimeActionType.ANSWER_ONLY
        )
        return RuntimeAction(
            action_type=action_type,
            answer_mode=mode,
            mutation_policy=mutation_policy,
            graph_allowed=False,
            graph_invocation_skipped_reason="active_case_process_question_answered_by_communication_runtime",
            answer_builder=RuntimeAnswerBuilder.ACTIVE_CASE_PROCESS,
            resume_strategy=resume_strategy,
            next_runtime_action="build_active_case_process_answer",
            reason=reason or "active_case_process_question_requires_answer_first",
            decision_source=decision_source,
            confidence=confidence,
        )

    if mode is AnswerMode.ACTIVE_CASE_SIDE_QUESTION:
        action_type = (
            RuntimeActionType.ANSWER_THEN_RESUME
            if resume_strategy is not ResumeStrategy.NONE
            else RuntimeActionType.ANSWER_ONLY
        )
        return RuntimeAction(
            action_type=action_type,
            answer_mode=mode,
            mutation_policy=mutation_policy,
            graph_allowed=False,
            graph_invocation_skipped_reason="active_case_side_question_answered_by_communication_runtime",
            answer_builder=RuntimeAnswerBuilder.ACTIVE_CASE_SIDE,
            resume_strategy=resume_strategy,
            next_runtime_action="build_active_case_side_answer",
            reason=reason or "active_case_side_question_requires_answer_first",
            decision_source=decision_source,
            confidence=confidence,
        )

    if mode is AnswerMode.PENDING_SLOT_ANSWER:
        return RuntimeAction(
            action_type=RuntimeActionType.ENTER_GOVERNED_GRAPH,
            answer_mode=mode,
            mutation_policy=mutation_policy,
            graph_allowed=True,
            graph_entry_reason="pending_slot_answer_requires_governed_validation",
            answer_builder=RuntimeAnswerBuilder.GOVERNED_OUTPUT_CONTRACT,
            resume_strategy=resume_strategy,
            slot_candidate_detected=True,
            next_runtime_action="route_slot_candidate_to_governed_graph",
            reason=reason or "pending_slot_answer_governed_binding",
            decision_source=decision_source,
            confidence=confidence,
        )

    if mode is AnswerMode.GOVERNED_INTAKE:
        return RuntimeAction(
            action_type=RuntimeActionType.ENTER_GOVERNED_GRAPH,
            answer_mode=mode,
            mutation_policy=mutation_policy,
            graph_allowed=True,
            graph_entry_reason="governed_intake_or_domain_continuation",
            answer_builder=RuntimeAnswerBuilder.GOVERNED_OUTPUT_CONTRACT,
            resume_strategy=resume_strategy,
            next_runtime_action="enter_governed_langgraph",
            reason=reason or "governed_intake_requires_langgraph",
            decision_source=decision_source,
            confidence=confidence,
        )

    if mode in {AnswerMode.NO_CASE_KNOWLEDGE, AnswerMode.MATERIAL_COMPARISON}:
        return RuntimeAction(
            action_type=RuntimeActionType.ANSWER_ONLY,
            answer_mode=mode,
            mutation_policy=mutation_policy,
            graph_allowed=False,
            graph_invocation_skipped_reason="no_case_knowledge_answered_by_knowledge_path",
            answer_builder=RuntimeAnswerBuilder.KNOWLEDGE,
            resume_strategy=resume_strategy,
            next_runtime_action="return_knowledge_answer",
            reason=reason or "knowledge_answer_without_case_mutation",
            decision_source=decision_source,
            confidence=confidence,
        )

    if mode is AnswerMode.SAFETY_BLOCKED:
        return RuntimeAction(
            action_type=RuntimeActionType.ANSWER_ONLY,
            answer_mode=mode,
            mutation_policy=mutation_policy,
            graph_allowed=False,
            graph_invocation_skipped_reason="safety_blocked_before_governed_graph",
            resume_strategy=resume_strategy,
            next_runtime_action="return_safety_answer",
            reason=reason or "safety_blocked_answer_only",
            decision_source=decision_source,
            confidence=confidence,
        )

    return RuntimeAction(
        action_type=RuntimeActionType.ANSWER_ONLY,
        answer_mode=mode,
        mutation_policy=mutation_policy,
        graph_allowed=False,
        graph_invocation_skipped_reason="conversation_answer_does_not_require_governed_graph",
        resume_strategy=resume_strategy,
        next_runtime_action="return_conversation_answer",
        reason=reason or "conversation_answer_only",
        decision_source=decision_source,
        confidence=confidence,
    )


def build_answer_only_runtime_action(
    *,
    answer_mode: AnswerMode,
    answer_builder: RuntimeAnswerBuilder,
    reason: str,
    decision_source: str,
    mutation_policy: MutationPolicy = MutationPolicy.FORBIDDEN,
    graph_invocation_skipped_reason: str | None = None,
    next_runtime_action: str | None = None,
    confidence: float | None = None,
    trace: dict[str, Any] | None = None,
) -> RuntimeAction:
    return RuntimeAction(
        action_type=RuntimeActionType.ANSWER_ONLY,
        answer_mode=answer_mode,
        mutation_policy=mutation_policy,
        graph_allowed=False,
        graph_invocation_skipped_reason=(
            graph_invocation_skipped_reason
            or f"{answer_builder.value}_does_not_require_governed_graph"
        ),
        answer_builder=answer_builder,
        resume_strategy=ResumeStrategy.NONE,
        next_runtime_action=next_runtime_action,
        reason=reason,
        decision_source=decision_source,
        confidence=confidence,
        trace=trace or {},
    )


def build_knowledge_override_runtime_action(
    *,
    override_class: str,
    active_case_exists: bool,
    reason: str | None = None,
) -> RuntimeAction:
    return build_answer_only_runtime_action(
        answer_mode=(
            AnswerMode.ACTIVE_CASE_SIDE_QUESTION
            if active_case_exists
            else AnswerMode.NO_CASE_KNOWLEDGE
        ),
        answer_builder=RuntimeAnswerBuilder.KNOWLEDGE_OVERRIDE,
        reason=reason or "legacy_knowledge_override_before_governed_graph",
        decision_source="knowledge_override_classifier",
        graph_invocation_skipped_reason="legacy_knowledge_override_answer_only",
        next_runtime_action="return_knowledge_override_answer",
        trace={"knowledge_override_class": override_class},
    )


def build_rfq_readiness_runtime_action(
    *,
    rfq_action_type: str,
    action_type: RuntimeActionType = RuntimeActionType.SHOW_RFQ_READINESS,
    reason: str | None = None,
    trace: dict[str, Any] | None = None,
) -> RuntimeAction:
    safe_trace = {
        "rfq_intent_detected": True,
        "rfq_action_type": rfq_action_type,
        "consent_required": True,
        "dispatch_allowed": False,
        "external_contact_allowed": False,
        "manufacturer_review_framing": True,
        "final_approval_claim_allowed": False,
    }
    safe_trace.update(trace or {})
    return RuntimeAction(
        action_type=action_type,
        answer_mode=AnswerMode.RFQ_READINESS,
        mutation_policy=MutationPolicy.FORBIDDEN,
        graph_allowed=False,
        graph_invocation_skipped_reason="rfq_readiness_answered_without_governed_graph",
        answer_builder=RuntimeAnswerBuilder.RFQ_READINESS,
        resume_strategy=ResumeStrategy.NONE,
        next_runtime_action="return_rfq_readiness_answer",
        reason=reason or "rfq_readiness_runtime_action",
        decision_source="rfq_readiness_intent",
        rfq_action=rfq_action_type,
        trace=safe_trace,
    )


def _enum_value(value: Any) -> str | None:
    return str(getattr(value, "value", value) or "") or None


def _answer_mode(value: Any) -> AnswerMode:
    try:
        return AnswerMode(_enum_value(value))
    except Exception:
        return AnswerMode.GOVERNED_INTAKE


def _mutation_policy(value: Any) -> MutationPolicy:
    try:
        return MutationPolicy(_enum_value(value))
    except Exception:
        return MutationPolicy.PROPOSED


def _resume_strategy(value: Any) -> ResumeStrategy:
    try:
        return ResumeStrategy(_enum_value(value))
    except Exception:
        return ResumeStrategy.NONE


class EvidenceItem(BaseModel):
    evidence_id: str
    evidence_type: str
    source: str
    claim_level_max: ClaimLevel = ClaimLevel.L2_APPLICATION_ORIENTATION
    safe_points: list[str] = Field(default_factory=list)
    forbidden_phrasings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class SpeakableFact(BaseModel):
    fact_id: str
    field: str | None = None
    status: Literal["confirmed", "candidate", "ambiguous", "missing", "stale", "calculated", "open"] = "candidate"
    claim_level_max: ClaimLevel = ClaimLevel.L2_APPLICATION_ORIENTATION
    structured_value: dict[str, Any] = Field(default_factory=dict)
    safe_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    source: str
    visible_in_cockpit: bool = True

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @field_validator("safe_phrases")
    @classmethod
    def _safe_phrases_required(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("SpeakableFact requires at least one safe phrase")
        return value

    @model_validator(mode="after")
    def _safe_phrase_default_must_not_be_empty(self) -> "SpeakableFact":
        if not self.safe_phrases:
            raise ValueError("SpeakableFact requires at least one safe phrase")
        return self


class AnswerPlan(BaseModel):
    answer_mode: AnswerMode
    answer_goal: str
    response_obligations: list[str] = Field(default_factory=list)
    turn_decision: TurnDecision | None = None
    primary_task: TaskFrame | None = None
    side_task: TaskFrame | None = None
    resume_target: ResumeTarget | None = None
    allowed_claim_levels: list[ClaimLevel] = Field(default_factory=lambda: [ClaimLevel.L1_GENERAL])
    forbidden_claims: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class FinalAnswerTrace(BaseModel):
    reply_source: str
    answer_markdown_source: str
    final_visible_source: Literal["answer_markdown"] = "answer_markdown"
    answer_mode: AnswerMode
    composer_tier: ComposerTier = ComposerTier.FALLBACK
    composer_attempted: bool = False
    composer_succeeded: bool = False
    fallback_reason: str | None = None
    safety_result: Literal["passed", "fallback", "blocked"] = "passed"

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class FinalAnswerContract(BaseModel):
    reply: str
    answer_markdown: str
    answer_trace: FinalAnswerTrace
    proposed_case_delta: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _visible_answer_must_exist(self) -> "FinalAnswerContract":
        if not self.reply.strip() or not self.answer_markdown.strip():
            raise ValueError("reply and answer_markdown must be non-empty")
        return self
