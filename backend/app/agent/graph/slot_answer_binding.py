"""Structured pending-question slot answer binding for governed turns.

The resolver intentionally reads backend `PendingQuestion` state, never prior
assistant wording. Field-specific adapters can be added incrementally while the
outer contract stays generic.
"""
from __future__ import annotations

import re
from typing import Any

from app.agent.domain.medium_registry import classify_medium_value, is_medium_placeholder_value
from app.agent.domain.normalization import normalize_sealing_type_value
from app.agent.state.models import PendingQuestion, SlotAnswerBinding

_SHORT_SLOT_MAX_CHARS = 36
_SHORT_SLOT_DENY_RE = re.compile(
    r"\b(?:ja|nein|ok|okay|klar|danke|hallo|hi|servus|prima|super|klasse|top|perfekt|passt|gern|gerne|los\s+geht'?s|druck|temperatur|drehzahl|welle|mm|bar|rpm|u/min|grad)\b",
    re.IGNORECASE,
)
_SOCIAL_ACK_SHORT_RE = re.compile(
    r"^\s*(?:"
    r"(?:jo|ja|yes|yep|jep|okay|ok|klar|alles\s+klar|passt|passt\s+scho(?:n)?|klingt\s+gut|"
    r"prima+|su+per|top|perfekt|klasse|sehr\s+gut|gut|gern(?:e)?|"
    r"lass\s+uns\s+(?:loslegen|starten)|los\s+geht'?s|"
    r"ich\s+bin\s+(?:auch\s+)?gespannt|bin\s+(?:auch\s+)?gespannt|"
    r"freue\s+mich|machen\s+wir|leg\s+los)"
    r")\s*[.!?]*\s*$",
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
# Tolerant short-answer markers (§7.5/§7.6): leading fillers and approximation
# words around a single numeric value, e.g. "jo ca 3000", "etwa 80 grad".
_APPROX_MARKER_RE = re.compile(
    r"\b(?:ca|circa|zirka|etwa|ungef(?:ä|ae)hr|rund|knapp|so\s+um\s+die|um\s+die|"
    r"in\s+etwa|vielleicht|gesch(?:ä|ae)tzt|sch(?:ä|ae)tze|grob|gut)\b\.?",
    re.IGNORECASE,
)
_TOLERANT_DIGITS_RE = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
_PRESSURE_VALUE_RE = re.compile(r"\b([+-]?\d+(?:[.,]\d+)?)\s*bar\b", re.IGNORECASE)

_PRESSURE_CONTEXT_TARGET_FIELD: dict[str, str] = {
    "system_pressure": "pressure_system_bar",
    "direct_at_seal": "pressure_at_seal_bar",
    "differential": "pressure_delta_bar",
}
_PRESSURE_ROLE_FIELDS: frozenset[str] = frozenset(
    {
        "pressure_system_bar",
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "ambiguous_pressure_bar",
    }
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
    if _SOCIAL_ACK_SHORT_RE.match(text):
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


def _tolerant_numeric_answer(message: str) -> tuple[float | None, bool]:
    """Parse a single numeric value out of a short, noisy answer.

    Handles leading fillers and approximation words ("jo ca 3000", "etwa 80")
    that the strict :data:`_NUMBER_RE` rejects. Returns (value, approximate).
    Conservative: requires exactly one number and a short answer; refuses
    strong new-request phrasing so it only fires as a pending-slot answer.
    """
    text = _clean_short_answer(message)
    if not text or "?" in text or "\n" in text:
        return None, False
    if _STRONG_NEW_REQUEST_RE.search(text):
        return None, False
    words = [part for part in re.split(r"\s+", text) if part]
    if len(words) > 5:
        return None, False
    numbers = _TOLERANT_DIGITS_RE.findall(text)
    if len(numbers) != 1:
        return None, False
    approximate = bool(_APPROX_MARKER_RE.search(text))
    try:
        return float(numbers[0].replace(",", ".")), approximate
    except ValueError:
        return None, False


def _pressure_value_answer(message: str) -> float | None:
    match = _PRESSURE_VALUE_RE.search(str(message or "").strip())
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
    if is_medium_placeholder_value(raw):
        return None
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
    if not raw or is_medium_placeholder_value(raw):
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
        value = _pressure_value_answer(text)
        target_field = _PRESSURE_CONTEXT_TARGET_FIELD.get(pressure_context)
        if target_field is not None and value is not None and "bar" in lowered:
            return SlotAnswerBinding(
                target_field=target_field,
                raw_value=text,
                normalized_value=value,
                source="pending_question",
                confidence=0.94,
                ambiguity=False,
                needs_clarification=False,
                turn_index=turn_index,
            )
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
        value = _pressure_value_answer(text)
        if value is not None and "bar" in lowered:
            if str(pending_question.target_field or "").strip() in _PRESSURE_ROLE_FIELDS:
                target_field = str(pending_question.target_field).strip()
            else:
                target_field = "ambiguous_pressure_bar"
            return SlotAnswerBinding(
                target_field=target_field,
                raw_value=text,
                normalized_value=value,
                source="pending_question",
                confidence=0.92,
                ambiguity=target_field == "ambiguous_pressure_bar",
                needs_clarification=target_field == "ambiguous_pressure_bar",
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
    # Strict path first: preserves exact existing behaviour for clean answers.
    value = _numeric_answer(text)
    approximate = False
    if value is None:
        # Tolerant fallback for filler/approximation answers ("jo ca 3000").
        value, approximate = _tolerant_numeric_answer(text)
    if value is None:
        return None
    return SlotAnswerBinding(
        target_field=target_field,
        raw_value=text,
        normalized_value=value,
        source="pending_question",
        confidence=0.88 if approximate else 0.92,
        ambiguity=False,
        needs_clarification=False,
        approximate=approximate,
        turn_index=turn_index,
    )


# Yes / no / explicitly-unknown short answers for a boolean-style pending slot
# (e.g. the mobile triage "Dreht sich die Welle im Betrieb?" → shaft_rotates).
# Order of checks matters: "weiß ich nicht" contains "nicht", so unknown wins
# over no, and no wins over yes ("dreht sich nicht" is a no, not a yes).
_YNU_UNKNOWN_RE = re.compile(
    r"\b(?:wei(?:ß|ss)\s+ich\s+nicht|kein(?:e)?\s+ahnung|unbekannt|unklar|unsicher|"
    r"unknown|nicht\s+sicher|k\.?\s?a\.?)\b",
    re.IGNORECASE,
)
_YNU_NO_RE = re.compile(
    r"^(?:nein|n(?:ö|oe)|ne|no(?:pe)?|steht(?:\s+still)?|statisch|static|"
    r"dreht\s+(?:sich\s+)?nicht|keine\s+drehung)\b",
    re.IGNORECASE,
)
_YNU_YES_RE = re.compile(
    r"^(?:ja|jo|jep|jup|yes|yep|klar|sicher|genau|stimmt|"
    r"dreht(?:\s+sich)?|rotiert|l(?:ä|ae)uft)\b",
    re.IGNORECASE,
)


def _resolve_yes_no_unknown_answer(
    *,
    pending_question: PendingQuestion,
    message: str,
    turn_index: int,
) -> SlotAnswerBinding | None:
    """Bind a "Ja" / "Nein" / "Weiß ich nicht" answer to a yes/no/unknown slot.

    Generic by expected answer type, so it serves the mobile triage shaft-rotation
    question and any other boolean slot. It returns a confirmation-required
    binding (the State Gate still owns persistence); it never asserts a fact here.
    """

    if str(pending_question.expected_answer_type or "") != "yes_no_unknown":
        return None
    target_field = str(pending_question.target_field or "").strip()
    if not target_field:
        return None
    text = _clean_short_answer(message)
    if not text or "?" in text or "\n" in text:
        return None
    if _YNU_UNKNOWN_RE.search(text):
        normalized = "unknown"
    elif _YNU_NO_RE.match(text):
        normalized = "no"
    elif _YNU_YES_RE.match(text):
        normalized = "yes"
    else:
        return None
    return SlotAnswerBinding(
        target_field=target_field,
        raw_value=text,
        normalized_value=normalized,
        source="pending_question",
        confidence=0.9,
        ambiguity=False,
        needs_clarification=False,
        turn_index=turn_index,
    )


def _resolve_sealing_type_answer(
    *,
    pending_question: PendingQuestion,
    message: str,
    turn_index: int,
) -> SlotAnswerBinding | None:
    target_field = str(pending_question.target_field or "").strip()
    expected_type = str(pending_question.expected_answer_type or "")
    if target_field not in {"sealing_type", "seal_type"}:
        return None
    if expected_type not in {"seal_type_value", "free_text_value"}:
        return None
    text = _clean_short_answer(message)
    if not text or "?" in text:
        return None
    normalized = normalize_sealing_type_value(text)
    if normalized is None:
        return None
    return SlotAnswerBinding(
        target_field="sealing_type",
        raw_value=text,
        normalized_value=normalized,
        source="pending_question",
        confidence=0.94,
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
    canonical_target_field = "sealing_type" if target_field == "seal_type" else target_field
    if not target_field or canonical_target_field in already_extracted_fields:
        return None
    if target_field == "medium":
        return _resolve_medium_answer(
            pending_question=pending_question,
            message=message,
            turn_index=turn_index,
        )
    if target_field == "pressure_bar" or target_field in _PRESSURE_ROLE_FIELDS:
        return _resolve_pressure_answer(
            pending_question=pending_question,
            message=message,
            turn_index=turn_index,
        )
    yes_no_unknown = _resolve_yes_no_unknown_answer(
        pending_question=pending_question,
        message=message,
        turn_index=turn_index,
    )
    if yes_no_unknown is not None:
        return yes_no_unknown
    sealing_type = _resolve_sealing_type_answer(
        pending_question=pending_question,
        message=message,
        turn_index=turn_index,
    )
    if sealing_type is not None:
        return sealing_type
    numeric = _resolve_numeric_slot_answer(
        pending_question=pending_question,
        message=message,
        turn_index=turn_index,
    )
    if numeric is not None:
        return numeric
    return None
