from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationMode(str, Enum):
    SMALLTALK = "SMALLTALK"
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    CASE_QUALIFICATION = "CASE_QUALIFICATION"
    RFQ_PREPARATION = "RFQ_PREPARATION"
    FAILURE_ANALYSIS = "FAILURE_ANALYSIS"
    FIELD_EXTRACTION = "FIELD_EXTRACTION"
    OUT_OF_SCOPE_OR_UNSAFE = "OUT_OF_SCOPE_OR_UNSAFE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ConversationField(BaseModel):
    key: str
    label: str | None = None
    value: Any = None
    unit: str | None = None
    source: str | None = None
    status: str | None = None
    confirmed_at: str | None = None
    confidence: str | None = None

    model_config = ConfigDict(extra="forbid")


class MissingField(BaseModel):
    key: str
    label: str
    criticality: Literal["critical", "important", "optional"] = "important"
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class StaleField(BaseModel):
    key: str
    reason: str

    model_config = ConfigDict(extra="forbid")


class CalculationFact(BaseModel):
    id: str
    label: str
    value: Any = None
    unit: str | None = None
    inputs: list[str] = Field(default_factory=list)
    status: Literal["available", "blocked_by_missing_inputs"] = "blocked_by_missing_inputs"

    model_config = ConfigDict(extra="forbid")


class RiskFact(BaseModel):
    id: str
    label: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    reason: str = ""
    source: Literal["rule", "calculation", "evidence"] = "rule"

    model_config = ConfigDict(extra="forbid")


class ReadinessFact(BaseModel):
    status: Literal["not_ready", "partially_ready", "rfq_ready", "unknown"] = "unknown"
    blocking_reasons: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class EvidenceRef(BaseModel):
    id: str
    title: str
    source_type: Literal["rule", "datasheet", "standard", "internal_doc", "calculation", "user_input"] = "user_input"
    uri_or_ref: str | None = None

    model_config = ConfigDict(extra="forbid")


class CaseConversationState(BaseModel):
    case_id: str = "default"
    user_id: str | None = None
    tenant_id: str | None = None
    phase: str = "unknown"
    confirmed_fields: list[ConversationField] = Field(default_factory=list)
    proposed_fields: list[ConversationField] = Field(default_factory=list)
    missing_fields: list[MissingField] = Field(default_factory=list)
    stale_fields: list[StaleField] = Field(default_factory=list)
    calculations: list[CalculationFact] = Field(default_factory=list)
    risks: list[RiskFact] = Field(default_factory=list)
    readiness: ReadinessFact = Field(default_factory=ReadinessFact)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    allowed_next_actions: list[str] = Field(default_factory=list)
    conversation_summary: str | None = None
    latest_user_message: str = ""

    model_config = ConfigDict(extra="forbid")


AllowedClaimType = Literal[
    "confirmed_field",
    "proposed_field",
    "missing_field",
    "stale_field",
    "calculation",
    "risk",
    "readiness",
    "evidence",
    "allowed_action",
    "limitation",
]


class AllowedClaim(BaseModel):
    id: str
    type: AllowedClaimType
    statement: str
    source: Literal["user_confirmed", "backend_rule", "calculation", "evidence", "system_limitation"] = "backend_rule"
    confidence: Literal["confirmed", "calculated", "proposed", "uncertain"] = "uncertain"
    severity: Literal["none", "low", "medium", "high", "critical"] = "none"
    field_keys: list[str] = Field(default_factory=list)
    evidence_ref_ids: list[str] = Field(default_factory=list)
    lifecycle: Literal["active", "stale", "superseded", "revoked"] = "active"
    state_snapshot_hash: str | None = None

    model_config = ConfigDict(extra="forbid")


class ProposedFieldUpdate(BaseModel):
    key: str
    value: Any = None
    unit: str | None = None
    confidence: Literal["low", "medium", "high"] = "medium"
    requires_user_confirmation: bool = True

    model_config = ConfigDict(extra="forbid")


class LLMResponseContract(BaseModel):
    mode: ConversationMode
    assistant_message: str
    used_claim_ids: list[str] = Field(default_factory=list)
    cited_evidence_ref_ids: list[str] = Field(default_factory=list)
    asks_for_fields: list[str] = Field(default_factory=list)
    proposed_field_updates: list[ProposedFieldUpdate] = Field(default_factory=list)
    recommendation_level: Literal["none", "directional", "requires_review"] = "none"
    contains_solution_recommendation: bool = False
    contains_final_approval: bool = False
    requires_human_review: bool = False
    safety_flags: list[str] = Field(default_factory=list)
    next_action: str | None = None

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @field_validator("assistant_message")
    @classmethod
    def _message_must_not_be_empty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("assistant_message must not be empty")
        return text


class CommunicationTrace(BaseModel):
    turn_id: str
    case_id: str | None = None
    mode: ConversationMode
    prompt_version: str
    state_snapshot_hash: str
    allowed_claim_ids_used: list[str] = Field(default_factory=list)
    cited_evidence_ref_ids_used: list[str] = Field(default_factory=list)
    guard_result: str
    validation_errors: list[str] = Field(default_factory=list)
    model_provider: str | None = None
    model_name: str | None = None
    timestamp: str

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class HumanCommunicationResult(BaseModel):
    assistant_message: str
    response_contract: LLMResponseContract
    allowed_claims: list[AllowedClaim] = Field(default_factory=list)
    proposed_field_updates: list[ProposedFieldUpdate] = Field(default_factory=list)
    trace: CommunicationTrace
    used_fallback: bool = False

    model_config = ConfigDict(extra="forbid")
