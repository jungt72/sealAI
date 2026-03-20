from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class NormalizationDecision:
    canonical_value: str
    status: str
    mapping_reason: str


_MATERIAL_DIRECT = {
    "nbr": "NBR",
    "ptfe": "PTFE",
    "fkm": "FKM",
    "ffkm": "FFKM",
    "epdm": "EPDM",
    "silikon": "SILIKON",
}
_MATERIAL_INFERRED = {
    "nitril": ("NBR", "material_synonym:nitril"),
    "teflon": ("PTFE", "trade_name_requires_confirmation:teflon"),
}
_MATERIAL_CONFIRMATION = {
    "viton": ("FKM", "trade_name_requires_confirmation:viton"),
    "kalrez": ("FFKM", "trade_name_requires_confirmation:kalrez"),
}

_MEDIUM_DIRECT = {
    "wasser": "Wasser",
    "water": "Wasser",
    "öl": "Öl",
    "oil": "Öl",
    "mineralöl": "Öl",
    "hydrauliköl": "Öl",
    "hlp": "Öl",
    "bio-öl": "Bio-Öl",
    "hees": "Bio-Öl",
}
_MEDIUM_INFERRED = {}
_MEDIUM_CONFIRMATION = {
    "panolin": ("Bio-Öl", "trade_name_requires_confirmation:panolin"),
    "ester": ("Bio-Öl", "trade_name_requires_confirmation:ester"),
}
_MEDIUM_ID = {
    "bio-öl": "hees",
    "panolin": "hees",
    "ester": "hees",
    "hees": "hees",
    "öl": "hlp",
    "oil": "hlp",
    "mineralöl": "hlp",
    "hydrauliköl": "hlp",
    "hlp": "hlp",
    "wasser": "wasser",
    "water": "wasser",
}


def _lowered(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def normalize_material_decision(value: Any) -> NormalizationDecision | None:
    lowered = _lowered(value)
    if lowered is None:
        return None
    if lowered in _MATERIAL_DIRECT:
        return NormalizationDecision(_MATERIAL_DIRECT[lowered], "confirmed", f"normalized_material:{lowered}")
    if lowered in _MATERIAL_INFERRED:
        canonical, reason = _MATERIAL_INFERRED[lowered]
        status = "confirmation_required" if reason.startswith("trade_name_requires_confirmation") else "inferred"
        return NormalizationDecision(canonical, status, reason)
    if lowered in _MATERIAL_CONFIRMATION:
        canonical, reason = _MATERIAL_CONFIRMATION[lowered]
        return NormalizationDecision(canonical, "confirmation_required", reason)
    return NormalizationDecision(str(value), "unknown", "material_unmapped")


def normalize_medium_decision(value: Any) -> NormalizationDecision | None:
    lowered = _lowered(value)
    if lowered is None:
        return None
    if lowered in _MEDIUM_DIRECT:
        return NormalizationDecision(_MEDIUM_DIRECT[lowered], "confirmed", f"normalized_medium:{lowered}")
    if lowered in _MEDIUM_INFERRED:
        canonical, reason = _MEDIUM_INFERRED[lowered]
        return NormalizationDecision(canonical, "inferred", reason)
    if lowered in _MEDIUM_CONFIRMATION:
        canonical, reason = _MEDIUM_CONFIRMATION[lowered]
        return NormalizationDecision(canonical, "confirmation_required", reason)
    return NormalizationDecision(str(value), "unknown", "medium_unmapped")


def normalize_material(value: Any) -> Any:
    decision = normalize_material_decision(value)
    return None if decision is None else decision.canonical_value


def normalize_medium(value: Any) -> Any:
    lowered = _lowered(value)
    if lowered is None:
        return None
    if any(token in lowered for token in ("öliges", "wasserbasiert", "kühlschmierstoff", "emulsion")):
        return value
    decision = normalize_medium_decision(value)
    return None if decision is None else decision.canonical_value


def normalize_medium_id(value: Any) -> Any:
    lowered = _lowered(value)
    if lowered is None:
        return None
    if any(token in lowered for token in ("öliges", "wasserbasiert", "kühlschmierstoff", "emulsion")):
        return value
    return _MEDIUM_ID.get(lowered, value)


def normalize_unit_value(value: float, unit: str) -> tuple[float, str]:
    normalized_unit = unit.strip().lower()
    if normalized_unit == "psi":
        return float(value) / 14.5038, "bar"
    if normalized_unit == "f":
        return (float(value) - 32.0) * 5.0 / 9.0, "C"
    if normalized_unit in {"bar", "c"}:
        return float(value), "C" if normalized_unit == "c" else "bar"
    return float(value), unit


def extract_parameters(text: str) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    temp_match = re.search(r"(\d+(?:[.,]\d+)?)\s*°?\s*([CF])\b", text, re.I)
    if temp_match:
        raw = temp_match.group(0)
        value = float(temp_match.group(1).replace(",", "."))
        temp_value, _ = normalize_unit_value(value, temp_match.group(2))
        extracted["temperature_raw"] = raw
        extracted["temperature_c"] = temp_value
    pressure_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(bar|psi)\b", text, re.I)
    if pressure_match:
        raw = pressure_match.group(0)
        value = float(pressure_match.group(1).replace(",", "."))
        pressure_value, _ = normalize_unit_value(value, pressure_match.group(2))
        extracted["pressure_raw"] = raw
        extracted["pressure_bar"] = pressure_value
    diameter_match = re.search(r"(\d+(?:[.,]\d+)?)\s*mm\b", text, re.I)
    if diameter_match and re.search(r"\bwelle|\bshaft", text, re.I):
        extracted["diameter_mm"] = float(diameter_match.group(1).replace(",", "."))
    speed_match = re.search(r"(\d+(?:[.,]\d+)?)\s*rpm\b", text, re.I)
    if speed_match:
        extracted["speed_rpm"] = float(speed_match.group(1).replace(",", "."))

    for raw in ("Panolin", "HEES", "Ester", "Bio-Öl", "Wasser", "water", "Öl", "oil", "Mineralöl", "HLP"):
        if re.search(rf"\b{re.escape(raw)}\b", text, re.I):
            decision = normalize_medium_decision(raw)
            if decision and decision.status == "confirmation_required":
                extracted["medium_confirmation_required"] = decision.canonical_value
            elif decision and decision.status != "unknown":
                extracted["medium_normalized"] = decision.canonical_value
            if decision:
                extracted["medium_normalization_status"] = decision.status
                extracted["medium_mapping_reason"] = decision.mapping_reason
                extracted["medium_raw"] = raw
            break

    for raw in ("Viton", "Kalrez", "Teflon", "Nitril", "NBR", "PTFE", "FKM"):
        if re.search(rf"\b{re.escape(raw)}\b", text, re.I):
            decision = normalize_material_decision(raw)
            if decision and decision.status == "confirmation_required":
                extracted["material_confirmation_required"] = decision.canonical_value
            elif decision and decision.status != "unknown":
                extracted["material_normalized"] = decision.canonical_value
            if decision:
                extracted["material_normalization_status"] = decision.status
                extracted["material_mapping_reason"] = decision.mapping_reason
                extracted["material_raw"] = raw
            break

    return extracted
