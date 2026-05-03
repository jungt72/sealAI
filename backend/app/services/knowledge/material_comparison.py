from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MaterialComparisonProfile:
    canonical: str
    aliases: tuple[str, ...]
    family: str
    material_type: str
    typical_temperature: str
    key_strengths: tuple[str, ...]
    key_limits: tuple[str, ...]
    media_orientation: tuple[str, ...]
    dynamics_orientation: tuple[str, ...]
    typical_uses: tuple[str, ...]
    critical_checks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MaterialComparisonAnswer:
    answer: str
    title: str
    material_ids: tuple[str, str]



_GERMAN_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("Kompatibilitaets", "Kompatibilitäts"),
    ("Rechtsstaende", "Rechtsstände"),
    ("Lieferantenerklaerungen", "Lieferantenerklärungen"),
    ("Salzrueckstaende", "Salzrückstände"),
    ("Spuelung", "Spülung"),
    ("Entwaesserung", "Entwässerung"),
    ("Oberflaechenguete", "Oberflächengüte"),
    ("Güte", "Güte"),
    ("Guete", "Güte"),
    ("Huelsen", "Hülsen"),
    ("Huelse", "Hülse"),
    ("zusaetzlich", "zusätzlich"),
    ("Zusaetzlich", "Zusätzlich"),
    ("verschleissen", "verschleißen"),
    ("Verschleiss", "Verschleiß"),
    ("Staerken", "Stärken"),
    ("Staerke", "Stärke"),
    ("Herstellerpruefung", "Herstellerprüfung"),
    ("Fallpruefung", "Fallprüfung"),
    ("Pruefpunkte", "Prüfpunkte"),
    ("Pruefpfad", "Prüfpfad"),
    ("pruefenswert", "prüfenswert"),
    ("geprueft", "geprüft"),
    ("pruefen", "prüfen"),
    ("Pruefen", "Prüfen"),
    ("moeglich", "möglich"),
    ("Moeglich", "Möglich"),
    ("koennen", "können"),
    ("Koennen", "Können"),
    ("koennte", "könnte"),
    ("koennten", "könnten"),
    ("muessen", "müssen"),
    ("Muessen", "Müssen"),
    ("fuer", "für"),
    ("Fuer", "Für"),
    ("ueber", "über"),
    ("Ueber", "Über"),
    ("haeufig", "häufig"),
    ("Haeufig", "Häufig"),
    ("hoeher", "höher"),
    ("Hoeher", "Höher"),
    ("frueh", "früh"),
    ("frueher", "früher"),
    ("gehoeren", "gehören"),
    ("abhaengig", "abhängig"),
    ("Abhaengig", "Abhängig"),
    ("haengt", "hängt"),
    ("massgebend", "maßgebend"),
    ("Massgebend", "Maßgebend"),
    ("Bestaendigkeit", "Beständigkeit"),
    ("bestaendig", "beständig"),
    ("Waerme", "Wärme"),
    ("waerme", "wärme"),
    ("Oberflaeche", "Oberfläche"),
    ("Gegenlaufflaeche", "Gegenlauffläche"),
    ("Gleitflaeche", "Gleitfläche"),
    ("Dichtflaeche", "Dichtfläche"),
    ("Aussenbereich", "Außenbereich"),
    ("Fuehrungselemente", "Führungselemente"),
    ("Fuehrungen", "Führungen"),
    ("Fuehrung", "Führung"),
    ("Fuellstoffe", "Füllstoffe"),
    ("Fuellstoff", "Füllstoff"),
    ("Stuetzringe", "Stützringe"),
    ("Stuetzwerkstoff", "Stützwerkstoff"),
    ("geometriestuetzig", "geometriestützig"),
    ("Federunterstuetzung", "Federunterstützung"),
    ("Rueckstellung", "Rückstellung"),
    ("Elastizitaet", "Elastizität"),
    ("Verfuegbarkeit", "Verfügbarkeit"),
    ("verfuegbar", "verfügbar"),
    ("Vertraeglichkeit", "Verträglichkeit"),
    ("vertraeglichkeit", "verträglichkeit"),
    ("Oelanteilen", "Ölanteilen"),
    ("Oelanwendungen", "Ölanwendungen"),
    ("Oeltyp", "Öltyp"),
    ("Mineraloele", "Mineralöle"),
    ("Mineralole", "Mineralöle"),
    ("Oelen", "Ölen"),
    ("Oel", "Öl"),
    ("Heisswasser", "Heißwasser"),
    ("Loesemitteln", "Lösemitteln"),
    ("Loesemittel", "Lösemittel"),
    ("Saeuren", "Säuren"),
    ("Trockenlaufnaehe", "Trockenlaufnähe"),
    ("Gehaeuse", "Gehäuse"),
    ("Haerte", "Härte"),
    ("laeuft", "läuft"),
    ("moechtest", "möchtest"),
    ("aehnlich", "ähnlich"),
    ("Aenderung", "Änderung"),
    ("Gasdurchlaessigkeit", "Gasdurchlässigkeit"),
    ("Flexibilitaet", "Flexibilität"),
    ("Abriebbestaendigkeit", "Abriebbeständigkeit"),
    ("Witterungsbestaendigkeit", "Witterungsbeständigkeit"),
    ("Alterungsbestaendigkeit", "Alterungsbeständigkeit"),
    ("Temperaturbestaendigkeit", "Temperaturbeständigkeit"),
)


def humanize_german_technical_text(value: str) -> str:
    """Polish deterministic German answer text without changing routing keys."""
    text = str(value or "")
    for old, new in _GERMAN_TEXT_REPLACEMENTS:
        text = text.replace(old, new)
    text = re.sub(r"(?<=\d) C\b", " °C", text)
    return text

_MATERIAL_PROFILES: dict[str, MaterialComparisonProfile] = {
    "NBR": MaterialComparisonProfile(
        canonical="NBR",
        aliases=("nbr", "nitril", "nitrilkautschuk", "acrylnitril-butadien"),
        family="Nitrilkautschuk",
        material_type="Elastomer",
        typical_temperature="typisch etwa -30 bis +100 C, compound- und medienabhaengig",
        key_strengths=(
            "gute Orientierung fuer Mineralole, Fette und viele klassische Maschinenbaufluide",
            "elastisch, gut vorspannbar und in vielen Standarddichtungen wirtschaftlich",
            "oft robuste Standardwahl fuer Hydraulik-, Pneumatik- und Oelanwendungen, wenn Temperatur und Medium passen",
        ),
        key_limits=(
            "begrenzter bei Ozon, UV, Wetterung, vielen polaren Loesemitteln und anspruchsvoller Chemie",
            "Temperaturfenster enger als bei FKM, FFKM oder PTFE",
            "nicht automatisch geeignet fuer Heisswasser, Dampf, starke Oxidationsmittel oder aggressive Reinigungsmedien",
        ),
        media_orientation=(
            "Mineralol und Schmierfett oft naheliegend zu pruefen",
            "Kraftstoffe, Bioanteile, Additive und Hydraulikfluide muessen compoundbezogen geprueft werden",
            "Wasser/Heisswasser und Chemikalien nicht pauschal freigeben",
        ),
        dynamics_orientation=(
            "elastische Rueckstellung hilft bei klassischen O-Ringen, RWDR und Hydraulikdichtungen",
            "Reibung, Waerme und Verschleiss haengen stark von Schmierung, Oberflaeche und Geschwindigkeit ab",
        ),
        typical_uses=(
            "O-Ringe, Radialwellendichtringe, Hydraulik- und Pneumatikdichtungen",
            "Oel- und Fettabdichtung im allgemeinen Maschinenbau",
        ),
        critical_checks=(
            "exaktes Medium mit Additiven",
            "Dauer- und Spitzentemperatur",
            "Ozon/UV/Wetterung",
            "Druck, Spalt, Bewegung und Schmierung",
        ),
    ),
    "HNBR": MaterialComparisonProfile(
        canonical="HNBR",
        aliases=("hnbr", "hydrierter nbr", "hydriertes nbr"),
        family="Hydrierter Nitrilkautschuk",
        material_type="Elastomer",
        typical_temperature="haeufig hoeher belastbar als NBR, compoundabhaengig grob bis etwa +150 C",
        key_strengths=(
            "bessere Waerme-, Ozon- und Alterungsbestaendigkeit als NBR",
            "oft interessant fuer Oel, Kraftstoffnahe Medien und dynamisch belastete Dichtungen",
            "gute mechanische Festigkeit und Abriebbestaendigkeit je nach Mischung",
        ),
        key_limits=(
            "teurer und nicht automatisch chemisch universell",
            "polare Loesemittel, starke Saeuren/Basen und Dampf muessen genau geprueft werden",
            "Compoundauswahl ist wichtiger als die reine Werkstofffamilie",
        ),
        media_orientation=(
            "Oel- und kraftstoffnahe Anwendungen oft pruefenswert",
            "Heisswasser, Dampf und aggressive Chemie nicht pauschal ableiten",
        ),
        dynamics_orientation=(
            "gute Option bei hoeherer mechanischer Belastung als Standard-NBR",
            "PV, Schmierung und Oberflaeche bleiben massgebend",
        ),
        typical_uses=("Automotive, Hydraulik, dynamische Dichtungen, O-Ringe",),
        critical_checks=("Temperaturprofil", "Medium/Additive", "Druckspalt", "dynamische Reibwaerme"),
    ),
    "FKM": MaterialComparisonProfile(
        canonical="FKM",
        aliases=("fkm", "fpm", "viton", "fluorkautschuk", "fluorelastomer"),
        family="Fluorelastomer",
        material_type="Elastomer",
        typical_temperature="typisch etwa -20 bis +200 C, Tieftemperatur und Medien stark compoundabhaengig",
        key_strengths=(
            "breiteres Temperaturfenster als viele Standardelastomere",
            "oft stark bei Oelen, Kraftstoffen und vielen Kohlenwasserstoffen",
            "gute Alterungs-, Ozon- und Witterungsbestaendigkeit",
        ),
        key_limits=(
            "nicht automatisch geeignet fuer Heisswasser, Dampf, Amine, Ketone, bestimmte Bremsfluide oder starke Laugen",
            "Tieftemperatur kann kritischer sein als bei manchen Alternativen",
            "PFAS-/Fluorpolymer-Dokumentation und Lieferantenfreigaben koennen relevant sein",
        ),
        media_orientation=(
            "Oel, Kraftstoff und Kohlenwasserstoffe oft naheliegend zu pruefen",
            "Heisswasser/Dampf, Amine, Ketone und Laugen besonders vorsichtig behandeln",
        ),
        dynamics_orientation=(
            "als Elastomer gut fuer O-Ringe und viele dynamische Dichtungen einsetzbar, wenn Reibung/Temperatur passen",
            "Waermeeintrag an der Dichtkante kann das nutzbare Fenster deutlich reduzieren",
        ),
        typical_uses=("O-Ringe", "RWDR", "Chemie-/Oel-/Kraftstoffnahe Dichtungen", "statisch und dynamisch"),
        critical_checks=("Mediengruppe", "Temperaturspitzen", "Tieftemperatur", "PFAS-/Compliance-Anforderung"),
    ),
    "FFKM": MaterialComparisonProfile(
        canonical="FFKM",
        aliases=("ffkm", "perfluorelastomer", "kalrez", "chemraz"),
        family="Perfluorelastomer",
        material_type="Elastomer",
        typical_temperature="je nach Compound sehr hoch belastbar, konkrete Grenzen immer Herstellerdatenblatt",
        key_strengths=(
            "sehr breite chemische Bestaendigkeit im Vergleich zu vielen Elastomeren",
            "elastische Dichtfunktion mit deutlich erweitertem Chemiefenster",
            "interessant fuer kritische Chemie-, Halbleiter-, Pharma- oder Hochtemperaturfaelle",
        ),
        key_limits=(
            "sehr kostenintensiv und stark compound-/herstellerabhaengig",
            "nicht automatisch fuer jede Anwendung mechanisch oder thermisch passend",
            "Verfuegbarkeit, Lieferzeit und Compliance-Nachweise muessen frueh geklaert werden",
        ),
        media_orientation=("breite Chemieorientierung, aber keine pauschale Freigabe",),
        dynamics_orientation=("dynamische Anwendungen muessen wegen Reibung, Verschleiss und Waerme besonders geprueft werden",),
        typical_uses=("kritische O-Ringe", "Chemieanlagen", "Pharma", "Halbleiter", "Sonderdichtungen"),
        critical_checks=("Herstellerdatenblatt", "Medium/Konzentration", "Kosten/Nutzen", "Compliance und Verfuegbarkeit"),
    ),
    "EPDM": MaterialComparisonProfile(
        canonical="EPDM",
        aliases=("epdm", "aethylen-propylen", "ethylene propylene"),
        family="Ethylen-Propylen-Dien-Kautschuk",
        material_type="Elastomer",
        typical_temperature="typisch etwa -40 bis +130 C, Heisswasser/Dampf je nach Compound hoeher moeglich",
        key_strengths=(
            "oft stark bei Wasser, Heisswasser, Dampfnahe Anwendungen und Wetterung",
            "gute Ozon-, UV- und Alterungsbestaendigkeit",
            "haeufig relevant fuer Trinkwasser-, Food- oder Hygienefaelle mit passendem Compound und Nachweis",
        ),
        key_limits=(
            "meist nicht passend fuer Mineraloele, Fette, Kraftstoffe und viele Kohlenwasserstoffe",
            "Medien mit Oelanteilen oder Schmierstoffen koennen kritisch sein",
            "Zulassungen und Rezeptur sind bei Wasser/Food/Pharma entscheidend",
        ),
        media_orientation=(
            "Wasser, Dampf und polare Medien oft naheliegend zu pruefen",
            "Oel, Fett und Kraftstoff eher kritisch",
        ),
        dynamics_orientation=(
            "als Elastomer gut dichtend, aber bei dynamischem Lauf sind Reibung, Schmierung und Temperatur zu pruefen",
        ),
        typical_uses=("O-Ringe", "Flachdichtungen", "Wasser-/Dampfanwendungen", "Aussenbereich", "Hygieneanwendungen mit Nachweis"),
        critical_checks=("Oelkontakt", "Dampfprofil", "Zulassungen", "Reinigungschemie", "Temperaturspitzen"),
    ),
    "PTFE": MaterialComparisonProfile(
        canonical="PTFE",
        aliases=("ptfe", "teflon", "polytetrafluorethylen"),
        family="Fluorpolymer",
        material_type="Thermoplast / Fluorpolymer, kein Elastomer",
        typical_temperature="sehr breites Temperaturfenster, haeufig grob -200 bis +250 C; Auslegung und Compound entscheidend",
        key_strengths=(
            "sehr breite chemische Orientierung und niedrige Reibung",
            "kaum elastische Quellung wie Elastomere, gute Medienbarriere in vielen Chemiefaellen",
            "interessant bei aggressiven Medien, Trockenlaufnaehe oder niedriger Reibung, wenn die Konstruktion passt",
        ),
        key_limits=(
            "nicht elastisch wie NBR/FKM/EPDM und oft feder- oder geometriestuetzig auszulegen",
            "Kriechen, Kaltfluss, Spalt, Vorspannung und thermische Ausdehnung sind zentrale Risiken",
            "Compound, Fuellstoff, Gegenlaufpartner und Montage entscheiden stark ueber Funktion",
        ),
        media_orientation=(
            "sehr breite Chemieorientierung, aber Ausnahmen und Fuellstoffe pruefen",
            "Alkalimetalle, Fluorchemie, Temperaturzersetzung und spezifische Medien immer herstellerseitig klaeren",
        ),
        dynamics_orientation=(
            "niedrige Reibung kann vorteilhaft sein",
            "Gegenlaufflaeche, Waermeabfuhr, Fuellstoff und Anpressung sind entscheidend",
        ),
        typical_uses=("PTFE-RWDR", "Federenergized Seals", "Chemiedichtungen", "Gleit- und Fuehrungselemente"),
        critical_checks=("Konstruktion/Vorspannung", "Kriechen/Kaltfluss", "Gegenlaufflaeche", "Fuellstoff", "PFAS-/Compliance-Anforderung"),
    ),
    "PU": MaterialComparisonProfile(
        canonical="PU",
        aliases=("pu", "pur", "tpu", "polyurethan", "polyurethane"),
        family="Polyurethan",
        material_type="Elastomer / thermoplastisches Elastomer, je nach Typ",
        typical_temperature="enger als FKM/PTFE, haeufig etwa -30 bis +100 C, Typ abhaengig",
        key_strengths=(
            "sehr gute Abrieb- und Extrusionsfestigkeit in vielen Hydraulikfaellen",
            "mechanisch robust bei Druck und dynamischer Bewegung",
            "oft stark fuer Stangen-/Kolbendichtungen und Abstreifer",
        ),
        key_limits=(
            "Hydrolyse, Wasser/Heisswasser, Dampf und manche Chemikalien koennen kritisch sein",
            "Temperaturfenster ist begrenzt",
            "Typauswahl ist entscheidend, Polyester/Polyether-Verhalten unterscheiden sich",
        ),
        media_orientation=("Hydraulikoel oft relevant", "Wasser/Heisswasser und aggressive Chemie vorsichtig pruefen"),
        dynamics_orientation=("stark bei Abrieb und Druck, aber Waerme und Schmierung pruefen"),
        typical_uses=("Hydraulikdichtungen", "Abstreifer", "Stangen- und Kolbendichtungen"),
        critical_checks=("Hydrolyse", "Temperatur", "Druckspalt", "Abrasion", "Oeltyp"),
    ),
    "VMQ": MaterialComparisonProfile(
        canonical="VMQ",
        aliases=("vmq", "silikon", "silicone", "silicon", "silikonkautschuk"),
        family="Silikonkautschuk",
        material_type="Elastomer",
        typical_temperature="breites Temperaturfenster, haeufig etwa -50 bis +200 C, mechanisch oft weicher",
        key_strengths=(
            "sehr gutes Tieftemperaturverhalten und gute Waermealterung",
            "oft relevant fuer Food/Pharma/Medizin mit passender Zulassung",
            "gute Flexibilitaet bei niedrigen Temperaturen",
        ),
        key_limits=(
            "mechanisch weniger robust, geringere Abrieb- und Weiterreissfestigkeit als viele technische Elastomere",
            "nicht automatisch passend fuer Oel, Kraftstoff oder dynamisch abrasive Dichtstellen",
            "Gasdurchlaessigkeit kann hoeher sein",
        ),
        media_orientation=("Food/Pharma/Wassernahe Medien mit Zulassung pruefen", "Oel/Kraftstoff je nach Typ kritisch"),
        dynamics_orientation=("eher vorsichtig bei abrasiver oder stark dynamischer Beanspruchung"),
        typical_uses=("statische Dichtungen", "Food/Pharma", "Tieftemperatur", "Medizintechnik"),
        critical_checks=("mechanische Belastung", "Zulassung", "Gasdurchlaessigkeit", "Reinigungsmedium"),
    ),
    "PEEK": MaterialComparisonProfile(
        canonical="PEEK",
        aliases=("peek", "polyetheretherketon"),
        family="Hochleistungsthermoplast",
        material_type="Thermoplast",
        typical_temperature="hohes Temperatur- und Festigkeitsfenster, genaue Grenzen bauteil- und compoundabhaengig",
        key_strengths=(
            "hohe mechanische Festigkeit und gute Temperaturbestaendigkeit",
            "chemisch in vielen Medien robust",
            "gut fuer Stuetzringe, Fuehrungen oder Sonderbauteile",
        ),
        key_limits=(
            "keine elastische Dichtfunktion wie Elastomere",
            "Konstruktion, Toleranzen, Waermeausdehnung und Kosten sind zentral",
            "nicht als direkter Ersatz fuer einen O-Ring ohne Designaenderung verstehen",
        ),
        media_orientation=("breite technische Chemieorientierung, konkrete Medien pruefen"),
        dynamics_orientation=("als Fuehrungs-/Stuetzwerkstoff relevant, Reibpaarung und Verschleiss pruefen"),
        typical_uses=("Stuetzringe", "Fuehrungselemente", "Sonderteile", "Hochtemperaturbauteile"),
        critical_checks=("Bauteildesign", "Toleranz", "Reibpaarung", "Kosten", "Temperatur"),
    ),
}

_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias.casefold(): canonical
    for canonical, profile in _MATERIAL_PROFILES.items()
    for alias in profile.aliases
}

_MATERIAL_TOKEN_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(alias) for alias in _ALIAS_TO_CANONICAL), key=len, reverse=True)) + r")\b",
    re.IGNORECASE | re.UNICODE,
)

_COMPARISON_RE = re.compile(
    r"\b(vergleiche|vergleich(?:e|en)?|materialvergleich|werkstoffvergleich|unterschied(?:e)?|vs\.?|versus|oder|statt|gegenueber|gegenüber|vorteile?|nachteile?|besser|schlechter|wann\s+nimmt\s+man)\b",
    re.IGNORECASE | re.UNICODE,
)


def build_material_comparison_answer(user_input: str) -> MaterialComparisonAnswer | None:
    text = str(user_input or "")
    materials = _extract_materials(text)
    if len(materials) < 2:
        return None
    if not _COMPARISON_RE.search(text):
        return None
    left = _MATERIAL_PROFILES[materials[0]]
    right = _MATERIAL_PROFILES[materials[1]]
    answer = _render_comparison(left, right)
    return MaterialComparisonAnswer(
        answer=answer,
        title=f"Werkstoffvergleich {left.canonical} vs {right.canonical}",
        material_ids=(left.canonical, right.canonical),
    )



def supported_material_ids() -> tuple[str, ...]:
    return tuple(_MATERIAL_PROFILES.keys())

def _extract_materials(text: str) -> list[str]:
    seen: list[str] = []
    for match in _MATERIAL_TOKEN_RE.finditer(text.casefold()):
        canonical = _ALIAS_TO_CANONICAL.get(match.group(1).casefold())
        if canonical and canonical not in seen:
            seen.append(canonical)
    return seen[:2]


def _render_comparison(left: MaterialComparisonProfile, right: MaterialComparisonProfile) -> str:
    answer = "\n".join(
        [
            f"## Werkstoffvergleich: {left.canonical} vs {right.canonical}",
            "",
            f"Kurz gesagt: {left.canonical} und {right.canonical} koennen beide sinnvolle Dichtungswerkstoffe sein, aber sie arbeiten technisch unterschiedlich und sind nicht austauschbar ohne Fallpruefung. Das ist eine allgemeine technische Orientierung, keine Auswahl und keine konkrete Materialfreigabe. Ob ein Werkstoff passt, haengt immer von Medium, Konzentration, Temperatur, Druck, Bewegung, Geometrie, Oberflaeche, Reinigungsprozess und Herstellerdaten ab.",
            "",
            "### Direkter Vergleich",
            "",
            "| Thema | " + left.canonical + " | " + right.canonical + " |",
            "| --- | --- | --- |",
            f"| Werkstofffamilie | {left.family} | {right.family} |",
            f"| Werkstofftyp | {left.material_type} | {right.material_type} |",
            f"| Temperatur-Orientierung | {left.typical_temperature} | {right.typical_temperature} |",
            f"| Staerken | {_join(left.key_strengths)} | {_join(right.key_strengths)} |",
            f"| Typische Grenzen | {_join(left.key_limits)} | {_join(right.key_limits)} |",
            f"| Medien-Orientierung | {_join(left.media_orientation)} | {_join(right.media_orientation)} |",
            f"| Dynamik / Reibung | {_join(left.dynamics_orientation)} | {_join(right.dynamics_orientation)} |",
            f"| Typische Dichtungsrollen | {_join(left.typical_uses)} | {_join(right.typical_uses)} |",
            f"| Kritisch zu pruefen | {_join(left.critical_checks)} | {_join(right.critical_checks)} |",
            "",
            "### Was der Unterschied praktisch bedeutet",
            "",
            *_difference_lines(left, right),
            "",
            "### Fuer eine echte Auswahl fehlen noch diese Angaben",
            "",
            "- Exaktes Medium inklusive Konzentration, Additive, Reinigungsmedien und Kontaktzeit.",
            "- Temperaturprofil: Minimum, normaler Betrieb, Spitzen und Reinigungs-/Sterilisationszyklen.",
            "- Druck direkt an der Dichtstelle, nicht nur Systemdruck.",
            "- Bewegung: statisch, rotierend, linear, oszillierend; bei Dynamik auch Drehzahl oder Geschwindigkeit.",
            "- Geometrie, Spalt, Gegenlaufflaeche, Rauheit, Haerte, Schmierung und Einbauraum.",
            "- Nachweise: Food/FDA, EU 1935/2004, USP Class VI, ATEX, Trinkwasser, TA-Luft oder andere projektbezogene Anforderungen.",
            "",
            "Wenn du mir Medium, Temperatur, Druck und die Dichtstelle nennst, kann SeaLAI daraus einen konkreten Fall aufbauen. Die finale Werkstofffreigabe bleibt trotzdem beim Hersteller oder der verantwortlichen technischen Stelle.",
        ]
    )
    return humanize_german_technical_text(answer)


def _difference_lines(left: MaterialComparisonProfile, right: MaterialComparisonProfile) -> list[str]:
    lines = [
        f"- **{left.canonical}** ist {article(left.material_type)} {left.material_type.lower()} aus der Familie {left.family}. **{right.canonical}** ist {article(right.material_type)} {right.material_type.lower()} aus der Familie {right.family}.",
    ]
    if left.material_type.lower().startswith("elastomer") and "kein elastomer" in right.material_type.lower():
        lines.append(
            f"- **Dichtprinzip:** {left.canonical} dichtet als Elastomer vor allem ueber elastische Verformung und Rueckstellung. {right.canonical} braucht wegen geringer Elastizitaet haeufig mehr konstruktive Fuehrung, Vorspannung oder Federunterstuetzung."
        )
    elif right.material_type.lower().startswith("elastomer") and "kein elastomer" in left.material_type.lower():
        lines.append(
            f"- **Dichtprinzip:** {right.canonical} dichtet als Elastomer vor allem ueber elastische Verformung und Rueckstellung. {left.canonical} braucht wegen geringer Elastizitaet haeufig mehr konstruktive Fuehrung, Vorspannung oder Federunterstuetzung."
        )
    elif left.material_type != right.material_type:
        lines.append(
            "- **Dichtprinzip:** Die Werkstofftypen sind unterschiedlich. Ein Wechsel ist deshalb oft keine reine Materialersetzung, sondern kann Profil, Nut, Vorspannung oder Gegenlaufpartner betreffen."
        )
    else:
        lines.append(
            "- **Dichtprinzip:** Beide liegen in einer aehnlichen Werkstoffklasse, aber Compound, Haerte, Rezeptur und Herstellerfreigabe koennen den Unterschied ausmachen."
        )
    lines.extend(
        [
            "- **Chemie:** Begriffe wie Oel, Wasser, Dampf, Salzwasser oder Reiniger reichen nicht fuer eine Freigabe. Konzentration, Temperatur und Kontaktzeit koennen die Bewertung komplett drehen.",
            "- **Temperatur:** Das nominelle Temperaturfenster ist nur ein Startpunkt. Reibwaerme, Trockenlauf, Druck, Medienalterung und Reinigungszyklen koennen die Grenze frueher erreichen.",
            "- **Mechanik:** Druckspalt, Extrusion, Kriechen, Abrieb und Montage entscheiden, ob ein Werkstoff in der konkreten Dichtungskonstruktion sinnvoll ist.",
        ]
    )
    return lines


def _join(values: tuple[str, ...]) -> str:
    return "; ".join(values)


def article(material_type: str) -> str:
    lower = material_type.lower()
    if lower.startswith("elastomer"):
        return "ein"
    if lower.startswith("thermoplast"):
        return "ein"
    return "eine Werkstoffrichtung:"
