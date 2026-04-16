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

ADMISSIBILITY_COMPAT_ALIASES: dict[str, str] = {
    "rfq_admissible": "inquiry_admissible",
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


def build_admissibility_payload(
    flag: bool,
    *,
    include_compat_aliases: bool = False,
) -> dict[str, bool | dict[str, bool]]:
    value = bool(flag)
    payload: dict[str, bool | dict[str, bool]] = {
        "inquiry_admissible": value,
    }
    if include_compat_aliases:
        payload["compat_aliases"] = {
            alias: value
            for alias in ADMISSIBILITY_COMPAT_ALIASES
        }
    return payload
