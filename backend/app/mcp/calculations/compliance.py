"""
Compliance-Status — Deterministisch

Prüft Werkstoffe gegen regulatorische Anforderungen.
Kein LLM. Lookup-only + deterministischer Regelset.

Abdeckung: 7 Flags × 8 Werkstoffe

Quellen:
  - FDA:     21 CFR 177.1550 / 177.2600
  - ATEX:    EU 2014/34/EU / EN 13463-1
  - EHEDG:   EHEDG Doc. 8 / EN 1935/2004
  - TA_LUFT: VDI 2440 / TA-Luft 2021 §5.2.5
  - NORSOK:  NORSOK M-710 / ISO 23936-1/-2
  - PED:     EU PED 2014/68/EU / EN 13480-3
  - AED:     VDI 2440 / DIN EN ISO 15848-1
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .material_limits import MATERIAL_ALIASES, MATERIAL_LIMITS


# ──────────────────────────────────────────────────────────────────────────────
# Enum
# ──────────────────────────────────────────────────────────────────────────────

class ComplianceFlag(str, Enum):
    FDA     = "FDA"      # US Food & Drug Administration — 21 CFR 177
    ATEX    = "ATEX"     # ATmosphères EXplosibles — EU 2014/34/EU
    EHEDG   = "EHEDG"    # European Hygienic Engineering & Design Group
    TA_LUFT = "TA_LUFT"  # Deutsche TA-Luft 2021, §5.2 — Fugitive Emissions
    NORSOK  = "NORSOK"   # NORSOK M-710 / ISO 23936 — Sour Service
    PED     = "PED"      # Pressure Equipment Directive — EU 2014/68/EU
    AED     = "AED"      # Außendichtheitsnachweis — VDI 2440


# ──────────────────────────────────────────────────────────────────────────────
# Datenmodelle
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FlagResult:
    flag: ComplianceFlag
    passed: bool          # True = konform
    severity: str         # "ok" | "warning" | "blocker"
    reasons: list[str]
    norm_ref: str


@dataclass
class ComplianceResult:
    material: str
    medium: Optional[str]
    temp_c: Optional[float]
    pressure_bar: Optional[float]
    flag_results: list[FlagResult] = field(default_factory=list)
    overall_passed: bool = True
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_critical_application: bool = False  # Drop-in für calc_engine + quality_gate


# ──────────────────────────────────────────────────────────────────────────────
# Klassifizierungstabellen
# ──────────────────────────────────────────────────────────────────────────────

# FDA 21 CFR 177.1550 / 177.2600
_FDA_OK      = frozenset({"PTFE", "FFKM", "EPDM", "VMQ"})
_FDA_WARN    = frozenset({"FKM"})        # nur Food-Grade Compound
_FDA_BLOCKED = frozenset({"NBR", "HNBR", "CR"})

# EHEDG Doc. 8 / EN 1935/2004
_EHEDG_OK      = frozenset({"PTFE", "FFKM", "EPDM", "VMQ"})
_EHEDG_WARN    = frozenset({"FKM"})     # nur EHEDG-zertifizierter Compound
_EHEDG_BLOCKED = frozenset({"NBR", "HNBR", "CR"})

# NORSOK M-710 / ISO 23936-1/-2
_NORSOK_OK      = frozenset({"FKM", "HNBR", "FFKM", "PTFE"})
_NORSOK_WARN    = frozenset({"NBR", "EPDM"})   # begrenzte Scope-Freigabe
_NORSOK_BLOCKED = frozenset({"CR", "VMQ"})

# Medien die NORSOK-Prüfung auslösen (Sour Service)
_NORSOK_SOUR_MEDIA = frozenset({
    "h2", "hydrogen", "wasserstoff",
    "h2s", "schwefelwasserstoff",
    "co2", "kohlendioxid",
    "o2", "oxygen", "sauerstoff",
    "cl2", "chlor", "chlorine",
    "nh3", "ammoniak", "ammonia",
    "hf", "flusssaeure", "fluorwasserstoff",
    "crude_oil", "rohoel",
    "natural_gas", "erdgas",
})

# ATEX — brennbare Medien (EN 13463-1)
_ATEX_FLAMMABLE_MEDIA = frozenset({
    "h2", "hydrogen", "wasserstoff",
    "diesel",
    "ethanol", "alkohol", "alcohol",
    "methanol",
    "propan", "propane",
    "butan", "butane",
    "natural_gas", "erdgas",
})

# PED Gruppe 1 — Gefahrmedien (EU PED 2014/68/EU Anhang II)
_PED_GROUP1_MEDIA = frozenset({
    "h2", "hydrogen", "wasserstoff",
    "o2", "oxygen", "sauerstoff",
    "cl2", "chlor", "chlorine",
    "nh3", "ammoniak", "ammonia",
    "hf", "flusssaeure", "fluorwasserstoff",
    "ethanol", "alkohol", "alcohol",
    "diesel",
    "natural_gas", "erdgas",
})

# is_critical_application — immer kritische Medien
_CRITICAL_MEDIA = frozenset({
    "h2", "hydrogen", "wasserstoff",
    "o2", "oxygen", "sauerstoff",
    "cl2", "chlor", "chlorine",
    "hf", "flusssaeure", "fluorwasserstoff",
    "nh3", "ammoniak", "ammonia",
})


# ──────────────────────────────────────────────────────────────────────────────
# Normalisierung
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_material(material: str) -> str:
    key = MATERIAL_ALIASES.get(material.lower().strip())
    if key is None:
        raise KeyError(
            f"Werkstoff '{material}' unbekannt. "
            f"Bekannte Werkstoffe: {sorted(MATERIAL_LIMITS)}"
        )
    return key


def _normalize_medium(medium: Optional[str]) -> Optional[str]:
    if not medium:
        return None
    return (
        medium.lower()
        .strip()
        .replace(" ", "_")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ä", "ae")
    )


# ──────────────────────────────────────────────────────────────────────────────
# Flag-Checker
# ──────────────────────────────────────────────────────────────────────────────

def _check_fda(mat: str, _med: Optional[str], _t: Optional[float], _p: Optional[float]) -> FlagResult:
    if mat in _FDA_OK:
        return FlagResult(
            flag=ComplianceFlag.FDA,
            passed=True,
            severity="ok",
            reasons=[f"{mat} ist FDA-konform nach 21 CFR 177."],
            norm_ref="FDA 21 CFR 177.1550 / 177.2600",
        )
    if mat in _FDA_WARN:
        return FlagResult(
            flag=ComplianceFlag.FDA,
            passed=True,
            severity="warning",
            reasons=[f"{mat}: nur mit spezifiziertem Food-Grade-Compound FDA-konform."],
            norm_ref="FDA 21 CFR 177.2600 / SAE J200",
        )
    return FlagResult(
        flag=ComplianceFlag.FDA,
        passed=False,
        severity="blocker",
        reasons=[f"{mat} ist nicht FDA-zugelassen für Lebensmittelkontakt."],
        norm_ref="FDA 21 CFR 177.1550 / 177.2600",
    )


def _check_atex(mat: str, medium_raw: Optional[str], _t: Optional[float], _p: Optional[float]) -> FlagResult:
    medium_norm = _normalize_medium(medium_raw) or ""
    flammable = medium_norm in _ATEX_FLAMMABLE_MEDIA

    if not flammable:
        return FlagResult(
            flag=ComplianceFlag.ATEX,
            passed=True,
            severity="ok",
            reasons=["Medium nicht brennbar — keine ATEX-Einschränkung."],
            norm_ref="EU 2014/34/EU / EN 13463-1",
        )

    if mat == "PTFE":
        return FlagResult(
            flag=ComplianceFlag.ATEX,
            passed=True,
            severity="warning",
            reasons=[
                f"{mat} in brennbarer Atmosphäre ({medium_raw}): "
                "antistatischer PTFE-Grade erforderlich (Leitfähigkeit < 10⁹ Ω)."
            ],
            norm_ref="EU 2014/34/EU / EN 13463-1",
        )

    return FlagResult(
        flag=ComplianceFlag.ATEX,
        passed=True,
        severity="warning",
        reasons=[
            f"{mat} in brennbarer Atmosphäre ({medium_raw}): "
            "antistatischen Compound bestätigen (EN 13463-1 §5.7)."
        ],
        norm_ref="EU 2014/34/EU / EN 13463-1",
    )


def _check_ehedg(mat: str, _med: Optional[str], _t: Optional[float], _p: Optional[float]) -> FlagResult:
    if mat in _EHEDG_OK:
        return FlagResult(
            flag=ComplianceFlag.EHEDG,
            passed=True,
            severity="ok",
            reasons=[f"{mat} ist EHEDG-kompatibel."],
            norm_ref="EHEDG Doc. 8 / EN 1935/2004",
        )
    if mat in _EHEDG_WARN:
        return FlagResult(
            flag=ComplianceFlag.EHEDG,
            passed=True,
            severity="warning",
            reasons=[
                f"{mat}: nur EHEDG-zertifizierter Compound geeignet — "
                "Compound-Datenblatt prüfen."
            ],
            norm_ref="EHEDG Doc. 8 / EN 1935/2004",
        )
    return FlagResult(
        flag=ComplianceFlag.EHEDG,
        passed=False,
        severity="blocker",
        reasons=[f"{mat} ist für EHEDG-Anwendungen nicht freigegeben."],
        norm_ref="EHEDG Doc. 8 / EN 1935/2004",
    )


def _check_ta_luft(mat: str, _med: Optional[str], _t: Optional[float], _p: Optional[float]) -> FlagResult:
    lim = MATERIAL_LIMITS[mat]
    if lim.aed_certifiable:
        return FlagResult(
            flag=ComplianceFlag.TA_LUFT,
            passed=True,
            severity="ok",
            reasons=[f"{mat} ist AED-zertifizierbar — TA-Luft-konform."],
            norm_ref="VDI 2440 / TA-Luft 2021 §5.2.5",
        )
    return FlagResult(
        flag=ComplianceFlag.TA_LUFT,
        passed=False,
        severity="blocker",
        reasons=[f"{mat} ist nicht AED-zertifizierbar — nicht TA-Luft-konform."],
        norm_ref="VDI 2440 / TA-Luft 2021 §5.2.5",
    )


def _check_norsok(mat: str, medium_raw: Optional[str], _t: Optional[float], _p: Optional[float]) -> FlagResult:
    medium_norm = _normalize_medium(medium_raw) or ""
    is_sour = medium_norm in _NORSOK_SOUR_MEDIA

    if not is_sour:
        return FlagResult(
            flag=ComplianceFlag.NORSOK,
            passed=True,
            severity="ok",
            reasons=["Medium kein Sour-Service — NORSOK M-710 nicht anwendbar."],
            norm_ref="NORSOK M-710 / ISO 23936-1/-2",
        )

    if mat in _NORSOK_OK:
        return FlagResult(
            flag=ComplianceFlag.NORSOK,
            passed=True,
            severity="ok",
            reasons=[f"{mat} erfüllt NORSOK M-710 für Sour-Service."],
            norm_ref="NORSOK M-710 / ISO 23936-1/-2",
        )
    if mat in _NORSOK_WARN:
        return FlagResult(
            flag=ComplianceFlag.NORSOK,
            passed=True,
            severity="warning",
            reasons=[
                f"{mat}: begrenzte NORSOK-Scope-Freigabe — "
                "Compound-Qualifikation nach ISO 23936 prüfen."
            ],
            norm_ref="NORSOK M-710 / ISO 23936-1/-2",
        )
    return FlagResult(
        flag=ComplianceFlag.NORSOK,
        passed=False,
        severity="blocker",
        reasons=[f"{mat} ist für NORSOK M-710 Sour-Service nicht zugelassen."],
        norm_ref="NORSOK M-710 / ISO 23936-1/-2",
    )


def _check_ped(mat: str, medium_raw: Optional[str], _t: Optional[float], pressure_bar: Optional[float]) -> FlagResult:
    p = pressure_bar or 0.0

    if p <= 0.5:
        return FlagResult(
            flag=ComplianceFlag.PED,
            passed=True,
            severity="ok",
            reasons=["Druck ≤ 0,5 bar — PED nicht anwendbar (SEP-Ausnahme)."],
            norm_ref="EU PED 2014/68/EU Art. 4",
        )

    medium_norm = _normalize_medium(medium_raw) or ""
    group1 = medium_norm in _PED_GROUP1_MEDIA

    return FlagResult(
        flag=ComplianceFlag.PED,
        passed=True,
        severity="warning" if group1 else "ok",
        reasons=[
            f"PED anwendbar (p = {p} bar). "
            + (
                "Gruppe 1 (Gefahrmedium) — erhöhte Konformitätsanforderungen."
                if group1
                else "Gruppe 2 — Standard-Konformitätsdokumentation erforderlich."
            )
        ],
        norm_ref="EU PED 2014/68/EU / EN 13480-3",
    )


def _check_aed(mat: str, _med: Optional[str], _t: Optional[float], _p: Optional[float]) -> FlagResult:
    lim = MATERIAL_LIMITS[mat]
    if lim.aed_certifiable:
        return FlagResult(
            flag=ComplianceFlag.AED,
            passed=True,
            severity="ok",
            reasons=[f"{mat} ist AED-zertifizierbar (Außendichtheitsnachweis möglich)."],
            norm_ref="VDI 2440 / DIN EN ISO 15848-1",
        )
    return FlagResult(
        flag=ComplianceFlag.AED,
        passed=False,
        severity="blocker",
        reasons=[f"{mat} ist nicht AED-zertifizierbar — kein Außendichtheitsnachweis möglich."],
        norm_ref="VDI 2440 / DIN EN ISO 15848-1",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch-Tabelle
# ──────────────────────────────────────────────────────────────────────────────

_FLAG_DISPATCH: dict[
    ComplianceFlag,
    Callable[[str, Optional[str], Optional[float], Optional[float]], FlagResult],
] = {
    ComplianceFlag.FDA:     _check_fda,
    ComplianceFlag.ATEX:    _check_atex,
    ComplianceFlag.EHEDG:   _check_ehedg,
    ComplianceFlag.TA_LUFT: _check_ta_luft,
    ComplianceFlag.NORSOK:  _check_norsok,
    ComplianceFlag.PED:     _check_ped,
    ComplianceFlag.AED:     _check_aed,
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def check_compliance(
    material: str,
    medium: Optional[str] = None,
    temp_c: Optional[float] = None,
    pressure_bar: Optional[float] = None,
    flags: Optional[list[ComplianceFlag]] = None,
    is_dynamic: bool = False,
) -> ComplianceResult:
    """
    Deterministischer Compliance-Check für einen Werkstoff.
    Kein LLM.

    Args:
        material:     Werkstoffbezeichnung (DE/EN, case-insensitive)
        medium:       Prozessmedium (optional)
        temp_c:       Betriebstemperatur [°C] (optional)
        pressure_bar: Betriebsdruck [bar] (optional)
        flags:        Zu prüfende Flags (kein Flag-Check wenn None)
        is_dynamic:   True = dynamische Abdichtung (für zukünftige Erweiterung)

    Returns:
        ComplianceResult mit flag_results, blockers, warnings, is_critical_application
    """
    mat = _normalize_material(material)
    active_flags: list[ComplianceFlag] = flags or []

    flag_results: list[FlagResult] = [
        _FLAG_DISPATCH[flag](mat, medium, temp_c, pressure_bar)
        for flag in active_flags
    ]

    blockers = [
        f"{fr.flag.value}: {reason}"
        for fr in flag_results if fr.severity == "blocker"
        for reason in fr.reasons
    ]
    warnings = [
        f"{fr.flag.value}: {reason}"
        for fr in flag_results if fr.severity == "warning"
        for reason in fr.reasons
    ]
    overall_passed = all(fr.passed for fr in flag_results)

    # is_critical_application — kompatibel mit calc_engine + quality_gate Logik
    medium_norm = _normalize_medium(medium) or ""
    is_critical = (
        medium_norm in _CRITICAL_MEDIA
        or (pressure_bar is not None and pressure_bar > 100.0)
        or (temp_c is not None and temp_c > 400.0)
        or (temp_c is not None and temp_c < -40.0)
    )

    return ComplianceResult(
        material=mat,
        medium=medium,
        temp_c=temp_c,
        pressure_bar=pressure_bar,
        flag_results=flag_results,
        overall_passed=overall_passed,
        blockers=blockers,
        warnings=warnings,
        is_critical_application=is_critical,
    )


def is_critical_application(
    medium: Optional[str] = None,
    temp_c: Optional[float] = None,
    pressure_bar: Optional[float] = None,
) -> bool:
    """Material-unabhängiger Critical-Flag.

    Für Kontexte ohne bekannten Werkstoff (z.B. Flanschberechnung, Quality Gate).
    Delegiert die Erkennungslogik aus check_compliance — single source of truth.
    """
    medium_norm = _normalize_medium(medium) or ""
    return (
        medium_norm in _CRITICAL_MEDIA
        or (pressure_bar is not None and pressure_bar > 100.0)
        or (temp_c is not None and temp_c > 400.0)
        or (temp_c is not None and temp_c < -40.0)
    )


__all__ = [
    "ComplianceFlag",
    "FlagResult",
    "ComplianceResult",
    "check_compliance",
    "is_critical_application",
]
