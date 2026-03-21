"""
Interaction Policy V1 — Deterministic Evaluation Logic
Phase 0A.2

The LLM may supply an extracted intent string as a soft hint.
This function makes the final, binding routing decision via deterministic rules.

Architecture rule (Umbauplan R1):
  - LLM provides intent pre-structuring (optional, passed as `extracted_intent`)
  - This function makes the hard policy decision — never the LLM directly
"""
from __future__ import annotations

import re
from typing import Any

from app.agent.agent.policy import (
    INTERACTION_POLICY_VERSION,
    InteractionPolicyDecision,
    ResultForm,
    RoutingPath,
)

# ---------------------------------------------------------------------------
# Pattern banks for intent scoring
# ---------------------------------------------------------------------------

_GLOSSARY_PATTERNS = [
    r"\bwas ist\b",
    r"\bwas sind\b",
    r"\bwas bedeutet\b",
    r"\bwas versteht man\b",
    r"\bwas heißt\b",
    r"\bdefiniere\b",
    r"\berkläre\b",
    r"\berklärung\b",
    r"\bwhat is\b",
    r"\bwhat are\b",
    r"\bbegriff\b",
    r"\bdefinition\b",
    r"\bwozu dient\b",
    r"\bwofür steht\b",
]

_COMPARISON_PATTERNS = [
    r"\bvergleich\b",
    r"\bvergleiche\b",
    r"\bunterschied\b",
    r"\bvs\b",
    r"\bversus\b",
    r"\boder\b.*\bbetter\b",
    r"\bbesser als\b",
    r"\bschlechter als\b",
    r"\bgeeigneter\b",
    r"\bwelches material\b",
    r"\bwelcher werkstoff\b",
    r"\bgegenüber\b",
    r"\bvor- und nachteile\b",
]

_CALCULATION_PATTERNS = [
    r"\bberechne\b",
    r"\bberechnung\b",
    r"\brechne\b",
    r"\bumlaufgeschwindigkeit\b",
    r"\bgleitgeschwindigkeit\b",
    r"\bu/min\b",
    r"\brpm\b",
    r"\bdrehzahl\b",
    r"\bwellendurchmesser\b",
    r"\bdruckaufbaurate\b",
    r"\bdp/dt\b",
    r"\bpv.?wert\b",
    r"\breibungsleistung\b",
    r"\bv_s\b",
    r"\bv_surface\b",
]

# numeric value followed immediately by a technical unit
_NUMERIC_UNIT_RE = re.compile(
    r"\d[\d\.,]*\s*(?:mm|bar|°c|rpm|u/min|m/s|kn|°f|mpa|hrc|μm)",
    re.IGNORECASE,
)

# Strong qualification/certification signals
_QUALIFICATION_PATTERNS = [
    r"\bfreigabe\b",
    r"\bzulassung\b",
    r"\bzertifikat\b",
    r"\bzertifizierung\b",
    r"\bkonformitätserklärung\b",
    r"\bfda\b",
    r"\batex\b",
    r"\bnorsok\b",
    r"\bprüfzeugnis\b",
    r"\bwerkstoffzeugnis\b",
    r"\bfreigabeliste\b",
    r"\brfq\b",
    r"\bausschreibung\b",
    r"\bfreigegeben\b",
    r"\bherstellerfreigabe\b",
    r"\bnachweispflichtig\b",
]

# ---------------------------------------------------------------------------
# Helper: intent score map
# ---------------------------------------------------------------------------

def _score(text: str, patterns: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for p in patterns if re.search(p, lowered))


def _has_numeric_units(text: str) -> bool:
    return bool(_NUMERIC_UNIT_RE.search(text))


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
    if not current_state:
        return ("medium", "pressure", "temperature")
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
# Intent hint normalizer (optional LLM input)
# ---------------------------------------------------------------------------

_INTENT_MAP: dict[str, str] = {
    "glossary": "glossary",
    "concept_explanation": "glossary",
    "terminology": "glossary",
    "definition": "glossary",
    "comparison": "comparison",
    "material_comparison": "comparison",
    "calculation": "calculation",
    "deterministic": "calculation",
    "rwdr": "calculation",
    "qualification": "qualification",
    "certification": "qualification",
    "compliance": "qualification",
    "guidance": "guidance",
    "recommendation": "guidance",
}


def _normalize_intent(raw: str) -> str:
    """Map a raw LLM-provided intent string to a canonical category."""
    return _INTENT_MAP.get(raw.lower().strip(), "")


# ---------------------------------------------------------------------------
# Core factory helpers
# ---------------------------------------------------------------------------

def _direct_answer(*, coverage: str = "in_scope") -> InteractionPolicyDecision:
    return InteractionPolicyDecision(
        result_form=ResultForm.DIRECT_ANSWER,
        path=RoutingPath.FAST_PATH,
        stream_mode="reply_only",
        interaction_class="DIRECT_ANSWER",
        runtime_path="FAST_DIRECT",
        binding_level="KNOWLEDGE",
        has_case_state=False,
        coverage_status=coverage,
        boundary_flags=("not_a_manufacturer_release",),
        required_fields=(),
    )


def _guided_recommendation(
    *,
    missing: tuple[str, ...] = (),
    escalation: str | None = None,
) -> InteractionPolicyDecision:
    flags: list[str] = ["orientation_only", "not_a_manufacturer_release"]
    if missing:
        flags.append("parameters_incomplete")
    return InteractionPolicyDecision(
        result_form=ResultForm.GUIDED_RECOMMENDATION,
        path=RoutingPath.FAST_PATH,
        stream_mode="reply_only",
        interaction_class="GUIDED_RECOMMENDATION",
        runtime_path="FAST_GUIDANCE",
        binding_level="ORIENTATION",
        has_case_state=False,
        coverage_status="partial" if missing else "in_scope",
        boundary_flags=tuple(flags),
        escalation_reason=escalation,
        required_fields=missing,
    )


def _deterministic_result(
    *,
    missing: tuple[str, ...] = (),
) -> InteractionPolicyDecision:
    return InteractionPolicyDecision(
        result_form=ResultForm.DETERMINISTIC_RESULT,
        path=RoutingPath.STRUCTURED_PATH,
        stream_mode="structured_progress_stream",
        interaction_class="DETERMINISTIC_RESULT",
        runtime_path="STRUCTURED_DETERMINISTIC",
        binding_level="ORIENTATION",
        has_case_state=True,
        coverage_status="in_scope" if not missing else "partial",
        boundary_flags=("not_a_manufacturer_release",),
        required_fields=missing,
    )


def _qualified_case(
    *,
    missing: tuple[str, ...] = (),
) -> InteractionPolicyDecision:
    return InteractionPolicyDecision(
        result_form=ResultForm.QUALIFIED_CASE,
        path=RoutingPath.STRUCTURED_PATH,
        stream_mode="structured_progress_stream",
        interaction_class="QUALIFIED_CASE",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        has_case_state=True,
        coverage_status="in_scope",
        boundary_flags=("manufacturer_validation_may_be_required",),
        required_fields=missing,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_policy(
    user_input: str,
    current_state: dict[str, Any] | None = None,
    extracted_intent: str = "",
) -> InteractionPolicyDecision:
    """
    Deterministic interaction policy gate.

    Parameters
    ----------
    user_input:
        Raw user message.
    current_state:
        Optional current AgentState dict for context-aware decisions.
    extracted_intent:
        Optional LLM-pre-classified intent string (soft hint only).
        The final routing decision is always made by this function.

    Returns
    -------
    InteractionPolicyDecision
        Authoritative routing decision. Never produced by free LLM generation.
    """
    # --- Score text signals ---
    glossary_score = _score(user_input, _GLOSSARY_PATTERNS)
    comparison_score = _score(user_input, _COMPARISON_PATTERNS)
    calc_score = _score(user_input, _CALCULATION_PATTERNS)
    qual_score = _score(user_input, _QUALIFICATION_PATTERNS)
    has_units = _has_numeric_units(user_input)

    # --- Boost from optional LLM intent hint ---
    intent = _normalize_intent(extracted_intent)
    if intent == "glossary":
        glossary_score += 2
    elif intent == "comparison":
        comparison_score += 2
    elif intent == "calculation":
        calc_score += 2
    elif intent == "qualification":
        qual_score += 3  # strong: LLM confirmed

    # --- Hard gates (order matters: most specific first) ---

    # 1. Qualification/certification — always structured
    if qual_score >= 1:
        missing = _missing_critical_params(current_state)
        return _qualified_case(missing=missing)

    # 2. Calculation with numeric evidence — structured deterministic
    if calc_score >= 1 and has_units:
        return _deterministic_result()

    # 3. Calculation keyword only (no numbers yet) — ask for params via guidance
    if calc_score >= 2:
        return _deterministic_result(missing=("shaft_diameter_mm", "rpm"))

    # 4. Glossary / concept explanation — direct answer, fast path
    if glossary_score >= 1 and comparison_score == 0 and calc_score == 0:
        return _direct_answer()

    # 5. Material/concept comparison — direct answer, fast path
    if comparison_score >= 1:
        return _direct_answer()

    # 6. Default: guided recommendation — NOT heavy qualification
    #    (This is the key fix: don't blast every open question into structured path)
    missing = _missing_critical_params(current_state)
    return _guided_recommendation(missing=missing)
