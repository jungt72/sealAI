from __future__ import annotations

import math
from typing import Annotated, Any, Dict, Iterable, List, Optional, Sequence, TypedDict
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import add_messages
from langgraph.managed import RemainingSteps
from typing_extensions import Literal, NotRequired

class ContextRef(TypedDict, total=False):
    kind: str  # "rag" or "tool"
    id: str
    meta: Optional[Dict[str, Any]]


class IntentPrediction(TypedDict, total=False):
    """Normalized intent classification shared across routing nodes."""

    domain: str
    kind: str
    task: str
    confidence: float
    type: Literal["general", "consulting", "general_answer", "consultation"]
    reason: str


class Routing(TypedDict, total=False):
    domains: List[str]
    primary_domain: Optional[str]
    confidence: float
    coverage: float

class MetaInfo(TypedDict, total=False):
    thread_id: str
    user_id: str
    trace_id: str

PhaseLiteral = Literal["rapport", "warmup", "bedarfsanalyse", "berechnung", "auswahl", "review", "exit"]


class StyleContract(TypedDict, total=False):
    raw_instruction: str
    no_intro: bool
    no_outro: bool
    single_sentence: bool
    numbers_with_commas: bool
    literal_numbers_start: int
    literal_numbers_end: int
    enforce_plain_answer: bool
    additional_notes: str


class ChecklistResult(TypedDict, total=False):
    approved: bool
    confidence: float
    critique: str
    improved_answer: str


class RwdRequirements(TypedDict, total=False):
    machine: str
    application: str
    medium: str
    temperature_min: float
    temperature_max: float
    speed_rpm: float
    pressure_inner: float
    pressure_outer: float
    shaft_diameter: float
    housing_diameter: float
    axial_position_notes: str
    surface_roughness: str
    shaft_material: str
    housing_material: str
    norms: str
    history: str
    failure_modes: str
    target_lifetime: str
    sealing_goal: str
    notes: str


class RwdCalcResults(TypedDict, total=False):
    surface_speed_m_per_s: float
    pv_value: float
    pressure_delta: float
    notes: str


class WarmupState(TypedDict, total=False):
    rapport: str
    user_mood: str
    ready_for_analysis: bool


class LongTermMemoryRef(TypedDict, total=False):
    storage: str
    id: str
    summary: str
    score: float


class MemoryInjection(TypedDict, total=False):
    summary: str
    relevance: float
    source: str


class UserProfile(TypedDict, total=False):
    display_name: str
    company: str
    industry: str
    preferences: List[str]

class SealAIState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    remaining_steps: NotRequired[RemainingSteps]
    slots: Dict[str, Any]
    context_state: Dict[str, Any]
    intent: Optional[IntentPrediction]
    message_in: NotRequired[str]
    message_out: NotRequired[str]
    msg_type: NotRequired[str]
    pending_intent_choice: NotRequired[bool | str]
    intent_confidence: NotRequired[float]
    intent_reason: NotRequired[str]
    routing: Routing
    context_refs: List[ContextRef]
    meta: MetaInfo
    rwd_requirements: RwdRequirements
    rwd_calc_results: RwdCalcResults
    bedarfsanalyse: Dict[str, Any]
    warmup: WarmupState
    phase: PhaseLiteral
    requirements_coverage: float
    rapport_phase_done: bool
    rapport_summary: str
    discovery_summary: str
    long_term_memory_refs: List[LongTermMemoryRef]
    memory_injections: List[MemoryInjection]
    user_profile: UserProfile
    confidence: float
    review_loops: int


def new_user_message(content: str, *, user_id: str, msg_id: str) -> HumanMessage:
    return HumanMessage(content=content, id=msg_id, name=user_id)


def new_assistant_message(content: str, *, msg_id: str) -> AIMessage:
    return AIMessage(content=content, id=msg_id)

def validate_slots(slots: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in slots.items():
        if isinstance(value, (str, dict, list)) and len(str(value)) > 1000:
            raise ValueError(f"Slot {key} too large")
    return slots


_NUMERIC_FIELDS: Sequence[str] = (
    "temperature_min",
    "temperature_max",
    "speed_rpm",
    "pressure_inner",
    "pressure_outer",
    "shaft_diameter",
    "housing_diameter",
)

_REQUIRED_FIELDS: Sequence[str] = (
    "machine",
    "application",
    "medium",
    "temperature_max",
    "temperature_min",
    "speed_rpm",
    "shaft_diameter",
    "pressure_inner",
)


def _to_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not math.isnan(float(value)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", ".")
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def sanitize_rwd_requirements(payload: Any) -> RwdRequirements:
    """Sanitize arbitrary payload to the defined RWD requirement schema."""
    result: RwdRequirements = RwdRequirements()
    if not isinstance(payload, dict):
        return result
    for key, value in payload.items():
        if key in _NUMERIC_FIELDS:
            maybe = _to_optional_float(value)
            if maybe is not None:
                result[key] = maybe  # type: ignore[index]
            continue
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                result[key] = trimmed  # type: ignore[index]
        elif isinstance(value, (int, float)):
            result[key] = str(value)  # type: ignore[index]
    return result


def merge_rwd_requirements(current: Optional[RwdRequirements], updates: Optional[RwdRequirements]) -> RwdRequirements:
    base: RwdRequirements = RwdRequirements()
    if current:
        base.update({k: v for k, v in current.items() if v not in (None, "")})
    if updates:
        base.update({k: v for k, v in updates.items() if v not in (None, "")})
    return base


def compute_requirements_coverage(req: Optional[RwdRequirements]) -> float:
    if not req:
        return 0.0
    filled = sum(1 for field in _REQUIRED_FIELDS if req.get(field) not in (None, ""))
    return round(filled / len(_REQUIRED_FIELDS), 3)


def missing_requirement_fields(req: Optional[RwdRequirements]) -> List[str]:
    if not req:
        return list(_REQUIRED_FIELDS)
    return [field for field in _REQUIRED_FIELDS if req.get(field) in (None, "")]


def ensure_phase(state: SealAIState, default: PhaseLiteral = "rapport") -> PhaseLiteral:
    phase = state.get("phase")
    if phase not in ("rapport", "warmup", "bedarfsanalyse", "berechnung", "auswahl", "review", "exit"):
        return default
    return phase  # type: ignore[return-value]


def format_requirements_summary(req: Optional[RwdRequirements]) -> str:
    if not req:
        return "Es liegen noch keine strukturierten Angaben zur Einbausituation vor."
    key_order: Sequence[tuple[str, str]] = (
        ("machine", "Maschine"),
        ("application", "Anwendung"),
        ("medium", "Medium"),
        ("temperature_min", "Temperatur min"),
        ("temperature_max", "Temperatur max"),
        ("speed_rpm", "Drehzahl [rpm]"),
        ("pressure_inner", "Innendruck [bar]"),
        ("pressure_outer", "Außendruck [bar]"),
        ("shaft_diameter", "Wellen-Ø [mm]"),
        ("housing_diameter", "Gehäuse-Ø [mm]"),
        ("surface_roughness", "Oberfläche"),
        ("shaft_material", "Wellenmaterial"),
        ("housing_material", "Gehäusematerial"),
        ("norms", "Normen/Zulassungen"),
        ("history", "Historie"),
        ("failure_modes", "Ausfallbilder"),
        ("target_lifetime", "Ziel-Lebensdauer"),
        ("sealing_goal", "Zielsetzung"),
    )
    lines: List[str] = []
    for key, label in key_order:
        value = req.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, float):
            display = f"{value:.3f}".rstrip("0").rstrip(".")
        else:
            display = str(value)
        lines.append(f"{label}: {display}")
    return "\n".join(lines) or "Die Angaben sind noch unvollständig."


__all__ = [
    "ContextRef",
    "RwdRequirements",
    "RwdCalcResults",
    "PhaseLiteral",
    "WarmupState",
    "LongTermMemoryRef",
    "MemoryInjection",
    "UserProfile",
    "Routing",
    "MetaInfo",
    "SealAIState",
    "compute_requirements_coverage",
    "ensure_phase",
    "format_requirements_summary",
    "merge_rwd_requirements",
    "missing_requirement_fields",
    "new_assistant_message",
    "new_user_message",
    "sanitize_rwd_requirements",
    "validate_slots",
]
