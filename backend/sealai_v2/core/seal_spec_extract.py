"""Pure extractor: Werkstoff + optional Bauform aus Freitext -> dict | None.

No I/O, no LLM, no mutation, no float literals.
Feeds Case.seal_spec for the Gegencheck entry (INC-4a).
"""

from __future__ import annotations

import re

from sealai_v2.core.seal_type_extract import extract_seal_type

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


def extract_material_candidates(message: str) -> tuple[str, ...]:
    """Return deterministic vocabulary matches without resolving ambiguity."""

    found: list[str] = []
    for pattern, canonical in _MATERIAL_PATTERNS:
        if pattern.search(message) and canonical not in found:
            found.append(canonical)
    return tuple(found)


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
    found = extract_material_candidates(message)

    if len(found) != 1:
        return None

    result: dict[str, str] = {"material": found[0]}

    seal_type = extract_seal_type(message)
    if seal_type is not None:
        result["type"] = seal_type

    return result
