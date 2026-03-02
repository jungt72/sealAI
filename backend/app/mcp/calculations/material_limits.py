"""
Werkstoff-Grenzwerte — Deterministisch

Quellen: DIN 3760, ISO 6194-1, Parker O-Ring Handbook (ORD 5700),
         Trelleborg Sealing Guide, Freudenberg Material Data
Kein LLM. Lookup-only.

Abdeckung: 8 Werkstoffe × 5 Dimensionen
  - Temperaturfenster (min / max / peak)
  - Drucklimit statisch / dynamisch [bar]
  - AED-Zertifizierbarkeit (Außendichtheitsnachweis)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


# ──────────────────────────────────────────────────────────────────────────────
# Datenmodelle
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MaterialLimits:
    name: str
    temp_min_c: int               # Dauergebrauch — Kältegrenze [°C]
    temp_max_c: int               # Dauergebrauch — Wärmegrenze [°C]
    temp_peak_c: int              # Kurzzeitige Spitzenlast [°C]
    pressure_static_max_bar: int  # Statische Abdichtung [bar]
    pressure_dynamic_max_bar: int # Dynamische Abdichtung (Hub/Rotation) [bar]
    aed_certifiable: bool         # AED-Zertifizierung möglich (Außendichtheitsnachweis)
    shore_a_range: tuple          # Typischer Shore-A-Bereich (von, bis)
    note: str
    norm_ref: str


@dataclass
class LimitsCheckResult:
    material: str
    limits: MaterialLimits
    # True = OK | "warning" = Grauzone (max_c < t <= peak_c) | False = NOK | None = nicht geprüft
    temp_ok: Union[bool, str, None] = None
    pressure_ok: Optional[bool] = None
    aed_ok: Optional[bool] = None
    warnings: list = field(default_factory=list)
    recommendation: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Normalisierungs-Aliases
# ──────────────────────────────────────────────────────────────────────────────

MATERIAL_ALIASES: dict[str, str] = {
    "nbr":        "NBR",
    "perbunan":   "NBR",
    "fkm":        "FKM",
    "viton":      "FKM",
    "epdm":       "EPDM",
    "ptfe":       "PTFE",
    "teflon":     "PTFE",
    "hnbr":       "HNBR",
    "ffkm":       "FFKM",
    "kalrez":     "FFKM",
    "cr":         "CR",
    "neopren":    "CR",
    "chloropren": "CR",
    "vmq":        "VMQ",
    "silikon":    "VMQ",
    "silicone":   "VMQ",
}


# ──────────────────────────────────────────────────────────────────────────────
# Grenzwerttabelle: 8 Werkstoffe
# ──────────────────────────────────────────────────────────────────────────────

MATERIAL_LIMITS: dict[str, MaterialLimits] = {

    "NBR": MaterialLimits(
        name="NBR",
        temp_min_c=-40,
        temp_max_c=120,
        temp_peak_c=140,
        pressure_static_max_bar=500,
        pressure_dynamic_max_bar=250,
        aed_certifiable=True,
        shore_a_range=(40, 90),
        note=(
            "Standardwerkstoff für Mineralöl-Hydraulik. "
            "Druckwerte gelten mit Stützring (backup ring). "
            "Nicht geeignet für Dampf, Ketone und konzentrierte Säuren."
        ),
        norm_ref="DIN 3760 / ISO 6194-1",
    ),

    "FKM": MaterialLimits(
        name="FKM",
        temp_min_c=-20,
        temp_max_c=200,
        temp_peak_c=230,
        pressure_static_max_bar=700,
        pressure_dynamic_max_bar=300,
        aed_certifiable=True,
        shore_a_range=(50, 90),
        note=(
            "Spezielle Low-Temp-Compounds bis -40 °C verfügbar. "
            "AED-Grades für E85/Kraftstoff vorhanden (SAE J200). "
            "Nicht geeignet für Dampf, starke Basen oder Ketone."
        ),
        norm_ref="DIN 3760 / ISO 6194-1 / SAE J200",
    ),

    "EPDM": MaterialLimits(
        name="EPDM",
        temp_min_c=-50,
        temp_max_c=150,
        temp_peak_c=175,
        pressure_static_max_bar=350,
        pressure_dynamic_max_bar=150,
        aed_certifiable=False,
        shore_a_range=(40, 90),
        note=(
            "Beste Dampf- und Wasserbeständigkeit. "
            "Nicht geeignet für Mineralöle und Kraftstoffe. "
            "AED-Zertifizierung nicht praxisrelevant (kein rotierender Wellendichtring-Einsatz)."
        ),
        norm_ref="DIN 7716 / ISO 4633",
    ),

    "PTFE": MaterialLimits(
        name="PTFE",
        temp_min_c=-200,
        temp_max_c=260,
        temp_peak_c=300,
        pressure_static_max_bar=1500,
        pressure_dynamic_max_bar=350,
        aed_certifiable=True,
        shore_a_range=(55, 65),
        note=(
            "Thermoplast — kein Elastomer. Shore-A nur orientierend. "
            "Gefüllte Grades (GFP, MoS₂) für dynamische Abdichtung. "
            "Kein Rückstellvermögen ohne Federelement. "
            "Druckwerte bei gefüllten Grades."
        ),
        norm_ref="DIN 3760 / ASTM D1457",
    ),

    "HNBR": MaterialLimits(
        name="HNBR",
        temp_min_c=-40,
        temp_max_c=150,
        temp_peak_c=165,
        pressure_static_max_bar=700,
        pressure_dynamic_max_bar=350,
        aed_certifiable=True,
        shore_a_range=(50, 95),
        note=(
            "Exzellente H₂-Beständigkeit und RGD-Resistenz. "
            "Beste mechanische Eigenschaften unter Elastomeren. "
            "Empfohlen für Hochdruck-Hydraulik und H₂-Anwendungen."
        ),
        norm_ref="ISO 23936-2 / DIN 3760",
    ),

    "FFKM": MaterialLimits(
        name="FFKM",
        temp_min_c=-15,
        temp_max_c=320,
        temp_peak_c=327,
        pressure_static_max_bar=500,
        pressure_dynamic_max_bar=200,
        aed_certifiable=True,
        shore_a_range=(60, 90),
        note=(
            "Universell chemisch beständig. "
            "Höchste Temperaturbeständigkeit unter Elastomeren. "
            "Spezielle Grades für O₂-Anwendungen (z. B. Kalrez 4079). "
            "Hoher Kostenfaktor."
        ),
        norm_ref="ASTM D1418 / Chemours Kalrez Datasheet",
    ),

    "CR": MaterialLimits(
        name="CR",
        temp_min_c=-40,
        temp_max_c=100,
        temp_peak_c=120,
        pressure_static_max_bar=200,
        pressure_dynamic_max_bar=100,
        aed_certifiable=False,
        shore_a_range=(40, 80),
        note=(
            "Gute Witterungs- und Ozonbeständigkeit. "
            "Mäßige Kraftstoffbeständigkeit — Quellung prüfen. "
            "Eingeschränktes Druckpotenzial. "
            "AED-Zertifizierung nicht etabliert."
        ),
        norm_ref="DIN 7716",
    ),

    "VMQ": MaterialLimits(
        name="VMQ",
        temp_min_c=-60,
        temp_max_c=200,
        temp_peak_c=220,
        pressure_static_max_bar=100,
        pressure_dynamic_max_bar=50,
        aed_certifiable=False,
        shore_a_range=(20, 80),
        note=(
            "Breites Temperaturfenster, niedrige mechanische Festigkeit. "
            "Nicht für Mineralöl und Kraftstoffe. "
            "Geringer Abriebwiderstand — nur für langsame dynamische Bewegungen geeignet. "
            "AED nicht relevant."
        ),
        norm_ref="DIN 7716 / ISO 6072",
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def get_limits(material: str) -> MaterialLimits:
    """
    Gibt die Grenzwerte für einen Werkstoff zurück.

    Args:
        material: Werkstoffbezeichnung (DE/EN, case-insensitive)

    Raises:
        KeyError: wenn Werkstoff nicht bekannt
    """
    key = MATERIAL_ALIASES.get(material.lower().strip())
    if key is None:
        known = sorted(MATERIAL_LIMITS)
        raise KeyError(
            f"Werkstoff '{material}' unbekannt. Bekannte Werkstoffe: {known}"
        )
    return MATERIAL_LIMITS[key]


def check(
    material: str,
    temp_c: Optional[float] = None,
    pressure_bar: Optional[float] = None,
    is_dynamic: bool = False,
    aed_required: bool = False,
) -> LimitsCheckResult:
    """
    Deterministischer Grenzwert-Check für einen Werkstoff.
    Kein LLM.

    Args:
        material:     Werkstoffbezeichnung (DE/EN, case-insensitive)
        temp_c:       Betriebstemperatur [°C] — optional
        pressure_bar: Betriebsdruck [bar] — optional
        is_dynamic:   True = dynamische Abdichtung, False = statisch
        aed_required: True = AED-Zertifizierung gefordert

    Returns:
        LimitsCheckResult mit:
          temp_ok     → True | "warning" | False | None
          pressure_ok → True | False | None
          aed_ok      → True | False | None
    """
    key = MATERIAL_ALIASES.get(material.lower().strip())
    if key is None:
        known = sorted(MATERIAL_LIMITS)
        raise KeyError(
            f"Werkstoff '{material}' unbekannt. Bekannte Werkstoffe: {known}"
        )

    lim = MATERIAL_LIMITS[key]
    warnings: list[str] = []

    # — Temperaturprüfung —
    temp_ok: Union[bool, str, None] = None
    if temp_c is not None:
        if lim.temp_min_c <= temp_c <= lim.temp_max_c:
            temp_ok = True
        elif lim.temp_max_c < temp_c <= lim.temp_peak_c:
            temp_ok = "warning"
            warnings.append(
                f"Temperatur {temp_c} °C liegt im Kurzzeitbereich "
                f"(Dauergrenze: {lim.temp_max_c} °C, Spitzenlast: {lim.temp_peak_c} °C)."
            )
        else:
            temp_ok = False
            if temp_c > lim.temp_peak_c:
                warnings.append(
                    f"Temperatur {temp_c} °C überschreitet Spitzenlast-Grenze "
                    f"{lim.temp_peak_c} °C für {key}."
                )
            else:
                warnings.append(
                    f"Temperatur {temp_c} °C unterschreitet Kältegrenze "
                    f"{lim.temp_min_c} °C für {key}."
                )

    # — Druckprüfung —
    pressure_ok: Optional[bool] = None
    if pressure_bar is not None:
        limit = (
            lim.pressure_dynamic_max_bar if is_dynamic
            else lim.pressure_static_max_bar
        )
        pressure_ok = pressure_bar <= limit
        if not pressure_ok:
            mode = "dynamisches" if is_dynamic else "statisches"
            warnings.append(
                f"Druck {pressure_bar} bar überschreitet {mode} Limit "
                f"von {limit} bar für {key}."
            )

    # — AED-Prüfung —
    aed_ok: Optional[bool] = None
    if aed_required:
        aed_ok = lim.aed_certifiable
        if not aed_ok:
            warnings.append(
                f"AED-Zertifizierung für {key} nicht verfügbar "
                f"(kein AED-relevanter Einsatzbereich)."
            )

    recommendation = _build_recommendation(key, temp_ok, pressure_ok, aed_ok, warnings)

    return LimitsCheckResult(
        material=key,
        limits=lim,
        temp_ok=temp_ok,
        pressure_ok=pressure_ok,
        aed_ok=aed_ok,
        warnings=warnings,
        recommendation=recommendation,
    )


def _build_recommendation(
    material: str,
    temp_ok: Union[bool, str, None],
    pressure_ok: Optional[bool],
    aed_ok: Optional[bool],
    warnings: list[str],
) -> str:
    blockers = []
    cautions = []

    if temp_ok is False:
        blockers.append("Temperatur außerhalb Grenzwert")
    elif temp_ok == "warning":
        cautions.append("Temperatur im Kurzzeitbereich — Dauerbelastung klären")

    if pressure_ok is False:
        blockers.append("Druck überschreitet Limit")

    if aed_ok is False:
        blockers.append("AED-Zertifizierung nicht verfügbar")

    if blockers:
        return f"BLOCKER für {material}: {'; '.join(blockers)}."
    if cautions:
        return f"Hinweis für {material}: {'; '.join(cautions)}."
    if any(v is not None for v in [temp_ok, pressure_ok, aed_ok]):
        return f"{material} erfüllt alle geprüften Grenzwerte."
    return f"Grenzwerte für {material} verfügbar — keine Prüfparameter angegeben."
