"""
Chemische Beständigkeitstabelle — Deterministisch
Quelle: Parker Chemical Resistance Guide + intern validierte Daten
Kein LLM. Lookup-only.

Bewertung:
  A = beständig (empfohlen)
  B = bedingt beständig (Rückfrage empfohlen)
  C = nicht beständig (gesperrt)
  X = unbekannt (HITL erforderlich)

Abdeckung v1: 11 Medien × 8 Werkstoffe = 88 Einträge
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Rating = str  # "A" | "B" | "C" | "X"


@dataclass
class ResistanceEntry:
    rating: Rating
    note: str
    temp_limit_c: Optional[int] = None
    source: str = "Parker Chemical Resistance Guide"


@dataclass
class ResistanceResult:
    medium: str
    material: str
    rating: Rating
    note: str
    temp_limit_c: Optional[int]
    source: str
    recommendation: str


# Kurzform-Konstruktor für die Tabelle
def _e(
    rating: Rating,
    note: str,
    temp: Optional[int] = None,
    src: str = "Parker Chemical Resistance Guide",
) -> ResistanceEntry:
    return ResistanceEntry(rating=rating, note=note, temp_limit_c=temp, source=src)


# ──────────────────────────────────────────────────────────────────────────────
# Normalisierungs-Aliases (DE + EN, lowercase → interner Schlüssel)
# ──────────────────────────────────────────────────────────────────────────────

MEDIUM_ALIASES: dict[str, str] = {
    "hydrauliköl":      "hydraulic_oil_hlp",
    "hydraulikoel":     "hydraulic_oil_hlp",
    "hlp":              "hydraulic_oil_hlp",
    "hydraulic oil":    "hydraulic_oil_hlp",
    "hydraulic_oil":    "hydraulic_oil_hlp",
    "hydraulic_oil_hlp": "hydraulic_oil_hlp",
    "wasser":           "water",
    "water":            "water",
    "dampf":            "steam",
    "steam":            "steam",
    "diesel":           "diesel",
    "ethanol":          "ethanol",
    "alkohol":          "ethanol",
    "alcohol":          "ethanol",
    "aceton":           "acetone",
    "acetone":          "acetone",
    "keton":            "acetone",
    "schwefelsäure":    "h2so4",
    "schwefelsaeure":   "h2so4",
    "h2so4":            "h2so4",
    "sulfuric acid":    "h2so4",
    "natronlauge":      "naoh",
    "naoh":             "naoh",
    "sodium hydroxide": "naoh",
    "kalilauge":        "naoh",
    "wasserstoff":      "h2",
    "hydrogen":         "h2",
    "h2":               "h2",
    "sauerstoff":       "o2",
    "oxygen":           "o2",
    "o2":               "o2",
    "kohlendioxid":     "co2",
    "carbon dioxide":   "co2",
    "co2":              "co2",
}

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
# Beständigkeitstabelle: 11 Medien × 8 Werkstoffe = 88 Einträge
# ──────────────────────────────────────────────────────────────────────────────

RESISTANCE_TABLE: dict[str, dict[str, ResistanceEntry]] = {

    "hydraulic_oil_hlp": {
        "NBR":  _e("A", "Mineralöl-basierte Hydrauliköle sind der Hauptanwendungsfall für NBR."),
        "FKM":  _e("A", "Exzellente Beständigkeit gegen Mineralöle und deren Additivpakete."),
        "EPDM": _e("C", "EPDM quillt stark in Mineralölen — nicht geeignet."),
        "PTFE": _e("A", "Chemisch inert gegenüber allen Mineralölen."),
        "HNBR": _e("A", "Sehr gute Mineralölbeständigkeit, besser als NBR bei erhöhter Temperatur.", temp=150),
        "FFKM": _e("A", "Universell beständig, auch gegen Hochdruck-HLP-Additivpakete.", src="DIN 51524 / Parker Guide"),
        "CR":   _e("B", "Mäßige Beständigkeit — Quellung möglich; Additive prüfen."),
        "VMQ":  _e("C", "Silikonkautschuk quillt stark in Mineralöl — nicht geeignet."),
    },

    "water": {
        "NBR":  _e("B", "Beständig bis ca. 80 °C; oberhalb Quellung und Härteverlust möglich.", temp=80),
        "FKM":  _e("B", "Wasserbeständig; bei Heißwasser >120 °C Compound-Rückfrage empfohlen.", temp=120),
        "EPDM": _e("A", "Exzellente Wasser- und Heißwasserbeständigkeit bis 150 °C.", temp=150),
        "PTFE": _e("A", "Chemisch inert, auch gegen entionisiertes Wasser."),
        "HNBR": _e("A", "Sehr gute Heißwasserbeständigkeit bis 150 °C.", temp=150),
        "FFKM": _e("A", "Universell beständig."),
        "CR":   _e("A", "Gute Wasserbeständigkeit."),
        "VMQ":  _e("A", "Gute Wasserbeständigkeit; Extraktion von Weichmachern bei Dauerbeaufschlagung prüfen."),
    },

    "steam": {
        "NBR":  _e("C", "Dampf greift NBR ab 120 °C stark an — nicht geeignet.", temp=100),
        "FKM":  _e("C", "FKM hydrolysiert unter Dampf — nicht geeignet.", src="Parker Guide / AMS 7276"),
        "EPDM": _e("A", "Beste Dampfbeständigkeit unter Standardwerkstoffen bis 150 °C.", temp=150),
        "PTFE": _e("A", "Beständig bis ca. 230 °C Dampftemperatur.", temp=230),
        "HNBR": _e("B", "Begrenzte Dampfbeständigkeit; Compound-Auswahl kritisch, max. 130 °C.", temp=130),
        "FFKM": _e("A", "Exzellent beständig gegen Dampf (spezielle FFKM-Grades erforderlich)."),
        "CR":   _e("C", "Chloropren degradiert unter Dampf — nicht geeignet."),
        "VMQ":  _e("C", "VMQ versagt unter Sattdampf durch Hydrolyse — nicht geeignet."),
    },

    "diesel": {
        "NBR":  _e("A", "Standardwerkstoff für Dieselkraftstoff-Anwendungen."),
        "FKM":  _e("A", "Sehr gute Kraftstoffbeständigkeit."),
        "EPDM": _e("C", "EPDM quillt stark in Kraftstoffen — nicht geeignet."),
        "PTFE": _e("A", "Chemisch inert."),
        "HNBR": _e("A", "Exzellente Kraftstoffbeständigkeit, auch gegen FAME-Beimischungen (Bio-Diesel)."),
        "FFKM": _e("A", "Universell beständig."),
        "CR":   _e("B", "Mäßige Kraftstoffbeständigkeit — Quellung prüfen."),
        "VMQ":  _e("C", "Nicht geeignet für Kohlenwasserstoff-Kraftstoffe."),
    },

    "ethanol": {
        "NBR":  _e("B", "Quellneigung in Alkoholen; bei E85-Kraftstoff kritisch prüfen.", temp=60),
        "FKM":  _e("B", "Standard-FKM begrenzt beständig; spezielle AED-Grades verfügbar.", src="Parker Guide / SAE J200"),
        "EPDM": _e("A", "Exzellente Alkoholbeständigkeit."),
        "PTFE": _e("A", "Chemisch inert."),
        "HNBR": _e("B", "Bedingt beständig; Compound-Spezifikation prüfen.", temp=80),
        "FFKM": _e("A", "Universell beständig."),
        "CR":   _e("B", "Mäßige Beständigkeit in kurzkettigen Alkoholen."),
        "VMQ":  _e("A", "Gute Alkoholbeständigkeit."),
    },

    "acetone": {
        "NBR":  _e("C", "Aceton (Keton) greift NBR stark an — nicht geeignet."),
        "FKM":  _e("C", "Ketone greifen FKM an — nicht geeignet.", src="Parker Guide"),
        "EPDM": _e("A", "Exzellente Beständigkeit gegen Ketone und Ester."),
        "PTFE": _e("A", "Chemisch inert."),
        "HNBR": _e("C", "Nicht geeignet für Ketone."),
        "FFKM": _e("A", "Universell beständig."),
        "CR":   _e("C", "Nicht geeignet für Ketone."),
        "VMQ":  _e("B", "Bedingt beständig; Quellung möglich, kurzzeitiger Kontakt prüfen."),
    },

    "h2so4": {
        "NBR":  _e("C", "Schwefelsäure greift NBR an — nicht geeignet."),
        "FKM":  _e("B", "Beständig gegen verdünnte H₂SO₄ (<70 %); konzentriert + heiß kritisch.", temp=100),
        "EPDM": _e("B", "Mäßige Beständigkeit gegen verdünnte Säuren; Konzentration und Temp prüfen.", temp=60),
        "PTFE": _e("A", "Beständig gegen konzentrierte und verdünnte H₂SO₄."),
        "HNBR": _e("C", "Nicht geeignet für starke Mineralsäuren."),
        "FFKM": _e("A", "Universell beständig, auch gegen konzentrierte Säuren.", src="Chemours / Parker Guide"),
        "CR":   _e("C", "Nicht geeignet für konzentrierte Schwefelsäure."),
        "VMQ":  _e("C", "Nicht geeignet für starke Säuren."),
    },

    "naoh": {
        "NBR":  _e("B", "Bedingt beständig gegen verdünnte NaOH; konzentriert + heiß meiden.", temp=60),
        "FKM":  _e("C", "FKM wird von starken Basen und Aminen angegriffen — nicht geeignet.", src="Parker Guide"),
        "EPDM": _e("A", "Exzellente Laugenbeständigkeit — bevorzugter Werkstoff für Basen."),
        "PTFE": _e("A", "Chemisch inert gegen Laugen."),
        "HNBR": _e("B", "Begrenzte Laugenbeständigkeit; konzentriert vermeiden.", temp=60),
        "FFKM": _e("A", "Universell beständig."),
        "CR":   _e("B", "Mäßige Beständigkeit gegen verdünnte Laugen."),
        "VMQ":  _e("B", "Bedingt beständig; starke Basen können VMQ hydrolysieren.", temp=60),
    },

    "h2": {
        "NBR":  _e("B", "RGD-Risiko (Rapid Gas Decompression) bei Druckwechseln >200 bar.", src="ISO 23936-2 / Parker Guide"),
        "FKM":  _e("A", "Gute H₂-Beständigkeit; RGD-optimiertes Compound für Hochdruck wählen.", src="ISO 23936-2"),
        "EPDM": _e("B", "Erhöhte H₂-Permeation; für Hochdruck-H₂ Compounds spezifizieren."),
        "PTFE": _e("A", "Sehr geringe Permeation, chemisch inert."),
        "HNBR": _e("A", "Sehr gute RGD-Beständigkeit — empfohlen für H₂-Hochdruckanwendungen.", src="ISO 23936-2"),
        "FFKM": _e("A", "Universell beständig, niedrige Permeabilität."),
        "CR":   _e("B", "Mäßige H₂-Beständigkeit; RGD-Risiko prüfen."),
        "VMQ":  _e("B", "Höhere H₂-Permeation als FKM/HNBR — für Hochdruck ungeeignet."),
    },

    "o2": {
        "NBR":  _e("C", "Brandgefahr in O₂-Atmosphäre >21 % — nicht geeignet.", src="BAM / ASTM G86"),
        "FKM":  _e("B", "Besser als NBR; Materialprüfnachweis für >21 % O₂ zwingend erforderlich.", src="BAM / ASTM G86", temp=200),
        "EPDM": _e("C", "Degradiert in angereicherter O₂-Atmosphäre schnell."),
        "PTFE": _e("A", "Beständig; LOX-Sondergrade für Flüssigsauerstoff verwenden.", src="ASTM G63"),
        "HNBR": _e("B", "Besser als NBR; Freigabetest für >21 % O₂ erforderlich.", src="BAM-Richtlinien"),
        "FFKM": _e("A", "Bevorzugter Werkstoff für O₂-Anwendungen (z. B. Kalrez 4079).", src="Chemours / ASTM G86"),
        "CR":   _e("C", "Degradiert in angereicherter O₂-Atmosphäre — nicht geeignet."),
        "VMQ":  _e("C", "VMQ ist brennbar in angereicherter O₂-Atmosphäre — nicht geeignet.", src="BAM"),
    },

    "co2": {
        "NBR":  _e("A", "Gute CO₂-Beständigkeit; bei überkritischem CO₂ (scCO₂) Extraktion von Weichmachern möglich.", src="Parker Guide"),
        "FKM":  _e("A", "Gute CO₂-Beständigkeit."),
        "EPDM": _e("A", "Gute CO₂-Beständigkeit."),
        "PTFE": _e("A", "Chemisch inert."),
        "HNBR": _e("A", "Sehr gute RGD-Beständigkeit auch für CO₂-Hochdruck.", src="ISO 23936-2"),
        "FFKM": _e("A", "Universell beständig."),
        "CR":   _e("A", "Gute CO₂-Beständigkeit."),
        "VMQ":  _e("A", "Gute CO₂-Beständigkeit."),
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def lookup(medium: str, material: str) -> ResistanceResult:
    """
    Gibt die Beständigkeitsbewertung für Medium × Werkstoff zurück.

    Args:
        medium:   Medienbezeichnung (DE/EN, case-insensitive)
        material: Werkstoffbezeichnung (DE/EN, case-insensitive)

    Returns:
        ResistanceResult mit Bewertung, Begründung, Temp-Limit und Quellenhinweis

    Raises:
        KeyError: wenn Medium oder Werkstoff nicht in der Tabelle enthalten
    """
    medium_key = MEDIUM_ALIASES.get(medium.lower().strip())
    if medium_key is None:
        known = sorted(set(MEDIUM_ALIASES.values()))
        raise KeyError(
            f"Medium '{medium}' unbekannt. Bekannte Medien: {known}"
        )

    material_key = MATERIAL_ALIASES.get(material.lower().strip())
    if material_key is None:
        known = sorted(set(MATERIAL_ALIASES.values()))
        raise KeyError(
            f"Werkstoff '{material}' unbekannt. Bekannte Werkstoffe: {known}"
        )

    entry = RESISTANCE_TABLE.get(medium_key, {}).get(material_key)
    if entry is None:
        return ResistanceResult(
            medium=medium,
            material=material_key,
            rating="X",
            note="Kombination nicht bewertet — HITL erforderlich.",
            temp_limit_c=None,
            source="intern",
            recommendation="Manuelles Expert-Review erforderlich.",
        )

    return ResistanceResult(
        medium=medium,
        material=material_key,
        rating=entry.rating,
        note=entry.note,
        temp_limit_c=entry.temp_limit_c,
        source=entry.source,
        recommendation=_build_recommendation(entry),
    )


def get_compatible_materials(medium: str) -> list[ResistanceResult]:
    """
    Gibt alle Werkstoffe mit Bewertung A oder B für ein Medium zurück,
    sortiert A → B.
    """
    medium_key = MEDIUM_ALIASES.get(medium.lower().strip())
    if not medium_key:
        return []
    results = [
        ResistanceResult(
            medium=medium,
            material=mat,
            rating=e.rating,
            note=e.note,
            temp_limit_c=e.temp_limit_c,
            source=e.source,
            recommendation=_build_recommendation(e),
        )
        for mat, e in RESISTANCE_TABLE.get(medium_key, {}).items()
        if e.rating in ("A", "B")
    ]
    return sorted(results, key=lambda r: r.rating)  # A vor B


def _build_recommendation(entry: ResistanceEntry) -> str:
    base = {
        "A": "Einsatz empfohlen.",
        "B": "Bedingt geeignet — Rückfrage mit Anwendungsdetails empfohlen.",
        "C": "Nicht geeignet — alternativen Werkstoff wählen.",
        "X": "Nicht bewertet — Expertenrückfrage erforderlich.",
    }[entry.rating]
    if entry.temp_limit_c is not None:
        base += f" Temperaturgrenze: max. {entry.temp_limit_c} °C."
    return base
