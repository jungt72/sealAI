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
_PRESSURE_DIRECT_RE = re.compile(
    r"\b(?:direkt\s+(?:an|auf)\s+der\s+(?:dichtung|dichtstelle|dichtlippe)|"
    r"an\s+der\s+(?:dichtung|dichtstelle|dichtlippe)|dichtstelle|dichtlippe)\b",
    re.IGNORECASE,
)
_PRESSURE_SYSTEM_RE = re.compile(
    r"\b(?:systemdruck|system\s*druck|system|anlage|leitungsdruck|pumpendruck)\b",
    re.IGNORECASE,
)
_PRESSURE_DIFFERENTIAL_RE = re.compile(
    r"\b(?:differenzdruck|druckdifferenz|druckunterschied|delta\s*p|dp|"
    r"ueber\s+der\s+dichtung|über\s+der\s+dichtung)\b",
    re.IGNORECASE,
)
_PRESSURE_GAUGE_RE = re.compile(
    r"\b(?:barg|bar\s*g|ueberdruck|überdruck|relativdruck|gauge)\b",
    re.IGNORECASE,
)
_PRESSURE_ABSOLUTE_RE = re.compile(
    r"\b(?:bara|bar\s*a|absolutdruck|absolute?r?\s+druck|absolute?)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*(?:bar|°?\s*c|grad|mm|rpm|u[/.]?\s*min)?\s*$", re.IGNORECASE)


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


def _numeric_answer(message: str) -> float | None:
    match = _NUMBER_RE.match(str(message or "").strip())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _resolve_medium_answer(
    *,
    pending_question: PendingQuestion,
    message: str,
    turn_index: int,
) -> SlotAnswerBinding | None:
    if pending_question.expected_answer_type != "medium_value":
        return None
    explicit_binding = _resolve_explicit_medium_answer(
        message=message,
        turn_index=turn_index,
    )
    if explicit_binding is not None:
        return explicit_binding
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


def _resolve_explicit_medium_answer(
    *,
    message: str,
    turn_index: int,
) -> SlotAnswerBinding | None:
    text = " ".join(str(message or "").strip().split())
    if not text:
        return None
    lowered = text.casefold()
    if "?" in text or any(token in lowered for token in ("warum", "wozu", "weshalb", "wieso")):
        return None
    match = re.search(
        r"\b(?:das\s+)?medium\s+(?:ist|waere|wäre|is|=|:)\s+([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9 /+\-.]{1,48})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    raw = match.group(1).strip(" .,!;:")
    if not raw:
        return None
    decision = classify_medium_value(raw)
    normalized: Any = decision.canonical_label or _titlecase_answer(raw)
    confidence = 0.9 if decision.mapping_confidence in {"confirmed", "estimated"} else 0.76
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


def _resolve_pressure_answer(
    *,
    pending_question: PendingQuestion,
    message: str,
    turn_index: int,
) -> SlotAnswerBinding | None:
    expected_type = str(pending_question.expected_answer_type or "")
    text = " ".join(str(message or "").strip().split())
    if not text or "?" in text:
        return None
    lowered = text.casefold()

    pressure_context: str | None = None
    if _PRESSURE_DIRECT_RE.search(text):
        pressure_context = "direct_at_seal"
    elif _PRESSURE_DIFFERENTIAL_RE.search(text):
        pressure_context = "differential"
    elif _PRESSURE_SYSTEM_RE.search(text):
        pressure_context = "system_pressure"
    elif _PRESSURE_GAUGE_RE.search(text):
        pressure_context = "gauge"
    elif _PRESSURE_ABSOLUTE_RE.search(text):
        pressure_context = "absolute"

    if pressure_context is not None and expected_type in {
        "pressure_context",
        "pressure_value_or_context",
    }:
        return SlotAnswerBinding(
            target_field="pressure_bar",
            raw_value=text,
            normalized_value={"pressure_context": pressure_context},
            source="pending_question",
            confidence=0.94,
            ambiguity=False,
            needs_clarification=False,
            turn_index=turn_index,
        )

    if expected_type in {"pressure_value", "pressure_value_or_context"}:
        value = _numeric_answer(text)
        if value is not None and "bar" in lowered:
            return SlotAnswerBinding(
                target_field="pressure_bar",
                raw_value=text,
                normalized_value=value,
                source="pending_question",
                confidence=0.92,
                ambiguity=False,
                needs_clarification=False,
                turn_index=turn_index,
            )
    return None


def _resolve_numeric_slot_answer(
    *,
    pending_question: PendingQuestion,
    message: str,
    turn_index: int,
) -> SlotAnswerBinding | None:
    target_field = str(pending_question.target_field or "").strip()
    expected_type = str(pending_question.expected_answer_type or "")
    if target_field not in {"temperature_c", "shaft_diameter_mm", "speed_rpm"}:
        return None
    if expected_type not in {"temperature_value", "length_mm_value", "rotational_speed_value"}:
        return None
    text = str(message or "").strip()
    if not text or "?" in text:
        return None
    value = _numeric_answer(text)
    if value is None:
        return None
    return SlotAnswerBinding(
        target_field=target_field,
        raw_value=text,
        normalized_value=value,
        source="pending_question",
        confidence=0.92,
        ambiguity=False,
        needs_clarification=False,
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

    The function is generic by contract and dispatches to field adapters. It
    intentionally uses the pending slot metadata, not previous assistant text.
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
    if target_field == "pressure_bar":
        return _resolve_pressure_answer(
            pending_question=pending_question,
            message=message,
            turn_index=turn_index,
        )
    numeric = _resolve_numeric_slot_answer(
        pending_question=pending_question,
        message=message,
        turn_index=turn_index,
    )
    if numeric is not None:
        return numeric
    return None
