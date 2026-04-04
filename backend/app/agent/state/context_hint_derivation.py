from __future__ import annotations

import re

from app.agent.state.models import ContextHintState, ObservedState

_MOTION_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\b(?:lineare?\s+beweg\w*|linear\w*|hubbeweg\w*|hubstange|kolbenstange)\b", re.IGNORECASE), "linear", "high"),
    (re.compile(r"\b(?:schiffsschraube|rotierende?\s+welle|rotierend\w*|rwdr|radialwellendichtring|shaft)\b", re.IGNORECASE), "rotary", "high"),
    (re.compile(r"\b(?:welle)\b", re.IGNORECASE), "rotary", "medium"),
    (re.compile(r"\b(?:statische?\s+abdichtung|statisch\w*|gehaeuse|gehäuse)\b", re.IGNORECASE), "static", "high"),
)

_APPLICATION_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\b(?:lineare?\s+beweg\w*|linear\w*|kolbenstange|hubstange|zylinder)\b", re.IGNORECASE), "linear_sealing", "high"),
    (re.compile(r"\b(?:schiffsschraube)\b", re.IGNORECASE), "marine_propulsion", "high"),
    (re.compile(r"\b(?:draussen\s+halten|draußen\s+halten|aussen\s+abdichten|außen\s+abdichten)\b", re.IGNORECASE), "external_sealing", "high"),
    (re.compile(r"\b(?:gehaeuse|gehäuse)\b", re.IGNORECASE), "housing_sealing", "high"),
    (re.compile(r"\b(?:rotierende?\s+welle|welle|shaft|rwdr|radialwellendichtring)\b", re.IGNORECASE), "shaft_sealing", "medium"),
    (re.compile(r"\b(?:statische?\s+abdichtung|statisch\w*)\b", re.IGNORECASE), "static_sealing", "medium"),
)


def _derive_hint(
    *,
    message: str,
    observed: ObservedState,
    previous: ContextHintState | None,
    patterns: tuple[tuple[re.Pattern[str], str, str], ...],
) -> ContextHintState:
    existing = previous if isinstance(previous, ContextHintState) else ContextHintState()
    text = str(message or "").strip()

    for pattern, label, confidence in patterns:
        if not pattern.search(text):
            continue
        source_turn_index = max(observed.source_turns) if observed.source_turns else existing.source_turn_index
        source_turn_ref = f"turn:{source_turn_index}" if source_turn_index is not None else existing.source_turn_ref
        return ContextHintState(
            label=label,
            confidence=confidence,  # type: ignore[arg-type]
            source_turn_ref=source_turn_ref,
            source_turn_index=source_turn_index,
            source_type="deterministic_text_inference",
        )

    return existing


def derive_motion_hint(
    *,
    message: str,
    observed: ObservedState,
    previous: ContextHintState | None = None,
) -> ContextHintState:
    return _derive_hint(
        message=message,
        observed=observed,
        previous=previous,
        patterns=_MOTION_PATTERNS,
    )


def derive_application_hint(
    *,
    message: str,
    observed: ObservedState,
    previous: ContextHintState | None = None,
) -> ContextHintState:
    return _derive_hint(
        message=message,
        observed=observed,
        previous=previous,
        patterns=_APPLICATION_PATTERNS,
    )
