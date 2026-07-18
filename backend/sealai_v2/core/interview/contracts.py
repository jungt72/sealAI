"""Typed contracts for the deterministic adaptive technical interview.

The models in this module deliberately contain no persistence, retrieval, LLM, or
calculation behavior.  They are the narrow boundary between the canonical case
state, a versioned domain pack, and the interview policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class NeedStatus(str, Enum):
    UNKNOWN = "unknown"
    PARTIAL = "partial"
    SATISFIED = "satisfied"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"
    UNOBTAINABLE = "unobtainable"


class FactOrigin(str, Enum):
    USER_TEXT = "user_text"
    USER_FORM = "user_form"
    DOCUMENT = "document"
    IMPORT = "import"
    KERNEL = "kernel"
    EXPERT = "expert"


class VerificationStatus(str, Enum):
    CANDIDATE = "candidate"
    NORMALIZED = "normalized"
    USER_CONFIRMED = "user_confirmed"
    SYSTEM_VALIDATED = "system_validated"
    EXPERT_APPROVED = "expert_approved"
    REJECTED = "rejected"


class EpistemicStatus(str, Enum):
    STATED = "stated"
    OBSERVED = "observed"
    DERIVED = "derived"
    ASSUMED = "assumed"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


class PendingQuestionStatus(str, Enum):
    ACTIVE = "active"
    ANSWERED = "answered"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class InterviewDirectiveType(str, Enum):
    ASK = "ask"
    CLARIFY_CONFLICT = "clarify_conflict"
    CONFIRM_CRITICAL_FACT = "confirm_critical_fact"
    ESCALATE = "escalate"
    COMPLETE = "complete"


class InterviewStatePatchType(str, Enum):
    UPSERT_PENDING = "upsert_pending"
    UPDATE_PENDING_STATUS = "update_pending_status"


@dataclass(frozen=True)
class DomainPackVersion:
    pack_id: str
    version: str


@dataclass(frozen=True)
class PolicyVersion:
    value: str


@dataclass(frozen=True)
class FactSemantics:
    origin: FactOrigin
    verification_status: VerificationStatus
    epistemic_status: EpistemicStatus
    field_key: str
    value: str | float | None
    unit: str = ""
    source_ref: str = ""


@dataclass(frozen=True)
class NeedDefinition:
    need_id: str
    field_keys: tuple[str, ...]
    active: bool
    required: bool
    criticality: str
    question_id: str | None
    dependency_refs: tuple[str, ...] = ()
    rule_refs: tuple[str, ...] = ()
    curated_order: int = 1000
    dependency_depth: int = 0
    downstream_unlock_count: int = 0
    min_present: int = 1
    derived_calc_id: str | None = None
    conflict_sensitive: bool = False


@dataclass(frozen=True)
class NeedState:
    need_id: str
    status: NeedStatus
    facts: tuple[FactSemantics, ...] = ()
    reason_code: str = ""

    @property
    def is_documented(self) -> bool:
        return self.status in {
            NeedStatus.SATISFIED,
            NeedStatus.CONFLICTED,
            NeedStatus.UNOBTAINABLE,
            NeedStatus.NOT_APPLICABLE,
            NeedStatus.BLOCKED,
        }

    @property
    def is_completion_satisfying(self) -> bool:
        return self.status in {
            NeedStatus.SATISFIED,
            NeedStatus.UNOBTAINABLE,
            NeedStatus.NOT_APPLICABLE,
        }


@dataclass(frozen=True)
class QuestionDefinition:
    question_id: str
    primary_need_id: str
    related_need_ids: tuple[str, ...]
    canonical_text_de: str
    question_type: str
    answer_schema: dict[str, Any]
    allowed_unknown: bool
    allowed_unobtainable: bool
    criticality: str
    dependency_refs: tuple[str, ...]
    rule_refs: tuple[str, ...]
    curated_order: int
    legacy_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainPack:
    pack_id: str
    version: str
    question_catalog_version: str
    case_schema_version: int
    policy_version: str
    stop_profile: str
    supported_seal_types: tuple[str, ...]
    unsupported_primary_types: tuple[str, ...]
    rwdr_signal_fields: tuple[str, ...]
    needs: tuple[NeedDefinition, ...]
    questions: tuple[QuestionDefinition, ...]
    calculator_version_refs: tuple[str, ...] = ()

    def need(self, need_id: str) -> NeedDefinition | None:
        return next((item for item in self.needs if item.need_id == need_id), None)

    def question(self, question_id: str) -> QuestionDefinition | None:
        return next(
            (item for item in self.questions if item.question_id == question_id),
            None,
        )

    def allows_unobtainable(self, need_id: str) -> bool:
        """Only an explicitly enabled primary need can be overridden."""

        return any(
            question.primary_need_id == need_id and question.allowed_unobtainable
            for question in self.questions
        )


@dataclass(frozen=True)
class UnobtainableOverrideAudit:
    need_id: str
    reason: str
    actor_ref: str
    created_at: str
    pack_version: str
    policy_version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("need_id", self.need_id),
            ("reason", self.reason),
            ("actor_ref", self.actor_ref),
            ("created_at", self.created_at),
            ("pack_version", self.pack_version),
            ("policy_version", self.policy_version),
        ):
            if not value or value != value.strip():
                raise ValueError(f"unobtainable override requires canonical {label}")
        try:
            created = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                "unobtainable override requires an ISO-8601 timestamp"
            ) from exc
        if created.tzinfo is None or created.utcoffset() != timezone.utc.utcoffset(
            created
        ):
            raise ValueError("unobtainable override timestamp must be UTC")


@dataclass(frozen=True)
class InterviewConflict:
    conflict_id: str
    field_key: str
    need_id: str
    candidate_values: tuple[str, ...]
    created_from_state_revision: int
    status: str = "active"
    reason_code: str = "corrected_decision_critical_fact"


@dataclass(frozen=True)
class FactSnapshot:
    field_key: str
    value: str
    unit: str
    state_revision: int
    status: str


@dataclass(frozen=True)
class PendingQuestion:
    pending_question_id: str
    question_id: str
    primary_need_id: str
    related_need_ids: tuple[str, ...]
    topic_id: str
    pack_id: str
    pack_version: str
    policy_version: str
    created_at: str
    created_from_state_revision: int
    dependency_snapshot: dict[str, str]
    status: PendingQuestionStatus = PendingQuestionStatus.ACTIVE
    invalidated_reason: str = ""
    answered_at: str = ""
    directive_type: InterviewDirectiveType = InterviewDirectiveType.ASK


@dataclass(frozen=True)
class InterviewRuntimeState:
    topic_id: str = "rwdr.default"
    pack_id: str = "legacy_unversioned"
    pack_version: str = "legacy_unversioned"
    policy_version: str = "legacy_unversioned"
    question_catalog_version: str = "legacy_unversioned"
    case_schema_version: int = 2
    state_revision: int = 0
    pending_questions: tuple[PendingQuestion, ...] = ()
    unobtainable_overrides: tuple[UnobtainableOverrideAudit, ...] = ()
    conflicts: tuple[InterviewConflict, ...] = ()
    fact_snapshots: tuple[FactSnapshot, ...] = ()
    calculator_version_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not isinstance(item, UnobtainableOverrideAudit)
            for item in self.unobtainable_overrides
        ):
            raise TypeError("unobtainable_overrides must contain typed audit records")
        ids = [item.need_id for item in self.unobtainable_overrides]
        if len(ids) != len(set(ids)):
            raise ValueError("unobtainable overrides require unique need_id values")


@dataclass(frozen=True)
class InterviewDirective:
    type: InterviewDirectiveType
    reason_code: str
    question_id: str | None = None
    primary_need_id: str | None = None
    conflict_id: str | None = None
    pending_question_id: str | None = None


@dataclass(frozen=True)
class InterviewStatePatch:
    type: InterviewStatePatchType
    pending_question: PendingQuestion


@dataclass(frozen=True)
class InterviewDecision:
    directives: tuple[InterviewDirective, ...]
    rule_refs: tuple[str, ...]
    pack_id: str
    pack_version: str
    policy_version: str
    state_revision: int
    state_patches: tuple[InterviewStatePatch, ...] = ()


@dataclass(frozen=True)
class NextQuestionPayload:
    case_id: str
    topic_id: str
    state_revision: int
    pack_id: str
    pack_version: str
    policy_version: str
    question_id: str
    primary_need_id: str
    related_need_ids: tuple[str, ...]
    question_text: str
    question_type: str
    answer_schema: dict[str, Any]
    allowed_unknown: bool
    allowed_unobtainable: bool
    criticality: str
    rule_refs: tuple[str, ...]
    dependency_refs: tuple[str, ...]
    pending_question_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("related_need_ids", "rule_refs", "dependency_refs"):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True)
class InterviewCompletenessMetrics:
    active_required_needs: int
    documented_required_needs: int
    satisfied: int
    conflicted: int
    unobtainable: int
    not_applicable: int
    blocked: int
    additional_llm_calls_by_controller: int = 0

    @property
    def ratio(self) -> float:
        if self.active_required_needs == 0:
            return 1.0
        return self.documented_required_needs / self.active_required_needs


@dataclass(frozen=True)
class InterviewShadowRecord:
    tenant_id: str
    case_reference: str
    state_revision: int
    pack_id: str
    pack_version: str
    policy_version: str
    legacy_question_present: bool
    legacy_question_fingerprint: str | None
    controller_directive: str
    controller_question_id: str | None
    rule_refs: tuple[str, ...]
    divergence_type: str
    decision_duration_ms: float
    completeness: dict[str, Any]
    created_at: str
    legacy_need_id: str | None = None
    record_id: str = ""
