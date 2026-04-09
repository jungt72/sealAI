from __future__ import annotations

OUTWARD_CLASS_ALIASES: dict[str, str] = {
    "governed_recommendation": "technical_preselection",
    "manufacturer_match_result": "candidate_shortlist",
    "rfq_ready": "inquiry_ready",
}

OUTWARD_STATUS_ALIASES: dict[str, str] = {
    **OUTWARD_CLASS_ALIASES,
    "governed_non_binding_result": "technical_preselection",
    "withheld_review": "technical_preselection",
    "clarification_needed": "structured_clarification",
}


def normalize_outward_response_class(
    value: str | None,
    *,
    default: str = "structured_clarification",
) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return OUTWARD_CLASS_ALIASES.get(text, text)


def normalize_outward_status(
    value: str | None,
    *,
    default: str = "structured_clarification",
) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return OUTWARD_STATUS_ALIASES.get(text, text)


def build_admissibility_payload(flag: bool) -> dict[str, bool]:
    value = bool(flag)
    return {
        "inquiry_admissible": value,
        "rfq_admissible": value,
    }
