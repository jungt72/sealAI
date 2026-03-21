"""
Normalization Layer V1 — Phase 0B.3

Deterministic translation from raw user/LLM-extracted values into
canonical domain values with explicit confidence grading.

Architecture:
  observed (raw)  →  normalize_parameter()  →  normalized layer
                           ↓ confidence
                    CONFIRMED | ESTIMATED | INFERRED | REQUIRES_CONFIRMATION

All public APIs below the "Backward-compatible layer" header are unchanged
from v0 and used directly by logic.py / graph.py.
New API surface: MappingConfidence, NormalizedEntity, normalize_parameter().
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


# ===========================================================================
# V1 Type Layer — Phase 0B.3
# ===========================================================================

class MappingConfidence(str, Enum):
    """Confidence grade for a normalization mapping.

    Used to determine whether a mapped value may drive binding decisions or
    must be treated as provisional / blocked by a confirmation gate.
    """

    CONFIRMED = "confirmed"
    """Unambiguous, mathematically exact, or source-backed mapping.
    No user confirmation required. Safe for binding decisions."""

    ESTIMATED = "estimated"
    """High-probability mapping (well-known synonym) but not formally
    source-backed. Should be displayed to user but does not block processing."""

    INFERRED = "inferred"
    """Contextual best-effort guess with meaningful uncertainty.
    Must be treated as provisional; not suitable for binding decisions."""

    REQUIRES_CONFIRMATION = "requires_confirmation"
    """Risky or ambiguous mapping that MUST NOT drive binding decisions without
    explicit user confirmation. Triggers a 'known unknown' gate in the state."""


@dataclass(frozen=True)
class NormalizedEntity:
    """Result of a single normalization step.

    Attributes:
        raw_value:         The input value before normalization.
        normalized_value:  The canonical output value, or None if unresolvable.
        domain_type:       One of: "material" | "temperature" | "pressure" | "medium".
        confidence:        How reliable the mapping is (MappingConfidence).
        warning_message:   Human-readable note when confidence < CONFIRMED.
    """
    raw_value: Any
    normalized_value: Optional[Any]
    domain_type: str
    confidence: MappingConfidence
    warning_message: Optional[str] = None


# ---------------------------------------------------------------------------
# V1 Mapping Tables
# ---------------------------------------------------------------------------

# ── Materials ────────────────────────────────────────────────────────────────

_MAT_CONFIRMED: dict[str, str] = {
    "nbr":         "NBR",
    "ptfe":        "PTFE",
    "fkm":         "FKM",
    "ffkm":        "FFKM",
    "epdm":        "EPDM",
    "silikon":     "SILIKON",
    "hnbr":        "HNBR",
    "acm":         "ACM",
    "au":          "AU",
    "eu":          "EU",
}

_MAT_ESTIMATED: dict[str, tuple[str, str]] = {
    "nitril":          ("NBR",     "synonym:nitril→NBR — sehr gebräuchliches Synonym"),
    "nitrilkautschuk": ("NBR",     "synonym:nitrilkautschuk→NBR"),
    "silikonkautschuk":("SILIKON", "synonym:silikonkautschuk→SILIKON"),
    "perbunan":        ("NBR",     "trade_name:perbunan — gebräuchlicher NBR-Handelsname (Lanxess)"),
}

_MAT_REQUIRES_CONFIRMATION: dict[str, tuple[str, str]] = {
    # Trade names: chemically well-known but compound-grade-specific → confirm before binding
    "viton":     ("FKM",  "trade_name:viton — Chemours-Marke für FKM; Compound-Bestätigung erforderlich"),
    "kalrez":    ("FFKM", "trade_name:kalrez — DuPont-Marke für FFKM; Compound-Bestätigung erforderlich"),
    "teflon":    ("PTFE", "trade_name:teflon — Chemours-Marke; PTFE-Typ/Grade-Bestätigung erforderlich"),
    "tecnoflon": ("FKM",  "trade_name:tecnoflon — Solvay-Marke für FKM; Compound-Bestätigung erforderlich"),
    "dyneon":    ("FKM",  "trade_name:dyneon — 3M-Marke für FKM; Compound-Bestätigung erforderlich"),
    "aflas":     ("FKM",  "trade_name:aflas — TFE/P-Copolymer; Anwendungsbestätigung erforderlich"),
}

# ── Media ────────────────────────────────────────────────────────────────────

_MED_CONFIRMED: dict[str, str] = {
    "wasser":          "Wasser",
    "water":           "Wasser",
    "reinwasser":      "Wasser",
    "druckluft":       "Druckluft",
    "compressed air":  "Druckluft",
    "luft":            "Luft",
    "stickstoff":      "Stickstoff",
    "nitrogen":        "Stickstoff",
    "sauerstoff":      "Sauerstoff",
    "oxygen":          "Sauerstoff",
}

_MED_ESTIMATED: dict[str, tuple[str, str]] = {
    "öl":          ("Öl",     "generic_oil:Öltyp nicht spezifiziert — HLP/HEES/VG klären"),
    "oil":         ("Öl",     "generic_oil:oil type not specified"),
    "mineralöl":   ("Öl",     "mineral_oil:wahrscheinlich HLP/ISO VG"),
    "hydrauliköl": ("Öl",     "hydraulic_oil:wahrscheinlich HLP"),
    "hlp":         ("Öl",     "hydraulic_oil_hlp:HLP-Hydrauliköl"),
    "bio-öl":      ("Bio-Öl", "bio_oil:HEES oder ähnlich"),
    "hees":        ("Bio-Öl", "bio_oil_hees:HEES-Esteröl"),
    "kraftstoff":  ("Kraftstoff", "fuel:Kraftstofftyp klären"),
    "diesel":      ("Kraftstoff", "fuel_diesel"),
    "benzin":      ("Kraftstoff", "fuel_petrol"),
    "ethanol":     ("Kraftstoff", "fuel_ethanol"),
}

_MED_REQUIRES_CONFIRMATION: dict[str, tuple[str, str]] = {
    # Phase-aware or inherently ambiguous media
    "heißdampf":    ("Dampf", (
        "medium_ambiguous:Heißdampf — überhitzter Dampf; "
        "Temperatur und Druck sind zwingend für Materialauswahl; "
        "gesättigter vs. überhitzter Dampf beeinflusst Materialwahl erheblich"
    )),
    "dampf":        ("Dampf", (
        "medium_ambiguous:Dampf — Sattdampf vs. Heißdampf unklar; "
        "Betriebstemperatur und -druck erforderlich"
    )),
    "steam":        ("Dampf",          "medium_ambiguous:steam — phase clarification required"),
    "säure":        ("Säure",          "medium_ambiguous:Säure — Konzentration, Typ und Temperatur erforderlich"),
    "acid":         ("Säure",          "medium_ambiguous:acid — concentration and type required"),
    "lauge":        ("Lauge",          "medium_ambiguous:Lauge — Konzentration und NaOH/KOH-Typ erforderlich"),
    "lösungsmittel":("Lösungsmittel",  "medium_ambiguous:Lösungsmittel — Typ erforderlich"),
    "solvent":      ("Lösungsmittel",  "medium_ambiguous:solvent — type required"),
    "kühlmittel":   ("Kühlmittel",     "medium_ambiguous:Kühlmittel — Typ und Konzentration erforderlich"),
    "coolant":      ("Kühlmittel",     "medium_ambiguous:coolant — type and concentration required"),
    "panolin":      ("Bio-Öl",         "trade_name_ambiguous:panolin — HEES-Bio-Öl-Marke; Typ bestätigen"),
    "ester":        ("Bio-Öl",         "medium_ambiguous:ester — Esterbasis und Typ unklar"),
}

# ── Unit conversion tables ────────────────────────────────────────────────────

_PRESSURE_TO_BAR: dict[str, float] = {
    "bar": 1.0,
    "psi": 0.0689476,   # 1 psi = 6894.757 Pa = 0.0689476 bar
    "mpa": 10.0,        # 1 MPa = 10 bar
    "kpa": 0.01,        # 1 kPa = 0.01 bar
}

_TEMP_PATTERN = re.compile(
    r"^([+-]?\d+(?:[.,]\d+)?)\s*°?\s*([CF])\s*$",
    re.IGNORECASE,
)
_PRESSURE_PATTERN = re.compile(
    r"^([+-]?\d+(?:[.,]\d+)?)\s*(bar|psi|mpa|kpa)\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Internal normalizers
# ---------------------------------------------------------------------------

def _parse_temp_input(raw: Any) -> Optional[tuple[float, str]]:
    if isinstance(raw, (int, float)):
        return float(raw), "C"
    text = str(raw).strip().replace(",", ".")
    m = _TEMP_PATTERN.match(text)
    return (float(m.group(1)), m.group(2).upper()) if m else None


def _normalize_temperature_entity(raw: Any) -> NormalizedEntity:
    parsed = _parse_temp_input(raw)
    if parsed is None:
        return NormalizedEntity(raw, None, "temperature",
                                MappingConfidence.REQUIRES_CONFIRMATION,
                                f"Temperaturformat nicht erkannt: {raw!r}")
    value, unit = parsed
    if unit == "C":
        return NormalizedEntity(raw, round(value, 2), "temperature",
                                MappingConfidence.CONFIRMED)
    celsius = round((value - 32.0) * 5.0 / 9.0, 2)
    return NormalizedEntity(raw, celsius, "temperature",
                            MappingConfidence.CONFIRMED,
                            f"Umgerechnet von {value}°F → {celsius}°C")


def _parse_pressure_input(raw: Any) -> Optional[tuple[float, str]]:
    if isinstance(raw, (int, float)):
        return float(raw), "bar"
    text = str(raw).strip().replace(",", ".")
    m = _PRESSURE_PATTERN.match(text)
    return (float(m.group(1)), m.group(2).lower()) if m else None


def _normalize_pressure_entity(raw: Any) -> NormalizedEntity:
    parsed = _parse_pressure_input(raw)
    if parsed is None:
        return NormalizedEntity(raw, None, "pressure",
                                MappingConfidence.REQUIRES_CONFIRMATION,
                                f"Druckformat nicht erkannt: {raw!r}")
    value, unit = parsed
    factor = _PRESSURE_TO_BAR.get(unit, 1.0)
    bar_val = round(value * factor, 4)
    warn = f"Umgerechnet von {value} {unit.upper()} → {bar_val} bar" if unit != "bar" else None
    return NormalizedEntity(raw, bar_val, "pressure", MappingConfidence.CONFIRMED, warn)


def _normalize_material_entity(raw: Any) -> NormalizedEntity:
    if raw is None:
        return NormalizedEntity(None, None, "material",
                                MappingConfidence.REQUIRES_CONFIRMATION,
                                "Kein Materialwert übergeben")
    key = str(raw).strip().lower()
    if key in _MAT_CONFIRMED:
        return NormalizedEntity(raw, _MAT_CONFIRMED[key], "material",
                                MappingConfidence.CONFIRMED)
    if key in _MAT_ESTIMATED:
        canonical, reason = _MAT_ESTIMATED[key]
        return NormalizedEntity(raw, canonical, "material",
                                MappingConfidence.ESTIMATED, reason)
    if key in _MAT_REQUIRES_CONFIRMATION:
        canonical, reason = _MAT_REQUIRES_CONFIRMATION[key]
        return NormalizedEntity(raw, canonical, "material",
                                MappingConfidence.REQUIRES_CONFIRMATION, reason)
    return NormalizedEntity(raw, None, "material", MappingConfidence.INFERRED,
                            f"Material nicht im V1-Mapping: {raw!r}")


def _normalize_medium_entity(raw: Any) -> NormalizedEntity:
    if raw is None:
        return NormalizedEntity(None, None, "medium",
                                MappingConfidence.REQUIRES_CONFIRMATION,
                                "Kein Mediumwert übergeben")
    key = str(raw).strip().lower()
    if key in _MED_CONFIRMED:
        return NormalizedEntity(raw, _MED_CONFIRMED[key], "medium",
                                MappingConfidence.CONFIRMED)
    if key in _MED_ESTIMATED:
        canonical, reason = _MED_ESTIMATED[key]
        return NormalizedEntity(raw, canonical, "medium",
                                MappingConfidence.ESTIMATED, reason)
    if key in _MED_REQUIRES_CONFIRMATION:
        canonical, reason = _MED_REQUIRES_CONFIRMATION[key]
        return NormalizedEntity(raw, canonical, "medium",
                                MappingConfidence.REQUIRES_CONFIRMATION, reason)
    return NormalizedEntity(raw, None, "medium", MappingConfidence.INFERRED,
                            f"Medium nicht im V1-Mapping: {raw!r}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def normalize_parameter(domain_type: str, raw_value: Any) -> NormalizedEntity:
    """Normalize a single domain value to its canonical form with confidence grading.

    This is the primary entry point for the Normalization Layer V1 (Phase 0B.3).
    It feeds the ``normalized`` layer of SealingAIState.

    Args:
        domain_type:  "material" | "temperature" | "pressure" | "medium"
        raw_value:    Raw input (string, number, or None).

    Returns:
        NormalizedEntity — never raises; unrecognised inputs return INFERRED or
        REQUIRES_CONFIRMATION depending on whether the domain_type is known.
    """
    if domain_type == "material":
        return _normalize_material_entity(raw_value)
    if domain_type == "temperature":
        return _normalize_temperature_entity(raw_value)
    if domain_type == "pressure":
        return _normalize_pressure_entity(raw_value)
    if domain_type == "medium":
        return _normalize_medium_entity(raw_value)
    return NormalizedEntity(raw_value, raw_value, domain_type,
                            MappingConfidence.INFERRED,
                            f"Unbekannter Domain-Typ: {domain_type!r}")


# ---------------------------------------------------------------------------
# Confidence → legacy identity_class / normalization_certainty bridge
# (used when populating SealingAIState.normalized.identity_records)
# ---------------------------------------------------------------------------

def confidence_to_identity_class(confidence: MappingConfidence) -> str:
    """Map MappingConfidence to the legacy identity_class string in SealingAIState."""
    return {
        MappingConfidence.CONFIRMED:             "identity_confirmed",
        MappingConfidence.ESTIMATED:             "identity_probable",
        MappingConfidence.INFERRED:              "identity_probable",
        MappingConfidence.REQUIRES_CONFIRMATION: "identity_unresolved",
    }[confidence]


def confidence_to_normalization_certainty(confidence: MappingConfidence) -> str:
    """Map MappingConfidence to the legacy normalization_certainty string."""
    return {
        MappingConfidence.CONFIRMED:             "explicit_value",
        MappingConfidence.ESTIMATED:             "inferred",
        MappingConfidence.INFERRED:              "ambiguous",
        MappingConfidence.REQUIRES_CONFIRMATION: "ambiguous",
    }[confidence]


# ===========================================================================
# Backward-compatible layer (v0 — unchanged)
# Used by logic.py, graph.py, and existing tests.
# DO NOT modify these functions without updating callers in logic.py.
# ===========================================================================

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
_MEDIUM_INFERRED: dict[str, Any] = {}
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


def _lowered(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def normalize_material_decision(value: Any) -> Optional[NormalizationDecision]:
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


def normalize_medium_decision(value: Any) -> Optional[NormalizationDecision]:
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
