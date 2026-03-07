from __future__ import annotations

from typing import Any, Dict


# Blueprint v1.2 — RFQ Redaction Allowlist
# Only these keys are allowed to pass through to outward-facing RFQ artifacts.
# Everything else is considered internal context or unnecessarily precise.
_RFQ_REDACTION_ALLOWLIST = {
    "medium",
    "pressure_bar",
    "temperature_C",
    "shaft_diameter",
    "speed_rpm",
    "dynamic_type",
    "shaft_runout",
    "shaft_hardness",
    "seal_material",
    "normative_references",
}


def redact_operating_context(raw_context: Dict[str, Any]) -> Dict[str, Any]:
    """Apply Blueprint v1.2 redaction rules to the technical context.
    
    Ensures that only supplier-relevant information is exposed and 
    reduces precision of numeric values to avoid leaking internal design intent.
    """
    redacted = {}
    for key in _RFQ_REDACTION_ALLOWLIST:
        if key in raw_context:
            value = raw_context[key]
            # Rule: Round overly precise floating point numbers to 1 decimal place
            # unless they are specific IDs or markers.
            if isinstance(value, float):
                redacted[key] = round(value, 1)
            else:
                redacted[key] = value
    return redacted
