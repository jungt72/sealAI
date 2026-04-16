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

import json
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from app.agent.domain.medium_registry import (
    classify_medium_value,
    extract_medium_mentions,
    medium_registry_entries,
)

logger = logging.getLogger(__name__)

# Fast/cheap model for the medium-extraction fallback.
# Override via env var SEALAI_MEDIUM_FALLBACK_MODEL.
_MEDIUM_LLM_FALLBACK_MODEL: str = os.environ.get(
    "SEALAI_MEDIUM_FALLBACK_MODEL", "gpt-4o-mini"
)

# Phase 0C.2: LLM in a deterministic layer is an architecture violation.
# The fallback is disabled by default; set SEALAI_ENABLE_MEDIUM_LLM_FALLBACK=1
# to re-enable for offline diagnostics only.
_MEDIUM_LLM_FALLBACK_ENABLED: bool = (
    os.environ.get("SEALAI_ENABLE_MEDIUM_LLM_FALLBACK", "0").strip() == "1"
)


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


@dataclass(frozen=True)
class MediumSpecialistInput:
    latest_user_message: str = ""
    observed_notes: tuple[str, ...] = ()
    candidate_media_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class MediumSpecialistResult:
    canonical_medium: Optional[str]
    medium_confidence: MappingConfidence
    medium_uncertainty_reason: Optional[str] = None
    followup_question_if_needed: Optional[str] = None
    candidate_media_token: Optional[str] = None


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

_MED_CONFIRMED: dict[str, str] = {}
_MED_ESTIMATED: dict[str, tuple[str, str]] = {}
_MED_REQUIRES_CONFIRMATION: dict[str, tuple[str, str]] = {}
for _entry in medium_registry_entries():
    for _alias in _entry.aliases:
        if _entry.mapping_confidence == "confirmed":
            _MED_CONFIRMED[_alias] = _entry.canonical_label
        elif _entry.mapping_confidence == "estimated":
            _MED_ESTIMATED[_alias] = (
                _entry.canonical_label,
                _entry.mapping_reason or f"medium_registry:{_entry.registry_key}",
            )
        else:
            _MED_REQUIRES_CONFIRMATION[_alias] = (
                _entry.canonical_label,
                _entry.mapping_reason or f"medium_registry:{_entry.registry_key}",
            )

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

_SHAFT_DIAMETER_KEYWORD_VALUE_PATTERN = re.compile(
    r"\b(?:wellen?durchmesser|wellendurchmesser|durchmesser|diameter)\b"
    r"(?:\s*(?:liegt\s*(?:bei)?|ist|beträgt|betragt|=|:))?\s*"
    r"([+-]?\d+(?:[.,]\d+)?)\s*(?:mm\b)?",
    re.IGNORECASE,
)

_SHAFT_DIAMETER_SYMBOL_PATTERN = re.compile(
    r"\b(?:d|d1)\s*[:=]\s*([+-]?\d+(?:[.,]\d+)?)\s*(?:mm\b)?",
    re.IGNORECASE,
)

_SHAFT_DIAMETER_MM_WITH_CONTEXT_PATTERN = re.compile(
    r"([+-]?\d+(?:[.,]\d+)?)\s*mm\b",
    re.IGNORECASE,
)

_SHAFT_DIAMETER_CONTEXT_RE = re.compile(
    r"\b(?:welle|shaft|durchmesser|diameter|rwdr|radialwellendichtring)\b",
    re.IGNORECASE,
)

_MEDIUM_FALLBACK_PATTERN = re.compile(
    r"\b(?:mit|medium|fluid|flüssigkeit)(?:\s+(?:ist|is|liegt|sind))?\s+([\w\-äöüÄÖÜß]+)\b",
    re.I,
)

_MEDIUM_FALLBACK_STOPWORDS: frozenset[str] = frozenset({"ist", "is", "liegt", "sind"})

_MEDIUM_FOLLOWUP_QUESTIONS: dict[str, str] = {
    "Dampf": "Handelt es sich um Sattdampf oder Heißdampf, und in welchem Druck- und Temperaturbereich arbeiten Sie?",
    "Säure": "Um welche Säure handelt es sich genau, in welcher Konzentration und bei welcher Temperatur?",
    "Lauge": "Welche Lauge liegt an, in welcher Konzentration und bei welcher Temperatur?",
    "Lösungsmittel": "Welches Lösungsmittel liegt genau an?",
    "Kühlmittel": "Welcher Kühlmitteltyp und welche Konzentration liegen an?",
    "Öl": "Welcher Öltyp liegt genau an?",
    "Bio-Öl": "Welcher Öltyp liegt genau an?",
}


def _mapping_confidence_rank(confidence: MappingConfidence) -> int:
    return {
        MappingConfidence.CONFIRMED: 4,
        MappingConfidence.ESTIMATED: 3,
        MappingConfidence.INFERRED: 2,
        MappingConfidence.REQUIRES_CONFIRMATION: 1,
    }[confidence]


def _unique_nonempty(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(text)
    return unique


def _extract_candidate_media_tokens(text: str) -> list[str]:
    message = str(text or "").strip()
    if not message:
        return []
    capture = extract_medium_mentions(message)
    candidates = list(capture.raw_mentions)
    fallback_match = _MEDIUM_FALLBACK_PATTERN.search(message)
    if fallback_match:
        raw_medium = str(fallback_match.group(1) or "").strip()
        if (
            raw_medium
            and raw_medium.lower() not in _MEDIUM_FALLBACK_STOPWORDS
            and not re.match(r"^\d", raw_medium)
        ):
            candidates.append(raw_medium)
    return _unique_nonempty(candidates)


def _followup_question_for_medium(
    canonical_medium: Optional[str],
    confidence: MappingConfidence,
    reason: Optional[str],
) -> Optional[str]:
    if canonical_medium and canonical_medium in _MEDIUM_FOLLOWUP_QUESTIONS:
        if confidence in {
            MappingConfidence.ESTIMATED,
            MappingConfidence.INFERRED,
            MappingConfidence.REQUIRES_CONFIRMATION,
        }:
            return _MEDIUM_FOLLOWUP_QUESTIONS[canonical_medium]
    if confidence not in {
        MappingConfidence.INFERRED,
        MappingConfidence.REQUIRES_CONFIRMATION,
    }:
        return None
    if canonical_medium and canonical_medium in _MEDIUM_FOLLOWUP_QUESTIONS:
        return _MEDIUM_FOLLOWUP_QUESTIONS[canonical_medium]
    if reason and str(reason).startswith("medium_conflict:"):
        return "Welches Medium liegt genau an?"
    return "Welches Medium liegt genau an?"


def _medium_result_from_token(token: str) -> MediumSpecialistResult:
    entity = normalize_parameter("medium", token)
    canonical_medium = entity.normalized_value
    return MediumSpecialistResult(
        canonical_medium=canonical_medium,
        medium_confidence=entity.confidence,
        medium_uncertainty_reason=entity.warning_message,
        followup_question_if_needed=_followup_question_for_medium(
            canonical_medium,
            entity.confidence,
            entity.warning_message,
        ),
        candidate_media_token=str(token or "").strip() or None,
    )


def run_medium_specialist(
    specialist_input: MediumSpecialistInput,
) -> MediumSpecialistResult:
    """Bounded internal specialist for deterministic medium interpretation."""
    candidates = list(specialist_input.candidate_media_tokens)
    if not candidates and specialist_input.latest_user_message:
        candidates.extend(_extract_candidate_media_tokens(specialist_input.latest_user_message))
    for note in specialist_input.observed_notes:
        candidates.extend(_extract_candidate_media_tokens(note))
    candidates = _unique_nonempty(candidates)

    if not candidates:
        return MediumSpecialistResult(
            canonical_medium=None,
            medium_confidence=MappingConfidence.REQUIRES_CONFIRMATION,
            medium_uncertainty_reason="no_medium_candidate_found",
            followup_question_if_needed="Welches Medium liegt genau an?",
        )

    results = [_medium_result_from_token(token) for token in candidates]
    canonicals = {
        str(result.canonical_medium).strip().lower(): str(result.canonical_medium).strip()
        for result in results
        if str(result.canonical_medium or "").strip()
    }
    if len(canonicals) > 1:
        return MediumSpecialistResult(
            canonical_medium=None,
            medium_confidence=MappingConfidence.REQUIRES_CONFIRMATION,
            medium_uncertainty_reason="medium_conflict:" + " | ".join(sorted(canonicals.values())),
            followup_question_if_needed="Welches Medium liegt genau an?",
        )

    selected = max(results, key=lambda item: _mapping_confidence_rank(item.medium_confidence))
    return selected


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
    decision = classify_medium_value(str(raw))
    if decision.canonical_label and decision.mapping_confidence == "confirmed":
        return NormalizedEntity(raw, decision.canonical_label, "medium",
                                MappingConfidence.CONFIRMED, decision.mapping_reason)
    if decision.canonical_label and decision.mapping_confidence == "estimated":
        return NormalizedEntity(raw, decision.canonical_label, "medium",
                                MappingConfidence.ESTIMATED, decision.mapping_reason)
    if decision.canonical_label and decision.mapping_confidence == "requires_confirmation":
        return NormalizedEntity(raw, decision.canonical_label, "medium",
                                MappingConfidence.REQUIRES_CONFIRMATION, decision.mapping_reason)
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

# ---------------------------------------------------------------------------
# STS-code direct lookup (used by normalize_material() — not decision layer)
# Maps lowercased input → canonical STS-MAT-* code.
# normalize_material_decision() is intentionally untouched (backward compat).
# ---------------------------------------------------------------------------
_GENERIC_TO_STS: dict[str, str] = {
    "NBR":    "STS-MAT-NBR-A1",
    "PTFE":   "STS-MAT-PTFE-A1",
    "FKM":    "STS-MAT-FKM-A1",
    "FFKM":   "STS-MAT-FFKM-A1",
    "EPDM":   "STS-MAT-EPDM-A1",
    "SILIKON": "STS-MAT-SI-A1",
    "HNBR":   "STS-MAT-HNBR-A1",
    "ACM":    "STS-MAT-ACM-A1",
    "AU":     "STS-MAT-AU-A1",
    "EU":     "STS-MAT-EU-A1",
}

_MAT_DIRECT_STS: dict[str, str] = {
    # Ceramic / cermet
    "sic":                      "STS-MAT-SIC-A1",
    "ssic":                     "STS-MAT-SIC-A1",
    "siliziumkarbid":           "STS-MAT-SIC-A1",
    "siliziumcarbid":           "STS-MAT-SIC-A1",
    "silicon carbide":          "STS-MAT-SIC-A1",
    "siliciumcarbide":          "STS-MAT-SIC-A1",
    "rbsic":                    "STS-MAT-SIC-B1",
    "sisic":                    "STS-MAT-SIC-B1",
    "reaktionsgebundenes sic":  "STS-MAT-SIC-B1",
    "wc":                       "STS-MAT-WC-A1",
    "wolframkarbid":            "STS-MAT-WC-A1",
    "tungsten carbide":         "STS-MAT-WC-A1",
    "al2o3":                    "STS-MAT-AL2O3-A1",
    "aluminiumoxid":            "STS-MAT-AL2O3-A1",
    "alumina":                  "STS-MAT-AL2O3-A1",
    # Elastomers
    "nbr":                      "STS-MAT-NBR-A1",
    "nitrilkautschuk":          "STS-MAT-NBR-A1",
    "buna n":                   "STS-MAT-NBR-A1",
    "buna-n":                   "STS-MAT-NBR-A1",
    "nitril":                   "STS-MAT-NBR-A1",
    "fkm":                      "STS-MAT-FKM-A1",
    "viton":                    "STS-MAT-FKM-A1",
    "fluorokautschuk":          "STS-MAT-FKM-A1",
    "fluorkautschuk":           "STS-MAT-FKM-A1",
    "ffkm":                     "STS-MAT-FFKM-A1",
    "kalrez":                   "STS-MAT-FFKM-A1",
    "perfluorkautschuk":        "STS-MAT-FFKM-A1",
    "epdm":                     "STS-MAT-EPDM-A1",
    "hnbr":                     "STS-MAT-HNBR-A1",
    "hydrierter nitrilkautschuk": "STS-MAT-HNBR-A1",
    "cr":                       "STS-MAT-CR-A1",
    "neopren":                  "STS-MAT-CR-A1",
    "chloropren":               "STS-MAT-CR-A1",
    "chloroprenkautschuk":      "STS-MAT-CR-A1",
    "silikon":                  "STS-MAT-SI-A1",
    "vmq":                      "STS-MAT-SI-A1",
    "silikonkautschuk":         "STS-MAT-SI-A1",
    "silicon":                  "STS-MAT-SI-A1",
    # Polymers
    "ptfe":                     "STS-MAT-PTFE-A1",
    "teflon":                   "STS-MAT-PTFE-A1",
    "polytetrafluorethylen":    "STS-MAT-PTFE-A1",
    "peek":                     "STS-MAT-PEEK-A1",
    "polyetheretherketon":      "STS-MAT-PEEK-A1",
    "pvdf":                     "STS-MAT-PVDF-A1",
    "polyvinylidenfluorid":     "STS-MAT-PVDF-A1",
    # Carbon / graphite
    "grafit":                   "STS-MAT-GRAFIT-A1",
    "graphit":                  "STS-MAT-GRAFIT-A1",
    "graphite":                 "STS-MAT-GRAFIT-A1",
    "carbon":                   "STS-MAT-CARBON-A1",
    "kohle":                    "STS-MAT-CARBON-A1",
}

_MEDIUM_DIRECT: dict[str, str] = {}
_MEDIUM_INFERRED: dict[str, Any] = {}
_MEDIUM_CONFIRMATION: dict[str, tuple[str, str]] = {}
_MEDIUM_ID: dict[str, str] = {}
for _entry in medium_registry_entries():
    for _alias in _entry.aliases:
        if _entry.mapping_confidence in {"confirmed", "estimated"}:
            _MEDIUM_DIRECT[_alias] = _entry.canonical_label
        else:
            _MEDIUM_CONFIRMATION[_alias] = (
                _entry.canonical_label,
                _entry.mapping_reason or f"medium_registry:{_entry.registry_key}",
            )
        _MEDIUM_ID[_alias] = _entry.registry_key


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
    decision = classify_medium_value(lowered)
    if decision.canonical_label and decision.mapping_confidence == "confirmed":
        return NormalizationDecision(
            decision.canonical_label,
            "confirmed",
            f"normalized_medium:{lowered}",
        )
    if decision.canonical_label and decision.mapping_confidence == "estimated":
        return NormalizationDecision(
            decision.canonical_label,
            "inferred",
            decision.mapping_reason or f"medium_registry:{decision.registry_key or lowered}",
        )
    if decision.canonical_label and decision.mapping_confidence == "requires_confirmation":
        return NormalizationDecision(
            decision.canonical_label,
            "confirmation_required",
            decision.mapping_reason or f"medium_registry:{decision.registry_key or lowered}",
        )
    return NormalizationDecision(str(value), "unknown", "medium_unmapped")


def normalize_material(value: Any) -> Any:
    """Normalize a material term to its canonical STS-MAT-* code.

    Returns a STS code string (e.g. ``"STS-MAT-FKM-A1"``) when the input can
    be resolved, otherwise the generic canonical name or the raw input.

    Note: ``normalize_material_decision()`` still returns generic names
    (``"FKM"``, ``"PTFE"`` …) for backward compatibility.
    """
    lowered = _lowered(value)
    if lowered is None:
        return None
    # 1. Direct STS-code lookup (covers ceramics, trade names, synonyms)
    if lowered in _MAT_DIRECT_STS:
        return _MAT_DIRECT_STS[lowered]
    # 2. Generic-name → STS-code via decision layer
    decision = normalize_material_decision(value)
    if decision is None:
        return None
    generic = decision.canonical_value
    if isinstance(generic, str) and generic in _GENERIC_TO_STS:
        return _GENERIC_TO_STS[generic]
    return generic


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
    if normalized_unit == "mpa":
        return float(value) * 10.0, "bar"
    if normalized_unit == "kpa":
        return float(value) * 0.01, "bar"
    if normalized_unit == "f":
        return (float(value) - 32.0) * 5.0 / 9.0, "C"
    if normalized_unit in {"bar", "c"}:
        return float(value), "C" if normalized_unit == "c" else "bar"
    return float(value), unit

def extract_shaft_diameter_mm(text: str, *, allow_context_free_mm: bool = False) -> float | None:
    message = str(text or "").strip()
    if not message:
        return None

    for pattern in (_SHAFT_DIAMETER_KEYWORD_VALUE_PATTERN, _SHAFT_DIAMETER_SYMBOL_PATTERN):
        match = pattern.search(message)
        if match:
            return float(match.group(1).replace(",", "."))

    mm_match = _SHAFT_DIAMETER_MM_WITH_CONTEXT_PATTERN.search(message)
    if not mm_match:
        return None
    if allow_context_free_mm or _SHAFT_DIAMETER_CONTEXT_RE.search(message):
        return float(mm_match.group(1).replace(",", "."))
    return None


def _llm_extract_medium(text: str) -> Optional[dict[str, Any]]:
    """LLM fallback for medium extraction when regex yields nothing.

    Uses a fast, cheap model (default: gpt-4o-mini, overridable via
    SEALAI_MEDIUM_FALLBACK_MODEL) via the synchronous OpenAI client.

    Returns a dict with keys "medium" (str | None) and "properties" (list[str]),
    or None when the call fails or no medium is found.
    """
    try:
        from openai import OpenAI  # lazy import — not required for pure-regex path
    except ImportError:
        logger.debug("openai package not available — skipping LLM medium fallback")
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.debug("OPENAI_API_KEY not set — skipping LLM medium fallback")
        return None

    prompt = (
        "Du bist ein technischer Assistent für Dichtungstechnik. "
        "Extrahiere aus dem folgenden Text das Medium (die Flüssigkeit, das Gas oder das Material), "
        "das abgedichtet werden soll. "
        "Extrahiere außerdem relevante Eigenschaften (z.B. abrasiv, klebrig, aggressiv). "
        'Antworte ausschließlich als JSON: {"medium": "Name oder null", "properties": ["klebrig", ...]}. '
        f"Text: {text}"
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=_MEDIUM_LLM_FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=80,
        )
        raw_content = response.choices[0].message.content or ""
        # Strip markdown code fences if present
        raw_content = raw_content.strip()
        if raw_content.startswith("```"):
            raw_content = re.sub(r"^```[a-z]*\n?", "", raw_content)
            raw_content = re.sub(r"\n?```$", "", raw_content)
        result: dict[str, Any] = json.loads(raw_content)
        medium = result.get("medium")
        if medium and str(medium).lower() not in ("null", "none", ""):
            return {
                "medium": str(medium).strip(),
                "properties": [str(p) for p in result.get("properties", []) if p],
            }
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM medium fallback failed: %s", exc)
        return None


# motion_type — ordered by specificity; first match wins
_MOTION_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r'\b(?:linear|lineare?|hub(?:bewegung)?|hin[- ]?und[- ]?her|translat(?:ion|ions?bewegung)?)\b', 'linear'),
    (r'\b(?:rotier(?:end)?|drehend|dreht|radial(?:welle)?|rotierende?\s+welle)\b', 'rotary'),
    (r'\b(?:statisch|keine\s+bewegung|stillstand|flansch(?:abdichtung)?)\b', 'static'),
]

_SEALING_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:gleitringdichtung|gleitring|mechanical\s+seal)\b", "mechanical_seal"),
    (r"\b(?:rwdr|radialwellendichtring|simmerring|wellendichtring)\b", "rwdr"),
    (r"\b(?:o[- ]?ring|oring)\b", "o_ring"),
    (r"\b(?:flachdichtung|gasket)\b", "gasket"),
    (r"\b(?:packung|stopfbuchse)\b", "packing"),
]

_PRESSURE_DIRECTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:beidseitig|wechselnd\w*\s+druck|druck\s+wechselnd|bidirectional)\b", "bidirectional"),
    (r"\b(?:von\s+innen\s+nach\s+aussen|von\s+innen\s+nach\s+außen|innen\s+nach\s+aussen|innen\s+nach\s+außen)\b", "inside_out"),
    (r"\b(?:von\s+aussen\s+nach\s+innen|von\s+außen\s+nach\s+innen|aussen\s+nach\s+innen|außen\s+nach\s+innen)\b", "outside_in"),
    (r"\b(?:drucklos|atmosphaerisch|atmosphärisch)\b", "pressureless_or_atmospheric"),
]

_DUTY_PROFILE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:24\s*/\s*7|dauerbetrieb|kontinuierlich|permanent|continuous)\b", "continuous"),
    (r"\b(?:gelegentlich\w*|intermittierend|zeitweise|batch|taktbetrieb|anlaufbetrieb)\b", "intermittent"),
    (r"\b(?:trockenlauf|dry\s*run(?:ning)?)\b", "dry_running_risk"),
]

_INSTALLATION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:pumpe|kreiselpumpe|pump)\b", "pump"),
    (r"\b(?:ventil|valve)\b", "valve"),
    (r"\b(?:flansch|flange)\b", "flange"),
    (r"\b(?:gehaeuse|gehäuse|housing)\b", "housing"),
    (r"\b(?:einbauraum|bauraum|radialer\s+bauraum|axialer\s+bauraum|nur\s+\d+(?:[.,]\d+)?\s*mm)\b", "limited_installation_space"),
]

_GEOMETRY_CONTEXT_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:nut|nute|nutgeometrie|groove)\b", "groove"),
    (r"\b(?:bohrung|dichtsitz|dichtstelle|bauform|geometrie)\b", "geometry_context"),
    (r"\b(?:cartouche|cartridge|kartusche)\b", "cartridge_geometry"),
]

_CONTAMINATION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:schmutz|verschmutz\w*|partikel|feststoff\w*|solids?)\b", "solids_or_particles"),
    (r"\b(?:abrasiv\w*|sand|slurry|schlamm)\b", "abrasive"),
]

_COUNTERFACE_SURFACE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:gegenlauf(?:flaeche|fläche|partner)|wellenzustand|wellenoberflaeche|wellenoberfläche|laufpartner)\b", "counterface_condition"),
    (r"\b(?:rauheit|ra\s*\d|oberflaeche|oberfläche|verschlissen|riefen)\b", "surface_quality_context"),
    (r"\b(?:huelse|hülse|buchse|wellenwerkstoff)\b", "counterface_material_context"),
]

_TOLERANCE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:rundlauf|runout|exzentrizitaet|exzentrizität)\b", "runout_or_eccentricity"),
    (r"\b(?:toleranz\w*|spiel|spalt|clearance)\b", "tolerance_or_clearance"),
]

_INDUSTRY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:lebensmittel\w*|food|pharma|hygien\w*)\b", "food_pharma"),
    (r"\b(?:chemie|chemisch\w*|chemical|prozess(?:technik|industrie)?)\b", "chemical_process"),
    (r"\b(?:wasser|abwasser|marine|schiff)\b", "water_or_marine"),
]

_COMPLIANCE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:fda|eu\s*10/2011|lebensmittelkonform)\b", "food_contact"),
    (r"\b(?:atex|explosionsschutz|ex[- ]?zone)\b", "atex"),
    (r"\b(?:ta[- ]?luft|api\s*682|din\s+en\s+12756|din\s+3760)\b", "norm_or_regulatory"),
]

_MEDIUM_QUALIFIER_PATTERNS: list[tuple[str, str]] = [
    (r"(?:\b(?:konzentration|konzentriert|prozent)\b|\d+(?:[.,]\d+)?\s*%)", "concentration_context"),
    (r"\b(?:chlorid(?:e|gehalt)?|chlorides?|salzgehalt|nacl)\b", "chlorides_or_salinity"),
    (r"\b(?:abrasiv\w*|partikel|feststoff\w*|solids?|slurry|schlamm)\b", "solids_or_abrasives"),
    (r"\b(?:sattdampf|heissdampf|heißdampf|dampfqualitaet|dampfqualität)\b", "steam_detail"),
    (r"\b(?:saeure|säure|salzsaeure|salzsäure|lauge|loesungsmittel|lösungsmittel)\b", "chemistry_detail"),
]


def _extract_motion_type(text: str) -> str | None:
    """Return 'rotary', 'linear', or 'static' if motion type is detectable, else None."""
    text_lower = text.lower()
    for pattern, motion in _MOTION_TYPE_PATTERNS:
        if re.search(pattern, text_lower):
            return motion
    return None


def _first_pattern_value(text: str, patterns: list[tuple[str, str]]) -> str | None:
    for pattern, value in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return value
    return None


# Negation words that directly precede a matched term, e.g. "kein Gleitring".
# Matches only when a negation word appears within 1 word before the match end.
# "kein Gleitring" → match; "kein Gleitring sondern " → no match (too far away).
_NEGATION_BEFORE_RE = re.compile(
    r"\b(?:kein|keine|keinen|keinem|nicht|statt|anstatt|anstelle(?:\s+von)?|no|not)\s+\w*\s*$",
    re.IGNORECASE,
)


def _sealing_type_value(text: str, patterns: list[tuple[str, str]]) -> str | None:
    """Negation-aware sealing type extraction.

    Unlike _first_pattern_value, this:
    - Skips matches that are immediately preceded by a negation word
      (kein, nicht, statt, …).
    - Returns the last non-negated match so that corrections like
      "kein Gleitring sondern RWDR" yield 'rwdr', not 'mechanical_seal'.
    """
    best_value: str | None = None
    best_pos: int = -1
    for pattern, value in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            before = text[: m.start()]
            if _NEGATION_BEFORE_RE.search(before):
                continue  # This match is negated — skip
            if m.start() > best_pos:
                best_value = value
                best_pos = m.start()
    return best_value


def _all_pattern_values(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    values: list[str] = []
    for pattern, value in patterns:
        if re.search(pattern, text, re.IGNORECASE) and value not in values:
            values.append(value)
    return values


def extract_parameters(text: str) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    # Match "80°C", "80C", "80 Grad", "80 grad" — group(2) is None for bare "grad" → default Celsius
    temp_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:°?\s*([CF])\b|\bgrad\b)", text, re.I)
    if temp_match:
        raw = temp_match.group(0)
        value = float(temp_match.group(1).replace(",", "."))
        unit = temp_match.group(2) or "C"  # "grad" without explicit C/F → Celsius
        temp_value, _ = normalize_unit_value(value, unit)
        extracted["temperature_raw"] = raw
        extracted["temperature_c"] = temp_value
    pressure_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(bar|psi|mpa|kpa)\b", text, re.I)
    if pressure_match:
        raw = pressure_match.group(0)
        value = float(pressure_match.group(1).replace(",", "."))
        pressure_value, _ = normalize_unit_value(value, pressure_match.group(2))
        extracted["pressure_raw"] = raw
        extracted["pressure_bar"] = pressure_value
    diameter_value = extract_shaft_diameter_mm(text)
    if diameter_value is not None:
        extracted["diameter_mm"] = diameter_value
    speed_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:rpm|u[/.]?min)\b", text, re.I)
    if speed_match:
        raw_rpm = float(speed_match.group(1).replace(",", "."))
        # Store as int when there's no fractional part (6000.0 → 6000)
        extracted["speed_rpm"] = int(raw_rpm) if raw_rpm == int(raw_rpm) else raw_rpm

    motion_type = _extract_motion_type(text)
    if motion_type is not None:
        extracted["motion_type"] = motion_type

    # sealing_type uses negation-aware extraction to handle corrections like
    # "kein Gleitring sondern RWDR" correctly.
    sealing_type_value = _sealing_type_value(text, _SEALING_TYPE_PATTERNS)
    if sealing_type_value is not None:
        extracted["sealing_type"] = sealing_type_value

    for field_name, patterns in (
        ("pressure_direction", _PRESSURE_DIRECTION_PATTERNS),
        ("duty_profile", _DUTY_PROFILE_PATTERNS),
        ("installation", _INSTALLATION_PATTERNS),
        ("geometry_context", _GEOMETRY_CONTEXT_PATTERNS),
        ("contamination", _CONTAMINATION_PATTERNS),
        ("counterface_surface", _COUNTERFACE_SURFACE_PATTERNS),
        ("tolerances", _TOLERANCE_PATTERNS),
        ("industry", _INDUSTRY_PATTERNS),
    ):
        value = _first_pattern_value(text, patterns)
        if value is not None:
            extracted[field_name] = value

    compliance = _all_pattern_values(text, _COMPLIANCE_PATTERNS)
    if compliance:
        extracted["compliance"] = compliance

    medium_qualifiers = _all_pattern_values(text, _MEDIUM_QUALIFIER_PATTERNS)
    if medium_qualifiers:
        extracted["medium_qualifiers"] = medium_qualifiers

    medium_result = run_medium_specialist(
        MediumSpecialistInput(
            latest_user_message=text,
            candidate_media_tokens=tuple(_extract_candidate_media_tokens(text)),
        )
    )
    if medium_result.canonical_medium:
        if medium_result.medium_confidence == MappingConfidence.REQUIRES_CONFIRMATION:
            extracted["medium_confirmation_required"] = medium_result.canonical_medium
        else:
            extracted["medium_normalized"] = medium_result.canonical_medium
        extracted["medium_normalization_status"] = medium_result.medium_confidence.value
        extracted["medium_mapping_reason"] = (
            medium_result.medium_uncertainty_reason
            or f"medium_specialist:{str(medium_result.candidate_media_token or medium_result.canonical_medium).lower()}"
        )
        extracted["medium_raw"] = medium_result.candidate_media_token or medium_result.canonical_medium
        if medium_result.followup_question_if_needed:
            extracted["medium_followup_question"] = medium_result.followup_question_if_needed

    # LLM fallback: fires only when regex + whitelist both found nothing.
    # Disabled by default (Phase 0C.2 — LLM must not run inside a deterministic node).
    # Enable via SEALAI_ENABLE_MEDIUM_LLM_FALLBACK=1 for offline diagnostics only.
    if (
        _MEDIUM_LLM_FALLBACK_ENABLED
        and "medium_normalized" not in extracted
        and "medium_confirmation_required" not in extracted
    ):
        llm_result = _llm_extract_medium(text)
        if llm_result:
            extracted["medium_normalized"] = llm_result["medium"].capitalize()
            extracted["medium_normalization_status"] = "llm_fallback"
            extracted["medium_mapping_reason"] = f"llm_fallback:{llm_result['medium'].lower()}"
            extracted["medium_raw"] = llm_result["medium"]
            if llm_result["properties"]:
                extracted["medium_properties"] = llm_result["properties"]

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
