from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from app.agent.agent.calc import calculate_physics
from app.agent.agent.knowledge import retrieve_rag_context
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
class RuntimeExecutionResult:
    reply: str
    working_profile: Optional[Dict[str, Any]] = None


def route_interaction(message: str, *, has_rwdr_payload: bool = False) -> RuntimeDecision:
    text = (message or "").strip().lower()
    if has_rwdr_payload:
        return RuntimeDecision(
            interaction_class="QUALIFICATION",
            runtime_path="STRUCTURED_QUALIFICATION",
            binding_level="QUALIFIED_PRESELECTION",
            has_case_state=True,
        )

    if is_fast_calculation_candidate(text):
        return RuntimeDecision(
            interaction_class="CALCULATION",
            runtime_path="FAST_CALCULATION",
            binding_level="CALCULATION",
            has_case_state=False,
        )

    if looks_like_structured_qualification(text):
        return RuntimeDecision(
            interaction_class="QUALIFICATION",
            runtime_path="STRUCTURED_QUALIFICATION",
            binding_level="QUALIFIED_PRESELECTION",
            has_case_state=True,
        )

    if looks_like_structured_guidance(text):
        return RuntimeDecision(
            interaction_class="GUIDANCE",
            runtime_path="STRUCTURED_GUIDANCE",
            binding_level="ORIENTATION",
            has_case_state=True,
        )

    if is_fast_knowledge_candidate(text):
        return RuntimeDecision(
            interaction_class="KNOWLEDGE",
            runtime_path="FAST_KNOWLEDGE",
            binding_level="KNOWLEDGE",
            has_case_state=False,
        )

    return RuntimeDecision(
        interaction_class="GUIDANCE",
        runtime_path="FALLBACK_SAFE_STRUCTURED",
        binding_level="ORIENTATION",
        has_case_state=True,
    )


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
    profile: Dict[str, float] = {}
    diameter = _extract_value(text, (r"(\d+(?:[.,]\d+)?)\s*mm", r"(?:durchmesser|diameter)\s*[:=]?\s*(\d+(?:[.,]\d+)?)"))
    speed = _extract_value(text, (r"(\d+(?:[.,]\d+)?)\s*(?:rpm|u/min|1/min)", r"(?:drehzahl|speed)\s*[:=]?\s*(\d+(?:[.,]\d+)?)"))
    pressure = _extract_value(text, (r"(\d+(?:[.,]\d+)?)\s*bar", r"(?:druck|pressure)\s*[:=]?\s*(\d+(?:[.,]\d+)?)"))

    if diameter is not None:
        profile["diameter"] = diameter
    if speed is not None:
        profile["speed"] = speed
    if pressure is not None:
        profile["pressure"] = pressure
    return profile


def _extract_value(text: str, patterns: tuple[str, ...]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            continue
    return None


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
