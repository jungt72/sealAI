"""
Frontdoor Gate — Phase B.1

Answers a single question: which frontdoor mode is appropriate for this turn?
Route is explicit and three-way:
  - CONVERSATION
  - EXPLORATION
  - GOVERNED

Decision logic (in order):
  1. Sticky session: already governed biases to GOVERNED
  2. Hard overrides: deterministic pattern match → GOVERNED immediately
  3. Deterministic light-route heuristics:
     - CONVERSATION for greetings / smalltalk / harmless meta
     - EXPLORATION for open goal / problem / uncertainty / replacement
  4. Mini-LLM: 3-way classification with structured JSON response
     {"routing": "...", "confidence": 0.0-1.0}
  5. Parse error, low confidence, timeout, or any uncertainty → GOVERNED

Architecture rule:
  - Gate remains the only frontdoor routing decision point.
  - The session envelope is passed in by the caller; gate is stateless.
  - Uncertainty must bias to GOVERNED.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_GATE_MODEL = os.environ.get("SEALAI_GATE_MODEL", "gpt-4o-mini")
_CONFIDENCE_THRESHOLD = 0.75
# Stricter threshold for non-governed override while the session is already
# sticky-governed. We only allow the light modes when the signal is clearly
# non-technical and non-authoritative.
_GOVERNED_LIGHT_THRESHOLD = 0.85

FrontdoorRoute = Literal[
    "CONVERSATION",
    "EXPLORATION",
    "GOVERNED",
]

# Rückwärtskompatibilität: Alte Route-Namen auf neue Namen mappen.
# Externe Konsumenten die noch die alten Strings prüfen können dieses Dict nutzen.
ROUTE_ALIASES: dict[str, FrontdoorRoute] = {
    "instant_light_reply": "CONVERSATION",
    "light_exploration": "EXPLORATION",
    "governed_needed": "GOVERNED",
}


def _get_gate_system_prompt() -> str:
    """Gate-System-Prompt aus Jinja2-Template laden (via PromptRegistry)."""
    from app.agent.prompts import prompts  # lazy import — vermeidet zirkulaere Abhaengigkeiten
    return prompts.render("gate/gate_classify.j2", {})

# ---------------------------------------------------------------------------
# Hard-override patterns (→ GOVERNED immediately, no LLM needed)
# ---------------------------------------------------------------------------

# Numeric values with technical units
_NUMERIC_UNIT_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|psi|°?\s*[cCfF]|rpm|u\.?/?min|kN|MPa|kPa|Hz|N/mm)\b",
    re.IGNORECASE | re.UNICODE,
)
_DIAMETER_PATTERN = re.compile(
    r"[ØøΦ]\s*\d+(?:[.,]\d+)?",
    re.IGNORECASE | re.UNICODE,
)

# Calculation requests
_CALCULATION_PATTERN = re.compile(
    r"\b(berechne|berechnen|berechnung|RWDR|Drehzahl|Grenzgeschwindigkeit"
    r"|Flächenpressung|Vmax|calc|calculate)\b",
    re.IGNORECASE | re.UNICODE,
)

# Manufacturer / supplier matching triggers
_MATCHING_PATTERN = re.compile(
    r"\b(Hersteller|wer\s+liefert|Anbieter|Lieferant|wer\s+stellt\s+her"
    r"|welche\s+Firmen|Bezugsquell\w*)\b",
    re.IGNORECASE | re.UNICODE,
)

# RFQ / order triggers
_RFQ_PATTERN = re.compile(
    r"\b(Anfrage|Angebot|bestellen|Bestellung|Anforderung\s+stellen"
    r"|RFQ|Request\s+for\s+Quotation|Kostenvoranschlag)\b",
    re.IGNORECASE | re.UNICODE,
)

_RECOMMENDATION_PATTERN = re.compile(
    r"\b(empfehl\w*|welches\s+material|welche\s+dichtung|was\s+soll(?:en)?\s+wir\s+nehmen"
    r"|was\s+passt|was\s+ist\s+besser|welche\s+loesung|welche\s+lösung)\b",
    re.IGNORECASE | re.UNICODE,
)

_CORRECTION_PATTERN = re.compile(
    r"\b(korrigier\w*|korrektur|das\s+stimmt\s+nicht|nicht\s+sondern|stattdessen|falsch\b|gemeint\s+war)\b",
    re.IGNORECASE | re.UNICODE,
)

_AMBIGUITY_PATTERN = re.compile(
    r"\b(widerspruch|widerspruech\w*|widersprüch\w*|mehrdeutig|ambig\w*|entweder|oder\s+doch)\b",
    re.IGNORECASE | re.UNICODE,
)

_GREETING_PATTERN = re.compile(
    r"^\s*(hallo|hi|hey|guten\s+tag|guten\s+morgen|moin|servus|gruess\s+gott|grüß\s+gott)\b[\s!,.?]*$",
    re.IGNORECASE | re.UNICODE,
)

_SMALLTALK_PATTERN = re.compile(
    r"\b(wie\s+geht'?s|wie\s+geht\s+es(?:\s+dir)?(?:\s+heute)?|danke\b|vielen\s+dank|alles\s+gut|schoenen?\s+tag|schönen?\s+tag)\b",
    re.IGNORECASE | re.UNICODE,
)

_META_PROCESS_PATTERN = re.compile(
    r"\b(wie\s+laeuft\s+das|wie\s+läuft\s+das|wie\s+funktioniert\s+das|wie\s+gehen\s+wir\s+vor"
    r"|wie\s+gehen\s+wir\s+dabei\s+vor"
     r"|was\s+brauchst\s+du\s+von\s+mir|welche\s+infos\s+brauchst\s+du|was\s+ist\s+der\s+naechste\s+schritt"
     r"|was\s+ist\s+der\s+nächste\s+schritt|erklaer\s+mir\s+den\s+ablauf|erklär\s+mir\s+den\s+ablauf)\b",
    re.IGNORECASE | re.UNICODE,
)

_ORIENTATION_PATTERN = re.compile(
    r"^\s*(was\s+ist|was\s+bedeutet|wie\s+funktioniert|erklaer\w*|erklär\w*|wofuer|wofür|wann\s+nimmt\s+man)\b",
    re.IGNORECASE | re.UNICODE,
)

_OPEN_GOAL_PATTERN = re.compile(
    r"\b(moechte|möchte|will|wir\s+suchen|suche|brauche|benoetige|benötige|benoetigen|benötigen|hilfe|unterstuetzung|unterstützung|ersatz|bestandsfall|neuauslegung)\b",
    re.IGNORECASE | re.UNICODE,
)

_PROBLEM_PATTERN = re.compile(
    r"\b(problem\w*|leck\w*|leckage\w*|undicht\w*|ausfall\w*|stoer\w*|stör\w*|schaden\w*|fehler\w*)\b",
    re.IGNORECASE | re.UNICODE,
)

_UNCERTAINTY_PATTERN = re.compile(
    r"\b(unsicher|unklar|weiss\s+nicht|weiß\s+nicht|nicht\s+sicher|offen)\b",
    re.IGNORECASE | re.UNICODE,
)

_HARD_OVERRIDE_CHECKS: list[tuple[str, re.Pattern[str]]] = [
    ("numeric_unit", _NUMERIC_UNIT_PATTERN),
    ("diameter", _DIAMETER_PATTERN),
    ("calculation", _CALCULATION_PATTERN),
    ("matching", _MATCHING_PATTERN),
    ("rfq", _RFQ_PATTERN),
    ("recommendation", _RECOMMENDATION_PATTERN),
    ("correction", _CORRECTION_PATTERN),
    ("ambiguity", _AMBIGUITY_PATTERN),
]


@dataclass(frozen=True)
class HardOverrideMatch:
    trigger: str  # e.g. "numeric_unit", "calculation"


def check_hard_overrides(message: str) -> HardOverrideMatch | None:
    """Deterministic check for signals that force GOVERNED routing.

    Returns None if no hard override matches.
    No LLM, no I/O — pure regex.
    """
    for trigger, pattern in _HARD_OVERRIDE_CHECKS:
        if pattern.search(message):
            return HardOverrideMatch(trigger=trigger)
    return None


# ---------------------------------------------------------------------------
# Session protocol (F-A.2 will provide the concrete SessionEnvelope)
# ---------------------------------------------------------------------------

@runtime_checkable
class HasSessionZone(Protocol):
    """Minimal protocol expected from a session object by the gate."""
    session_zone: str  # "conversation" | "governed"


# ---------------------------------------------------------------------------
# LLM classification result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMGateResult:
    routing: FrontdoorRoute
    confidence: float
    parse_error: bool = False
    timeout: bool = False


# ---------------------------------------------------------------------------
# Gate decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateDecision:
    route: FrontdoorRoute
    reason: str


# ---------------------------------------------------------------------------
# LLM call (sync + async)
# ---------------------------------------------------------------------------

def _call_gate_llm(message: str) -> LLMGateResult:
    """Synchronous mini-LLM call for binary gate classification.

    Kept for tests and CLI usage. Production callers use _call_gate_llm_async.
    Raises on network/timeout to let decide_route handle the fallback.
    """
    import openai  # lazy import

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model=_GATE_MODEL,
        messages=[
            {"role": "system", "content": _get_gate_system_prompt()},
            {"role": "user", "content": message},
        ],
        max_tokens=32,
        temperature=0,
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        payload = json.loads(raw)
        routing = payload.get("routing", "")
        confidence = float(payload.get("confidence", 0.0))
        if routing not in ("CONVERSATION", "EXPLORATION", "GOVERNED"):
            raise ValueError(f"Unexpected routing value: {routing!r}")
        return LLMGateResult(
            routing=routing,  # type: ignore[arg-type]
            confidence=confidence,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("[gate] LLM parse error (%s: %s) raw=%r", type(exc).__name__, exc, raw)
        return LLMGateResult(routing="GOVERNED", confidence=0.0, parse_error=True)


async def _call_gate_llm_async(message: str) -> LLMGateResult:
    """Async mini-LLM call — does not block the event loop."""
    import openai  # lazy import

    client = openai.AsyncOpenAI()
    response = await client.chat.completions.create(
        model=_GATE_MODEL,
        messages=[
            {"role": "system", "content": _get_gate_system_prompt()},
            {"role": "user", "content": message},
        ],
        max_tokens=32,
        temperature=0,
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        payload = json.loads(raw)
        routing = payload.get("routing", "")
        confidence = float(payload.get("confidence", 0.0))
        if routing not in ("CONVERSATION", "EXPLORATION", "GOVERNED"):
            raise ValueError(f"Unexpected routing value: {routing!r}")
        return LLMGateResult(
            routing=routing,  # type: ignore[arg-type]
            confidence=confidence,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("[gate] LLM parse error (%s: %s) raw=%r", type(exc).__name__, exc, raw)
        return LLMGateResult(routing="GOVERNED", confidence=0.0, parse_error=True)


def classify_light_route(message: str) -> GateDecision | None:
    """Deterministic classification for the two light frontdoor modes."""
    text = str(message or "").strip()
    if not text:
        return None
    if _GREETING_PATTERN.match(text) or _SMALLTALK_PATTERN.search(text):
        return GateDecision(route="CONVERSATION", reason="deterministic_instant:greeting_or_smalltalk")
    if _META_PROCESS_PATTERN.search(text) or _ORIENTATION_PATTERN.search(text):
        return GateDecision(route="CONVERSATION", reason="deterministic_instant:meta_or_orientation")
    if _OPEN_GOAL_PATTERN.search(text) or _PROBLEM_PATTERN.search(text) or _UNCERTAINTY_PATTERN.search(text):
        return GateDecision(route="EXPLORATION", reason="deterministic_light:goal_problem_or_uncertainty")
    return None


# ---------------------------------------------------------------------------
# Core routing logic (shared between sync and async)
# ---------------------------------------------------------------------------

def _apply_llm_result(result: LLMGateResult, message: str) -> GateDecision:
    """Translate an LLMGateResult into a GateDecision.

    Handles timeout and low-confidence fallback logic.
    """
    if result.parse_error:
        return GateDecision(route="GOVERNED", reason="json_parse_fallback")

    if result.timeout:
        deterministic = check_hard_overrides(message)
        if deterministic:
            return GateDecision(
                route="GOVERNED",
                reason=f"timeout_with_deterministic_signal:{deterministic.trigger}",
            )
        return GateDecision(route="GOVERNED", reason="timeout_fallback_to_governed")

    if result.confidence < _CONFIDENCE_THRESHOLD:
        return GateDecision(route="GOVERNED", reason="low_confidence_fallback")

    return GateDecision(
        route=result.routing,
        reason="llm_frontdoor_classification",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decide_route(message: str, session: HasSessionZone) -> GateDecision:
    """Synchronous 3-mode frontdoor decision.

    Args:
        message: Raw user message text.
        session: Any object with a ``session_zone`` attribute
                 ("conversation" | "governed"). The concrete
                 ``SessionEnvelope`` from F-A.2 satisfies this protocol.

    Returns:
        GateDecision with one of the 3 v1.2 frontdoor modes and a reason string.

    Fail-safe: any uncertainty falls back to GOVERNED.

    Governed-session behaviour:
      The session zone remains governed. Only clearly non-technical light turns
      may use a light reply mode; everything uncertain stays GOVERNED.
    """
    # 1. Governed session
    if session.session_zone == "governed":
        hard = check_hard_overrides(message)
        if hard:
            return GateDecision(route="GOVERNED", reason=f"hard_override:{hard.trigger}")
        instant = classify_light_route(message)
        if instant is not None and instant.route == "CONVERSATION":
            return GateDecision(route="CONVERSATION", reason="governed_instant_override")
        try:
            result = _call_gate_llm(message)
        except Exception as exc:
            log.warning(
                "[gate] LLM call failed in governed session (%s: %s) — staying governed",
                type(exc).__name__,
                exc,
            )
            return GateDecision(route="GOVERNED", reason="sticky_governed_session")
        if (
            not result.parse_error
            and not result.timeout
            and result.routing != "GOVERNED"
            and result.confidence >= _GOVERNED_LIGHT_THRESHOLD
        ):
            return GateDecision(route=result.routing, reason="governed_light_override")
        return GateDecision(route="GOVERNED", reason="sticky_governed_session")

    # 2. Deterministic hard overrides (fresh session)
    hard = check_hard_overrides(message)
    if hard:
        return GateDecision(route="GOVERNED", reason=f"hard_override:{hard.trigger}")

    # 3. Deterministic light routing
    light = classify_light_route(message)
    if light is not None:
        return light

    # 4. Mini-LLM classification
    try:
        result = _call_gate_llm(message)
    except Exception as exc:
        log.warning(
            "[gate] LLM call failed (%s: %s) — checking deterministic fallback",
            type(exc).__name__,
            exc,
        )
        deterministic = check_hard_overrides(message)
        if deterministic:
            return GateDecision(
                route="GOVERNED",
                reason=f"timeout_with_deterministic_signal:{deterministic.trigger}",
            )
        return GateDecision(route="GOVERNED", reason="timeout_fallback_to_governed")

    return _apply_llm_result(result, message)


async def decide_route_async(message: str, session: HasSessionZone) -> GateDecision:
    """Async 3-mode frontdoor decision — does not block the event loop.

    Identical logic to decide_route but uses _call_gate_llm_async.
    Use this from async FastAPI endpoints.
    """
    # 1. Governed session (mirrors decide_route exactly)
    if session.session_zone == "governed":
        hard = check_hard_overrides(message)
        if hard:
            return GateDecision(route="GOVERNED", reason=f"hard_override:{hard.trigger}")
        instant = classify_light_route(message)
        if instant is not None and instant.route == "CONVERSATION":
            return GateDecision(route="CONVERSATION", reason="governed_instant_override")
        try:
            result = await _call_gate_llm_async(message)
        except Exception as exc:
            log.warning(
                "[gate] LLM call failed in governed session (%s: %s) — staying governed",
                type(exc).__name__,
                exc,
            )
            return GateDecision(route="GOVERNED", reason="sticky_governed_session")
        if (
            not result.parse_error
            and not result.timeout
            and result.routing != "GOVERNED"
            and result.confidence >= _GOVERNED_LIGHT_THRESHOLD
        ):
            return GateDecision(route=result.routing, reason="governed_light_override")
        return GateDecision(route="GOVERNED", reason="sticky_governed_session")

    # 2. Deterministic hard overrides (fresh session)
    hard = check_hard_overrides(message)
    if hard:
        return GateDecision(route="GOVERNED", reason=f"hard_override:{hard.trigger}")

    # 3. Deterministic light routing
    light = classify_light_route(message)
    if light is not None:
        return light

    # 4. Mini-LLM classification
    try:
        result = await _call_gate_llm_async(message)
    except Exception as exc:
        log.warning(
            "[gate] LLM call failed (%s: %s) — checking deterministic fallback",
            type(exc).__name__,
            exc,
        )
        deterministic = check_hard_overrides(message)
        if deterministic:
            return GateDecision(
                route="GOVERNED",
                reason=f"timeout_with_deterministic_signal:{deterministic.trigger}",
            )
        return GateDecision(route="GOVERNED", reason="timeout_fallback_to_governed")

    return _apply_llm_result(result, message)
