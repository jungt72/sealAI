"""
Interaction Policy V2 — DEPRECATED (W3.4)

Production routing is handled by app.agent.runtime.gate (decide_route / decide_route_async).
This module is kept only for test backward-compat. Do not call from production paths.

──────────────────────────────────────────────────────────────────────────────
Patch D — Deletion pre-conditions (as of 2026-04-12)

gate.py IS the production replacement: evaluate_policy → decide_route,
evaluate_policy_async → decide_route_async, InteractionPolicyDecision → GateDecision.

Deletion is BLOCKED by 4 test files that still import from this module:
  • test_interaction_policy.py       — patches _call_routing_llm; tests all 4 tiers
  • test_interaction_policy_0d.py    — imports module directly; tests deterministic tiers
  • test_graph_routing.py            — imports evaluate_policy, patches _call_routing_llm
  • test_working_profile_semantics.py — imports _missing_critical_params

Required migration before deletion:
  1. Rewrite test_interaction_policy.py + test_interaction_policy_0d.py to test
     gate.py APIs (decide_route / classify_light_route / check_hard_overrides).
  2. Update test_graph_routing.py to import from gate.py instead.
  3. Update test_working_profile_semantics.py — replace _missing_critical_params
     with the equivalent pattern from selection.py or gate.py.
  4. Remove the lazy shim in runtime.py (evaluate_interaction_policy).
  5. Delete agent/interaction_policy.py (re-export shim).
  6. Then delete this file.
──────────────────────────────────────────────────────────────────────────────

Original: Semantic Routing via Nano-LLM
Phase 0A.3 / 0D / 0D+

Four-tier deterministic pre-check runs BEFORE any LLM call:

  1. META check     → State-status questions ("Was fehlt?") → meta path (no LLM)
  2. BLOCK check    → Explicitly forbidden requests → blocked path (no LLM, safe refusal)
  3. GREETING check → Trivial smalltalk ("Hallo", "Danke") → greeting path (no LLM, no RAG)
  4. FAST capability check → Fast-path ineligible inputs are upgraded to structured

Then the Nano-LLM classifies remaining messages into "Fast" or "Structured".

Fail-safe: Any LLM error falls back to the Structured path.

Architecture rule (Umbauplan R1):
  - LLM provides the routing signal only for the narrow fast/structured split
  - All policy-critical decisions (meta, blocked, greeting, fast upgrade) are deterministic
  - The decision object is never produced by free LLM generation

Performance:
  - evaluate_policy_async() is the preferred entry point from async FastAPI endpoints
  - Uses openai.AsyncOpenAI for non-blocking routing LLM calls
  - evaluate_policy() (sync) is kept for tests and CLI usage
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from app.agent.runtime.policy import INTERACTION_POLICY_VERSION, InteractionPolicyDecision
from app.agent.runtime.selection import STRUCTURED_REQUIRED_CORE_PARAMS
from app.domain.pre_gate_classification import PreGateClassification
from app.services.output_classifier import OutputClass
from app.services.pre_gate_classifier import PreGateClassifier

log = logging.getLogger(__name__)
_PRE_GATE_CLASSIFIER = PreGateClassifier()

# ---------------------------------------------------------------------------
# Routing model configuration
# ---------------------------------------------------------------------------

_ROUTING_MODEL = os.environ.get("SEALAI_ROUTING_MODEL", "gpt-4o-mini")

_SYSTEM_PROMPT = (
    "Du bist der Türsteher (Router) für einen Dichtungs-Engineering-Agenten. "
    "Analysiere die Nachricht des Users. "
    "Antworte AUSSCHLIESSLICH mit JSON im Format: "
    '{\"route\": \"Structured\"} oder {\"route\": \"Fast\"}. '
    "- 'Structured': Der User nennt technische Parameter (z.B. '50 mm', '2 bar', "
    "'für Teig'), fordert eine Auslegung an oder reicht technische Daten nach. "
    "- 'Fast': Reiner Smalltalk ('Hallo', 'Danke', 'Wie gehts?'), allgemeine "
    "Begrüßungen oder reine Wissensfragen ohne Auslegungsbezug."
)


# ---------------------------------------------------------------------------
# Phase 0D: Deterministic pre-check patterns
# ---------------------------------------------------------------------------

# Inputs that must be BLOCKED — user explicitly requests what SealAI cannot provide
_INPUT_BLOCK_PATTERNS: tuple[str, ...] = (
    r"\bwelch\w*\s+hersteller\b",                              # "welchen/welchem/welche Hersteller"
    r"\bhersteller[- ]?empfehlung\b",                          # "Herstellerempfehlung"
    r"\b(empfiehl|empfehle)\s+mir\b",                          # "empfiehl mir"
    r"\bwas\s+empfiehlst\s+du\b",                              # "was empfiehlst du"
    r"\bwelche[rs]?\s+(werkstoff|material|dichtring)\s+soll\b", # "welches Material soll ich"
    r"\bwelche\s+dichtung\s+soll\b",                           # "welche Dichtung soll ich"
)

# Inputs where a Fast-LLM decision must be upgraded to Structured
# (technical specificity detected — fast path is not appropriate)
_FAST_PATH_FORCE_STRUCTURED_PATTERNS: tuple[str, ...] = (
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|psi|°?\s*[cCfF]|rpm|u\.?/?min)\b",  # numeric+unit
    r"\b(geeignet|eignet\s+sich|taugt\s+für)\b",               # suitability framing
    r"\b(PTFE|NBR|FKM|EPDM|HNBR|FFKM|SILIKON|VMQ)\b.*\b(für|bei|in)\b",  # material + context
)

# Inputs that are meta-queries about current session state
_META_QUERY_PATTERNS: tuple[str, ...] = (
    r"\b(was\s+fehlt\s+(noch|mir|dir)?|welche\s+(angaben|parameter|daten)\s+fehlen)\b",
    r"\b(wie\s+ist\s+der\s+(aktuelle\s+)?(stand|fortschritt))\b",
    r"\b(was\s+(hast\s+du|haben\s+sie)\s+(schon\s+)?(verstanden|erfasst|gespeichert))\b",
    r"\b(welche\s+(angaben|parameter)\s+(brauche|benötige)\s+ich\s+noch)\b",
    r"\bzeig\s+(mir\s+)?(den\s+)?(fortschritt|stand|übersicht|status)\b",
    r"\bwas\s+fehlt\b",
    r"\bwas\s+hast\s+du\s+(bisher|schon)\b",
)

# Trivial greetings / smalltalk — deterministic P0, no LLM, no RAG
_GREETING_PATTERNS: tuple[str, ...] = (
    r"^(hallo|hi|hey|moin|servus|grüß\s*(gott|dich)|guten\s*(morgen|tag|abend))[\s!.?,]*$",
    r"^(danke|vielen\s+dank|dankeschön|merci|thanks)[\s!.?,]*$",
    r"^(tschüss|auf\s+wiedersehen|bis\s+dann|ciao|bye)[\s!.?,]*$",
    r"^wie\s+geht('?s|\s+es\s+dir)[\s?!.]*$",
    r"^(wer\s+bist\s+du|was\s+bist\s+du|was\s+kannst\s+du)[\s?!.]*$",
)


def _check_input_blocked(user_input: str) -> Optional[str]:
    """Return a block reason string if the input explicitly requests forbidden content.

    Returns None if the input is not blocked.
    Deterministic — no LLM involved.
    """
    for pattern in _INPUT_BLOCK_PATTERNS:
        if re.search(pattern, user_input, re.IGNORECASE | re.UNICODE):
            return f"input_policy_block:{pattern}"
    return None


def _is_greeting(user_input: str) -> bool:
    """True when the input is trivial smalltalk / greeting.

    These are answered with a deterministic canned response — no LLM, no RAG.
    Deterministic — no LLM involved.
    """
    stripped = user_input.strip()
    for pattern in _GREETING_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE | re.UNICODE):
            return True
    return False


def _is_meta_query(user_input: str) -> bool:
    """True when the input is a state-status / progress question.

    These must be answered deterministically from session state — not by the LLM.
    Deterministic — no LLM involved.
    """
    for pattern in _META_QUERY_PATTERNS:
        if re.search(pattern, user_input, re.IGNORECASE | re.UNICODE):
            return True
    return False


def _fast_path_upgrade_to_structured(user_input: str) -> bool:
    """True when a Fast-LLM decision must be upgraded to Structured.

    Detects technical specificity that belongs in the structured pipeline
    regardless of what the nano-LLM decided.
    Deterministic — no LLM involved.
    """
    for pattern in _FAST_PATH_FORCE_STRUCTURED_PATTERNS:
        if re.search(pattern, user_input, re.IGNORECASE | re.UNICODE):
            return True
    return False


# ---------------------------------------------------------------------------
# Helper: current state signals
# ---------------------------------------------------------------------------

def _has_active_case(current_state: dict[str, Any] | None) -> bool:
    """True when the current state already has meaningful technical data."""
    if not current_state:
        return False
    asserted = ((current_state.get("sealing_state") or {}).get("asserted") or {})
    medium = (asserted.get("medium_profile") or {}).get("name")
    material = (asserted.get("machine_profile") or {}).get("material")
    oc = asserted.get("operating_conditions") or {}
    return bool(medium or material or oc.get("pressure") or oc.get("temperature"))


def _missing_critical_params(current_state: dict[str, Any] | None) -> tuple[str, ...]:
    """Return which STRUCTURED_REQUIRED_CORE_PARAMS are absent from asserted_state.

    Mirrors the canonical parameter list from selection.STRUCTURED_REQUIRED_CORE_PARAMS.
    Both lists must stay in sync — selection.py is the authoritative source.
    """
    if not current_state:
        return STRUCTURED_REQUIRED_CORE_PARAMS  # all missing
    asserted = ((current_state.get("sealing_state") or {}).get("asserted") or {})
    missing: list[str] = []
    if not (asserted.get("medium_profile") or {}).get("name"):
        missing.append("medium")
    oc = asserted.get("operating_conditions") or {}
    if not oc.get("pressure"):
        missing.append("pressure")
    if not oc.get("temperature"):
        missing.append("temperature")
    return tuple(missing)


# ---------------------------------------------------------------------------
# Core factory helpers  (return types MUST remain exactly as defined)
# ---------------------------------------------------------------------------

def _direct_answer(*, coverage: str = "in_scope") -> InteractionPolicyDecision:
    return InteractionPolicyDecision(
        output_class=OutputClass.CONVERSATIONAL_ANSWER,
        pre_gate_classification=PreGateClassification.KNOWLEDGE_QUERY,
        stream_mode="reply_only",
        interaction_class="DIRECT_ANSWER",
        runtime_path="FAST_DIRECT",
        binding_level="KNOWLEDGE",
        has_case_state=False,
        coverage_status=coverage,
        boundary_flags=("not_a_manufacturer_release",),
        required_fields=(),
    )


# _guided_recommendation() removed (Phase 0D): FAST_PATH now maps to
# conversational_answer until the remaining light runtime is migrated.


def _deterministic_result(
    *,
    missing: tuple[str, ...] = (),
) -> InteractionPolicyDecision:
    return InteractionPolicyDecision(
        output_class=OutputClass.STRUCTURED_CLARIFICATION
        if missing
        else OutputClass.GOVERNED_STATE_UPDATE,
        pre_gate_classification=PreGateClassification.DOMAIN_INQUIRY,
        stream_mode="structured_progress_stream",
        interaction_class="DETERMINISTIC_RESULT",
        runtime_path="STRUCTURED_DETERMINISTIC",
        binding_level="ORIENTATION",
        has_case_state=True,
        coverage_status="in_scope" if not missing else "partial",
        boundary_flags=("not_a_manufacturer_release",),
        required_fields=missing,
    )


# _qualified_case() removed (Phase 0D): structured routing remains a
# transitional gate path; final output-class selection lives in OutputClassifier.


def _meta_path() -> InteractionPolicyDecision:
    """State-status query — answered deterministically, no LLM."""
    return InteractionPolicyDecision(
        output_class=OutputClass.CONVERSATIONAL_ANSWER,
        pre_gate_classification=PreGateClassification.META_QUESTION,
        stream_mode="reply_only",
        interaction_class="META_STATUS",
        runtime_path="META_DETERMINISTIC",
        binding_level="KNOWLEDGE",
        has_case_state=False,
        coverage_status="in_scope",
        boundary_flags=("not_a_manufacturer_release",),
        required_fields=(),
    )


def _greeting_path() -> InteractionPolicyDecision:
    """Trivial greeting / smalltalk — deterministic response, no LLM, no RAG."""
    return InteractionPolicyDecision(
        output_class=OutputClass.CONVERSATIONAL_ANSWER,
        pre_gate_classification=PreGateClassification.GREETING,
        stream_mode="reply_only",
        interaction_class="GREETING",
        runtime_path="GREETING_DETERMINISTIC",
        binding_level="KNOWLEDGE",
        has_case_state=False,
        coverage_status="in_scope",
        boundary_flags=(),
        required_fields=(),
    )


def _blocked_path(*, reason: str) -> InteractionPolicyDecision:
    """Explicitly forbidden request — deterministic safe refusal, no LLM, no pipeline."""
    return InteractionPolicyDecision(
        output_class=OutputClass.CONVERSATIONAL_ANSWER,
        pre_gate_classification=PreGateClassification.BLOCKED,
        stream_mode="reply_only",
        interaction_class="BLOCKED",
        runtime_path="BLOCKED_POLICY",
        binding_level="BLOCKED",
        has_case_state=False,
        coverage_status="out_of_scope",
        boundary_flags=("policy_block", "not_a_manufacturer_release"),
        escalation_reason=reason,
        required_fields=(),
    )


# ---------------------------------------------------------------------------
# Semantic routing via Nano-LLM
# ---------------------------------------------------------------------------

def _call_routing_llm(user_input: str) -> str:
    """
    Call the routing LLM synchronously and return "Fast" or "Structured".

    Kept for backwards-compatibility (tests patch this name).
    Production callers should use _call_routing_llm_async().
    """
    import openai  # lazy import — keeps startup lean when routing is unused

    client = openai.OpenAI()  # picks up OPENAI_API_KEY from environment
    response = client.chat.completions.create(
        model=_ROUTING_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ],
        max_tokens=16,
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    payload = json.loads(raw.strip())
    route = payload.get("route", "")
    if route not in ("Fast", "Structured"):
        raise ValueError(f"Unexpected route value from LLM: {route!r}")
    return route


async def _call_routing_llm_async(user_input: str) -> str:
    """Non-blocking routing LLM call — does not block the event loop.

    Uses openai.AsyncOpenAI so FastAPI can serve other requests while waiting.
    """
    import openai  # lazy import

    client = openai.AsyncOpenAI()
    response = await client.chat.completions.create(
        model=_ROUTING_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ],
        max_tokens=16,
        temperature=0,
    )
    raw = response.choices[0].message.content or ""
    payload = json.loads(raw.strip())
    route = payload.get("route", "")
    if route not in ("Fast", "Structured"):
        raise ValueError(f"Unexpected route value from LLM: {route!r}")
    return route


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _evaluate_deterministic_tiers(
    user_input: str,
    current_state: dict[str, Any] | None = None,
) -> InteractionPolicyDecision | None:
    """Run all deterministic pre-checks (no LLM, no I/O).

    Returns a decision if a deterministic tier matches, else None.
    Shared by both sync and async evaluate_policy variants.
    """
    classification = _PRE_GATE_CLASSIFIER.classify(user_input).classification

    if classification is PreGateClassification.META_QUESTION or _is_meta_query(user_input):
        log.debug("Policy decision: META (state-status query)")
        return _meta_path()

    if classification is PreGateClassification.BLOCKED:
        block_reason = _check_input_blocked(user_input) or "pre_gate_blocked"
        log.info("Policy decision: BLOCKED (%s)", block_reason)
        return _blocked_path(reason=block_reason)

    if classification is PreGateClassification.GREETING:
        log.debug("Policy decision: GREETING (trivial smalltalk)")
        return _greeting_path()

    if classification is PreGateClassification.KNOWLEDGE_QUERY:
        log.debug("Policy decision: KNOWLEDGE_QUERY (pre-gate)")
        return _direct_answer()

    if classification is PreGateClassification.DOMAIN_INQUIRY:
        missing = _missing_critical_params(current_state)
        return _deterministic_result(missing=missing)

    return None


def _resolve_llm_route(
    route: str,
    user_input: str,
    current_state: dict[str, Any] | None,
) -> InteractionPolicyDecision:
    """Given an LLM route result ("Fast" / "Structured"), produce the decision."""
    if route == "Fast":
        if _fast_path_upgrade_to_structured(user_input):
            log.debug(
                "Policy decision: STRUCTURED (fast→structured upgrade: "
                "technical specificity detected)"
            )
            missing = _missing_critical_params(current_state)
            return _deterministic_result(missing=missing)
        log.debug("Policy decision: FAST (chit-chat / knowledge question)")
        return _direct_answer()

    log.debug("Policy decision: STRUCTURED (technical input / assessment)")
    missing = _missing_critical_params(current_state)
    return _deterministic_result(missing=missing)


def evaluate_policy(
    user_input: str,
    current_state: dict[str, Any] | None = None,
    extracted_intent: str = "",
) -> InteractionPolicyDecision:
    """
    Authoritative interaction policy gate — Phase 0D.

    Four-tier deterministic pre-check runs first (no LLM, no I/O):
      1. META: state-status questions → meta path
      2. BLOCK: explicitly forbidden requests → blocked path
      3. GREETING: trivial smalltalk → greeting path (no LLM, no RAG)
      4. After LLM "Fast" decision: technical-specificity upgrade to Structured

    Then the Nano-LLM classifies remaining messages into "Fast" or "Structured".
    Fail-safe: any LLM error falls back to Structured.

    Parameters
    ----------
    user_input:
        Raw user message.
    current_state:
        Optional current AgentState dict for context-aware decisions.
    extracted_intent:
        Accepted for API compatibility; not used in routing logic.

    Returns
    -------
    InteractionPolicyDecision
        Authoritative routing decision — one of: meta, blocked, greeting, fast, structured.
    """
    # ── Deterministic tiers (no LLM) ──────────────────────────────────────
    deterministic = _evaluate_deterministic_tiers(user_input, current_state)
    if deterministic is not None:
        return deterministic

    # ── Tier 1: Nano-LLM routing (fast vs structured) ─────────────────────
    try:
        route = _call_routing_llm(user_input)
    except Exception as exc:
        log.warning(
            "Routing LLM call failed (%s: %s) — falling back to Structured path",
            type(exc).__name__,
            exc,
        )
        route = "Structured"

    return _resolve_llm_route(route, user_input, current_state)


async def evaluate_policy_async(
    user_input: str,
    current_state: dict[str, Any] | None = None,
    extracted_intent: str = "",
) -> InteractionPolicyDecision:
    """Async variant of evaluate_policy — does not block the event loop.

    Identical logic to evaluate_policy but uses _call_routing_llm_async
    for the nano-LLM call. Use this from async FastAPI endpoints.
    """
    deterministic = _evaluate_deterministic_tiers(user_input, current_state)
    if deterministic is not None:
        return deterministic

    try:
        route = await _call_routing_llm_async(user_input)
    except Exception as exc:
        log.warning(
            "Routing LLM call failed (%s: %s) — falling back to Structured path",
            type(exc).__name__,
            exc,
        )
        route = "Structured"

    return _resolve_llm_route(route, user_input, current_state)
