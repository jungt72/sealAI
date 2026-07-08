"""Legal-by-Design Phase D (Goal 6): deterministic risk-flag detection over the user's question
text — no LLM, no randomness, cannot be "talked out of" by a model. Reuses
``core.legal_doctrine.RISK_TRIGGER_TERMS`` (one shared list — also the L1-prompt-hardening
vocabulary and the UI-terminology-lint fixture) so the trigger vocabulary never drifts across
consumers.

Doctrine (owner-specified): a match does NOT hard-block the turn — it MARKS it for restriction/
review. Three independent, always-on surfaces render the same signal: ``PipelineResult.risk_flags``
(chat/briefing response → SPA badge), the PDF export badge (``frontend-v2/src/lib/pdf.ts``), and —
only when ``SEALAI_V2_RISK_FLAG_PROMPT_ENABLED`` is explicitly turned on — an additional L1 prompt
instruction (``prompts/system_l1.jinja``'s ``{% if risk_flags %}`` block). The deterministic
detection+display path is the PRIMARY guarantee (always on, never depends on an LLM behaving); the
prompt reinforcement is a secondary, opt-in layer. See docs/ai-safety-guardrails.md.
"""

from __future__ import annotations

import re

from sealai_v2.core.legal_doctrine import RISK_TRIGGER_TERMS

_PATTERNS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (term, re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE))
    for term in RISK_TRIGGER_TERMS
)


def detect_risk_flags(text: str) -> tuple[str, ...]:
    """Returns the subset of RISK_TRIGGER_TERMS found in ``text`` — order matches
    RISK_TRIGGER_TERMS, each term at most once. Empty/falsy text -> empty tuple. Word-boundary
    matched (so "CE" doesn't fire inside an unrelated word) and case-insensitive."""
    if not text:
        return ()
    return tuple(term for term, pattern in _PATTERNS if pattern.search(text))


RISK_WARNING_TEXT = (
    "⚠️ Potenziell regulierter oder sicherheitskritischer Anwendungsbereich erkannt. sealingAI "
    "liefert hierzu ausschließlich informative Strukturierung — keine Empfehlung, keine Eignungs-, "
    "Freigabe- oder Konformitätsaussage. Eine Prüfung durch den Hersteller bzw. die zuständige "
    "Fachstelle ist vor produktiver Nutzung zwingend erforderlich."
)
