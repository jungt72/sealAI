from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .keyword_foundation import keyword_foundation_rows


@dataclass(frozen=True)
class RoadmapPage:
    phase: int
    path: str
    route_status: str
    page_type: str
    primary_keyword: str
    secondary_keywords: tuple[str, ...]
    intent: str
    h1: str
    meta_title: str
    meta_description: str
    v8_claim_boundary: str
    rfq_fields: tuple[str, ...]
    internal_links: tuple[str, ...]


RUN0_PAGES: tuple[RoadmapPage, ...] = (
    RoadmapPage(
        1,
        "/wissen/wellendichtring",
        "existing_dynamic_route",
        "pillar knowledge page",
        "wellendichtring",
        ("radialwellendichtring", "rwdr", "din 3760"),
        "Terminologie, Einsatzkontext und Anfrageparameter verstehen",
        "Wellendichtring: Funktion, Grenzen und Angaben fuer eine Herstellerpruefung",
        "Wellendichtring: Funktion, Grenzen, DIN 3760 und Anfrageparameter",
        "Technische Orientierung zu Wellendichtringen: Funktion, Grenzen, typische Angaben und strukturierte Anfragebasis fuer die Herstellerpruefung.",
        "Keine finale Auslegung, keine Freigabe einer konkreten Dichtung.",
        ("Welle", "Gehaeuse", "Medium", "Temperatur", "Druck", "Drehzahl", "Bauraum", "Werkstoffwunsch"),
        ("/wissen/radialwellendichtring-din-3760", "/werkstoffe/fkm", "/wissen/wellendichtring-undicht"),
    ),
    RoadmapPage(
        1,
        "/werkstoffe/epdm",
        "existing_dynamic_route",
        "material page",
        "epdm dichtung",
        ("dichtung dampf", "dichtung wasserstoff"),
        "EPDM als Dichtungswerkstoff einordnen",
        "EPDM-Dichtung: Medien, Temperaturgrenzen und offene Pruefpunkte",
        "EPDM-Dichtung: Einsatz, Grenzen und RFQ-Angaben",
        "EPDM technisch einordnen: typische Einsatzfelder, kritische Medien und Angaben, die vor einer Herstellerpruefung benoetigt werden.",
        "Materialeignung nur als Orientierung; finale Bewertung bleibt Hersteller-/Spezialistenpruefung.",
        ("Medium", "Konzentration", "Temperatur", "Druck", "Dauerbetrieb", "Reinigung", "Normen"),
        ("/werkstoffe/nbr", "/werkstoffe/fkm", "/medien/dichtung-dampf"),
    ),
    RoadmapPage(
        1,
        "/werkstoffe/nbr",
        "existing_dynamic_route",
        "material page",
        "nbr dichtung",
        ("nbr vs fkm", "dichtung oel"),
        "NBR fuer oel- und kraftstoffnahe Anwendungen einordnen",
        "NBR-Dichtung: Einsatzbereiche, Grenzen und Vergleich zu FKM",
        "NBR-Dichtung: Oel, Temperatur, Grenzen und Anfrageparameter",
        "Orientierung zu NBR-Dichtungen fuer oelnahe Anwendungen mit klaren Angaben fuer eine pruefbare technische Anfrage.",
        "Keine pauschale Medienfreigabe; Grenzfaelle muessen fachlich geprueft werden.",
        ("Oeltyp", "Additive", "Temperatur", "Druck", "Bewegung", "Dichtungsgeometrie"),
        ("/werkstoffe/fkm", "/medien/dichtung-oel", "/wissen/wellendichtring"),
    ),
    RoadmapPage(
        1,
        "/werkstoffe/fkm",
        "existing_dynamic_route",
        "material page",
        "fkm dichtung",
        ("viton dichtung", "fkm vs epdm", "nbr vs fkm"),
        "FKM/Viton fuer Temperatur und Medienbestaendigkeit einordnen",
        "FKM-Dichtung: Medien, Temperatur und Grenzen vor der Herstellerpruefung",
        "FKM-Dichtung: Einsatz, Viton-Bezug, Grenzen und RFQ-Angaben",
        "FKM/Viton technisch einordnen und die offenen Betriebsdaten fuer eine belastbare Herstellerpruefung sichtbar machen.",
        "FKM/Viton nicht als automatisch geeignet darstellen.",
        ("Medium", "Temperatur", "Konzentration", "Druck", "Kontaktzeit", "Freigaben", "Dynamik"),
        ("/werkstoffe/epdm", "/werkstoffe/ptfe", "/medien/dichtung-oel"),
    ),
    RoadmapPage(
        1,
        "/werkstoffe/ptfe",
        "existing_dynamic_route",
        "material page",
        "ptfe dichtung",
        ("ptfe vs fkm", "dichtung chemikalienbestaendig"),
        "PTFE als chemisch bestaendigen Dichtungswerkstoff einordnen",
        "PTFE-Dichtung: chemische Bestaendigkeit, Grenzen und Anfrageparameter",
        "PTFE-Dichtung: Einsatz, Grenzen, Vergleich zu FKM und RFQ-Daten",
        "PTFE fuer chemische, thermische und konstruktive Anforderungen einordnen, ohne finale Eignung zu behaupten.",
        "Keine abschliessende Materialfreigabe; Betriebsdaten und Konstruktion entscheiden.",
        ("Chemikalie", "Konzentration", "Temperatur", "Druck", "Verformung", "Dichtstelle", "Gegenlaufpartner"),
        ("/werkstoffe/fkm", "/medien/dichtung-salzsaeure", "/medien/dichtung-chemikalienbestaendig"),
    ),
    RoadmapPage(
        2,
        "/wissen/radialwellendichtring-din-3760",
        "existing_dynamic_route",
        "standard knowledge page",
        "radialwellendichtring din 3760",
        ("din 3760", "radialwellendichtring bauform", "wellendichtring maße"),
        "DIN- und Masskontext vor einer Anfrage klaeren",
        "Radialwellendichtring DIN 3760: Bauformen, Masse und Anfrageparameter",
        "Radialwellendichtring DIN 3760: Orientierung und RFQ-Angaben",
        "DIN-3760-Kontext fuer eine strukturierte Anfragebasis erklaeren, nicht als technische Freigabe verwenden.",
        "Normbezug ist Orientierung; konkrete Auslegung bleibt pruefpflichtig.",
        ("Nennmass", "Bauform", "Werkstoff", "Feder", "Drehzahl", "Einbauraum", "Medium"),
        ("/wissen/wellendichtring", "/wissen/wellendichtring-masse", "/werkstoffe/fkm"),
    ),
    RoadmapPage(
        2,
        "/medien/dichtung-oel",
        "existing_dynamic_route",
        "media page",
        "dichtung öl",
        ("nbr dichtung", "fkm dichtung"),
        "Dichtungswerkstoffe fuer Oel-Kontexte vorpruefen",
        "Dichtung fuer Oel: Werkstoff-Orientierung und notwendige Betriebsdaten",
        "Dichtung fuer Oel: NBR, FKM und Angaben fuer die Herstellerpruefung",
        "Oel-Kontexte strukturiert klaeren: Oeltyp, Additive, Temperatur, Druck und Dynamik als Pruefbasis.",
        "Keine pauschale Oelbestaendigkeit behaupten.",
        ("Oeltyp", "Additive", "Temperatur", "Druck", "Drehzahl", "Dichtungsart"),
        ("/werkstoffe/nbr", "/werkstoffe/fkm", "/wissen/wellendichtring"),
    ),
    RoadmapPage(
        2,
        "/medien/dichtung-dampf",
        "existing_dynamic_route",
        "media page",
        "dichtung dampf",
        ("epdm dichtung", "ptfe dichtung"),
        "Dampf als kritisches Medium fuer Dichtungen einordnen",
        "Dichtung fuer Dampf: Temperatur, Druck und offene Pruefpunkte",
        "Dichtung fuer Dampf: Werkstoff-Orientierung und RFQ-Angaben",
        "Dampf-Anwendungen ueber Temperatur, Druck, Kondensat und Betriebsweise fuer Herstellerpruefung strukturieren.",
        "Keine Dampf-Freigabe ohne genaue Betriebsdaten.",
        ("Dampftemperatur", "Druck", "Sattdampf/Ueberhitzung", "Zyklen", "Reinigung", "Dichtungsart"),
        ("/werkstoffe/epdm", "/werkstoffe/ptfe", "/wissen/dichtung-temperatur-druck"),
    ),
    RoadmapPage(
        2,
        "/wissen/wellendichtring-undicht",
        "existing_dynamic_route",
        "diagnostic workflow page",
        "wellendichtring undicht",
        ("dichtung undicht ursache", "wellendichtring ausfall"),
        "Fehlerbild strukturiert fuer Herstellerklaerung aufnehmen",
        "Wellendichtring undicht: Ursachen eingrenzen und Anfragebasis vorbereiten",
        "Wellendichtring undicht: Ursachen, Pruefpunkte und Herstelleranfrage",
        "Leckageursachen strukturieren und fehlende Angaben sichtbar machen; keine finale Schadensursache behaupten.",
        "Keine finale Root-Cause-Analyse ohne Bauteil-/Betriebsdaten.",
        ("Leckageort", "Betriebsstunden", "Medium", "Drehzahl", "Wellenzustand", "Einbau", "Temperatur"),
        ("/wissen/wellendichtring", "/wissen/dichtung-schadensanalyse", "/werkstoffe/fkm"),
    ),
    RoadmapPage(
        3,
        "/anfrage/dichtung-auslegen-lassen",
        "new_route_required",
        "rfq landing page",
        "dichtung auslegen lassen",
        ("dichtung technische anfrage", "dichtung anfrage vorbereiten"),
        "Hohe kommerzielle Intention in geregelte RFQ-Qualifizierung ueberfuehren",
        "Dichtung auslegen lassen: technische Anfrage strukturiert vorbereiten",
        "Dichtung auslegen lassen: Anfragebasis statt Schnellfreigabe",
        "SealAI als Qualifikationsruntime positionieren: Anforderungen klaeren, Herstellerpruefung vorbereiten.",
        "Nicht versprechen, dass SealAI final auslegt oder freigibt.",
        ("Anwendung", "Medium", "Temperatur", "Druck", "Bewegung", "Bauraum", "Normen", "Menge", "Zeithorizont"),
        ("/wissen/wellendichtring", "/werkstoffe/fkm", "/wissen/dichtung-anfrage-vorbereiten"),
    ),
)


def _metrics_by_keyword(conn: sqlite3.Connection, *, location_code: int, language_code: str) -> dict[str, dict]:
    return {
        row["keyword"]: row
        for row in keyword_foundation_rows(conn, location_code=location_code, language_code=language_code)
    }


def roadmap_rows(conn: sqlite3.Connection, *, location_code: int, language_code: str) -> list[dict]:
    metrics = _metrics_by_keyword(conn, location_code=location_code, language_code=language_code)
    rows: list[dict] = []
    for page in RUN0_PAGES:
        primary = metrics.get(page.primary_keyword, {})
        secondary_volume = sum(int(metrics.get(keyword, {}).get("search_volume") or 0) for keyword in page.secondary_keywords)
        rows.append(
            {
                **page.__dict__,
                "secondary_keywords": ", ".join(page.secondary_keywords),
                "rfq_fields": ", ".join(page.rfq_fields),
                "internal_links": ", ".join(page.internal_links),
                "primary_search_volume": primary.get("search_volume"),
                "primary_cpc": primary.get("cpc"),
                "primary_competition_index": primary.get("competition_index"),
                "opportunity_score": primary.get("opportunity_score", page.phase * 10),
                "secondary_known_volume": secondary_volume,
            }
        )
    return sorted(rows, key=lambda row: (row["phase"], -float(row["opportunity_score"] or 0), row["path"]))
