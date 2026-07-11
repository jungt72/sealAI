"""Pure extractor: Werkstoff + optional Bauform aus Freitext -> dict | None.

No I/O, no LLM, no mutation, no float literals.
Feeds Case.seal_spec for the Gegencheck entry (INC-4a).
"""

from __future__ import annotations

import re

# Canonical material tags from the Verträglichkeitsmatrix allowlist.
# Key: token to match (case-insensitive, word boundary); value: canonical tag.
_MATERIAL_SYNONYMS: dict[str, str] = {
    "aflas": "FEPM",  # Handelsname → ASTM-D1418-Klasse FEPM (wie fpm→FKM, vmq→Silikon)
    "epdm": "EPDM",
    "fepm": "FEPM",
    "ffkm": "FFKM",
    "fkm": "FKM",
    "fpm": "FKM",  # synonym -> canonical FKM
    "hnbr": "HNBR",
    "nbr": "NBR",
    "ptfe": "PTFE",
    "silikon": "Silikon",
    "vmq": "Silikon",  # synonym -> canonical Silikon
}

# Compiled patterns for all material tokens (word-boundary, case-insensitive).
_MATERIAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b" + re.escape(token) + r"\b", re.IGNORECASE), canonical)
    for token, canonical in _MATERIAL_SYNONYMS.items()
]

# Fixed set of recognised seal types — only unambiguous, terminology-stable terms.
_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bRWDR\b", re.IGNORECASE), "RWDR"),
    (re.compile(r"\bO-Ring\b", re.IGNORECASE), "O-Ring"),
    (re.compile(r"\bX-Ring\b", re.IGNORECASE), "X-Ring"),
    (re.compile(r"\bV-Ring\b", re.IGNORECASE), "V-Ring"),
    (re.compile(r"\bNutring\b", re.IGNORECASE), "Nutring"),
    (re.compile(r"\bWellendichtring\b", re.IGNORECASE), "Wellendichtring"),
    (re.compile(r"\bGleitringdichtung\b", re.IGNORECASE), "Gleitringdichtung"),
    (re.compile(r"\bGLRD\b", re.IGNORECASE), "Gleitringdichtung"),
    (re.compile(r"\bMechanical\s+Seal\b", re.IGNORECASE), "Gleitringdichtung"),
]


def extract_seal_spec(message: str) -> dict | None:
    """Extract material (and optionally seal type) from a free-text message.

    Returns a dict with at least {"material": <canonical tag>} on success,
    optionally also {"type": <seal type>}.  Returns None when:
    - no material is recognised (conservative — never guesses), or
    - more than one distinct canonical material is found (ambiguous, fail-closed).

    Both axes follow the same "never guess" doctrine, differing only in severity
    because of field obligation:
    - material is mandatory → an ambiguous material (≥2 distinct) fails to None;
    - type is optional → an ambiguous type (≥2 distinct) drops the field
      (graceful degrade), keeping the recognised material.
    """
    found: list[str] = []
    for pattern, canonical in _MATERIAL_PATTERNS:
        if pattern.search(message) and canonical not in found:
            found.append(canonical)

    if len(found) != 1:
        return None

    result: dict[str, str] = {"material": found[0]}

    found_types: list[str] = []
    for pattern, seal_type in _TYPE_PATTERNS:
        if pattern.search(message) and seal_type not in found_types:
            found_types.append(seal_type)

    if len(found_types) == 1:
        result["type"] = found_types[0]

    return result
