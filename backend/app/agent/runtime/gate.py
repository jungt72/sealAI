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
import time
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metrics (optional — gate works without Prometheus)
# ---------------------------------------------------------------------------

def _observe_gate_decision(decision: "GateDecision", started_at: float) -> "GateDecision":
    """Record gate decision metrics and return the decision unchanged.

    Instruments Prometheus counters when available; silently skips otherwise.
    Called by decide_route and decide_route_async after every routing decision.
    """
    latency = time.monotonic() - started_at
    try:
        from app.observability.metrics import track_gate_decision_reason, track_gate_direct_reply, track_gate_route_decision  # noqa: PLC0415
        track_gate_route_decision(decision.route, latency)
        track_gate_decision_reason(_metric_reason_category(decision.reason))
        if decision.allow_direct_reply:
            track_gate_direct_reply(decision.route)
    except Exception:  # metrics unavailable (tests, offline) — fail-open
        pass
    log.debug("[gate] route=%s reason=%s latency_ms=%.1f", decision.route, decision.reason, latency * 1000)
    return decision

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_GATE_MODEL = os.environ.get("SEALAI_GATE_MODEL", "gpt-4o-mini")
_ENABLE_GATE_DIRECT_REPLY = os.environ.get("SEALAI_ENABLE_GATE_DIRECT_REPLY", "false").lower() == "true"
_CONFIDENCE_THRESHOLD = 0.75
# Stricter threshold for non-governed override while the session is already
# sticky-governed. We only allow the light modes when the signal is clearly
# non-technical and non-authoritative.
_GOVERNED_LIGHT_THRESHOLD = 0.85
_DIRECT_REPLY_CONFIDENCE_THRESHOLD = 0.90
_GATE_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "route": {
            "type": "string",
            "enum": ["CONVERSATION", "EXPLORATION", "GOVERNED"],
        },
        "confidence": {
            "type": "number",
        },
        "allow_direct_reply": {
            "type": "boolean",
        },
        "reason_code": {
            "type": "string",
        },
        "direct_reply": {
            "type": ["string", "null"],
        },
    },
    "required": [
        "route",
        "confidence",
        "allow_direct_reply",
        "reason_code",
        "direct_reply",
    ],
}
_GATE_RESPONSE_FORMAT: dict[str, object] = {
    "type": "json_schema",
    "json_schema": {
        "name": "sealai_gate_decision",
        "strict": True,
        "schema": _GATE_JSON_SCHEMA,
    },
}

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


def _get_gate_system_prompt(
    *,
    current_zone: str,
    short_state_summary: str | None,
    missing_critical_fields: list[str] | None,
    case_active: bool,
    last_route: str | None,
) -> str:
    """Gate-System-Prompt aus Jinja2-Template laden (via PromptRegistry)."""
    from app.agent.prompts import prompts  # lazy import — vermeidet zirkulaere Abhaengigkeiten
    return prompts.render(
        "gate/gate_classify.j2",
        {
            "current_zone": current_zone,
            "short_state_summary": str(short_state_summary or "").strip() or None,
            "missing_critical_fields": list(missing_critical_fields or []),
            "case_active": bool(case_active),
            "last_route": str(last_route or "").strip() or None,
        },
    )


class GateLLMContract(BaseModel):
    route: FrontdoorRoute
    confidence: float = Field(ge=0.0, le=1.0)
    allow_direct_reply: bool
    reason_code: str
    direct_reply: str | None

    model_config = {"extra": "forbid"}

    @field_validator("reason_code")
    @classmethod
    def _validate_reason_code(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("direct_reply")
    @classmethod
    def _validate_direct_reply(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value or "").strip()
        return text or None

# ---------------------------------------------------------------------------
# Hard-override patterns (→ GOVERNED immediately, no LLM needed)
# ---------------------------------------------------------------------------

# Numeric values with technical units
_NUMERIC_UNIT_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|psi|grad|°?\s*[cCfF]|rpm|u\.?/?min|kN|MPa|kPa|Hz|N/mm)\b",
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
    r"\b(empfehl\w*|welche\s+dichtung|was\s+soll(?:en)?\s+wir\s+nehmen"
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
    r"|was\s+ist\s+der\s+nächste\s+schritt|erklaer\s+mir\s+den\s+ablauf|erklär\s+mir\s+den\s+ablauf"
    r"|was\s+fehlt(\s+noch)?|welche\s+(angaben|parameter|daten)\s+fehlen"
    r"|was\s+(hast\s+du|haben\s+sie)\s+(schon\s+)?(verstanden|erfasst|gespeichert)"
    r"|wie\s+ist\s+der\s+(aktuelle\s+)?(stand|fortschritt))\b",
    re.IGNORECASE | re.UNICODE,
)

_ORIENTATION_PATTERN = re.compile(
    r"^\s*(was\s+ist|was\s+bedeutet|wie\s+funktioniert|erklaer\w*|erklär\w*|wofuer|wofür|wann\s+nimmt\s+man)\b",
    re.IGNORECASE | re.UNICODE,
)

_EXPLORATION_KNOWLEDGE_PATTERN = re.compile(
    r"^\s*(was\s+ist\s+ein\s+o-?ring|was\s+bedeutet\s+api\s*682|was\s+ist\s+der\s+unterschied\s+zwischen"
    r"|welches\s+material\s+ist\s+f(?:ue|ü)r|welche\s+dichtungstypen\s+gibt\s+es"
    r"|welche\s+materialien?\s+(?:eignen?\s+sich|sind\s+geeignet|kommen\s+infrage|empfehlen\s+sich)"
    r"|welche\s+werkstoffe?\s+(?:eignen?\s+sich|sind\s+geeignet|kommen\s+infrage)"
    r"|welche\s+normen?\s+(?:gilt|gelten|ist\s+relevant)"
    r"|wie\s+hoch\s+(?:ist|darf)\s+(?:der|die)\s+(?:p|pv|druck|temperatur)"
    r")\b",
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

_CONVERSATION_FAST_PATH_PATTERN = re.compile(
    r"\b(hallo|hi|hey|guten\s+tag|moin|servus|danke|vielen\s+dank|alles\s+gut|ok\b|okay\b|verstehe|macht\s+sinn)\b",
    re.IGNORECASE | re.UNICODE,
)

_FAST_PATH_TECHNICAL_BLOCK_PATTERN = re.compile(
    r"\d|\b(grad|bar|mm|rpm|u/min|welle|pumpe|medium|oel|öl|salzwasser|dampf|chem\w*)\b",
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
    route: FrontdoorRoute
    confidence: float
    parse_error: bool = False
    timeout: bool = False
    allow_direct_reply: bool = False
    direct_reply: str | None = None
    reason_code: str = ""


# ---------------------------------------------------------------------------
# Gate decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateDecision:
    route: FrontdoorRoute
    reason: str
    confidence: float | None = None
    allow_direct_reply: bool = False
    direct_reply: str | None = None
    reason_code: str = ""


def _metric_reason_category(reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        return "unknown"
    for prefix in (
        "hard_override",
        "json_parse_fallback",
        "low_confidence_fallback",
        "timeout_with_deterministic_signal",
        "timeout_fallback_to_governed",
        "sticky_governed_session",
        "governed_light_override",
        "governed_instant_override",
        "deterministic_instant",
        "deterministic_light",
        "llm_frontdoor_classification",
    ):
        if text == prefix or text.startswith(f"{prefix}:"):
            return prefix
    return "other"


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
    system_prompt = _get_gate_system_prompt(
        current_zone="conversation",
        short_state_summary=None,
        missing_critical_fields=None,
        case_active=False,
        last_route=None,
    )
    response = client.chat.completions.create(
        model=_GATE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        response_format=_GATE_RESPONSE_FORMAT,
        max_completion_tokens=220,
        temperature=0,
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        payload = GateLLMContract.model_validate_json(raw or "{}")
        return LLMGateResult(
            route=payload.route,
            confidence=float(payload.confidence),
            allow_direct_reply=bool(payload.allow_direct_reply and payload.direct_reply),
            direct_reply=payload.direct_reply,
            reason_code=payload.reason_code,
        )
    except (ValidationError, json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("[gate] LLM parse error (%s: %s) raw=%r", type(exc).__name__, exc, raw)
        return LLMGateResult(route="GOVERNED", confidence=0.0, parse_error=True)


async def _call_gate_llm_async(
    message: str,
    *,
    current_zone: str = "conversation",
    short_state_summary: str | None = None,
    missing_critical_fields: list[str] | None = None,
    case_active: bool = False,
    last_route: str | None = None,
) -> LLMGateResult:
    """Async mini-LLM call — does not block the event loop."""
    import openai  # lazy import

    client = openai.AsyncOpenAI()
    system_prompt = _get_gate_system_prompt(
        current_zone=current_zone,
        short_state_summary=short_state_summary,
        missing_critical_fields=missing_critical_fields,
        case_active=case_active,
        last_route=last_route,
    )
    response = await client.chat.completions.create(
        model=_GATE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        response_format=_GATE_RESPONSE_FORMAT,
        max_completion_tokens=220,
        temperature=0,
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        payload = GateLLMContract.model_validate_json(raw or "{}")
        return LLMGateResult(
            route=payload.route,
            confidence=float(payload.confidence),
            allow_direct_reply=bool(payload.allow_direct_reply and payload.direct_reply),
            direct_reply=payload.direct_reply,
            reason_code=payload.reason_code,
        )
    except (ValidationError, json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("[gate] LLM parse error (%s: %s) raw=%r", type(exc).__name__, exc, raw)
        return LLMGateResult(route="GOVERNED", confidence=0.0, parse_error=True)


def classify_light_route(message: str) -> GateDecision | None:
    """Deterministic classification for the two light frontdoor modes."""
    text = str(message or "").strip()
    if not text:
        return None
    if _GREETING_PATTERN.match(text) or _SMALLTALK_PATTERN.search(text):
        return GateDecision(route="CONVERSATION", reason="deterministic_instant:greeting_or_smalltalk")
    if _EXPLORATION_KNOWLEDGE_PATTERN.search(text):
        return GateDecision(route="EXPLORATION", reason="deterministic_light:technical_explainer")
    if _META_PROCESS_PATTERN.search(text) or _ORIENTATION_PATTERN.search(text):
        return GateDecision(route="CONVERSATION", reason="deterministic_instant:meta_or_orientation")
    if _OPEN_GOAL_PATTERN.search(text) or _PROBLEM_PATTERN.search(text) or _UNCERTAINTY_PATTERN.search(text):
        return GateDecision(route="EXPLORATION", reason="deterministic_light:goal_problem_or_uncertainty")
    return None


# ---------------------------------------------------------------------------
# Core routing logic (shared between sync and async)
# ---------------------------------------------------------------------------

def _direct_reply_eligible(
    *,
    message: str,
    session_zone: str,
    result: LLMGateResult,
) -> bool:
    if result.route != "CONVERSATION":
        return False
    if result.confidence < _DIRECT_REPLY_CONFIDENCE_THRESHOLD:
        return False
    if not result.allow_direct_reply or not str(result.direct_reply or "").strip():
        return False
    if check_hard_overrides(message) is not None:
        return False
    deterministic_light = classify_light_route(message)
    if deterministic_light is None or deterministic_light.route != "CONVERSATION":
        return False
    if not _CONVERSATION_FAST_PATH_PATTERN.search(message):
        return False
    if _FAST_PATH_TECHNICAL_BLOCK_PATTERN.search(message):
        return False
    if session_zone == "governed" and result.confidence < _GOVERNED_LIGHT_THRESHOLD:
        return False
    return True


def _apply_llm_result(
    result: LLMGateResult,
    message: str,
    *,
    session_zone: str = "conversation",
) -> GateDecision:
    """Translate an LLMGateResult into a GateDecision.

    Handles timeout and low-confidence fallback logic.
    """
    if result.parse_error:
        return GateDecision(route="GOVERNED", reason="json_parse_fallback", confidence=0.0)

    if result.timeout:
        deterministic = check_hard_overrides(message)
        if deterministic:
            return GateDecision(
                route="GOVERNED",
                reason=f"timeout_with_deterministic_signal:{deterministic.trigger}",
                confidence=0.0,
            )
        return GateDecision(route="GOVERNED", reason="timeout_fallback_to_governed", confidence=0.0)

    if result.confidence < _CONFIDENCE_THRESHOLD:
        return GateDecision(
            route="GOVERNED",
            reason="low_confidence_fallback",
            confidence=result.confidence,
            reason_code=result.reason_code,
        )

    direct_reply = result.direct_reply if _direct_reply_eligible(message=message, session_zone=session_zone, result=result) else None
    reason = "llm_frontdoor_classification"
    if result.reason_code:
        reason = f"{reason}:{result.reason_code}"
    return GateDecision(
        route=result.route,
        reason=reason,
        confidence=result.confidence,
        allow_direct_reply=direct_reply is not None,
        direct_reply=direct_reply,
        reason_code=result.reason_code,
    )


def _maybe_enrich_conversation_with_direct_reply(
    *,
    message: str,
    session_zone: str,
    fallback: GateDecision,
) -> GateDecision:
    if not _ENABLE_GATE_DIRECT_REPLY:
        return fallback
    try:
        result = _call_gate_llm(message)
    except Exception:
        return fallback
    enriched = _apply_llm_result(result, message, session_zone=session_zone)
    if enriched.route == "CONVERSATION" and enriched.allow_direct_reply and enriched.direct_reply:
        return enriched
    return fallback


async def _maybe_enrich_conversation_with_direct_reply_async(
    *,
    message: str,
    session_zone: str,
    fallback: GateDecision,
    short_state_summary: str | None = None,
    missing_critical_fields: list[str] | None = None,
    case_active: bool = False,
    last_route: str | None = None,
) -> GateDecision:
    if not _ENABLE_GATE_DIRECT_REPLY:
        return fallback
    try:
        result = await _call_gate_llm_async(
            message,
            current_zone=session_zone,
            short_state_summary=short_state_summary,
            missing_critical_fields=missing_critical_fields,
            case_active=case_active,
            last_route=last_route,
        )
    except Exception:
        return fallback
    enriched = _apply_llm_result(result, message, session_zone=session_zone)
    if enriched.route == "CONVERSATION" and enriched.allow_direct_reply and enriched.direct_reply:
        return enriched
    return fallback


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
    started_at = time.monotonic()

    # 1. Governed session
    if session.session_zone == "governed":
        hard = check_hard_overrides(message)
        if hard:
            return _observe_gate_decision(GateDecision(route="GOVERNED", reason=f"hard_override:{hard.trigger}"), started_at)
        instant = classify_light_route(message)
        if instant is not None and instant.route == "CONVERSATION":
            return _observe_gate_decision(
                _maybe_enrich_conversation_with_direct_reply(
                    message=message,
                    session_zone="governed",
                    fallback=GateDecision(route="CONVERSATION", reason="governed_instant_override"),
                ),
                started_at,
            )
        try:
            result = _call_gate_llm(message)
        except Exception as exc:
            log.warning(
                "[gate] LLM call failed in governed session (%s: %s) — staying governed",
                type(exc).__name__,
                exc,
            )
            return _observe_gate_decision(GateDecision(route="GOVERNED", reason="sticky_governed_session"), started_at)
        if not result.parse_error and not result.timeout and result.route != "GOVERNED" and result.confidence >= _GOVERNED_LIGHT_THRESHOLD:
            decision = _apply_llm_result(result, message, session_zone="governed")
            return _observe_gate_decision(
                GateDecision(
                    route=decision.route,
                    reason="governed_light_override",
                    confidence=decision.confidence,
                    allow_direct_reply=decision.allow_direct_reply,
                    direct_reply=decision.direct_reply,
                    reason_code=decision.reason_code,
                ),
                started_at,
            )
        return _observe_gate_decision(GateDecision(route="GOVERNED", reason="sticky_governed_session"), started_at)

    # 2. Deterministic hard overrides (fresh session)
    hard = check_hard_overrides(message)
    if hard:
        return _observe_gate_decision(GateDecision(route="GOVERNED", reason=f"hard_override:{hard.trigger}"), started_at)

    # 3. Deterministic light routing
    light = classify_light_route(message)
    if light is not None:
        if light.route == "CONVERSATION":
            light = _maybe_enrich_conversation_with_direct_reply(
                message=message,
                session_zone="conversation",
                fallback=light,
            )
        return _observe_gate_decision(light, started_at)

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
            return _observe_gate_decision(
                GateDecision(route="GOVERNED", reason=f"timeout_with_deterministic_signal:{deterministic.trigger}"),
                started_at,
            )
        return _observe_gate_decision(GateDecision(route="GOVERNED", reason="timeout_fallback_to_governed"), started_at)

    return _observe_gate_decision(_apply_llm_result(result, message, session_zone="conversation"), started_at)


async def decide_route_async(
    message: str,
    session: HasSessionZone,
    *,
    short_state_summary: str | None = None,
    missing_critical_fields: list[str] | None = None,
    case_active: bool = False,
    last_route: str | None = None,
) -> GateDecision:
    """Async 3-mode frontdoor decision — does not block the event loop.

    Identical logic to decide_route but uses _call_gate_llm_async.
    Use this from async FastAPI endpoints.
    """
    started_at = time.monotonic()

    # 1. Governed session (mirrors decide_route exactly)
    if session.session_zone == "governed":
        hard = check_hard_overrides(message)
        if hard:
            return _observe_gate_decision(GateDecision(route="GOVERNED", reason=f"hard_override:{hard.trigger}"), started_at)
        instant = classify_light_route(message)
        if instant is not None and instant.route == "CONVERSATION":
            return _observe_gate_decision(
                await _maybe_enrich_conversation_with_direct_reply_async(
                    message=message,
                    session_zone="governed",
                    fallback=GateDecision(route="CONVERSATION", reason="governed_instant_override"),
                    short_state_summary=short_state_summary,
                    missing_critical_fields=missing_critical_fields,
                    case_active=case_active,
                    last_route=last_route,
                ),
                started_at,
            )
        try:
            result = await _call_gate_llm_async(
                message,
                current_zone="governed",
                short_state_summary=short_state_summary,
                missing_critical_fields=missing_critical_fields,
                case_active=case_active,
                last_route=last_route,
            )
        except Exception as exc:
            log.warning(
                "[gate] LLM call failed in governed session (%s: %s) — staying governed",
                type(exc).__name__,
                exc,
            )
            return _observe_gate_decision(GateDecision(route="GOVERNED", reason="sticky_governed_session"), started_at)
        if not result.parse_error and not result.timeout and result.route != "GOVERNED" and result.confidence >= _GOVERNED_LIGHT_THRESHOLD:
            decision = _apply_llm_result(result, message, session_zone="governed")
            return _observe_gate_decision(
                GateDecision(
                    route=decision.route,
                    reason="governed_light_override",
                    confidence=decision.confidence,
                    allow_direct_reply=decision.allow_direct_reply,
                    direct_reply=decision.direct_reply,
                    reason_code=decision.reason_code,
                ),
                started_at,
            )
        return _observe_gate_decision(GateDecision(route="GOVERNED", reason="sticky_governed_session"), started_at)

    # 2. Deterministic hard overrides (fresh session)
    hard = check_hard_overrides(message)
    if hard:
        return _observe_gate_decision(GateDecision(route="GOVERNED", reason=f"hard_override:{hard.trigger}"), started_at)

    # 3. Deterministic light routing
    light = classify_light_route(message)
    if light is not None:
        if light.route == "CONVERSATION":
            light = await _maybe_enrich_conversation_with_direct_reply_async(
                message=message,
                session_zone="conversation",
                fallback=light,
                short_state_summary=short_state_summary,
                missing_critical_fields=missing_critical_fields,
                case_active=case_active,
                last_route=last_route,
            )
        return _observe_gate_decision(light, started_at)

    # 4. Mini-LLM classification
    try:
        result = await _call_gate_llm_async(
            message,
            current_zone="conversation",
            short_state_summary=short_state_summary,
            missing_critical_fields=missing_critical_fields,
            case_active=case_active,
            last_route=last_route,
        )
    except Exception as exc:
        log.warning(
            "[gate] LLM call failed (%s: %s) — checking deterministic fallback",
            type(exc).__name__,
            exc,
        )
        deterministic = check_hard_overrides(message)
        if deterministic:
            return _observe_gate_decision(
                GateDecision(route="GOVERNED", reason=f"timeout_with_deterministic_signal:{deterministic.trigger}"),
                started_at,
            )
        return _observe_gate_decision(GateDecision(route="GOVERNED", reason="timeout_fallback_to_governed"), started_at)

    return _observe_gate_decision(
        _apply_llm_result(result, message, session_zone="conversation"),
        started_at,
    )
