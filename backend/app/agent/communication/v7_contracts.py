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
    GOVERNED_INTAKE = "governed_intake"
    PENDING_SLOT_ANSWER = "pending_slot_answer"
    ACTIVE_CASE_SIDE_QUESTION = "active_case_side_question"
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
