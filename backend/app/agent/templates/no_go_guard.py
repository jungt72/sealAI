"""No-Go phrase guard for normal case-building chat turns.

Blueprint §18.3 / §27.1 / §31: normal case-building turns must not sound like an
"AI protocol" and must not contain final suitability/release wording. This guard
is **additive** and complements — it does not replace — the semantic claim guards
in ``app.agent.runtime.output_guard`` and the streamed approval-pattern guard in
``app.agent.communication.governed_answer_composer`` (which stays untouched).

Scope (Patch 2): structural protocol phrases + affirmative final-release wording.
It operates on the *rendered* chat markdown produced by the chat-style registry.
"""

from __future__ import annotations

import re

# Literal structural "AI protocol" phrases forbidden in a normal case turn
# (Blueprint §18.3 + §27.1 FORBIDDEN_NORMAL_TURN_PHRASES).
FORBIDDEN_NORMAL_TURN_PHRASES: tuple[str, ...] = (
    "Ich verstehe den Fall aktuell als",
    "Technisch relevant sind hier vor allem",
    "Als Nächstes wäre die wichtigste Frage",
    "Grenze:",
    "Bitte beachten Sie, dass",
    "Auf Basis Ihrer Angaben empfehle ich final",
    "Der optimale Dichtring ist",
)

# Extra forbidden phrases for low-confidence vision turns (Blueprint Golden H
# "Must not contain"): no final identification of product/material/part number.
VISUAL_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "Das ist sicher ein",
    "Material ist",
    "Artikelnummer ist",
)

# Affirmative final suitability/release wording (Blueprint §31 + V1.8 §5.4 "any
# final suitability/release wording", incl. "können Sie bedenkenlos"). Refusals
# (e.g. "kann ich nicht freigeben", "nicht bedenkenlos") are intentionally NOT
# matched: each pattern keeps the release verb adjacent / guards negation.
FINAL_RELEASE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE | re.UNICODE)
    for pattern in (
        r"\bgarantiert\s+(?:passt|passend|dicht|geeignet)\b",
        r"\bempfehle\s+ich\s+final\b",
        r"\bder\s+optimale\s+dichtring\s+ist\b",
        r"\bdie\s+(?:beste|optimale|richtige)\s+(?:l(?:ö|oe)sung|dichtung)\s+ist\b",
        r"\bfinal\s+(?:freigegeben|geeignet|zugelassen)\b",
        # V1.8 §5.4 literal "können Sie bedenkenlos …": affirmative assurance only.
        # Requiring "können" BEFORE "bedenkenlos" (within 3 words) excludes the
        # interrogative/refusal "… bedenkenlos einsetzen können" (können follows).
        r"\bk(?:ö|oe)nnen\b(?:\s+\w+){0,3}\s+bedenkenlos\b",
    )
)


class NoGoPhraseError(ValueError):
    """Raised when forbidden chat wording reaches the guard."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("no_go_phrase_detected: " + "; ".join(violations))


def detect_no_go_phrases(
    text: str,
    forbidden_phrases: tuple[str, ...] = FORBIDDEN_NORMAL_TURN_PHRASES,
    *,
    include_final_release: bool = True,
) -> list[str]:
    """Return all forbidden phrases/patterns found in ``text`` (empty = clean)."""
    if not text:
        return []
    haystack = text.lower()
    violations: list[str] = [
        phrase for phrase in forbidden_phrases if phrase.lower() in haystack
    ]
    if include_final_release:
        violations.extend(
            pattern.pattern
            for pattern in FINAL_RELEASE_PATTERNS
            if pattern.search(text)
        )
    return violations


def assert_no_no_go(
    text: str,
    forbidden_phrases: tuple[str, ...] = FORBIDDEN_NORMAL_TURN_PHRASES,
    *,
    include_final_release: bool = True,
) -> None:
    """Raise :class:`NoGoPhraseError` if forbidden wording is present."""
    violations = detect_no_go_phrases(
        text, forbidden_phrases, include_final_release=include_final_release
    )
    if violations:
        raise NoGoPhraseError(violations)


def sanitize_no_go(
    text: str,
    forbidden_phrases: tuple[str, ...] = FORBIDDEN_NORMAL_TURN_PHRASES,
    *,
    include_final_release: bool = True,
) -> str:
    """Best-effort removal of forbidden literal phrases (non-strict callers)."""
    cleaned = text
    for phrase in forbidden_phrases:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)
    if include_final_release:
        for pattern in FINAL_RELEASE_PATTERNS:
            cleaned = pattern.sub("", cleaned)
    # Collapse whitespace gaps left behind by removals.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
