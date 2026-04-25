"""DocumentInput to ProposedCaseDelta helpers.

The extractor is intentionally deterministic and conservative: document values are
never applied directly to the governed state. They become proposed deltas that the
user can accept or reject through the existing case-delta review path.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from app.agent.state.models import ProposedCaseDelta, ProposedCaseDeltaField

_NUMBER = r"(-?\d+(?:[,.]\d+)?)"


def _as_float(value: str) -> float:
    number = float(value.replace(",", "."))
    return int(number) if number.is_integer() else number


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _first_match(pattern: str, text: str, *, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return str(match.group(1)).strip()


def _append_field(
    fields: list[ProposedCaseDeltaField],
    seen: set[str],
    *,
    field_name: str,
    value: Any,
    unit: str | None = None,
    confidence: str = "inferred",
) -> None:
    if field_name in seen or value in (None, "", []):
        return
    seen.add(field_name)
    fields.append(
        ProposedCaseDeltaField(
            field_name=field_name,
            proposed_value=value,
            unit=unit,
            provenance="documented",
            confidence=confidence,  # type: ignore[arg-type]
            source_turn_index=0,
            status="proposed",
        )
    )


def _extract_medium(text: str, tags: Iterable[str] | None) -> str | None:
    for tag in tags or []:
        match = re.match(r"medium\s*[:=]\s*(.+)", str(tag).strip(), flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(1))
    candidates = (
        "Salzwasser", "Wasser", "Dampf", "Oel", "Ol", "Oil", "Hydraulikoel", "Loesemittel",
        "Ethanol", "Methanol", "Saeure", "Lauge", "Luft", "Gas",
    )
    for candidate in candidates:
        if re.search(rf"\b{re.escape(candidate)}\b", text, flags=re.IGNORECASE):
            return "Oel" if candidate in {"Ol", "Oil"} else candidate
    return None


def document_delta_from_text(
    *,
    text: str,
    filename: str | None = None,
    category: str | None = None,
    tags: Iterable[str] | None = None,
) -> ProposedCaseDelta:
    """Project deterministic document hints into non-authoritative delta fields."""
    haystack = _clean_text(" ".join([filename or "", category or "", " ".join(tags or []), text or ""]))
    fields: list[ProposedCaseDeltaField] = []
    seen: set[str] = set()

    medium = _extract_medium(haystack, tags)
    _append_field(fields, seen, field_name="medium", value=medium, confidence="requires_confirmation")
    _append_field(fields, seen, field_name="medium_name", value=medium, confidence="requires_confirmation")

    pressure = _first_match(rf"(?:betriebsdruck|druck|pressure|\bp\b)\D{{0,24}}{_NUMBER}\s*bar\b", haystack)
    if pressure is not None:
        _append_field(fields, seen, field_name="pressure_bar", value=_as_float(pressure), unit="bar")

    temp_max = _first_match(rf"(?:temperatur\s*max(?:imum)?|temp(?:erature)?\s*max(?:imum)?|tmax)\D{{0,24}}{_NUMBER}\s*(?:deg\s*c|degc|c|°c)\b", haystack)
    if temp_max is not None:
        _append_field(fields, seen, field_name="temperature_max", value=_as_float(temp_max), unit="degC")

    temp_min = _first_match(rf"(?:temperatur\s*min(?:imum)?|temp(?:erature)?\s*min(?:imum)?|tmin)\D{{0,24}}{_NUMBER}\s*(?:deg\s*c|degc|c|°c)\b", haystack)
    if temp_min is not None:
        _append_field(fields, seen, field_name="temperature_min", value=_as_float(temp_min), unit="degC")

    temp = _first_match(rf"(?:temperatur|temperature|temp\.?|\bt\b)\D{{0,24}}{_NUMBER}\s*(?:deg\s*c|degc|c|°c)\b", haystack)
    if temp is not None:
        _append_field(fields, seen, field_name="temperature_c", value=_as_float(temp), unit="degC")

    speed = _first_match(rf"(?:drehzahl|speed|rpm|\bn\b)\D{{0,24}}{_NUMBER}\s*(?:rpm|1/min|min-1|min\^-1)\b", haystack)
    if speed is not None:
        _append_field(fields, seen, field_name="speed_rpm", value=_as_float(speed), unit="rpm")

    shaft = _first_match(rf"(?:welle|shaft|wellendurchmesser|durchmesser|diameter|\bd\b)\D{{0,24}}{_NUMBER}\s*mm\b", haystack)
    if shaft is not None:
        _append_field(fields, seen, field_name="shaft_diameter_mm", value=_as_float(shaft), unit="mm")

    if re.search(r"\b(?:ptfe|teflon)\b", haystack, flags=re.IGNORECASE):
        _append_field(fields, seen, field_name="material", value="PTFE", confidence="requires_confirmation")
    elif re.search(r"\b(?:fkm|viton)\b", haystack, flags=re.IGNORECASE):
        _append_field(fields, seen, field_name="material", value="FKM", confidence="requires_confirmation")

    if re.search(r"\b(?:rwdr|radialwellendichtring|radial shaft seal)\b", haystack, flags=re.IGNORECASE):
        _append_field(fields, seen, field_name="sealing_type", value="rwdr", confidence="requires_confirmation")
    elif re.search(r"\b(?:gleitringdichtung|mechanical seal)\b", haystack, flags=re.IGNORECASE):
        _append_field(fields, seen, field_name="sealing_type", value="mechanical_seal", confidence="requires_confirmation")

    return ProposedCaseDelta(fields=fields, source="document")
