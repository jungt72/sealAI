from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from app.agent.agent.calc import calculate_physics
from app.agent.agent.knowledge import retrieve_rag_context
from app.agent.domain.normalization import extract_parameters as norm_extract
from app.agent.hardening.plausibility import check_circumferential_speed, check_pv_value

InteractionClass = Literal["KNOWLEDGE", "CALCULATION", "GUIDANCE", "QUALIFICATION"]
RuntimePath = Literal[
    "FAST_KNOWLEDGE",
    "FAST_CALCULATION",
    "STRUCTURED_GUIDANCE",
    "STRUCTURED_QUALIFICATION",
    "FALLBACK_SAFE_STRUCTURED",
]
BindingLevel = Literal[
    "KNOWLEDGE",
    "CALCULATION",
    "ORIENTATION",
    "QUALIFIED_PRESELECTION",
    "RFQ_BASIS",
]

# --- 0A.5: Interaction Policy version constant ---
INTERACTION_POLICY_VERSION = "interaction_policy_v1"

# --- 0A.2: Interaction Policy V1 types ---
ResultForm = Literal["direct", "guided", "deterministic", "qualified"]
PathDecision = Literal["fast", "structured"]
StreamMode = Literal["direct_answer_stream", "structured_progress_stream"]
CoverageStatus = Literal["in_scope", "partial", "out_of_scope", "unknown"]

_CALC_INTENT_KEYWORDS = (
    "berechne",
    "calculate",
    "calc",
    "rechnung",
    "rechne",
    "pv",
    "umfangsgeschwindigkeit",
    "surface speed",
)
_KNOWLEDGE_PREFIXES = (
    "was ist",
    "what is",
    "erkläre",
    "erklaere",
    "explain",
    "warum",
    "wieso",
    "weshalb",
    "wie funktioniert",
    "unterschied",
    "difference",
    "define",
)
_QUALIFICATION_KEYWORDS = (
    "empfehl",
    "recommend",
    "geeignet",
    "suitable",
    "qualif",
    "freig",
    "rfq",
    "materialauswahl",
    "materialwahl",
    "werkstoffauswahl",
    "preselection",
    "auslegen",
    "selekt",
    "candidate",
    "rwdr",
)
_GUIDANCE_KEYWORDS = (
    "anwendung",
    "application",
    "fall",
    "case",
    "betriebspunkt",
    "betriebsfall",
    "medium",
    "druck",
    "temperatur",
    "welle",
    "gehäuse",
    "housing",
    "shaft",
    "dichtung",
    "seal",
)


@dataclass(frozen=True)
class RuntimeDecision:
    interaction_class: InteractionClass
    runtime_path: RuntimePath
    binding_level: BindingLevel
    has_case_state: bool


@dataclass(frozen=True)
class InteractionPolicyDecision:
    """0A.2: Explicit typed interaction policy decision.

    Superset of RuntimeDecision. result_form / path / stream_mode / coverage_status /
    boundary_flags / escalation_reason / required_fields are the new policy-level fields.
    interaction_class / runtime_path / binding_level / has_case_state preserve
    backward compatibility with all existing RuntimeDecision consumers.
    """

    result_form: ResultForm
    path: PathDecision
    stream_mode: StreamMode
    interaction_class: InteractionClass
    runtime_path: RuntimePath
    binding_level: BindingLevel
    has_case_state: bool
    required_fields: tuple[str, ...] = field(default_factory=tuple)
    coverage_status: CoverageStatus = "unknown"
    boundary_flags: tuple[str, ...] = field(default_factory=tuple)
    escalation_reason: Optional[str] = None
    # 0A.5: explicit policy version for reproducibility
    policy_version: str = INTERACTION_POLICY_VERSION


@dataclass(frozen=True)
class RuntimeExecutionResult:
    reply: str
    working_profile: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Signal helpers (unchanged — used as input signals, not final decisions)
# ---------------------------------------------------------------------------

def is_fast_calculation_candidate(text: str) -> bool:
    parsed = extract_calc_inputs(text)
    has_direct_intent = any(keyword in text for keyword in _CALC_INTENT_KEYWORDS)
    has_speed_pair = parsed.get("diameter") is not None and parsed.get("speed") is not None
    asks_for_pv = "pv" in text and parsed.get("pressure") is not None and has_speed_pair
    return has_speed_pair and (has_direct_intent or asks_for_pv)


def is_fast_knowledge_candidate(text: str) -> bool:
    if not text:
        return False
    if looks_like_structured_qualification(text) or looks_like_structured_guidance(text):
        return False
    if extract_calc_inputs(text):
        return False
    return text.endswith("?") or any(text.startswith(prefix) for prefix in _KNOWLEDGE_PREFIXES)


def looks_like_structured_qualification(text: str) -> bool:
    return any(keyword in text for keyword in _QUALIFICATION_KEYWORDS)


def looks_like_structured_guidance(text: str) -> bool:
    if not text:
        return False
    keyword_hits = sum(1 for keyword in _GUIDANCE_KEYWORDS if keyword in text)
    has_numbers = bool(re.search(r"\d", text))
    return keyword_hits >= 2 or (keyword_hits >= 1 and has_numbers)


def extract_calc_inputs(text: str) -> Dict[str, float]:
    # 0B.3: Use central normalization
    extracted = norm_extract(text)
    profile: Dict[str, float] = {}
    
    if "diameter_mm" in extracted:
        profile["diameter"] = extracted["diameter_mm"]
    if "speed_rpm" in extracted:
        profile["speed"] = extracted["speed_rpm"]
    if "pressure_bar" in extracted:
        profile["pressure"] = extracted["pressure_bar"]
        
    return profile


# ---------------------------------------------------------------------------
# 0A.2: Policy gate helpers (deterministic, not LLM)
# ---------------------------------------------------------------------------

def _is_knowledge_intent(text: str) -> bool:
    """Returns True when the message has explicit knowledge/explanation intent.

    Guidance context suppresses knowledge intent only when guidance keywords AND
    numeric parameters are both present (e.g. "Was ist die beste Dichtung für 200°C?").
    Pure keyword matches without numbers (e.g. "What is a shaft seal?") do NOT
    suppress a knowledge prefix or trailing question mark.

    Explanation-prefix wins over qualification keywords (e.g. "Wie funktioniert eine RWDR?").
    """
    has_numbers = bool(re.search(r"\d", text))
    if looks_like_structured_guidance(text) and has_numbers:
        return False
    if text.endswith("?") and not looks_like_structured_qualification(text):
        return True
    return any(text.startswith(prefix) for prefix in _KNOWLEDGE_PREFIXES)


def _has_asserted_parameters(existing_state: dict | None) -> bool:
    """Returns True if the persisted case state has asserted engineering parameters.

    Used to gate the qualification downgrade: qualification signals without a
    data basis route to 'guided' rather than 'qualified'.
    """
    if not existing_state:
        return False
    sealing_state = existing_state.get("sealing_state") or {}
    asserted = sealing_state.get("asserted") or {}
    has_medium = bool((asserted.get("medium_profile") or {}).get("name"))
    operating = asserted.get("operating_conditions") or {}
    has_conditions = (
        operating.get("temperature") is not None
        or operating.get("pressure") is not None
    )
    return has_medium or has_conditions


def _derive_required_fields(existing_state: dict | None) -> tuple[str, ...]:
    """Surfaces up to 3 blocking unknowns from governance as required_fields."""
    if not existing_state:
        return ()
    sealing_state = existing_state.get("sealing_state") or {}
    governance = sealing_state.get("governance") or {}
    blocking = [
        str(item)
        for item in governance.get("unknowns_release_blocking", [])
        if item
    ][:3]
    return tuple(blocking)


# ---------------------------------------------------------------------------
# 0A.2: Primary policy entry point
# ---------------------------------------------------------------------------

def evaluate_interaction_policy(
    message: str,
    *,
    has_rwdr_payload: bool = False,
    existing_state: dict | None = None,
) -> InteractionPolicyDecision:
    """Evaluate the Interaction Policy V1 and return a typed decision.

    Decision priorities (deterministic, top-down):
    1. RWDR structured payload present → qualified / structured
    2. Fast calculation candidate (numeric inputs + calc intent) → deterministic / fast
    3. Explicit knowledge/explanation intent without guidance context → direct / fast
    4. Qualification signal:
       - with existing asserted parameters → qualified / structured
       - without data basis → guided / structured (downgrade, escalation_reason set)
    5. Guidance keywords with numbers or ≥2 hits → guided / structured
    6. Fallback → guided / structured (safe default)

    The existing RuntimeDecision-compatible fields (interaction_class, runtime_path,
    binding_level, has_case_state) are always set for backward compatibility.
    """
    text = (message or "").strip().lower()
    required = _derive_required_fields(existing_state)

    # Priority 1: RWDR structured payload → always qualified
    if has_rwdr_payload:
        return InteractionPolicyDecision(
            result_form="qualified",
            path="structured",
            stream_mode="structured_progress_stream",
            coverage_status="in_scope",
            boundary_flags=(),
            required_fields=required,
            escalation_reason=None,
            interaction_class="QUALIFICATION",
            runtime_path="STRUCTURED_QUALIFICATION",
            binding_level="QUALIFIED_PRESELECTION",
            has_case_state=True,
        )

    # Priority 2: Fast calculation with numeric inputs and explicit calc intent
    if is_fast_calculation_candidate(text):
        return InteractionPolicyDecision(
            result_form="deterministic",
            path="fast",
            stream_mode="direct_answer_stream",
            coverage_status="in_scope",
            boundary_flags=("orientation_only", "no_manufacturer_release"),
            required_fields=(),
            escalation_reason=None,
            interaction_class="CALCULATION",
            runtime_path="FAST_CALCULATION",
            binding_level="CALCULATION",
            has_case_state=False,
        )

    # Priority 3: Explicit knowledge/explanation intent without guidance context
    if _is_knowledge_intent(text) and not extract_calc_inputs(text):
        return InteractionPolicyDecision(
            result_form="direct",
            path="fast",
            stream_mode="direct_answer_stream",
            coverage_status="unknown",
            boundary_flags=("orientation_only", "no_manufacturer_release"),
            required_fields=(),
            escalation_reason=None,
            interaction_class="KNOWLEDGE",
            runtime_path="FAST_KNOWLEDGE",
            binding_level="KNOWLEDGE",
            has_case_state=False,
        )

    # Priority 4: Qualification signal — gate on existing asserted state
    if looks_like_structured_qualification(text):
        if _has_asserted_parameters(existing_state):
            return InteractionPolicyDecision(
                result_form="qualified",
                path="structured",
                stream_mode="structured_progress_stream",
                coverage_status="partial",
                boundary_flags=(),
                required_fields=required,
                escalation_reason=None,
                interaction_class="QUALIFICATION",
                runtime_path="STRUCTURED_QUALIFICATION",
                binding_level="QUALIFIED_PRESELECTION",
                has_case_state=True,
            )
        return InteractionPolicyDecision(
            result_form="guided",
            path="structured",
            stream_mode="structured_progress_stream",
            coverage_status="partial",
            boundary_flags=("orientation_only", "no_manufacturer_release"),
            required_fields=required,
            escalation_reason="qualification_signal_without_data_basis",
            interaction_class="GUIDANCE",
            runtime_path="STRUCTURED_GUIDANCE",
            binding_level="ORIENTATION",
            has_case_state=True,
        )

    # Priority 5: Guidance keywords with numbers or ≥2 keyword hits
    if looks_like_structured_guidance(text):
        return InteractionPolicyDecision(
            result_form="guided",
            path="structured",
            stream_mode="structured_progress_stream",
            coverage_status="partial",
            boundary_flags=("orientation_only", "no_manufacturer_release"),
            required_fields=required,
            escalation_reason=None,
            interaction_class="GUIDANCE",
            runtime_path="STRUCTURED_GUIDANCE",
            binding_level="ORIENTATION",
            has_case_state=True,
        )

    # Fallback: guided / structured (safe default — never drop to fast path blindly)
    return InteractionPolicyDecision(
        result_form="guided",
        path="structured",
        stream_mode="structured_progress_stream",
        coverage_status="unknown",
        boundary_flags=("orientation_only", "no_manufacturer_release"),
        required_fields=(),
        escalation_reason=None,
        interaction_class="GUIDANCE",
        runtime_path="FALLBACK_SAFE_STRUCTURED",
        binding_level="ORIENTATION",
        has_case_state=True,
    )


# ---------------------------------------------------------------------------
# Backward-compatible wrapper — delegates to evaluate_interaction_policy()
# ---------------------------------------------------------------------------

def route_interaction(message: str, *, has_rwdr_payload: bool = False) -> RuntimeDecision:
    """Backward-compatible wrapper around evaluate_interaction_policy().

    All call sites that consumed RuntimeDecision continue to work unchanged.
    New code should call evaluate_interaction_policy() directly.
    """
    decision = evaluate_interaction_policy(message, has_rwdr_payload=has_rwdr_payload)
    return RuntimeDecision(
        interaction_class=decision.interaction_class,
        runtime_path=decision.runtime_path,
        binding_level=decision.binding_level,
        has_case_state=decision.has_case_state,
    )


# ---------------------------------------------------------------------------
# Fast-path execution
# ---------------------------------------------------------------------------

async def execute_fast_calculation(message: str) -> RuntimeExecutionResult:
    profile = extract_calc_inputs(message)
    calculated = calculate_physics(dict(profile))
    parts: List[str] = []
    plausibility_warnings: List[str] = []
    if calculated.get("v_m_s") is not None:
        _speed_check = check_circumferential_speed(calculated["v_m_s"])
        if not _speed_check.is_usable:
            plausibility_warnings.append(f"[PLAUSIBILITY] {_speed_check.reason}")
        parts.append(f"Umfangsgeschwindigkeit: {calculated['v_m_s']:.3f} m/s")
    if calculated.get("pv_value") is not None:
        _pv_check = check_pv_value(calculated["pv_value"])
        if not _pv_check.is_usable:
            plausibility_warnings.append(f"[PLAUSIBILITY] {_pv_check.reason}")
        parts.append(f"PV-Wert: {calculated['pv_value']:.3f} bar*m/s")

    if parts:
        reply = "Direkte Berechnung:\n" + "\n".join(f"- {part}" for part in parts)
    else:
        reply = (
            "Für eine direkte Berechnung fehlen mir noch belastbare Eingaben. "
            "Für v benötige ich mindestens Durchmesser in mm und Drehzahl in rpm; "
            "für PV zusätzlich den Druck in bar."
        )

    if plausibility_warnings:
        reply += "\n\n" + "\n".join(plausibility_warnings)

    return RuntimeExecutionResult(
        reply=reply,
        working_profile=_build_fast_calc_working_profile(calculated),
    )


async def execute_fast_knowledge(message: str) -> RuntimeExecutionResult:
    cards = await retrieve_rag_context(message, limit=2)
    reply = build_fast_knowledge_reply(message, cards)
    return RuntimeExecutionResult(reply=reply, working_profile=None)


def build_fast_knowledge_reply(message: str, cards: List[Any]) -> str:
    del message
    if not cards:
        return (
            "Im Fast-Knowledge-Pfad liegt dazu aktuell keine belastbare Wissensreferenz vor. "
            "Für fall- oder qualifikationsnahe Fragen route ich sicherheitshalber in den Structured Path."
        )

    paragraphs: List[str] = []
    for card in cards[:2]:
        topic = getattr(card, "topic", "") or "Knowledge"
        content = " ".join((getattr(card, "content", "") or "").split())
        snippet = content[:260].rstrip()
        paragraphs.append(f"{topic}: {snippet}")
    return "\n\n".join(paragraphs)


def _build_fast_calc_working_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    live_calc_tile = {
        "status": "ok" if profile.get("v_m_s") is not None else "warning",
        "parameters": {
            "diameter_mm": profile.get("diameter"),
            "speed_rpm": profile.get("speed"),
            "pressure_bar": profile.get("pressure"),
        },
        "v_surface_m_s": profile.get("v_m_s"),
        "pv_value": profile.get("pv_value"),
    }
    return {
        **profile,
        "calc_results": {
            "v_surface_m_s": profile.get("v_m_s"),
            "pv_value": profile.get("pv_value"),
        },
        "live_calc_tile": live_calc_tile,
    }
