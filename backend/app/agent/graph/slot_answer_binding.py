"""Structured pending-question slot answer binding for governed turns.

The resolver intentionally reads backend `PendingQuestion` state, never prior
assistant wording. Field-specific adapters can be added incrementally while the
outer contract stays generic.
"""
from __future__ import annotations

import re
from typing import Any

from app.agent.domain.medium_registry import classify_medium_value
from app.agent.state.models import PendingQuestion, SlotAnswerBinding

_SHORT_SLOT_MAX_CHARS = 36
_SHORT_SLOT_DENY_RE = re.compile(
    r"\b(?:ja|nein|ok|okay|klar|danke|hallo|hi|servus|druck|temperatur|drehzahl|welle|mm|bar|rpm|u/min|grad)\b",
    re.IGNORECASE,
)
_STRONG_NEW_REQUEST_RE = re.compile(
    r"\b(?:ich brauche|ich habe|wir haben|bitte lege|auslegen|vergleiche|was ist|was bedeutet|wie funktioniert)\b",
    re.IGNORECASE,
)


def _clean_short_answer(message: str) -> str:
    return str(message or "").strip(" \t\n\r.,;:!")


def _looks_like_short_slot_answer(message: str) -> bool:
    text = _clean_short_answer(message)
    if not text or len(text) > _SHORT_SLOT_MAX_CHARS:
        return False
    if "?" in text or "\n" in text:
        return False
    if re.search(r"\d", text):
        return False
    if _STRONG_NEW_REQUEST_RE.search(text):
        return False
    words = [part for part in re.split(r"\s+", text) if part]
    if not words or len(words) > 3:
        return False
    if _SHORT_SLOT_DENY_RE.fullmatch(text) or _SHORT_SLOT_DENY_RE.search(text):
        return False
    return bool(re.search(r"[a-zA-ZäöüÄÖÜß]", text))


def _titlecase_answer(raw: str) -> str:
    text = _clean_short_answer(raw)
    return text[:1].upper() + text[1:]


def _resolve_medium_answer(
    *,
    pending_question: PendingQuestion,
    message: str,
    turn_index: int,
) -> SlotAnswerBinding | None:
    if pending_question.expected_answer_type != "medium_value":
        return None
    if not _looks_like_short_slot_answer(message):
        return None

    raw = _clean_short_answer(message)
    decision = classify_medium_value(raw)
    normalized: Any = decision.canonical_label or _titlecase_answer(raw)
    confidence = 0.92 if decision.mapping_confidence in {"confirmed", "estimated"} else 0.72
    needs_clarification = decision.mapping_confidence == "requires_confirmation" or decision.canonical_label is None

    return SlotAnswerBinding(
        target_field="medium",
        raw_value=raw,
        normalized_value=normalized,
        source="pending_question",
        confidence=confidence,
        ambiguity=needs_clarification,
        needs_clarification=needs_clarification,
        turn_index=turn_index,
    )


def resolve_slot_answer_binding(
    *,
    pending_question: PendingQuestion | None,
    message: str,
    turn_index: int,
    already_extracted_fields: set[str] | None = None,
) -> SlotAnswerBinding | None:
    """Bind a short current user answer to a structured pending slot.

    The function is generic by contract and dispatches to field adapters. For
    this patch only `medium` is actively supported.
    """

    if pending_question is None or pending_question.status != "open":
        return None
    already_extracted_fields = set(already_extracted_fields or set())
    target_field = str(pending_question.target_field or "").strip()
    if not target_field or target_field in already_extracted_fields:
        return None
    if target_field == "medium":
        return _resolve_medium_answer(
            pending_question=pending_question,
            message=message,
            turn_index=turn_index,
        )
    return None
