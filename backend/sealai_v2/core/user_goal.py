"""Shared deterministic speech-act predicates used by routing and response planning."""

from __future__ import annotations

import re


_REPLACEMENT_IDENTIFICATION_RE = re.compile(
    r"(?=.*\b(?:ersatz(?:teil|dichtung)?|ersetzen|originalspezifikation|altteil)\w*\b)"
    r"(?=.*\b(?:identifizier\w*|ermittel\w*|finde\w*|bestimm\w*|mess\w*|"
    r"(?:code|bezeichnung|spezifikation)\w*\s+(?:fehlt|fehlend|unbekannt|nicht\s+bekannt)|"
    r"ohne\s+(?:code|bezeichnung|spezifikation)|altteil)\b)",
    re.IGNORECASE | re.DOTALL,
)


def requests_replacement_identification(question: str) -> bool:
    """Whether the speech act is identifying an unknown replacement, not diagnosing damage."""

    return bool(_REPLACEMENT_IDENTIFICATION_RE.search(question or ""))
