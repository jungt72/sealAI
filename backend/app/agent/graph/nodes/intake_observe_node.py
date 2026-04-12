"""
intake_observe_node — Phase F-C.1, Zone 1

THE ONLY NODE IN THE GOVERNED GRAPH THAT MAY CALL AN LLM.

Responsibility:
    Extract typed technical parameters from the user message and write them
    as ObservedExtraction objects into ObservedState.

Architecture invariants enforced here (Blaupause V1.1 §4 + §5):
    - LLM output goes ONLY into ObservedState via with_extraction().
    - No direct writes to NormalizedState, AssertedState, or GovernanceState.
    - RAG is NOT called here. Evidence retrieval is Zone 4 (evidence_node).
    - All downstream state layers remain unchanged after this node.

Two-pass extraction:
    Pass 1 (deterministic, always runs):
        domain/normalization.extract_parameters() — regex-based, high confidence.
        Catches numeric patterns (°C, bar, mm, rpm) and known material/medium tokens.

    Pass 2 (LLM, feature-flag guarded):
        OpenAI async call in JSON mode — catches semantic patterns that regex misses
        (e.g. "das Medium ist Dampf", "Welle dreht mit 1500 Umdrehungen").
        LLM confidence is lower than regex (0.75 default vs 0.92 for regex).
        Only extractions for fields NOT already covered by Pass 1 are added.

Feature flag:
    SEALAI_ENABLE_LLM_EXTRACTION=true (default: true)
    Set to "false" to run deterministic-only mode (useful in tests / offline).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import openai

from app.agent.domain.normalization import (
    extract_parameters as regex_extract,
    extract_shaft_diameter_mm,
)
from app.agent.graph import GraphState
from app.agent.prompts import prompts
from app.agent.state.models import ObservedExtraction, UserOverride

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

_ENABLE_LLM_EXTRACTION: bool = (
    os.environ.get("SEALAI_ENABLE_LLM_EXTRACTION", "true").lower() == "true"
)

_EXTRACTION_MODEL: str = os.environ.get(
    "SEALAI_EXTRACTION_MODEL", "gpt-4o-mini"
)

# ---------------------------------------------------------------------------
# Field whitelist
# ---------------------------------------------------------------------------

_ALLOWED_FIELD_NAMES: frozenset[str] = frozenset({
    "medium",
    "pressure_bar",
    "temperature_c",
    "material",
    "shaft_diameter_mm",
    "speed_rpm",
    "motion_type",
    "sealing_type",
    "pressure_direction",
    "duty_profile",
    "installation",
    "geometry_context",
    "contamination",
    "counterface_surface",
    "tolerances",
    "industry",
    "compliance",
    "medium_qualifiers",
})

# Confidence assigned to regex-sourced extractions (high, but user-unconfirmed)
_REGEX_CONFIDENCE: float = 0.92

# Confidence assigned to LLM-sourced extractions (semantic, lower certainty)
_LLM_CONFIDENCE: float = 0.75

_MEDIUM_STATUS_TO_CONFIDENCE: dict[str, float] = {
    "confirmed": 0.92,
    "estimated": 0.85,
    "inferred": 0.60,
    "requires_confirmation": 0.60,
}

_CORRECTION_RE = re.compile(
    r"\b(?:korrigier\w*|korrektur|statt|sondern|nicht\b.+\bsondern)\b",
    re.IGNORECASE,
)

_PRIMARY_OVERRIDE_FIELDS: frozenset[str] = frozenset({
    "medium",
})


def _canonical_compare_value(value: Any) -> str:
    text = str(value if value is not None else "").strip().casefold()
    return re.sub(r"\s+", " ", text)


def _current_state_value(state: GraphState, field_name: str) -> Any:
    asserted = state.asserted.assertions.get(field_name)
    if asserted is not None and asserted.asserted_value is not None:
        return asserted.asserted_value
    normalized = state.normalized.parameters.get(field_name)
    if normalized is not None:
        return normalized.value
    return None


def _promote_primary_correction_overrides(
    *,
    state: GraphState,
    observed,
    new_extractions: list[ObservedExtraction],
    turn_index: int,
):
    if not _CORRECTION_RE.search(state.pending_message):
        return observed

    for extraction in new_extractions:
        if extraction.field_name not in _PRIMARY_OVERRIDE_FIELDS:
            continue
        current_value = _current_state_value(state, extraction.field_name)
        if current_value is not None and _canonical_compare_value(current_value) == _canonical_compare_value(extraction.raw_value):
            continue
        observed = observed.with_override(
            UserOverride(
                field_name=extraction.field_name,
                override_value=extraction.raw_value,
                override_unit=extraction.raw_unit,
                turn_index=turn_index,
            )
        )
    return observed

# ---------------------------------------------------------------------------
# Regex → ObservedExtraction bridge
# ---------------------------------------------------------------------------

def _regex_params_to_extractions(
    params: dict[str, Any],
    turn_index: int,
) -> list[ObservedExtraction]:
    """Convert normalization.extract_parameters() output to ObservedExtractions.

    Mapping rules (conservative — only well-typed keys are forwarded):
      temperature_c          → field_name="temperature_c",  confidence=0.92
      pressure_bar           → field_name="pressure_bar",   confidence=0.92
      diameter_mm            → field_name="shaft_diameter_mm", confidence=0.92
      speed_rpm              → field_name="speed_rpm",      confidence=0.92
      medium_normalized      → field_name="medium",         confidence=0.85
      medium_confirmation_req→ field_name="medium",         confidence=0.60
      material_normalized    → field_name="material",       confidence=0.85
      material_confirmation_r→ field_name="material",       confidence=0.60
    """
    results: list[ObservedExtraction] = []

    def _add(field: str, value: Any, conf: float, unit: str | None = None) -> None:
        if value is None:
            return
        results.append(ObservedExtraction(
            field_name=field,
            raw_value=value,
            raw_unit=unit,
            source="llm",        # regex is also a form of automated extraction
            confidence=conf,
            turn_index=turn_index,
        ))

    if "temperature_c" in params:
        _add("temperature_c", params["temperature_c"], _REGEX_CONFIDENCE, "°C")
    if "pressure_bar" in params:
        _add("pressure_bar", params["pressure_bar"], _REGEX_CONFIDENCE, "bar")
    if "diameter_mm" in params:
        _add("shaft_diameter_mm", params["diameter_mm"], _REGEX_CONFIDENCE, "mm")
    if "speed_rpm" in params:
        _add("speed_rpm", params["speed_rpm"], _REGEX_CONFIDENCE, "rpm")

    # Medium: prefer confirmed/estimated normalized values, fall back to
    # confirmation-required or inferred values at lower confidence.
    if "medium_normalized" in params:
        medium_conf = _MEDIUM_STATUS_TO_CONFIDENCE.get(
            str(params.get("medium_normalization_status") or "").strip().lower(),
            0.85,
        )
        _add("medium", params["medium_normalized"], medium_conf)
    elif "medium_confirmation_required" in params:
        _add(
            "medium",
            params["medium_confirmation_required"],
            _MEDIUM_STATUS_TO_CONFIDENCE["requires_confirmation"],
        )

    # Material: same pattern
    if "material_normalized" in params:
        _add("material", params["material_normalized"], 0.85)
    elif "material_confirmation_required" in params:
        _add("material", params["material_confirmation_required"], 0.60)

    if "motion_type" in params:
        _add("motion_type", params["motion_type"], 0.88)

    for field_name in (
        "sealing_type",
        "pressure_direction",
        "duty_profile",
        "installation",
        "geometry_context",
        "contamination",
        "counterface_surface",
        "tolerances",
        "industry",
        "compliance",
        "medium_qualifiers",
    ):
        if field_name in params:
            _add(field_name, params[field_name], 0.82)

    return results


def _state_has_rotary_shaft_context(state: GraphState) -> bool:
    motion_hint = getattr(state, "motion_hint", None)
    application_hint = getattr(state, "application_hint", None)

    motion_label = getattr(motion_hint, "label", None) if motion_hint is not None else None
    application_label = getattr(application_hint, "label", None) if application_hint is not None else None

    if motion_label == "rotary":
        return True
    if application_label in {"shaft_sealing", "marine_propulsion"}:
        return True
    if "shaft_diameter_mm" in state.asserted.assertions or "speed_rpm" in state.asserted.assertions:
        return True
    if "shaft_diameter_mm" in state.normalized.parameters or "speed_rpm" in state.normalized.parameters:
        return True
    return False


def _apply_contextual_regex_fallbacks(state: GraphState, params: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(params)
    if "diameter_mm" not in enriched and _state_has_rotary_shaft_context(state):
        contextual_diameter = extract_shaft_diameter_mm(
            state.pending_message,
            allow_context_free_mm=True,
        )
        if contextual_diameter is not None:
            enriched["diameter_mm"] = contextual_diameter
    return enriched


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------


async def _llm_extract_params(
    message: str,
    turn_index: int,
) -> list[ObservedExtraction]:
    """Call OpenAI to extract structured parameters from the message.

    Returns ObservedExtraction objects. On any error returns [] (fail-open).
    LLM is constrained to the allowed field list — no governance artefacts.
    """
    try:
        client = openai.AsyncOpenAI()
        system_prompt = prompts.render("intake/observe.j2", {})
        response = await client.chat.completions.create(
            model=_EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": message},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=512,
        )
        raw = response.choices[0].message.content or "[]"

        # The model may return {"extractions": [...]} or just [...]
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            # Try common wrapper keys
            for key in ("extractions", "parameters", "results", "data"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break
            else:
                # Fall back to values if it's a flat dict
                parsed = list(parsed.values()) if parsed else []

        if not isinstance(parsed, list):
            log.warning("[intake_observe_node] LLM returned unexpected shape: %s", type(parsed))
            return []

        extractions: list[ObservedExtraction] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            field_name = str(item.get("field_name", "")).strip()
            if field_name not in _ALLOWED_FIELD_NAMES:
                log.debug("[intake_observe_node] LLM proposed unknown field '%s' — skipped", field_name)
                continue
            raw_value = item.get("raw_value")
            if raw_value is None:
                continue
            conf_raw = item.get("confidence", _LLM_CONFIDENCE)
            try:
                confidence = float(conf_raw)
            except (TypeError, ValueError):
                confidence = _LLM_CONFIDENCE
            confidence = max(0.0, min(1.0, confidence))

            extractions.append(ObservedExtraction(
                field_name=field_name,
                raw_value=raw_value,
                raw_unit=item.get("raw_unit"),
                source="llm",
                confidence=confidence,
                turn_index=turn_index,
            ))

        log.debug(
            "[intake_observe_node] LLM extracted %d params: %s",
            len(extractions),
            [e.field_name for e in extractions],
        )
        return extractions

    except Exception as exc:
        log.warning("[intake_observe_node] LLM extraction failed (%s: %s) — using regex only", type(exc).__name__, exc)
        return []


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def intake_observe_node(state: GraphState) -> GraphState:
    """Zone 1 — Parameter extraction into ObservedState.

    INVARIANT: Only this node may produce LLM-sourced ObservedExtractions.
    All other nodes are deterministic and do not call the LLM.

    Pass 1 — deterministic regex extraction (always runs):
        Uses domain/normalization.extract_parameters() for numeric patterns and
        well-known material/medium tokens. High confidence (0.85–0.92).

    Pass 2 — LLM semantic extraction (feature-flag guarded):
        Catches natural language patterns missed by regex.
        Lower confidence (0.75). Only adds fields not already in Pass 1.

    Neither pass writes to NormalizedState, AssertedState, or GovernanceState.
    """
    if not state.pending_message:
        log.debug("[intake_observe_node] pending_message is empty — skipping")
        return state

    # user_turn_index is monotonically increasing per user message (set by router
    # before each ainvoke). Falls back to analysis_cycle for backwards compatibility.
    turn_index = getattr(state, "user_turn_index", None) or state.analysis_cycle
    observed = state.observed

    # ── Pass 1: deterministic regex extraction ────────────────────────────
    try:
        regex_params = _apply_contextual_regex_fallbacks(
            state,
            regex_extract(state.pending_message),
        )
        regex_extractions = _regex_params_to_extractions(regex_params, turn_index)
        for extraction in regex_extractions:
            observed = observed.with_extraction(extraction)
        observed = _promote_primary_correction_overrides(
            state=state,
            observed=observed,
            new_extractions=regex_extractions,
            turn_index=turn_index,
        )
        log.debug(
            "[intake_observe_node] regex extracted %d params: %s",
            len(regex_extractions),
            [e.field_name for e in regex_extractions],
        )
    except Exception as exc:
        log.warning("[intake_observe_node] regex extraction failed (%s: %s) — continuing", type(exc).__name__, exc)

    # ── Pass 2: LLM semantic extraction (feature-flag guarded) ───────────
    if _ENABLE_LLM_EXTRACTION:
        llm_extractions = await _llm_extract_params(state.pending_message, turn_index)
        already_covered: frozenset[str] = frozenset(e.field_name for e in regex_extractions)
        appended_llm_extractions: list[ObservedExtraction] = []
        for extraction in llm_extractions:
            if extraction.field_name not in already_covered:
                observed = observed.with_extraction(extraction)
                appended_llm_extractions.append(extraction)
                log.debug(
                    "[intake_observe_node] LLM added new field '%s' (confidence=%.2f)",
                    extraction.field_name,
                    extraction.confidence,
                )
        observed = _promote_primary_correction_overrides(
            state=state,
            observed=observed,
            new_extractions=appended_llm_extractions,
            turn_index=turn_index,
        )

    if observed is state.observed:
        # Nothing was extracted
        log.debug("[intake_observe_node] no extractions for message (len=%d)", len(state.pending_message))
        return state

    return state.model_copy(update={"observed": observed})
