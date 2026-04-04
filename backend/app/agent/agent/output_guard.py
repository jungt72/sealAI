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
    r"\b(bestens|gut|hervorragend|sehr\s+gut)\s+geeignet\b",
    r"\b(ideal|optimal|perfekt)\s+für\b",
    r"\b(unkritisch|problemlos|bedenkenlos|ohne\s+Bedenken)\b",
    r"\bkein\s+Problem\b",
    r"\bdas\s+(geht|passt|funktioniert)\b",
    r"\b(freigegeben|zugelassen)\s+für\b",
)

# Compile all patterns once at import time
_COMPILED: list[tuple[str, re.Pattern[str]]] = []
for _cat, _pats in (
    ("manufacturer", _MANUFACTURER_PATTERNS),
    ("recommendation", _RECOMMENDATION_PATTERNS),
    ("suitability", _SUITABILITY_PATTERNS),
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
