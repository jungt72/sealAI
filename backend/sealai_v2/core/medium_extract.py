"""Pure extractor: canonical Medium aus Freitext -> str | None.

No I/O, no LLM, no mutation, no float literals.
Feeds Case.medium for the Gegencheck operation (Modus E).

Symmetric sibling of ``seal_spec_extract``: where that extractor owns the
material vocabulary, this one owns the MEDIUM vocabulary — both transcribed from
the §4 Verträglichkeitsmatrix allowlist (``scope.medium``) so the matrix stays the
single owner of the compatibility vocabulary. Import boundary I3 forbids a runtime
``knowledge/`` import, so the vocab is duplicated here and kept honest by an
allowlist-drift TEST (``test_medium_matrix_drift``), exactly like the material side.

"Never guess" doctrine (mirrors the material extractor): an UNRECOGNISED medium
yields nothing. But a real seal-check names ONE medium with SEVERAL vocab tags
("Heißdampf-Sterilisation (SIP)" → three tags for one steam medium; "Synthetiköl
mit Ester" → two for one oil), so collecting ALL matched canonical media and letting
the disqualify-lean kernel fold over every matching cell is both correct and SAFE:
a co-mentioned disqualifying medium (e.g. "Mineralöl + Aceton") then wins the verdict
instead of being silently dropped. ``extract_media`` returns the full set;
``extract_medium`` keeps the single-value convenience API (the primary match).
"""

from __future__ import annotations

import re

from sealai_v2.core.contracts import RememberedFact

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
    for token, canonical in sorted(_MEDIUM_SYNONYMS.items(), key=lambda kv: -len(kv[0]))
]


def extract_media(message: str) -> tuple[str, ...]:
    """Extract ALL distinct canonical media from a free-text message.

    Deterministic order: longest match token first (most specific tag wins position),
    then first-seen. Empty tuple when nothing is recognised (never guesses). Overlapping
    tags that map to the SAME canonical collapse (Mineralöl / Mineralöl-Hydraulik → one).
    The Gegencheck stage joins these into the kernel query so its disqualify-lean fold
    runs over every matching matrix cell — a disqualifying medium is never dropped.
    """
    found: list[str] = []
    for pattern, canonical in _MEDIUM_PATTERNS:
        if pattern.search(message) and canonical not in found:
            found.append(canonical)
    return tuple(found)


def extract_medium(message: str) -> str | None:
    """Single-value convenience: the PRIMARY canonical medium (first of ``extract_media``),
    or ``None`` when none is recognised. Used for the Case.medium display name; the stage
    uses the full ``extract_media`` set for the verdict."""
    media = extract_media(message)
    return media[0] if media else None


# Phase-1 Medium-Wiring: canonical medium → the form's coarse Universal-Core category
# (frontend schema/situations.ts UNIVERSAL_CORE "medium" enum). Lossy BY DESIGN — the SPECIFIC
# medium is the value that matters for material/type selection; the category is only a coarse bucket.
# Unmapped (acids, food, chemicals, environmental conditions) → "Sonstiges" (Phase 2's LLM gives them
# a real medium-intelligence profile). Kept tiny + deterministic; not a knowledge claim.
_MEDIUM_CATEGORY: dict[str, str] = {
    "Hydrauliköl": "Öl",
    "Mineralöl": "Öl",
    "Synthetiköl": "Öl",
    "Getriebeöl": "Öl",
    "Bioöl": "Öl",
    "Ester": "Öl",
    "Öl": "Öl",
    "Fett": "Fett",
    "Heißwasser": "Wasser",
    "Dampf": "Wasser",
    "Heißdampf": "Wasser",
    "Sattdampf": "Wasser",
    "Kühlmittel": "Kühlmittel",
}


def medium_category(canonical: str) -> str:
    """The coarse form category for a canonical medium (lossy; unmapped → ``"Sonstiges"``)."""
    return _MEDIUM_CATEGORY.get(canonical, "Sonstiges")


def extract_medium_facts(message: str) -> tuple[RememberedFact, ...]:
    """Phase-1 Medium-Wiring: the PRIMARY stated medium as case-state facts so the form HYDRATES it
    and L1 / the optimal-solution evaluation SEE it in the state. ``feld="medium"`` = the specific
    canonical (e.g. "Hydrauliköl"); ``feld="medium_kategorie"`` = the coarse form category. Empty
    when no §4-vocab medium is recognised (Phase 2's LLM step covers truly any medium). Deterministic,
    no I/O, no LLM — so it RELIABLY persists the medium that the LLM distiller may otherwise drop."""
    primary = extract_medium(message)
    if not primary:
        return ()
    return (
        RememberedFact(feld="medium", wert=primary, provenance="chat-inline"),
        RememberedFact(
            feld="medium_kategorie",
            wert=medium_category(primary),
            provenance="chat-inline",
        ),
    )
