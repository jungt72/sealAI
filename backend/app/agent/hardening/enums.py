from enum import StrEnum


class ExtractionCertainty(StrEnum):
    """
    How a parameter value was obtained.
    Structurally derived from extraction context — NEVER self-assessed by the LLM.
    Replaces all ``confidence: float`` fields.
    """

    EXPLICIT_VALUE = "explicit_value"
    """User stated a clear value: "150°C"."""

    EXPLICIT_RANGE = "explicit_range"
    """User stated a range: "120–180°C"."""

    INFERRED_FROM_CONTEXT = "inferred"
    """LLM derived from context: "hot water" → ~95°C."""

    AMBIGUOUS = "ambiguous"
    """Multiple interpretations: "1500, maybe 2000"."""

    ASSUMED_DEFAULT = "assumed"
    """No user input; system assumed a default."""


class EngineStatus(StrEnum):
    """Status of every deterministic engine computation."""

    COMPUTED = "computed"
    """Engine produced a valid, usable result."""

    INSUFFICIENT_DATA = "insufficient_data"
    """One or more required inputs are missing or not yet calculable."""

    OUT_OF_RANGE = "out_of_range"
    """Result is outside the physical plausibility envelope for rotary seals."""

    NO_MATCH = "no_match"
    """No matching material or configuration found."""

    CONTRADICTION_DETECTED = "contradiction_detected"
    """Input values are mutually contradictory (e.g., min > max)."""
