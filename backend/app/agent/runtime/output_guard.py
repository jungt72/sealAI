"""
Fast-Path Output Guard — Phase 0C.1

Deterministic post-generation safety check for user-visible LLM text.
Applied exclusively to fast_guidance_node output — the structured-path
final reply is already fully deterministic (build_final_reply) and
requires no guard here.

Rules (lexical, Phase 1 — Blueprint Section 4.9):
  - Manufacturer names        → always block
  - Recommendation language   → always block
  - Suitability assertions    → always block
  - Implicit approval phrases → always block

Material/compound names alone (e.g. "FKM ist ein Fluorelastomer") are
intentionally NOT blocked: the fast path legitimately handles knowledge
questions. What is blocked is recommendation or fitness-for-use intent.

On violation: FAST_PATH_GUARD_FALLBACK is returned instead of LLM text.
The boundary disclaimer is still appended by the caller (graph.py).
"""
from __future__ import annotations

import logging
import re
from typing import Sequence

from app.agent.runtime.surface_claims import get_surface_claims_spec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern categories
# ---------------------------------------------------------------------------

# Hersteller — must never appear in any output
_MANUFACTURER_PATTERNS: Sequence[str] = (
    r"\b(Freudenberg|Simrit|SKF|Parker(?:\s+Hannifin)?|Trelleborg|NOK|Garlock"
    r"|Merkel|Elring|Victor\s*Reinz|Hutchinson|Hallite|Busak\+Shamban)\b",
)

# Explicit recommendation verbs / phrases
_RECOMMENDATION_PATTERNS: Sequence[str] = (
    r"\b(empfehle|empfehlen|empfiehlt|empfohlen)\b",
    r"\b(schlage\s+\w*\s*vor|schlage\s+vor)\b",
    r"\b(rate\s+zu|würde\s+\w+\s+nehmen"
    r"|sollte[n]?\s+\w+\s+(?:verwenden|einsetzen|nutzen|nehmen|wählen))\b",
    r"\b(am\s+besten\s+(?:wählen|nehmen|einsetzen|verwenden))\b",
)

# Suitability / fitness-for-use assertions
_SUITABILITY_PATTERNS: Sequence[str] = (
    r"\b\w+\s+ist\s+(?:gut\s+)?geeignet\b",
    r"\bmaterial\s+ist\s+geeignet\b",
    r"\b(bestens|gut|hervorragend|sehr\s+gut)\s+geeignet\b",
    r"\b\w+\s+eignet\s+sich(?:\s+\w+){0,5}\s+für\b",
    r"\beignet\s+sich(?:\s+\w+){0,5}\s+für\b",
    r"\bgeeignet\s+macht\b",
    r"\bmacht\b.{0,120}\bgeeignet\b",
    r"\b(ideal|optimal|perfekt)\s+für\b",
    r"\b(unkritisch|problemlos|bedenkenlos|ohne\s+Bedenken)\b",
    r"\bkein\s+Problem\b",
    # NOTE: r"\bdas\s+(geht|passt|funktioniert)\b" was removed — too broad.
    # "Das funktioniert durch..." is legitimate mechanism explanation, not a
    # suitability assertion. "Das geht problemlos" is still caught by "problemlos".
    r"\b(freigegeben|zugelassen)\s+für\b",
)

# Comparative application ranking / material preference. The doctrine forbids
# stating one material is better / more suitable / preferable for an application.
# Patterns are intentionally narrow: only application-preference constructions,
# NEVER bare property comparison ("bessere X als Y"). \bbesser\s+ excludes both
# "bessere" and "verbessert". Proven against material_comparison.py profiles and
# the full deterministic comparison renderer (zero false positives) — see
# tests/test_comparative_ranking_guard. Prompt (#1) + deterministic passthrough
# (#4) stay primary; this denylist is a leaky backstop.
_COMPARATIVE_RANKING_PATTERNS: Sequence[str] = (
    r"\bbesser\s+geeignet\s+(?:für|fuer|bei|zu|als)\b",
    r"\bbesser\s+f(?:ü|ue)r\b[^.\n]{0,60}\bgeeignet\b",
    r"\bgeeigneter\s+(?:für|fuer|bei|als)\b",
    r"\bf(?:ü|ue)r\s+(?:\w+\s+){1,5}bevorzugt\b",
    r"\bvorzuziehen\b",
    r"\bdie\s+bessere\s+wahl\b",
    r"\bbesser\s+(?:zu\s+)?handhaben\b",
)

# Explicit compliance / final-release overclaims. These phrases are forbidden
# without evidence and must not be emitted by free LLM text.
_COMPLIANCE_OVERCLAIM_PATTERNS: Sequence[str] = (
    r"\bfda[-\s]?konform\b",
    r"\batex[-\s]?zertifiziert\b",
    r"\b(?:fda|atex|ehedg|ta[-\s]?luft|trinkwasser|usp|gmp)[-\s]?"
    r"(?:konform|zugelassen|zertifiziert|freigegeben|bestätigt|bestaetigt)\b",
    r"\b(?:eu\s*1935/2004|eu\s*10/2011)[-\s]?"
    r"(?:konform|zugelassen|zertifiziert|freigegeben|bestätigt|bestaetigt)\b",
    r"\b(?:fda|atex|ehedg|ta[-\s]?luft|trinkwasser|usp|gmp)[-\s]?"
    r"konformität\s+(?:bestätigt|bestaetigt)\b",
    r"\b(?:konform|zugelassen|zertifiziert|freigegeben)\s+(?:nach|gemäß|gemaess)\b",
    r"\bfood\s+contact\s+freigegeben\b",
    r"\btrinkwasser\s+zugelassen\b",
    r"\b(?:pharma|lebensmittel|food)\s+(?:freigegeben|zugelassen|zertifiziert)\b",
    r"\bchemisch\s+(?:beständig|bestaendig|geeignet)\b",
    r"\b\w+\s+ist\s+(?:chemisch\s+)?(?:beständig|bestaendig)\s+gegen\b",
    r"\bmaterial\s+ist\s+geeignet\b",
    r"\bdichtung\s+ist\s+freigegeben\b",
    r"\btechnisch\s+validiert\b",
    r"\bgarantiert\s+passend\b",
    r"\bfinal\s+freigegeben\b",
)

# Form-dump phrases are disallowed by v0.4: SeaLAI asks one good next
# question instead of dumping a checklist into the chat surface.
_FORM_DUMP_PATTERNS: Sequence[str] = (
    r"\bbitte\s+nennen\s+sie\s+alle\s+folgenden\s+angaben\b",
    r"\bbitte\s+nenne\s+(?:mir\s+)?alle\s+folgenden\s+angaben\b",
    r"\b(?:nennen|nenne)\s+sie\s+alle\s+folgenden\s+parameter\b",
)

# Compile all patterns once at import time
_COMPILED: list[tuple[str, re.Pattern[str]]] = []
for _cat, _pats in (
    ("manufacturer", _MANUFACTURER_PATTERNS),
    ("recommendation", _RECOMMENDATION_PATTERNS),
    ("suitability", _SUITABILITY_PATTERNS),
    ("comparative_ranking", _COMPARATIVE_RANKING_PATTERNS),
    ("compliance_overclaim", _COMPLIANCE_OVERCLAIM_PATTERNS),
    ("form_dump", _FORM_DUMP_PATTERNS),
):
    for _p in _pats:
        _COMPILED.append((_cat, re.compile(_p, re.IGNORECASE | re.UNICODE)))

# ---------------------------------------------------------------------------
# Safe fallback (deterministic, never LLM-generated)
# ---------------------------------------------------------------------------

FAST_PATH_GUARD_FALLBACK = get_surface_claims_spec("conversational_answer")["fallback_text"]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_fast_path_output(text: str) -> tuple[bool, str | None]:
    """Check LLM output text for policy violations.

    Args:
        text: Raw LLM output string.

    Returns:
        (safe, violation_category):
            safe=True, violation_category=None  → text is clean
            safe=False, violation_category=str  → violation detected;
                caller MUST substitute FAST_PATH_GUARD_FALLBACK
    """
    for category, pattern in _COMPILED:
        if pattern.search(text):
            logger.warning(
                "[output_guard] fast-path policy violation (category=%s) "
                "— substituting safe fallback. pattern=%r",
                category,
                pattern.pattern,
            )
            return False, category
    lowered = str(text or "").lower()
    for fragment in get_surface_claims_spec("conversational_answer")["forbidden_fragments"]:
        if fragment.lower() in lowered:
            logger.warning(
                "[output_guard] fast-path surface-claim violation (fragment=%r) "
                "— substituting safe fallback",
                fragment,
            )
            return False, "surface_claims"
    return True, None
