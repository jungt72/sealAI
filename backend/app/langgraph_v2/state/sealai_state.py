# path: backend/app/langgraph_v2/state/sealai_state.py
"""Strict Pydantic state definition for SealAI LangGraph v2."""

from __future__ import annotations

import operator
import re
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import Literal

from app.langgraph_v2.io import AskMissingRequest, CoverageAnalysis, ParameterProfile
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
        """LLM-Rohoutput (de/en) auf canonical KnowledgeType mappen."""
        return normalize_knowledge_type(value)


class SealAIExtractedParameters(BaseModel):
    pressure_bar: Optional[float] = None
    temperature_c: Optional[float] = None
    medium: Optional[str] = None
    quantity: Optional[int] = None
    sku: Optional[str] = None

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


def _coerce_number(value: Any, field_name: str) -> Any:
    if value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        normalized = trimmed.replace(",", ".")
        match = _NUMBER_PATTERN.search(normalized)
        if not match:
            raise ValueError(f"{field_name} must be a number (e.g. 10 or 10.5)")
        return float(match.group(0))
    return value


class CalcResults(BaseModel):
    safety_factor: Optional[float] = None
    temperature_margin: Optional[float] = None
    pressure_margin: Optional[float] = None
    notes: List[str] = Field(default_factory=list)

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


class TechnicalParameters(BaseModel):
    # generische Felder
    medium: Optional[str] = None
    pressure_bar: Optional[float] = Field(default=None, alias="pressure")
    temperature_max: Optional[float] = None
    temperature_min: Optional[float] = None
    shaft_diameter: Optional[float] = None
    housing_diameter: Optional[float] = None
    speed_rpm: Optional[float] = None
    piston_diameter: Optional[float] = None
    bore_diameter: Optional[float] = None
    rod_diameter: Optional[float] = None
    diameter: Optional[float] = None
    d_shaft_nominal: Optional[float] = None
    shaft_tolerance: Optional[float] = None
    shaft_hardness: Optional[str] = None
    shaft_material: Optional[str] = None
    shaft_Ra: Optional[float] = None
    shaft_Rz: Optional[float] = None
    shaft_lead: Optional[str] = None
    shaft_runout: Optional[str] = None
    shaft_chamfer: Optional[str] = None
    d_bore_nominal: Optional[float] = None
    housing_tolerance: Optional[float] = None
    housing_surface_roughness: Optional[str] = None
    housing_material: Optional[str] = None
    housing_axial_space: Optional[float] = None

    # zusätzliche, discovery-nahe Felder
    temperature_C: Optional[float] = None
    inner_diameter_mm: Optional[float] = None
    outer_diameter_mm: Optional[float] = None
    medium_type: Optional[str] = None
    medium_viscosity: Optional[str] = None
    medium_additives: Optional[str] = None
    medium_solid_content: Optional[str] = None
    medium_food_grade: Optional[str] = None
    medium_elastomer_notes: Optional[str] = None
    n_min: Optional[float] = None
    n_max: Optional[float] = None
    v_max: Optional[float] = None
    p_min: Optional[float] = None
    p_max: Optional[float] = None
    T_medium_min: Optional[float] = None
    T_medium_max: Optional[float] = None
    T_ambient_min: Optional[float] = None
    T_ambient_max: Optional[float] = None
    misalignment: Optional[str] = None
    vibration_level: Optional[str] = None
    contamination_level: Optional[str] = None
    IP_requirement: Optional[str] = None
    water_exposure: Optional[str] = None
    chemicals_outside: Optional[str] = None
    target_lifetime: Optional[str] = None
    max_leakage: Optional[str] = None
    max_friction_torque: Optional[str] = None
    safety_factors: Optional[str] = None
    install_method: Optional[str] = None
    access_level: Optional[str] = None
    expected_service_interval: Optional[str] = None
    seal_type: Optional[str] = None
    lip_config: Optional[str] = None
    elastomer_material: Optional[str] = None
    spring_material: Optional[str] = None
    outer_case_type: Optional[str] = None
    dust_lip: Optional[str] = None
    helix_direction: Optional[str] = None
    standard_reference: Optional[str] = None
    nominal_diameter: Optional[float] = None
    tolerance: Optional[float] = None
    hardness: Optional[str] = None
    surface: Optional[str] = None
    roughness_ra: Optional[float] = None
    lead: Optional[str] = None
    lead_pitch: Optional[str] = None
    runout: Optional[float] = None
    eccentricity: Optional[str] = None
    housing_diameter: Optional[float] = None
    bore_diameter: Optional[float] = None
    housing_surface: Optional[str] = None
    axial_plate_axial: Optional[float] = None
    pressure_min: Optional[float] = None
    pressure_max: Optional[float] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    speed_linear: Optional[float] = None
    dynamic_runout: Optional[float] = None
    mounting_offset: Optional[float] = None
    contamination: Optional[str] = None
    lifespan: Optional[str] = None
    application_type: Optional[str] = None
    food_grade: Optional[str] = None

    @field_validator("pressure_bar", mode="before")
    @classmethod
    def _normalize_pressure_bar(cls, value: Any) -> Any:
        return _coerce_number(value, "pressure_bar")

    # wir erlauben zusätzliche Keys, damit zukünftige Felder nicht wegfallen
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


class SealParameterUpdate(TechnicalParameters):
    """Typed payload for frontend-triggered parameter patches."""

    model_config = ConfigDict(extra="forbid")


class WorkingMemory(BaseModel):
    supervisor_decision: Optional[str] = None
    retries: int = 0
    material_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    material_requirements: Dict[str, Any] = Field(default_factory=dict)
    material_recommendation: Dict[str, Any] = Field(default_factory=dict)
    knowledge_material: Optional[str] = None
    knowledge_lifetime: Optional[str] = None
    knowledge_generic: Optional[str] = None
    response_text: Optional[str] = None
    response_kind: Optional[str] = None

    frontdoor_reply: Optional[str] = None
    design_notes: Dict[str, Any] = Field(default_factory=dict)
    comparison_notes: Dict[str, Any] = Field(default_factory=dict)
    troubleshooting_notes: Dict[str, Any] = Field(default_factory=dict)

    panel_calculator: Dict[str, Any] = Field(default_factory=dict)
    panel_material: Dict[str, Any] = Field(default_factory=dict)
    panel_norms_rag: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def as_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


class SealAIState(BaseModel):
    # Core chat state
    messages: Annotated[List[BaseMessage], add_messages] = Field(default_factory=list)
    user_id: Optional[str] = None
    thread_id: Optional[str] = None
    user_context: Dict[str, Any] = Field(default_factory=dict)
    # Observability – carry run_id into state for logging/metadata
    run_id: Optional[str] = None
    prompt_traces: Annotated[list[RenderedPrompt], operator.add] = Field(default_factory=list)

    # Orchestrator meta
    phase: Optional[PhaseLiteral] = None
    last_node: Optional[str] = None
    router_classification: Optional[
        Literal["new_case", "follow_up", "clarification", "rfq_trigger"]
    ] = None

    # Discovery / Bedarfsklärung
    discovery_summary: Optional[str] = None
    discovery_coverage: Optional[float] = None
    discovery_missing: List[str] = Field(default_factory=list)
    coverage_score: float = 0.0
    coverage_gaps: List[str] = Field(default_factory=list)
    recommendation_ready: bool = False
    recommendation_go: bool = False

    # Intent / Use-Case
    intent: Optional[Intent] = None
    use_case_raw: Optional[str] = None
    application_category: Optional[str] = None
    motion_type: Optional[str] = None
    seal_family: Optional[str] = None

    # Parameter / Berechnung
    parameter_profile: Optional[ParameterProfile] = None
    parameters: TechnicalParameters = Field(default_factory=TechnicalParameters)
    parameter_provenance: Dict[str, str] = Field(default_factory=dict)
    parameter_versions: Dict[str, int] = Field(default_factory=dict)
    parameter_updated_at: Dict[str, float] = Field(default_factory=dict)
    missing_params: List[str] = Field(default_factory=list)
    coverage_analysis: Optional[CoverageAnalysis] = None
    ask_missing_request: Optional[AskMissingRequest] = None
    ask_missing_scope: Optional[AskMissingScope] = None
    awaiting_user_input: bool = False

    analysis_complete: bool = False
    calc_results_ok: bool = False
    calc_results: Optional[CalcResults] = None

    # Plan / Working Memory
    plan: Dict[str, Any] = Field(default_factory=dict)
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)

    # Empfehlung / Empfehlungstext
    recommendation: Optional[Recommendation] = None

    # HITL gate
    requires_human_review: bool = False

    # Wissens-/Quellenbezug
    need_sources: bool = False
    # Optional RAG for comparison/explanation flows.
    requires_rag: bool = False
    sources: List[Source] = Field(default_factory=list)
    knowledge_type: Optional[KnowledgeType] = None
    retrieval_meta: Optional[Dict[str, Any]] = None
    context: Optional[str] = None

    # Finaler Output / Fehler
    error: Optional[str] = None
    final_text: Optional[str] = None
    final_prompt: Optional[str] = None
    final_prompt_metadata: Dict[str, Any] = Field(default_factory=dict)

    # Human-in-the-loop confirmation
    pending_action: Optional[str] = None
    confirmed_actions: List[str] = Field(default_factory=list)
    awaiting_user_confirmation: bool = False
    confirm_checkpoint_id: Optional[str] = None
    confirm_checkpoint: Dict[str, Any] = Field(default_factory=dict)
    confirm_status: Optional[Literal["pending", "resolved"]] = None
    confirm_resolved_at: Optional[str] = None
    confirm_decision: Optional[str] = None
    confirm_edits: Dict[str, Any] = Field(default_factory=dict)

    # Flags zur Parameter-Completeness
    flags: Dict[str, Any] = Field(
        default_factory=lambda: {
            "parameters_complete_for_material": False,
            "parameters_complete_for_profile": False,
        }
    )

    # Material & Profilwahl
    material_choice: Dict[str, Any] = Field(default_factory=dict)
    profile_choice: Dict[str, Any] = Field(default_factory=dict)

    # Validierung & Critical Review
    validation: Dict[str, Any] = Field(
        default_factory=lambda: {"status": None, "issues": []}
    )
    critical: Dict[str, Any] = Field(
        default_factory=lambda: {
            "status": None,
            "target": None,
            "next_step": None,
            "iteration_count": 0,
        }
    )

    # Produktempfehlungen
    products: Dict[str, Any] = Field(
        default_factory=lambda: {
            "manufacturer": None,
            "matches": [],
            "match_quality": None,
        }
    )

    # Troubleshooting/Hypothesen
    troubleshooting: Dict[str, Any] = Field(
        default_factory=lambda: {
            "symptoms": [],
            "hypotheses": [],
            "pattern_match": None,
            "done": False,
        }
    )

    # MAI-DxO supervisor state (feature-flagged)
    open_questions: List[QuestionItem] = Field(default_factory=list)
    facts: Dict[str, FactItem] = Field(default_factory=dict)
    candidates: List[CandidateItem] = Field(default_factory=list)
    decision_log: List[DecisionEntry] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    confidence: float = 0.0
    round_index: int = 0
    next_action: Optional[str] = None

    # UI-State für Reasoning Status
    ui_state: Dict[str, Any] = Field(
        default_factory=lambda: {"current_step": None, "current_label": None}
    )

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access helper to ease migration from TypedDict."""
        return getattr(self, key, default)

    @field_validator("knowledge_type", mode="before")
    @classmethod
    def _normalize_state_knowledge_type(cls, value: Any) -> Any:
        """Top-level `knowledge_type` im State ebenfalls normalisieren."""
        return normalize_knowledge_type(value)


__all__ = [
    "Intent",
    "IntentGoal",
    "SealAIExtractedParameters",
    "SealAIIntentOutput",
    "RenderedPrompt",
    "CalcResults",
    "Recommendation",
    "Source",
    "QuestionItem",
    "FactItem",
    "CandidateItem",
    "DecisionEntry",
    "Budget",
    "SealAIState",
    "AskMissingScope",
    "TechnicalParameters",
    "SealParameterUpdate",
    "WorkingMemory",
]
