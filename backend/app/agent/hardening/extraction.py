from .enums import ExtractionCertainty


def classify_certainty(
    raw_text: str | None,
    parsed_value: object | None,
    has_explicit_unit: bool = False,
    is_range: bool = False,
    is_inferred: bool = False,
) -> ExtractionCertainty:
    """
    Deterministic classification of how a parameter value was obtained.

    This replaces LLM ``confidence: float`` self-assessment.  The classification
    is based entirely on the structural facts of the extraction — whether the user
    explicitly stated a value, gave a range, or whether the value was inferred
    from surrounding context.

    Called by the claim-processing pipeline to assign certainty BEFORE values
    enter the observed layer.

    Args:
        raw_text: The original text fragment the value was extracted from.
        parsed_value: The parsed numeric or string value, or ``None`` if parsing
            failed.
        has_explicit_unit: ``True`` when a unit (°C, bar, rpm …) was present in
            the source text alongside the value.
        is_range: ``True`` when the user provided a range rather than a single
            value ("120–180 °C").
        is_inferred: ``True`` when the value was derived from context rather than
            explicitly stated ("hot water application" → ~95 °C).

    Returns:
        An :class:`ExtractionCertainty` enum member.
    """
    # Check structural flags first — they take priority over parsed_value presence.
    if is_range:
        return ExtractionCertainty.EXPLICIT_RANGE

    if is_inferred and parsed_value is not None:
        return ExtractionCertainty.INFERRED_FROM_CONTEXT

    if parsed_value is None:
        return ExtractionCertainty.AMBIGUOUS

    if is_inferred:
        return ExtractionCertainty.INFERRED_FROM_CONTEXT

    if raw_text and (has_explicit_unit or parsed_value is not None):
        return ExtractionCertainty.EXPLICIT_VALUE

    return ExtractionCertainty.ASSUMED_DEFAULT


def is_calculable(certainty: ExtractionCertainty, confirmed: bool) -> bool:
    """
    Gate function: can the deterministic engine use this value?

    Rules
    -----
    - ``AMBIGUOUS`` → never calculable (must ask the user first).
    - ``INFERRED_FROM_CONTEXT`` → only if the user has explicitly confirmed.
    - ``ASSUMED_DEFAULT`` → only if the user has explicitly confirmed.
    - ``EXPLICIT_VALUE`` / ``EXPLICIT_RANGE`` → always calculable.

    Args:
        certainty: The :class:`ExtractionCertainty` assigned by
            :func:`classify_certainty`.
        confirmed: ``True`` when the user has explicitly confirmed this value
            in a follow-up interaction.

    Returns:
        ``True`` when the engine may use the value, ``False`` otherwise.
    """
    if certainty == ExtractionCertainty.AMBIGUOUS:
        return False
    if certainty == ExtractionCertainty.INFERRED_FROM_CONTEXT and not confirmed:
        return False
    if certainty == ExtractionCertainty.ASSUMED_DEFAULT and not confirmed:
        return False
    return True
