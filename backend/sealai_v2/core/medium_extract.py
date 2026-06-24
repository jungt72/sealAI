"""Pure extractor: canonical Medium aus Freitext -> str | None.

No I/O, no LLM, no mutation, no float literals.
Feeds Case.medium for the Gegencheck operation (Modus E).

Symmetric sibling of ``seal_spec_extract``: where that extractor owns the
material vocabulary, this one owns the MEDIUM vocabulary — both transcribed from
the §4 Verträglichkeitsmatrix allowlist (``scope.medium``) so the matrix stays the
single owner of the compatibility vocabulary. Import boundary I3 forbids a runtime
``knowledge/`` import, so the vocab is duplicated here and kept honest by an
allowlist-drift TEST (``test_medium_matrix_drift``), exactly like the material side.

"Never guess" doctrine (mirrors the material extractor): an unrecognised or
AMBIGUOUS medium (≥2 distinct canonical media) fails CLOSED to ``None`` — the safe
direction for a disqualify-only Gegencheck, since "no medium" abstains rather than
risking a wrong verdict on the wrong medium.
"""

from __future__ import annotations

import re

# Canonical medium tags from the Verträglichkeitsmatrix allowlist (scope.medium).
# Key: token to match (case-insensitive, word boundary); value: canonical tag.
# Singular/plural + spelling variants collapse to ONE canonical; OVERLAPPING tags
# (Mineralöl / Mineralöl-Hydraulik) collapse too, so a single phrase never reads as
# "≥2 distinct media" and falsely fails closed. Genuinely different media stay
# distinct (and co-occurrence → ambiguous → None, the conservative abstain).
_MEDIUM_SYNONYMS: dict[str, str] = {
    "aceton": "Aceton",
    "amin": "Amin",
    "amine": "Amin",
    "aminhaltig": "Amin",
    "base": "Base",
    "basen": "Base",
    "bioöl": "Bioöl",
    "bremsflüssigkeit": "Bremsflüssigkeit",
    "dampf": "Dampf",
    "heißdampf": "Heißdampf",
    "sattdampf": "Sattdampf",
    "sip": "SIP",
    "sterilisation": "Sterilisation",
    "ester": "Ester",
    "esteröl": "Ester",
    "fett": "Fett",
    "fette": "Fett",
    "fetthaltig": "Fett",
    "getriebeöl": "Getriebeöl",
    "glykol": "Glykol",
    "hfc": "HFC",
    "hfd-r": "HFD-R",
    "heißwasser": "Heißwasser",
    "hydrauliköl": "Hydrauliköl",
    "kakaobutter": "Kakaobutter",
    "keton": "Keton",
    "ketone": "Keton",
    "kohlenwasserstoffe": "Kohlenwasserstoffe",
    "kühlmittel": "Kühlmittel",
    "lauge": "Lauge",
    "naoh": "Lauge",
    "natronlauge": "Lauge",
    "lebensmittel": "Lebensmittel",
    "mineralöl": "Mineralöl",
    "mineralöl-hydraulik": "Mineralöl",
    "ozon": "Ozon",
    "schokolade": "Schokolade",
    "synthetiköl": "Synthetiköl",
    "uv": "UV",
    "witterung": "Witterung",
    "öl": "Öl",
}

# Compiled patterns for all medium tokens (word-boundary, case-insensitive).
# Longest token first so a specific tag (Mineralöl-Hydraulik) is tried before its
# substring overlap — both map to the same canonical, but ordering keeps matching
# deterministic and obvious.
_MEDIUM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b" + re.escape(token) + r"\b", re.IGNORECASE), canonical)
    for token, canonical in sorted(
        _MEDIUM_SYNONYMS.items(), key=lambda kv: -len(kv[0])
    )
]


def extract_medium(message: str) -> str | None:
    """Extract a single canonical medium from a free-text message.

    Returns the canonical medium tag on success, or ``None`` when:
    - no medium is recognised (conservative — never guesses), or
    - more than one distinct canonical medium is found (ambiguous, fail-closed).
    """
    found: list[str] = []
    for pattern, canonical in _MEDIUM_PATTERNS:
        if pattern.search(message) and canonical not in found:
            found.append(canonical)

    if len(found) != 1:
        return None
    return found[0]
