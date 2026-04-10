from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.agent.runtime.outward_names import normalize_outward_response_class
from app.agent.runtime.user_facing_reply import (
    assemble_user_facing_reply,
    derive_public_response_class,
)
from app.agent.state.models import ConfidenceLevel


BindingLevel = Literal["KNOWLEDGE", "ORIENTATION", "CALCULATION", "QUALIFIED_PRESELECTION", "RFQ_BASIS"]
# Legacy -> blueprint v1.1 outward class mapping:
# - legacy "guidance" + "_response"          -> conversational_answer
# - legacy structured_clarification          -> structured_clarification
# - legacy "structured" + "_review"          -> technical_preselection
# - legacy "structured" + "_escalation"      -> structured_clarification
# - legacy "structured_governed" + "_result" -> technical_preselection
# - legacy "structured_state" + "_update"    -> governed_state_update
ResponseClass = Literal[
    "conversational_answer",
    "structured_clarification",
    "governed_state_update",
    "technical_preselection",
    "candidate_shortlist",
    "inquiry_ready",
]
_NON_STRUCTURED_POLICY_PATHS: frozenset[str] = frozenset({"fast", "blocked", "meta", "greeting"})


# ---------------------------------------------------------------------------
# HITL Review — Blueprint Sections 08 & 12
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# F-B.3 — Override Endpoint models
# ---------------------------------------------------------------------------

class OverrideItem(BaseModel):
    """A single field override submitted by the UI tile.

    Mirrors UserOverride from state/models.py — kept separate so the API
    contract does not leak internal state types to callers.
    """

    field_name: str = Field(..., min_length=1, description="Canonical parameter name")
    value: Any = Field(..., description="New value for the field")
    unit: Optional[str] = Field(default=None, description="Unit for the new value")

    model_config = ConfigDict(extra="forbid")


class OverrideRequest(BaseModel):
    """Payload for PATCH /session/{session_id}/override."""

    overrides: list[OverrideItem] = Field(..., min_length=1)
    turn_index: int = Field(default=0, ge=0, description="Current turn number")

    model_config = ConfigDict(extra="forbid")


class OverrideGovernanceResult(BaseModel):
    """Governance outcome after applying overrides."""

    gov_class: Optional[str] = None
    inquiry_admissible: bool = Field(
        default=False,
        validation_alias=AliasChoices("inquiry_admissible", "rfq_admissible"),
        serialization_alias="inquiry_admissible",
    )
    blocking_unknowns: list[str] = Field(default_factory=list)
    conflict_flags: list[str] = Field(default_factory=list)
    validity_limits: list[str] = Field(default_factory=list)
    open_validation_points: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @property
    def rfq_admissible(self) -> bool:
        return self.inquiry_admissible


class OverrideResponse(BaseModel):
    """Response from PATCH /session/{session_id}/override."""

    session_id: str
    applied_fields: list[str]
    governance: OverrideGovernanceResult

    model_config = ConfigDict(extra="forbid")


class ReviewRequest(BaseModel):
    """Payload for the POST /review endpoint (human-in-the-loop decision)."""
    session_id: str = Field(..., min_length=1)
    action: Literal["approve", "reject"] = Field(
        ...,
        description="Reviewer decision: 'approve' → rfq_ready, 'reject' → inadmissible",
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Optional free-text annotation by the reviewer",
    )

    model_config = ConfigDict(extra="forbid")


class ReviewResponse(BaseModel):
    """Response from POST /review."""
    session_id: str
    action: str
    review_state: str
    release_status: str
    is_handover_ready: bool
    handover: Optional[Dict[str, Any]] = None
    reply: str = ""

    model_config = ConfigDict(extra="forbid")


class ReviewSeedResponse(BaseModel):
    """Response from POST /review/seed (test-only helper)."""
    session_id: str
    review_state: str
    release_status: str
    review_reason: str

    model_config = ConfigDict(extra="forbid")


class CaseMetadataResponse(BaseModel):
    id: str
    case_number: str
    user_id: str
    subsegment: Optional[str] = None
    status: str
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None

    model_config = ConfigDict(extra="forbid")


class GovernedSnapshotResponse(BaseModel):
    case_id: str
    case_number: str
    user_id: str
    revision: int
    state_json: Dict[str, Any]
    basis_hash: Optional[str] = None
    ontology_version: Optional[str] = None
    prompt_version: Optional[str] = None
    model_version: Optional[str] = None
    created_at: Optional[Any] = None

    model_config = ConfigDict(extra="forbid")


class CaseListItemResponse(BaseModel):
    id: str
    case_number: str
    status: str
    subsegment: Optional[str] = None
    updated_at: Optional[Any] = None
    latest_revision: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class GovernedSnapshotRevisionListItemResponse(BaseModel):
    revision: int
    basis_hash: Optional[str] = None
    ontology_version: Optional[str] = None
    prompt_version: Optional[str] = None
    model_version: Optional[str] = None
    created_at: Optional[Any] = None

    model_config = ConfigDict(extra="forbid")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default="default")

    model_config = ConfigDict(extra="forbid")


class VisibleCaseNarrativeItemResponse(BaseModel):
    key: str
    label: str
    value: str
    detail: Optional[str] = None
    severity: Literal["low", "medium", "high"]

    model_config = ConfigDict(extra="forbid")


class VisibleCaseNarrativeResponse(BaseModel):
    governed_summary: str
    technical_direction: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    validity_envelope: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    next_best_inputs: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    suggested_next_questions: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    failure_analysis: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    case_summary: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    qualification_status: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)
    coverage_scope: list[VisibleCaseNarrativeItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class StructuredStateExposureResponse(BaseModel):
    case_status: str
    output_status: str
    next_step: str
    primary_allowed_action: str
    active_blockers: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def build_public_response_core(
    *,
    reply: str,
    structured_state: Optional[Dict[str, Any]] = None,
    policy_path: Optional[str] = None,
    run_meta: Optional[Dict[str, Any]] = None,
    state_update: bool = False,
) -> Dict[str, Any]:
    """Legacy-compatible wrapper around the central user-facing reply assembly."""
    response_class = derive_public_response_class(
        structured_state=structured_state,
        state_update=state_update,
    )

    _assert_public_response_core_mapping(
        response_class=response_class,
        structured_state=structured_state,
        policy_path=policy_path,
        state_update=state_update,
    )
    return assemble_user_facing_reply(
        reply=reply,
        structured_state=structured_state,
        policy_path=policy_path,
        run_meta=run_meta,
        state_update=state_update,
        response_class=response_class,
    )


def _assert_public_response_core_mapping(
    *,
    response_class: str,
    structured_state: Optional[Dict[str, Any]],
    policy_path: Optional[str],
    state_update: bool,
) -> None:
    if response_class == "conversational_answer":
        if structured_state is not None:
            raise ValueError("conversational_answer must not expose structured_state")
        return

    if response_class == "governed_state_update":
        if not state_update or structured_state is None:
            raise ValueError("governed_state_update requires state_update=True and structured_state")
        if policy_path in _NON_STRUCTURED_POLICY_PATHS:
            raise ValueError("governed_state_update must not use a non-structured policy_path")
        return

    if structured_state is None:
        raise ValueError(f"{response_class} requires structured_state")
    if state_update:
        raise ValueError(f"{response_class} is not valid for state_update payloads")
    if policy_path in _NON_STRUCTURED_POLICY_PATHS:
        raise ValueError(f"{response_class} must not use a non-structured policy_path")


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sealing_state: Optional[Dict[str, Any]] = None
    policy_path: Optional[str] = None
    run_meta: Optional[Dict[str, Any]] = None
    response_class: Optional[ResponseClass | str] = None
    interaction_class: Optional[str] = None
    runtime_path: Optional[str] = None
    binding_level: Optional[BindingLevel | str] = None
    has_case_state: Optional[bool] = None
    case_id: Optional[str] = None
    qualified_action_gate: Optional[Dict[str, Any]] = None
    result_contract: Optional[Dict[str, Any]] = None
    rfq_ready: Optional[bool] = None
    visible_case_narrative: Optional[VisibleCaseNarrativeResponse | Dict[str, Any]] = None
    result_form: Optional[str] = None
    path: Optional[str] = None
    stream_mode: Optional[str] = None
    required_fields: list[str] = Field(default_factory=list)
    coverage_status: Optional[str] = None
    boundary_flags: list[str] = Field(default_factory=list)
    escalation_reason: Optional[str] = None
    case_state: Optional[Dict[str, Any]] = None
    working_profile: Optional[Dict[str, Any]] = None
    version_provenance: Optional[Dict[str, Any]] = None
    next_step_contract: Optional[Dict[str, Any]] = None
    structured_state: Optional[StructuredStateExposureResponse | Dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("response_class", mode="before")
    @classmethod
    def _normalize_response_class(cls, value: Any) -> Any:
        if value is None:
            return value
        return normalize_outward_response_class(value, default="structured_clarification")
