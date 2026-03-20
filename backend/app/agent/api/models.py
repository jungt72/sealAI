from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


BindingLevel = Literal["KNOWLEDGE", "ORIENTATION", "CALCULATION", "QUALIFIED_PRESELECTION", "RFQ_BASIS"]


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


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sealing_state: Dict[str, Any] = Field(default_factory=dict)
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

    model_config = ConfigDict(extra="forbid")
