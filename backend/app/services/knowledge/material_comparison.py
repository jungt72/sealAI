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
    material_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MaterialDefinitionAnswer:
    answer: str
    title: str
    material_id: str



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
    ("verschleiss", "verschleiß"),
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
    ("haengen", "hängen"),
    ("massgebend", "maßgebend"),
    ("Massgebend", "Maßgebend"),
    ("Masshaltigkeit", "Maßhaltigkeit"),
    ("Bestaendigkeit", "Beständigkeit"),
    ("bestaendig", "beständig"),
    ("Waerme", "Wärme"),
    ("waerme", "wärme"),
    ("Waermeabfuhr", "Wärmeabfuhr"),
    ("Oberflaeche", "Oberfläche"),
    ("Gegenlaufflaeche", "Gegenlauffläche"),
    ("Gleitflaeche", "Gleitfläche"),
    ("Dichtflaeche", "Dichtfläche"),
    ("Aussenbereich", "Außenbereich"),
    ("Fuehrungselemente", "Führungselemente"),
    ("Fuehrungsaufgaben", "Führungsaufgaben"),
    ("Fuehrungsringe", "Führungsringe"),
    ("Fuehrungen", "Führungen"),
    ("Fuehrung", "Führung"),
    ("Fuellstoffe", "Füllstoffe"),
    ("Fuellstoff", "Füllstoff"),
    ("gefuellt", "gefüllt"),
    ("ungefuellt", "ungefüllt"),
    ("Stuetzringe", "Stützringe"),
    ("Stuetzwerkstoff", "Stützwerkstoff"),
    ("Stuetz", "Stütz"),
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
    ("Mineralol", "Mineralöl"),
    ("Mineraloele", "Mineralöle"),
    ("Mineralole", "Mineralöle"),
    ("Oelen", "Ölen"),
    ("Oel", "Öl"),
    ("oel", "öl"),
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
    ("Designaenderung", "Designänderung"),
    ("Gasdurchlaessigkeit", "Gasdurchlässigkeit"),
    ("Flexibilitaet", "Flexibilität"),
    ("flexibilitaet", "flexibilität"),
    ("Abriebbestaendigkeit", "Abriebbeständigkeit"),
    ("Witterungsbestaendigkeit", "Witterungsbeständigkeit"),
    ("Wetterung", "Witterung"),
    ("Alterungsbestaendigkeit", "Alterungsbeständigkeit"),
    ("Temperaturbestaendigkeit", "Temperaturbeständigkeit"),
    ("bestaendigkeit", "beständigkeit"),
    ("faehig", "fähig"),
    ("Chemiefaellen", "Chemiefällen"),
    ("chemiefaellen", "chemiefällen"),
    ("klaeren", "klären"),
    ("Primaerdichtfunktion", "Primärdichtfunktion"),
    ("Dichtkoerper", "Dichtkörper"),
    ("Praezisions", "Präzisions"),
    ("praeziser", "präziser"),
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
        typical_temperature=(
            "Standard grob -30 bis +100 C; Sondercompounds etwa -40 C "
            "Tieftemperatur oder kurzzeitig +120 C moeglich; Dauerbetrieb "
            "oberhalb +100 C compoundbezogen kritisch pruefen"
        ),
        key_strengths=(
            "wirtschaftlicher Standard-Elastomerwerkstoff fuer viele oel- und fettnahe Dichtstellen",
            "ACN-Gehalt typischerweise grob 18 bis 50 %: hoeherer ACN-Anteil verbessert meist Oel-/Kraftstofforientierung, reduziert aber Tieftemperaturflexibilitaet",
            "typische Haerten in Dichtungen oft 60 bis 90 Shore A; 70 Shore A ist ein haeufiger Startpunkt fuer O-Ringe",
            "elastische Rueckstellung und gute Vorspannbarkeit fuer O-Ringe, RWDR, Hydraulik- und Pneumatikdichtungen",
        ),
        key_limits=(
            "Ozon, UV, Wetterung und Aussenklima sind ohne Schutz oder passende Rezeptur kritisch",
            "polare Loesemittel, Aromaten, Ketone, Ester, starke Oxidationsmittel, Dampf und Heisswasser koennen die Auswahl schnell ausschliessen",
            "Dauerbetrieb ueber dem Standard-Temperaturfenster beschleunigt Alterung, Haerteanstieg, Rissbildung und bleibende Verformung",
            "bei dynamischen Dichtungen begrenzen Schmierung, Reibwaerme, Wellenrauheit, Exzentrizitaet und Umfangsgeschwindigkeit die Nutzbarkeit",
        ),
        media_orientation=(
            "Mineraloele, Schmierfette und viele klassische HLP-/HLVP-Hydraulikfluide sind haeufig naheliegende Prueffelder",
            "Kraftstoffe, Bioanteile, Additive, synthetische Oele und schwer entflammbare Hydraulikfluide muessen compoundbezogen bewertet werden",
            "Wasser, Heisswasser, Dampf, Bremsfluide, aggressive Reiniger und Prozesschemie nicht aus dem Begriff NBR ableiten",
        ),
        dynamics_orientation=(
            "bei O-Ringen sind Quellung, Druckverformungsrest, Nutfuellung, Verpressung und Spaltextrusion zentrale Pruefpunkte",
            "bei RWDR sind Dichtlippengeometrie, Schmierung, Gegenlaufflaeche, Haerte, Rauheit, Rundlauf und Reibwaerme entscheidend",
            "Reibung, Waerme und Verschleiss haengen stark von Schmierung, Oberflaeche, Geschwindigkeit und Medium ab",
        ),
        typical_uses=(
            "O-Ringe, Radialwellendichtringe, Hydraulik- und Pneumatikdichtungen",
            "Oel- und Fettabdichtung im allgemeinen Maschinenbau",
        ),
        critical_checks=(
            "exaktes Medium mit Additiven, Konzentration, Alterung und Reinigungsmedien",
            "Dauer- und Spitzentemperatur an der Dichtstelle, nicht nur Umgebungstemperatur",
            "ACN-Gehalt, Haerte Shore A, Tieftemperaturkennwerte, Druckverformungsrest und Volumenaenderung im Zielmedium",
            "Ozon/UV/Wetterung, Lagerung und Aussenkontakt",
            "Druck, Spalt, Bewegung, Schmierung, Reibwaerme und Gegenlaufflaeche",
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
        typical_temperature=(
            "haeufig etwa -15/-20 bis +230/+260 C; Hochtemperatur-Compounds "
            "koennen je nach Hersteller grob bis +300/+320 C reichen; "
            "Tieftemperatur und Dauergrenze immer Datenblatt"
        ),
        key_strengths=(
            "sehr breite chemische Bestaendigkeit im Vergleich zu fast allen klassischen Elastomeren",
            "elastische Dichtfunktion mit deutlich erweitertem Chemiefenster",
            "typische Haerten in vielen O-Ring-Compounds etwa 70 bis 90 Shore A",
            "interessant fuer kritische Chemie-, Halbleiter-, Pharma- oder Hochtemperaturfaelle",
        ),
        key_limits=(
            "sehr kostenintensiv; Materialkosten liegen oft um Größenordnungen über Standardelastomeren",
            "Druckverformungsrest, Tieftemperatur, Dampf, Amine, Plasma, Abrieb und dynamische Reibung bleiben compoundbezogene Pruefthemen",
            "nicht automatisch fuer jede Anwendung mechanisch, tribologisch oder thermisch passend",
            "Verfuegbarkeit, Lieferzeit und Compliance-Nachweise muessen frueh geklaert werden",
        ),
        media_orientation=(
            "breite Chemieorientierung fuer viele aggressive Chemikalien, Loesemittel, Saeuren, Laugen und Oxidationsmedien",
            "Dampf, Heisswasser, Aminchemie, Hochtemperaturoxidation, Plasma und Spezialreiniger koennen je nach Grade trotzdem kritisch sein",
            "keine pauschale Freigabe ohne Medienname, Konzentration, Temperatur, Kontaktzeit und Herstellerdaten",
        ),
        dynamics_orientation=(
            "dynamische Anwendungen muessen wegen Reibung, Verschleiss, Waermeeintrag und Kosten besonders geprueft werden",
            "bei O-Ringen sind Compression Set, Nutfuellung und Langzeitelastizitaet oft entscheidender als die reine Chemiebestaendigkeit",
        ),
        typical_uses=("kritische O-Ringe", "Chemieanlagen", "Pharma", "Halbleiter", "Sonderdichtungen"),
        critical_checks=(
            "Herstellerdatenblatt mit genauem Compound",
            "Medium/Konzentration/Kontaktzeit und Reinigungszyklen",
            "Temperaturprofil inklusive Dauerbetrieb, Peaks, CIP/SIP oder Stillstand",
            "Kosten/Nutzen, Lieferzeit, Mindestmengen und Compliance",
            "Druckverformungsrest, Extrusion, dynamische Reibwaerme und Montage",
        ),
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
        dynamics_orientation=("stark bei Abrieb und Druck, aber Waerme und Schmierung pruefen",),
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
        dynamics_orientation=("eher vorsichtig bei abrasiver oder stark dynamischer Beanspruchung",),
        typical_uses=("statische Dichtungen", "Food/Pharma", "Tieftemperatur", "Medizintechnik"),
        critical_checks=("mechanische Belastung", "Zulassung", "Gasdurchlaessigkeit", "Reinigungsmedium"),
    ),
    "POM": MaterialComparisonProfile(
        canonical="POM",
        aliases=("pom", "polyoxymethylen", "polyacetal", "acetal", "delrin", "hostaform"),
        family="Polyoxymethylen / Polyacetal",
        material_type="Thermoplast, kein Elastomer",
        typical_temperature=(
            "orientierend etwa -40 bis +100/+110 C im Dauerbetrieb; "
            "kurzzeitige Spitzen je nach Type grob bis +120/+140 C pruefen"
        ),
        key_strengths=(
            "hohe Steifigkeit, gute Masshaltigkeit und geringe Feuchteaufnahme im Vergleich zu PA",
            "niedrige Reibung und gutes Verschleissverhalten in vielen Gleit- und Fuehrungsaufgaben",
            "oel-, fett- und kraftstoffnahe Medien sind haeufig naheliegende Prueffelder",
            "gut zerspanbar und oft wirtschaftlich fuer Praezisions-, Stuetz- und Fuehrungsteile",
        ),
        key_limits=(
            "keine elastische Primaerdichtfunktion wie NBR, EPDM, FKM oder FFKM",
            "starke Saeuren, starke Oxidationsmittel, halogenierte Medien und Chlorchemie koennen kritisch sein",
            "Heisswasser, Dampf und Hydrolyse-/Alterungsthemen muessen gradebezogen geprueft werden",
            "Kriechen, Kerbwirkung, Spaltpressung, Temperatur und Reibwaerme begrenzen die Konstruktion",
        ),
        media_orientation=(
            "Mineraloele, Schmierfette, viele Kraftstoffe und technische Fluide oft pruefenswert",
            "Wasser/Heisswasser, Dampf, starke Saeuren, Oxidationsmittel, Halogene und Reinigungschemie vorsichtig behandeln",
            "konkrete Type, Copolymer/Homopolymer, Additive, Kontaktzeit und Temperatur entscheiden",
        ),
        dynamics_orientation=(
            "als Fuehrungs-, Stuetz-, Gleitelement oder Back-up-Ring relevant, nicht als elastischer Dichtkoerper",
            "Reibpaarung, Schmierzustand, Oberflaeche, PV-Belastung, Waermeabfuhr und Partikelbelastung pruefen",
        ),
        typical_uses=(
            "Stuetzringe, Fuehrungsringe, Buchsen, Gleitteile, Ventilkomponenten, Sonderbauteile",
            "Praezisionsteile in oel- oder fettnahem Maschinenbau",
        ),
        critical_checks=(
            "POM-H oder POM-C, Additive, Herstellerdatenblatt",
            "Temperaturprofil, Dauerlast, Kriechen und Spaltpressung",
            "Medium, Konzentration, Kontaktzeit und Reinigungsmedien",
            "Reibpaarung, Schmierung, PV-Wert, Verschleiss und Waermeabfuhr",
            "Toleranzen, Feuchte, Montage, Kerbwirkung und mechanische Sicherheitsbeiwerte",
        ),
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
        media_orientation=("breite technische Chemieorientierung, konkrete Medien pruefen",),
        dynamics_orientation=("als Fuehrungs-/Stuetzwerkstoff relevant, Reibpaarung und Verschleiss pruefen",),
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

_PAIR_FOLLOWUP_RE = re.compile(
    r"\b(?:und|mit|vs\.?|versus|gegenueber|gegenüber)\b",
    re.IGNORECASE | re.UNICODE,
)

_CONCRETE_CASE_RE = re.compile(
    r"\b(?:meine[rmn]?\s+anwendung|bei\s+meiner\s+anlage|in\s+unserer\s+anwendung|"
    r"ich\s+habe|wir\s+haben|bei\s+uns|unsere[rmn]?|ich\s+brauche|wir\s+brauchen|"
    r"brauche\s+eine\s+dichtung|ben[oö]tige|suche|auslegen|auslegung|"
    r"f[aä]llt\s+aus|leckt|leckage|undicht|ausgefallen|verschlei[ßs])\b"
    r"|\b\d+(?:[.,]\d+)?\s*(?:mm|bar|psi|°?\s*[cCfF]|grad|rpm|u\.?/?min)\b"
    r"|\bmedium\s+(?:ist|=)\b",
    re.IGNORECASE | re.UNICODE,
)

_MATERIAL_INFORMATION_REQUEST_RE = re.compile(
    r"\b(?:info(?:s|rmation(?:en)?)?|details?|detailliert|erkl[aä]r(?:e|en)?|"
    r"kennwerte|materialdaten|datenblattwerte|eigenschaften|wissen|"
    r"vergleiche?|vergleich|unterschied(?:e)?|besser|schlechter)\b"
    r"|\b(?:über|ueber|zu)\s+"
    r"(?:ptfe|fkm|ffkm|fpm|epdm|nbr|hnbr|pu|tpu|pom|peek|pa6?|pa12|vmq|silikon|silicone|viton)\b",
    re.IGNORECASE | re.UNICODE,
)

_CONCRETE_APPLICATION_FACT_RE = re.compile(
    r"\b(?:ich\s+habe|wir\s+haben|bei\s+uns|bei\s+meiner\s+anlage|in\s+unserer\s+anwendung)\b"
    r"|\b(?:brauche|ben[oö]tige|suche)\s+(?:eine\s+)?(?:dichtung|dichtring|seal|rwdr|o[- ]?ring)\b"
    r"|\b(?:medium|fluid)\s*(?:ist|=)\b"
    r"|\b\d+(?:[.,]\d+)?\s*(?:mm|bar|barg|bara|psi|°?\s*[cCfF]|grad|rpm|u\.?/?min)\b"
    r"|\b(?:rotierende?\s+welle|welle|pumpe|getriebe|r[üu]hrwerk|kolben|flansch)\b.*"
    r"\b(?:dichtung|dichtstelle|seal|medium|[oö]l|bar|grad|rpm|mm)\b",
    re.IGNORECASE | re.UNICODE,
)


def _is_concrete_case_request(text: str) -> bool:
    if not _CONCRETE_CASE_RE.search(text):
        return False
    if (
        _MATERIAL_TOKEN_RE.search(text)
        and _MATERIAL_INFORMATION_REQUEST_RE.search(text)
        and not _CONCRETE_APPLICATION_FACT_RE.search(text)
    ):
        return False
    return True


def is_material_comparison_question(user_input: str) -> bool:
    """Return True for generic material-pair knowledge turns.

    This intentionally covers elliptical follow-ups such as ``und FKM mit NBR?``.
    The guard keeps concrete application/replacement cases in governed intake,
    where operating data and case truth belong.
    """
    text = str(user_input or "").strip()
    if not text:
        return False
    materials = _extract_materials(text)
    if len(materials) < 2:
        return False
    if _is_concrete_case_request(text):
        return False
    if _COMPARISON_RE.search(text):
        return True
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) > 90:
        return False
    return bool(_PAIR_FOLLOWUP_RE.search(compact))


def build_material_comparison_answer(user_input: str) -> MaterialComparisonAnswer | None:
    text = str(user_input or "")
    materials = _extract_materials(text)
    if len(materials) < 2:
        return None
    if not is_material_comparison_question(text):
        return None
    left = _MATERIAL_PROFILES[materials[0]]
    right = _MATERIAL_PROFILES[materials[1]]
    answer = _render_comparison(left, right)
    return MaterialComparisonAnswer(
        answer=answer,
        title=f"Werkstoffvergleich {left.canonical} vs {right.canonical}",
        material_ids=(left.canonical, right.canonical),
    )


def build_material_risk_comparison_answer(user_input: str) -> MaterialComparisonAnswer | None:
    text = str(user_input or "")
    lowered = text.casefold()
    materials = _extract_all_materials(text)
    if len(materials) < 2:
        return None
    if not any(marker in lowered for marker in ("risiko", "risiken", "kritisch", "grenze", "grenzen")):
        return None
    if not any(marker in lowered for marker in ("heißwasser", "heisswasser", "dampf", "wasser")):
        return None
    lines = [
        "## Werkstoffrisiken bei Heißwasser",
        "",
        "Kurz gesagt: Für Heißwasser bei 120 °C ist nicht der Werkstoffname allein entscheidend. Compound, Dichtungstyp, Vorspannung, Kontaktzeit, Druck, Wasserchemie und Herstellerdaten bestimmen, ob daraus ein prüfbarer Kandidat wird. Das ist eine technische Orientierung, keine Freigabe.",
        "",
        "| Werkstoff | Typische Richtung | Kritische Punkte |",
        "| --- | --- | --- |",
    ]
    for material_id in materials:
        if material_id == "PTFE":
            lines.append(
                "| PTFE | Chemisch sehr breit und temperaturfest, aber kein elastischer Gummiwerkstoff. | Kriechen, Kaltfluss, fehlende elastische Rückstellung, Vorspannkonzept, Einbauspalt, Füllstoff, Gegenlaufpartner und Dichtungsgeometrie prüfen. |"
            )
        elif material_id == "FKM":
            lines.append(
                "| FKM | Häufig stark bei Ölen, Kraftstoffen und vielen Kohlenwasserstoffen. | Heißwasser und Dampf sind je nach FKM-Typ oft kritisch; Alterung, Quellung, Hydrolyse-/Medieneffekte und Elastizitätsverlust müssen compoundbezogen geprüft werden. |"
            )
        elif material_id == "EPDM":
            lines.append(
                "| EPDM | Bei Wasser, Heißwasser, Dampf und Glykolen häufig eine naheliegende Prüfrichtung. | 120 °C liegt nahe an relevanten Dauergrenzen vieler Compounds; Wasserchemie, Additive, Druck, Setzverhalten und Langzeitkontakt prüfen. Nicht für Mineralöl ableiten. |"
            )
        else:
            profile = _MATERIAL_PROFILES[material_id]
            lines.append(
                f"| {material_id} | {_join(profile.media_orientation)} | {_join(profile.critical_checks)} |"
            )
    lines.extend(
        [
            "",
            "### Was ich früh klären würde",
            "",
            "- Ist es reines Wasser, Heißwasser mit Additiven, Dampf, Kondensat oder Reinigungsmedium?",
            "- Dauerbetrieb und Spitzen: 120 °C konstant, zyklisch oder nur kurzzeitig?",
            "- Dichtungstyp: O-Ring, Flachdichtung, RWDR, Membran, Formteil oder energisierte PTFE-Dichtung?",
            "- Druck direkt an der Dichtstelle, Bewegung, Einbauspalt, Vorspannung und Gegenfläche.",
            "- Geforderte Nachweise und Herstellerfreigaben, zum Beispiel Trinkwasser, Food, FDA oder USP.",
            "",
            "Als Vororientierung: EPDM ist für Heißwasser oft plausibler als FKM, PTFE kann konstruktiv interessant sein, braucht aber ein passendes Dichtprinzip. Eine konkrete Auswahl bleibt Hersteller- oder Spezialistenprüfung.",
        ]
    )
    answer = humanize_german_technical_text("\n".join(lines))
    return MaterialComparisonAnswer(
        answer=answer,
        title="Werkstoffrisiken bei Heißwasser",
        material_ids=tuple(materials[:2]),
    )



def supported_material_ids() -> tuple[str, ...]:
    return tuple(_MATERIAL_PROFILES.keys())


def extract_material_ids(text: str) -> tuple[str, ...]:
    """Return canonical material IDs mentioned in text, preserving first mention order."""

    return tuple(_extract_all_materials(text))


def build_material_definition_answer(user_input: str) -> MaterialDefinitionAnswer | None:
    """Return a guarded one-material orientation answer for generic material questions."""

    text = str(user_input or "").strip()
    if not text:
        return None
    if is_material_comparison_question(text):
        return None
    if _is_concrete_case_request(text):
        return None
    materials = _extract_all_materials(text)
    if len(materials) != 1:
        return None
    if not _looks_like_generic_material_information_request(text, materials[0]):
        return None

    profile = _MATERIAL_PROFILES[materials[0]]
    answer = _render_definition(profile)
    return MaterialDefinitionAnswer(
        answer=answer,
        title=f"{profile.canonical} - Werkstofforientierung",
        material_id=profile.canonical,
    )

def _extract_materials(text: str) -> list[str]:
    return _extract_all_materials(text)[:2]


def _extract_all_materials(text: str) -> list[str]:
    seen: list[str] = []
    for match in _MATERIAL_TOKEN_RE.finditer(text.casefold()):
        canonical = _ALIAS_TO_CANONICAL.get(match.group(1).casefold())
        if canonical and canonical not in seen:
            seen.append(canonical)
    return seen


_GENERIC_MATERIAL_INFO_RE = re.compile(
    r"\b(?:was\s+ist|was\s+sind|was\s+bedeutet|bedeutet|"
    r"was\s+kannst\s+du|erz[aä]hl(?:e)?|"
    r"info(?:s|rmation(?:en)?)?|details?|detailliert|erkl[aä]r(?:e|en)?|"
    r"kurz\s+zu|mehr\s+zu|wissen\s+zu|über|ueber)\b"
    r"|^\s*(?:bitte\s+)?(?:jetzt|nun|weiter|als\s+n[aä]chstes)\s+(?:zu|ueber|über)\b"
    r"|^\s*(?:und|auch)\s+(?:noch\s+)?(?:zu\s+|ueber\s+|über\s+)?\w+",
    re.IGNORECASE | re.UNICODE,
)


def _looks_like_generic_material_information_request(text: str, material_id: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if compact.casefold() == material_id.casefold():
        return True
    return bool(_GENERIC_MATERIAL_INFO_RE.search(compact))


_MATERIAL_DEFINITION_LEADS: dict[str, str] = {
    "NBR": (
        "NBR steht für Acrylnitril-Butadien-Kautschuk, häufig auch "
        "Nitrilkautschuk genannt. In der Dichtungstechnik ist NBR ein "
        "elastischer Standardwerkstoff für viele öl- und fettnahe "
        "Dichtstellen, wenn Temperatur, Medium und Compound dazu passen."
    ),
    "HNBR": (
        "HNBR ist hydrierter Nitrilkautschuk. Er wird oft betrachtet, wenn "
        "NBR mechanisch oder thermisch an Grenzen kommt, die Anwendung aber "
        "weiter in öl- oder kraftstoffnahen Bereichen liegt."
    ),
    "FKM": (
        "FKM ist eine Fluorelastomer-Werkstofffamilie. In Dichtungen wird "
        "FKM häufig für öl-, kraftstoff-, alterungs- und temperaturbelastete "
        "Anwendungen geprüft; die konkrete Rezeptur bleibt entscheidend."
    ),
    "FFKM": (
        "FFKM steht für Perfluorelastomer beziehungsweise Perfluorkautschuk. "
        "In der Dichtungstechnik ist FFKM eine sehr hochwertige "
        "Elastomer-Richtung für chemisch und thermisch anspruchsvolle Fälle, "
        "aber stark compound-, hersteller- und kostenabhängig."
    ),
    "EPDM": (
        "EPDM ist Ethylen-Propylen-Dien-Kautschuk. In Dichtungen wird EPDM "
        "häufig für wasser-, dampf-, glykol- und witterungsnahe Anwendungen "
        "geprüft, während Öl- und Kraftstoffkontakt besonders kritisch ist."
    ),
    "PTFE": (
        "PTFE ist Polytetrafluorethylen, ein Fluorpolymer und kein "
        "elastischer Gummiwerkstoff. Es wird oft wegen breiter "
        "Chemieorientierung und niedriger Reibung betrachtet, braucht aber "
        "ein passendes Dichtprinzip."
    ),
    "PU": (
        "PU beziehungsweise Polyurethan ist eine Werkstofffamilie, die in "
        "Dichtungen häufig für mechanisch robuste Hydraulik- und "
        "Abstreiferanwendungen geprüft wird. Temperatur, Hydrolyse und "
        "Medientyp grenzen die Auswahl stark ein."
    ),
    "VMQ": (
        "VMQ ist Silikonkautschuk. In Dichtungen wird VMQ häufig für "
        "Tieftemperatur-, Wärmealterungs- oder Hygieneanwendungen betrachtet, "
        "mechanisch aber vorsichtiger bewertet als viele technische Elastomere."
    ),
    "POM": (
        "POM ist Polyoxymethylen, auch Polyacetal genannt. In der "
        "Dichtungstechnik ist POM eher ein präziser Konstruktions-, "
        "Stütz-, Führungs- oder Gleitwerkstoff als ein elastisches "
        "Dichtmaterial."
    ),
    "PEEK": (
        "PEEK ist ein Hochleistungsthermoplast. In der Dichtungstechnik ist "
        "PEEK eher Stütz-, Führungs- oder Sonderbauteilwerkstoff als ein "
        "elastisches Dichtmaterial."
    ),
}


def _render_definition(profile: MaterialComparisonProfile) -> str:
    if profile.canonical == "PTFE":
        return _render_ptfe_definition(profile)
    if profile.canonical == "NBR":
        return _render_nbr_definition(profile)
    if profile.canonical == "FFKM":
        return _render_ffkm_definition(profile)

    lead = _MATERIAL_DEFINITION_LEADS.get(
        profile.canonical,
        (
            f"{profile.canonical} ist {article(profile.material_type)} "
            f"{profile.material_type.lower()} aus der Familie {profile.family}. "
            "In Dichtungsanwendungen wird diese Werkstoffrichtung immer im "
            "Zusammenspiel mit Medium, Temperatur, Bewegung, Geometrie und "
            "Herstellerdaten bewertet."
        ),
    )
    lines = [
        f"## {profile.canonical} in der Dichtungstechnik",
        "",
        lead,
        "",
        "### Technische Richtwerte für die Vorprüfung",
        "",
        "| Prüfpunkt | Orientierung |",
        "| --- | --- |",
        f"| Werkstofffamilie | {profile.family} |",
        f"| Werkstofftyp | {profile.material_type} |",
        f"| Temperatur | {_engineering_snapshot(profile, 'Temperatur')} |",
        f"| Härte / Rezeptur | {_engineering_snapshot(profile, 'Haerte / Rezeptur')} |",
        f"| Medienbild | {_engineering_snapshot(profile, 'Medienbild')} |",
        f"| Dynamik / Tribologie | {_engineering_snapshot(profile, 'Dynamik')} |",
        f"| Wirtschaft / Verfügbarkeit | {_engineering_snapshot(profile, 'Wirtschaft')} |",
        "",
        "### Technische Stärken",
        "",
        *(f"- {point}" for point in profile.key_strengths),
        "",
        "### Typische Grenzen",
        "",
        *(f"- {point}" for point in profile.key_limits),
        "",
        "### Rollen in Dichtungssystemen",
        "",
        *(f"- {point}" for point in profile.typical_uses),
        "",
        "### Was ich fachlich prüfen würde",
        "",
        *(f"- {point}" for point in profile.critical_checks),
        "",
        "Für eine konkrete Einschätzung brauche ich Medium inklusive Konzentration/Additiven, Temperaturprofil, Druck, Bewegung/Dichtungsart, Einbauraum, Gegenlaufpartner, Oberflächen, Toleranzen und Herstellerdaten. Das ist technische Orientierung, keine Freigabe und keine Kompatibilitätszusage.",
    ]
    return humanize_german_technical_text("\n".join(lines))


def _render_nbr_definition(profile: MaterialComparisonProfile) -> str:
    answer = "\n".join(
        [
            "## NBR in der Dichtungstechnik",
            "",
            "NBR steht für Acrylnitril-Butadien-Kautschuk, häufig auch "
            "Nitrilkautschuk genannt. In der Dichtungstechnik ist NBR kein "
            "High-End-Spezialwerkstoff, sondern ein sehr wichtiger "
            "Standard-Elastomerwerkstoff: wirtschaftlich, gut verfügbar und "
            "für viele öl- und fettnahe Dichtstellen ein plausibler "
            "Prüfkandidat, solange Medium, Temperatur, Compound und "
            "Dichtungskonstruktion zusammenpassen.",
            "",
            "### Technische Richtwerte für die Vorprüfung",
            "",
            "| Punkt | Typische Orientierung | Was daran kritisch ist |",
            "| --- | --- | --- |",
            "| Werkstofffamilie | Nitrilkautschuk, Elastomer | Rezeptur und Herstellercompound bestimmen das reale Verhalten. |",
            "| Temperatur | Standard grob -30 bis +100 °C; Sondermischungen etwa -40 °C oder kurzzeitig +120 °C möglich | Dauerwärme, Reibwärme und Mediumsalterung können die Grenze deutlich früher erreichen. |",
            "| Acrylnitril-Anteil | grob etwa 18 bis 50 % ACN | mehr ACN verbessert meist Öl-/Kraftstofforientierung, verschlechtert aber Tieftemperaturflexibilität. |",
            "| Härte | häufig 60 bis 90 Shore A; 70 Shore A ist bei O-Ringen ein verbreiteter Startpunkt | Härte beeinflusst Einbaukraft, Extrusionsrisiko, Rückstellung, Reibung und Dichtpressung. |",
            "| Druckverformungsrest | stark compound- und temperaturabhängig | wichtig für statische O-Ringe, Flachdichtungen und Langzeitdichtheit. |",
            "| Quellung im Medium | Volumenänderung wird medien- und compoundbezogen geprüft | zu hohe Quellung verändert Vorspannung, Reibung, Extrusion und Montagezustand. |",
            "",
            "### Medienbild",
            "",
            "- **Naheliegende Prüffelder:** Mineralöle, Schmierfette, viele klassische "
            "HLP-/HLVP-Hydraulikfluide, ölnahe Maschinenbauanwendungen und viele "
            "Pneumatik- oder Hydraulikdichtungen.",
            "- **Nicht pauschal ableiten:** Kraftstoffe, Bioanteile, synthetische Öle, "
            "Additivpakete, schwer entflammbare Hydraulikflüssigkeiten und "
            "Reinigungsmedien können das Verhalten deutlich verschieben.",
            "- **Typische Ausschluss- oder Warnfelder:** Ozon, UV, Witterung, viele "
            "polare Lösemittel, Aromaten, Ketone, Ester, starke Oxidationsmittel, "
            "Heißwasser und Dampf.",
            "",
            "### Mechanik und Dynamik",
            "",
            "- **O-Ringe:** Verpressung, Nutfüllung, Spalt, Druckrichtung, "
            "Druckverformungsrest, Quellung und Montagebeschädigung sind die "
            "entscheidenden Stellgrößen.",
            "- **Radialwellendichtringe:** Dichtlippengeometrie, Schmierfilm, "
            "Wellenhärte, Rauheit, Rundlauf, Exzentrizität, Umfangsgeschwindigkeit "
            "und Reibwärme bestimmen, ob NBR stabil läuft.",
            "- **Hydraulik/Pneumatik:** Druckspalt, Extrusionsgefahr, "
            "Führungssituation, Oberflächenqualität und Medienalterung müssen "
            "zusammen betrachtet werden.",
            "",
            "### Grenzen, die ich früh prüfen würde",
            "",
            "- Dauerbetrieb oberhalb des Standardfensters: Alterung, Härteanstieg, "
            "Rissbildung und bleibende Verformung nehmen zu.",
            "- Außenkontakt mit Ozon, UV oder Wetter: ohne Schutz, passende Rezeptur "
            "oder Gehäusekonzept riskant.",
            "- Dynamischer Betrieb mit schlechter Schmierung: Reibwärme kann aus einer "
            "eigentlich unkritischen Medientemperatur eine kritische Dichtkante machen.",
            "- Mediennamen wie \"Öl\" oder \"Hydraulikfluid\" reichen nicht. Additive, "
            "Basisöl, Wasseranteil, Alterung, Reiniger und Kontaktzeit gehören in die Bewertung.",
            "",
            "### Was ich für eine belastbare Einordnung brauche",
            "",
            "- exaktes Medium mit Herstellerbezeichnung, Additiven, Konzentration und Kontaktzeit",
            "- Temperaturprofil an der Dichtstelle: Minimum, Dauerbetrieb, Peaks und Stillstand",
            "- Dichtungstyp: O-Ring, RWDR, Stangen-/Kolbendichtung, Flachdichtung oder Formteil",
            "- Druck, Druckrichtung, Spalt, Bewegung, Geschwindigkeit oder Drehzahl",
            "- Gegenlauffläche, Rauheit, Härte, Schmierung, Montage und gewünschte Standzeit",
            "- erforderliche Nachweise, zum Beispiel Food, Trinkwasser, ATEX, FDA oder kundenspezifische Freigaben",
            "",
            "Kurz: NBR ist oft eine sehr sinnvolle, wirtschaftliche Prüfrichtung für "
            "öl- und fettnahe Standarddichtungen. Es ist aber kein universeller "
            "Werkstoff. Die belastbare Bewertung entsteht erst aus Medium, "
            "Temperatur, Bewegung, Geometrie, Compounddaten und Herstellerprüfung. "
            "Das ist technische Orientierung, keine Freigabe und keine "
            "Kompatibilitätszusage.",
        ]
    )
    return humanize_german_technical_text(answer)


def _render_ffkm_definition(profile: MaterialComparisonProfile) -> str:
    answer = "\n".join(
        [
            "## FFKM in der Dichtungstechnik",
            "",
            "FFKM steht für Perfluorelastomer beziehungsweise Perfluorkautschuk. "
            "Es ist ein elastomerer Hochleistungswerkstoff für chemisch und "
            "thermisch anspruchsvolle Dichtstellen. FFKM wird nicht gewählt, "
            "weil es ein günstiger Standard ist, sondern wenn klassische "
            "Elastomere chemisch, thermisch oder regulatorisch an Grenzen kommen.",
            "",
            "### Technische Richtwerte für die Vorprüfung",
            "",
            "| Punkt | Typische Orientierung | Was daran kritisch ist |",
            "| --- | --- | --- |",
            "| Werkstofffamilie | Perfluorelastomer, Elastomer | konkrete Grade unterscheiden sich stark. |",
            "| Temperatur | häufig etwa -15/-20 bis +230/+260 °C; Hochtemperatur-Compounds je nach Hersteller grob bis +300/+320 °C | Tieftemperatur, Dauergrenze, Dampf und Medienkontakt sind gradeabhängig. |",
            "| Härte | häufig etwa 70 bis 90 Shore A | beeinflusst Verpressung, Montagekraft, Extrusion und Rückstellung. |",
            "| Chemie | sehr breite Orientierung gegenüber vielen Chemikalien, Lösemitteln, Säuren, Laugen und Oxidationsmedien | keine pauschale Freigabe ohne Medium, Konzentration, Temperatur und Kontaktzeit. |",
            "| Kosten/Verfügbarkeit | oft um Größenordnungen teurer als Standardelastomere | Lieferzeit, Mindestmengen und Ersatzteilstrategie früh klären. |",
            "",
            "### Wann FFKM ins Spiel kommt",
            "",
            "- aggressive Prozesschemie, bei der NBR, EPDM, FKM oder PU nicht mehr belastbar einzuordnen sind",
            "- hohe Temperatur mit gleichzeitiger chemischer Exposition",
            "- Pharma-, Food-, Halbleiter- oder Chemieanlagen mit strengen Nachweispflichten",
            "- O-Ringe, Formteile oder Sonderdichtungen, bei denen elastische Dichtfunktion erhalten bleiben soll",
            "",
            "### Grenzen trotz Premiumwerkstoff",
            "",
            "- FFKM ist nicht automatisch tribologisch besser: Reibung, Abrieb, Wärme und dynamischer Betrieb müssen separat geprüft werden.",
            "- Compression Set, Langzeitelastizität, Extrusion und Montage können auch bei FFKM limitieren.",
            "- Dampf, Heißwasser, Amine, Plasma, Spezialreiniger und Hochtemperaturoxidation sind gradebezogene Prüffelder.",
            "- Der wirtschaftliche Hebel muss stimmen; häufig ist FFKM nur sinnvoll, wenn Ausfallkosten, Stillstand oder Chemierisiko den Preis rechtfertigen.",
            "",
            "Für eine belastbare Einschätzung brauche ich Medium, Konzentration, Temperaturprofil, Druck, Dichtungstyp, Bewegung, Einbauraum, Reinigungszyklen und gewünschte Nachweise. Das ist technische Orientierung, keine Freigabe und keine Kompatibilitätszusage.",
        ]
    )
    return humanize_german_technical_text(answer)


def _render_ptfe_definition(profile: MaterialComparisonProfile) -> str:
    answer = "\n".join(
        [
            "## PTFE in der Dichtungstechnik",
            "",
            "PTFE, Polytetrafluorethylen, ist ein Fluorpolymer und kein elastischer "
            "Gummiwerkstoff. Viele kennen PTFE unter dem Markennamen Teflon; in der "
            "Dichtungstechnik ist es aber vor allem ein Konstruktionswerkstoff für "
            "chemisch, thermisch oder reibungstechnisch anspruchsvolle Aufgaben.",
            "",
            "### Kennwerte für ungefülltes / Virgin PTFE",
            "",
            "Die folgenden Werte sind typische Orientierungswerte für ungefülltes "
            "PTFE bei Raumtemperatur beziehungsweise nach den genannten Prüfbedingungen. "
            "Sie sind keine Spezifikationsgrenzen; Halbzeug, Sinterprozess, Füllstoffe, "
            "Porosität, Orientierung, Geometrie und Hersteller-Grade können die Werte "
            "deutlich verschieben.",
            "",
            "| Eigenschaft | Typischer Wert / Bereich | Technische Bedeutung für Dichtungen |",
            "| --- | --- | --- |",
            "| Chemische Struktur | Wiederholeinheit -(CF2-CF2)n- | sehr starke C-F-Bindungen erklären die hohe chemische Inertheit. |",
            "| Dichte / spezifisches Gewicht | ca. 2,14-2,20 g/cm3 | relativ schwerer Thermoplast; beeinflusst Bauteilgewicht und Füllstoffvergleich. |",
            "| Kristalliner Schmelzpunkt | ca. 327 °C; bei PTFE-Resinen zweite Schmelzspitze häufig 327 +/- 10 °C | oberhalb davon bleibt die Schmelzviskosität sehr hoch; PTFE wird gesintert, nicht klassisch spritzgegossen. |",
            "| Dauereinsatztemperatur | häufig -190/-200 bis +260 °C | bei Dichtungen begrenzen Last, Medium, Reibwärme, Kriechen und Füllstoff das nutzbare Fenster. |",
            "| Wärmeleitfähigkeit | ca. 0,20-0,25 W/(m*K) | geringe Wärmeleitung; Reibwärme an PTFE-Lippen muss konstruktiv abgeführt werden. |",
            "| Linearer Wärmeausdehnungskoeffizient | ca. 12-13 * 10^-5 1/K, 23-100 °C | deutlich höher als Stahl; Spalt, Vorspannung und Toleranzen müssen Temperaturhub abbilden. |",
            "| Zugfestigkeit | typisch ca. 22-25 MPa, je nach Halbzeug auch breiter | mechanisch deutlich schwächer als viele Konstruktionskunststoffe; Lastpfad prüfen. |",
            "| Bruchdehnung | typisch ca. 220 bis >260 % | duktil, aber nicht elastisch rückstellend wie ein Gummiwerkstoff. |",
            "| Zug-/Biegemodul | typisch ca. 550-620 MPa | relativ geringe Steifigkeit; Stützgeometrie, Extrusionsspalt und Dauerlast sind wichtig. |",
            "| Druckfestigkeit bei 1 % Stauchung | ca. 4-5 MPa; je nach Datensatz auch höhere Prüfwerte möglich | kleine bleibende Verformungen können Dichtkraft und Spaltkontrolle verändern. |",
            "| Härte | ca. 55-72 Shore D | keine Shore-A-Elastomerhärte; Nut- und Lippenkonzepte sind anders zu bewerten. |",
            "| Reibwert gegen Stahl | kinetisch orientierend ca. 0,06; je nach Gegenlauf, Last, Geschwindigkeit und Schmierung variabel | niedrige Reibung ist ein Hauptgrund für PTFE in dynamischen Dichtungen. |",
            "| Wasseraufnahme | ca. 0,01 % beziehungsweise <0,01 % | sehr geringe Feuchteaufnahme; Maßänderung durch Wasser ist meist kein Haupttreiber. |",
            "| Dielektrizitätszahl | ca. 2,1 bei 10^3 bis 10^6 Hz | sehr guter elektrischer Isolator, auch bei Feuchte vorteilhaft. |",
            "| Verlustfaktor | ca. 0,0002 bei 10^3 bis 10^6 Hz | sehr geringe dielektrische Verluste. |",
            "| Durchschlagsfestigkeit | ca. 48-80 kV/mm, stark probendicken- und prüfabhängig | relevant für elektrische Isolations- und Sensorumgebungen. |",
            "| Volumenwiderstand | ca. >10^17 bis >10^18 Ohm*cm | sehr hohe elektrische Isolation. |",
            "| Brennverhalten | häufig UL94 V-0 bei passenden Halbzeugen | vorteilhaft, ersetzt aber keine projektspezifische Brandschutzfreigabe. |",
            "",
            "### Chemische Beständigkeit mit harten Grenzen",
            "",
            "- **Sehr breit beständig:** viele Säuren, Laugen, Alkohole, Ketone, Ester, "
            "Kohlenwasserstoffe, Kraftstoffe, Öle, Fette, Wasser, Dampf- und "
            "Reinigungsumfelder werden häufig als PTFE-Prüffeld betrachtet.",
            "- **Typische Ausnahmen:** geschmolzene oder gelöste Alkalimetalle, "
            "elementares Fluor und sehr aggressive Fluorierungsmedien wie "
            "Chlortrifluorid, besonders bei hoher Temperatur und Druck.",
            "- **Hochtemperaturhinweis:** PTFE ist bis etwa +260 °C als "
            "Dauereinsatzwerkstoff bekannt; oberhalb davon steigen Kriechen, "
            "Verformung und Zersetzungs-/Emissionsrisiken je nach Last und "
            "Umgebung. Eine Dichtungsauslegung sollte deshalb nicht nur auf den "
            "Schmelzpunkt schauen.",
            "",
            "### Was PTFE besonders macht",
            "",
            "- **Chemische Orientierung:** PTFE wird häufig dort betrachtet, wo Säuren, "
            "Laugen, Lösungsmittel, Kraftstoffe, Öle, Reinigungsmedien oder aggressive "
            "Prozesschemie Elastomere stark einschränken können. Die konkrete Medienlage "
            "bleibt trotzdem fall- und compoundbezogen zu prüfen.",
            "- **Temperaturfenster:** Ungefülltes PTFE wird häufig in Richtung "
            "-190/-200 bis +260 °C betrachtet; der konkrete nutzbare Bereich hängt "
            "von Sorte, Füllstoff, Dichtprinzip, Last, Reibwärme und Herstellerdaten ab.",
            "- **Reibung und Gleiten:** PTFE hat sehr niedrige Reibwerte. Das ist bei "
            "dynamischen Dichtungen, Führungen, Lippengeometrien, Ventilsitzen oder "
            "Trockenlaufanteilen oft der Grund, warum PTFE überhaupt ins Spiel kommt.",
            "",
            "### Die kritischen Punkte",
            "",
            "- **Kaltfluss und Kriechen:** Unter Dauerlast kann PTFE nachgeben. Dadurch "
            "können Vorspannung, Spaltkontrolle und Dichtkraft über die Zeit kritisch werden.",
            "- **Geringe elastische Rückstellung:** PTFE verhält sich nicht wie NBR, EPDM "
            "oder FKM. Bei Toleranzen, Exzentrizität, Druckwechseln oder Montagefehlern "
            "braucht es meist ein sauberes Vorspann- und Geometriekonzept.",
            "- **Wärmeausdehnung und Wärmeabfuhr:** Temperaturwechsel, Reibwärme und "
            "enge Einbauräume können die Funktion stark beeinflussen.",
            "- **Gegenlauffläche:** Rauheit, Härte, Beschichtung, Schmierung, Schmutz und "
            "Wellenlauf entscheiden bei dynamischen PTFE-Systemen häufig stärker als das "
            "Materialetikett allein.",
            "",
            "### Gefüllte PTFE-Typen",
            "",
            "| Füllstoff / Modifikation | Typischer Zweck | Kritischer Blickpunkt |",
            "| --- | --- | --- |",
            "| Glasfaser | Verschleiß- und Formstabilität verbessern | kann Gegenflächen stärker beanspruchen |",
            "| Kohle / Carbon | Wärmeleitung und Verschleißverhalten verbessern | Compound- und Medienfreigaben prüfen |",
            "| Graphit | Trockenlauf- und Reibverhalten verbessern | Druck, Temperatur und Abrieb prüfen |",
            "| Bronze | Druckfestigkeit und Maßstabilität verbessern | Medien- und Korrosionsthema prüfen |",
            "| PEEK / Hochleistungsfüller | mechanische Stabilität erhöhen | Herstellerdaten und PV-Grenzen prüfen |",
            "",
            "### Typische Dichtungsrollen",
            "",
            "- PTFE-Radialwellendichtringe und PTFE-Lippendichtungen",
            "- federunterstützte oder elastomerunterstützte PTFE-Dichtungen",
            "- Kolben- und Stangendichtungen mit niedriger Reibung",
            "- Ventilsitze, Flachdichtungen, Führungs- und Gleitelemente",
            "- Chemie-, Pharma-, Food- oder Hochtemperaturumgebungen, wenn die nötigen "
            "Nachweise für den konkreten Werkstoff vorliegen",
            "",
            "### Typische Denkfehler",
            "",
            "- **Chemische Breite ersetzt keine Auslegung.** Ein PTFE-System kann chemisch "
            "naheliegend wirken und mechanisch trotzdem früh ausfallen.",
            "- **PTFE ist kein Elastomer.** Rückstellung, Vorspannung und Einbauspalt müssen "
            "konstruktiv gelöst werden.",
            "- **PTFE allein ist keine Produktspezifikation.** Ungefüllt, glasgefüllt, "
            "carbongefüllt oder federenergisiert sind technisch unterschiedliche Fälle.",
            "- **Nachweise sind compound- und herstellerbezogen.** Food, Pharma, FDA, EU "
            "1935/2004, USP, ATEX oder PFAS/REACH-Themen dürfen nicht aus dem Wort PTFE "
            "abgeleitet werden.",
            "",
            "### Was ich vor einer konkreten Einschätzung wissen müsste",
            "",
            "- Medium inklusive Konzentration, Additive, Reinigungsmedien und Kontaktzeit",
            "- Temperaturprofil mit Normalbetrieb, Spitzen, CIP/SIP oder Stillstand",
            "- Druck direkt an der Dichtstelle und Druckrichtung",
            "- Bewegung: statisch, rotierend, linear oder oszillierend; bei Dynamik auch "
            "Geschwindigkeit, Drehzahl und Schmierzustand",
            "- Geometrie, Spalt, Gegenlauffläche, Rauheit, Härte, Exzentrizität und Montage",
            "- geforderte Nachweise und gewünschte Standzeit",
            "",
            "Kurz: PTFE ist oft eine starke Prüfrichtung, wenn Chemie, Temperatur oder "
            "Reibung anspruchsvoll werden. Der Mehrwert entsteht aber erst in der "
            "Systembetrachtung aus Medium, Konstruktion, Gegenlaufpartner, Last und "
            "Herstellerdaten. Das ist technische Orientierung, keine Freigabe und keine "
            "Kompatibilitätszusage.",
        ]
    )
    return humanize_german_technical_text(answer)


def _first_non_empty(*groups: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for group in groups:
        for value in group:
            clean = str(value or "").strip()
            if clean:
                values.append(clean)
    return tuple(values)


_ENGINEERING_SNAPSHOTS: dict[str, dict[str, str]] = {
    "NBR": {
        "Temperatur": "grob -30 bis +100 C; Sondermischungen etwa -40 C oder kurzzeitig +120 C moeglich",
        "Haerte / Rezeptur": "oft 60 bis 90 Shore A; ACN-Anteil grob 18 bis 50 % praegt Oel- und Tieftemperaturverhalten",
        "Medienbild": "Mineraloel, Schmierfett und viele HLP-/HLVP-Fluide oft naheliegend; Ozon, UV, Dampf, Heisswasser, Ketone, Ester, Aromaten und starke Oxidationsmittel kritisch",
        "Dynamik": "gut pruefbar fuer O-Ringe, RWDR und Hydraulik; Reibwaerme, Schmierung, Wellenrauheit, Rundlauf und Druckspalt begrenzen",
        "Wirtschaft": "Standardwerkstoff mit meist guter Verfuegbarkeit und niedrigen Kosten",
    },
    "HNBR": {
        "Temperatur": "haeufig bis etwa +150 C orientierend; Tieftemperatur und Medium compoundabhaengig",
        "Haerte / Rezeptur": "oft 60 bis 90 Shore A; Hydrierungsgrad und Rezeptur praegen Waerme- und Alterungsverhalten",
        "Medienbild": "oel- und kraftstoffnahe Medien oft pruefenswert; Dampf, starke Saeuren/Basen und polare Loesemittel genau pruefen",
        "Dynamik": "mechanisch robuster als Standard-NBR moeglich; PV, Abrieb, Schmierung und Spalt bleiben massgebend",
        "Wirtschaft": "teurer als NBR, meist deutlich guenstiger als FFKM",
    },
    "FKM": {
        "Temperatur": "typisch grob -20 bis +200 C; Tieftemperatur und Heisswasser/Dampf stark compoundabhaengig",
        "Haerte / Rezeptur": "oft 60 bis 90 Shore A; Fluorgehalt, Bisphenol-/Peroxidvernetzung und Spezialtypen praegen Verhalten",
        "Medienbild": "Oele, Kraftstoffe und Kohlenwasserstoffe oft stark; Amine, Ketone, Dampf, Heisswasser und Laugen kritisch pruefen",
        "Dynamik": "fuer O-Ringe und RWDR oft nutzbar, aber Dichtkantentemperatur und Schmierung sind entscheidend",
        "Wirtschaft": "teurer als NBR/EPDM, meist deutlich guenstiger als FFKM",
    },
    "FFKM": {
        "Temperatur": "haeufig etwa -15/-20 bis +230/+260 C; Hochtemperatur-Compounds je nach Hersteller grob bis +300/+320 C",
        "Haerte / Rezeptur": "oft 70 bis 90 Shore A; Grade unterscheiden sich stark bei Compression Set, Dampf, Plasma und Tieftemperatur",
        "Medienbild": "sehr breite Chemieorientierung; trotzdem Medium, Konzentration, Kontaktzeit, Dampf, Amine, Plasma und Reiniger konkret freigeben lassen",
        "Dynamik": "elastisch dichtend, aber Reibung, Abrieb, Waerme und Kosten machen dynamische Anwendungen besonders pruefpflichtig",
        "Wirtschaft": "Premiumwerkstoff; Kosten und Lieferzeit oft entscheidende Designgroessen",
    },
    "EPDM": {
        "Temperatur": "typisch grob -40 bis +130 C; Heisswasser/Dampf je nach Compound hoeher moeglich",
        "Haerte / Rezeptur": "oft 50 bis 90 Shore A; Zulassungen und Vernetzung praegen Wasser-/Dampfverhalten",
        "Medienbild": "Wasser, Dampf, Glykol und Witterung oft naheliegend; Mineraloel, Fett und Kraftstoff meist kritisch",
        "Dynamik": "elastisch gut, bei Dynamik aber Schmierung, Reibung, Medienquellung und Waerme pruefen",
        "Wirtschaft": "Standard bis Spezial, meist wirtschaftlich gut verfuegbar",
    },
    "PTFE": {
        "Temperatur": "haeufig -190/-200 bis +260 C Dauereinsatz; Schmelzpunkt ca. 327 C; Reibwaerme, Last, Kriechen und Fuellstoff begrenzen",
        "Haerte / Rezeptur": "kein Elastomer; ungefuellt ca. 55-72 Shore D, Dichte ca. 2.14-2.20 g/cm3, gefuellt mit Glas, Carbon, Graphit, Bronze, PEEK usw.",
        "Medienbild": "chemisch sehr breit orientiert; Alkalimetalle, elementares Fluor, Chlortrifluorid, Fuellstoffe und Zersetzungsthemen konkret pruefen",
        "Dynamik": "niedrige Reibung, kinetisch orientierend ca. 0.06 gegen Stahl; Kaltfluss, Kriechen, Vorspannung, Gegenlaufflaeche und Waermeabfuhr sind zentral",
        "Wirtschaft": "meist konstruktions- und fertigungsintensiver als Standardelastomerloesungen",
    },
    "PU": {
        "Temperatur": "haeufig grob -30 bis +100 C; Typ, Hydrolyse und Medium begrenzen",
        "Haerte / Rezeptur": "oft 80 bis 95 Shore A bei Hydraulikdichtungen; Polyester/Polyether unterscheiden sich deutlich",
        "Medienbild": "Hydraulikoel oft relevant; Wasser, Heisswasser, Dampf und aggressive Chemie kritisch",
        "Dynamik": "sehr stark bei Abrieb und Extrusion, aber Reibwaerme und Hydrolyse pruefen",
        "Wirtschaft": "wirtschaftlich bei Hydraulikserien, Spezialtypen teurer",
    },
    "VMQ": {
        "Temperatur": "haeufig grob -50 bis +200 C; mechanische Last und Medium begrenzen",
        "Haerte / Rezeptur": "oft 30 bis 80 Shore A; sehr flexibel, aber mechanisch begrenzter",
        "Medienbild": "Food/Pharma/Waerme/Tieftemperatur oft relevant; Oel, Kraftstoff und Abrieb kritisch",
        "Dynamik": "vorsichtig bei abrasiver oder hoher dynamischer Belastung",
        "Wirtschaft": "wirtschaftlich bis Spezial, stark zulassungs- und farb-/rezepturabhaengig",
    },
    "POM": {
        "Temperatur": "orientierend etwa -40 bis +100/+110 C im Dauerbetrieb; kurzzeitige Spitzen je nach Type grob bis +120/+140 C pruefen",
        "Haerte / Rezeptur": "kein Elastomer; POM-H/POM-C, Fuellstoffe/Additive und Herstellerdaten bestimmen Kriechen, Verschleiss und Medienverhalten",
        "Medienbild": "Oele, Fette und viele Kraftstoffe oft pruefenswert; starke Saeuren, Oxidationsmittel, Halogene, Heisswasser, Dampf und Reiniger kritisch pruefen",
        "Dynamik": "als Stuetz-, Fuehrungs- und Gleitwerkstoff; PV-Belastung, Schmierung, Reibpaarung, Waermeabfuhr und Partikel sind entscheidend",
        "Wirtschaft": "praeziser, gut zerspanbarer Standard-Thermoplast; meist wirtschaftlicher als PEEK, aber deutlich begrenzter",
    },
    "PEEK": {
        "Temperatur": "hochtemperaturfaehiger Thermoplast; konkrete Grenze bauteil-, last- und compoundabhaengig",
        "Haerte / Rezeptur": "kein Elastomer; hohe Steifigkeit, gefuellt oder ungefuellt moeglich",
        "Medienbild": "breite technische Chemieorientierung, aber konkrete Medien und Spannungsrissrisiken pruefen",
        "Dynamik": "als Stuetz-, Fuehrungs- oder Gleitwerkstoff; Reibpaarung, Verschleiss und Waerme pruefen",
        "Wirtschaft": "hochwertiger Konstruktionswerkstoff, deutlich teurer als Standardkunststoffe",
    },
}


def _engineering_snapshot(profile: MaterialComparisonProfile, field: str) -> str:
    snapshot = _ENGINEERING_SNAPSHOTS.get(profile.canonical, {})
    if field in snapshot:
        return snapshot[field]
    if field == "Temperatur":
        return profile.typical_temperature
    if field == "Medienbild":
        return _join(profile.media_orientation)
    if field == "Dynamik":
        return _join(profile.dynamics_orientation)
    if field == "Haerte / Rezeptur":
        return "Haerte, Compound, Vernetzung und Herstellerdaten konkret pruefen"
    if field == "Wirtschaft":
        return "Kosten, Verfuegbarkeit und Nachweise projektbezogen klaeren"
    return ""


def _engineering_comparison_rows(
    left: MaterialComparisonProfile,
    right: MaterialComparisonProfile,
) -> list[str]:
    fields = ("Temperatur", "Haerte / Rezeptur", "Medienbild", "Dynamik", "Wirtschaft")
    return [
        f"| {field} | {_engineering_snapshot(left, field)} | {_engineering_snapshot(right, field)} |"
        for field in fields
    ]


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
            "### Richtwerte für die technische Vorprüfung",
            "",
            "| Prüfpunkt | " + left.canonical + " | " + right.canonical + " |",
            "| --- | --- | --- |",
            *_engineering_comparison_rows(left, right),
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


def _join(values: tuple[str, ...] | str) -> str:
    if isinstance(values, str):
        return values
    return "; ".join(values)


def article(material_type: str) -> str:
    lower = material_type.lower()
    if lower.startswith("elastomer"):
        return "ein"
    if lower.startswith("thermoplast"):
        return "ein"
    return "eine Werkstoffrichtung:"
