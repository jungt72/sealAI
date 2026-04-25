# SeaLAI Konzept v0.4: Architecture-Ready Functional Specification

## 0. Status und Ziel dieser Version

Diese Version überführt v0.3 von einer umsetzungsbereiten Produkt-/UX-Spezifikation in eine **architecture-ready Functional Specification**.

Die wichtigste Änderung: Die zuvor offenen Architekturentscheidungen werden nicht mehr als spätere Implementierungsdetails behandelt, sondern als verbindliche Systementscheidungen festgelegt.

Diese Version ergänzt insbesondere:

- LLM-State-Interaction-Pattern
- Case Event Log und Revisionsmodell
- Dependency Graph für Derived Values
- Stale-/Invalidierungsmodell
- Conflict Detection
- Risk Evaluator als deterministischer, erklärbarer Service
- Projection Contract zwischen Case-State und Cockpit
- Enum-/Internationalisierungsgrundsätze
- Auditierbarkeit für Matching und RFQ
- Eval-Modell für LLM-Kommunikation
- Dokumenten-/Upload-Pfad als eigener Input-Kanal
- Hersteller-Capability-Registry als Matching-Grundlage

Diese Spezifikation ist als Grundlage für Design, Frontend, Backend, Agentenlogik, Tests und Codex-/Antigravity-Umsetzung gedacht.

---

# 0.1 Verbindliche Architekturentscheidungen v0.4

## ADR-001: LLM-State-Interaction-Pattern

SeaLAI verwendet für das MVP ein **Structured Double Output Pattern**.

Das bedeutet: Jeder relevante LLM-Turn kann zwei getrennte Ausgaben erzeugen:

```text
1. assistant_message
   Natürliche Sprache für den Nutzer.

2. proposed_case_delta
   Strukturierter Änderungsvorschlag für den Case-State.
```

Das LLM darf den Case-State nicht direkt verändern. Es darf nur ein Proposed Delta erzeugen.

Der Backend-Governor entscheidet anschließend:

```text
LLM proposed_case_delta
→ schema validation
→ provenance assignment
→ conflict detection
→ rule validation
→ event append
→ state materialization
→ derived recomputation
→ projection update
```

### Warum Pattern B und nicht Tool-Use als primäres Muster?

Tool-Use/Function-Calling ist stark, koppelt den Dialog aber früh an viele einzelne Backend-Aktionen. Für SeaLAI ist das MVP-Ziel zunächst ein kontrollierter, testbarer Diagnosefluss. Das strukturierte Doppelausgabe-Muster ist dafür robuster, weil jeder Turn als gesamter Vorschlag validiert und versioniert werden kann.

### Wann ist ein separater Extractor erlaubt?

Für Dokumente, Fotos, Zeichnungen, lange PDFs oder komplexe historische Chatabschnitte darf zusätzlich ein spezialisierter Extractor verwendet werden. Dieser Extractor erzeugt ebenfalls nur Proposed Deltas, keine direkten State-Mutationen.

Damit gilt:

```text
Chat LLM: Kommunikation + Proposed Delta
Document Extractor: Document-derived Proposed Delta
Governor: einzige Instanz, die State verändert
```

---

## ADR-002: Case-State wird eventbasiert geführt

SeaLAI verwendet kein reines CRUD-Modell für technische Wahrheit.

Jede State-Änderung wird als append-only Case Event erfasst.

```text
CaseEvent:
- event_id
- case_id
- case_revision_before
- case_revision_after
- event_type
- actor_type              user | assistant | extractor | rule_engine | system
- source_turn_id
- source_document_id
- proposed_delta
- accepted_delta
- rejected_delta
- rejection_reasons
- created_at
- ruleset_version
- model_id
```

Der aktuelle Case-State ist eine materialisierte Projektion aus dem Event Log.

Vorteile:

- technische Änderungen sind auditierbar
- Konflikte sind nachvollziehbar
- Matching-Entscheidungen können erklärt werden
- Regressionstests können Case-Verläufe replayen
- Hersteller-RFQs bekommen eine belastbare Entstehungsspur

---

## ADR-003: Revisions- und Stale-Modell

Jede akzeptierte Änderung an einem kritischen Eingabefeld erzeugt eine neue `case_revision`.

Kritische Eingabefelder sind insbesondere:

```text
asset_type
seal_location
motion_type
medium_name
temperature_min
temperature_max
pressure_nominal
pressure_peak
speed_rpm
shaft_diameter
housing_bore
installation_width
shaft_material
surface_finish
food_contact
atex_relevance
```

Abgeleitete Werte werden bei Änderung ihrer Eingaben nicht gelöscht, sondern als `stale` markiert, bis sie neu berechnet oder bewusst verworfen werden.

```text
DerivedValue:
- value
- status                  valid | stale | invalid | unknown
- derived_from_fields
- derived_from_revision
- calculated_at
- calculation_id
- ruleset_version
- stale_reason
```

Grundsatz:

```text
Neue Eingabe → neue Revision → abhängige Werte stale → Recompute → Projection aktualisieren
```

---

## ADR-004: Dependency Graph für Derived Values

SeaLAI führt einen expliziten Dependency Graph.

Beispiele:

```text
circumferential_speed
depends_on: shaft_diameter, speed_rpm

pv_load
depends_on: pressure_nominal, circumferential_speed

temperature_risk
depends_on: temperature_max, candidate_materials, medium_name

material_direction
depends_on: medium_name, temperature_max, motion_type, pressure_nominal, speed_rpm

readiness_level
depends_on: asset_type, seal_location, motion_type, medium_name, operating_conditions, geometry, conflicts, blocking_unknowns
```

Der Dependency Graph ist nicht optional. Ohne ihn entstehen zombie-abgeleitete Werte.

---

## ADR-005: Conflict Detection als eigener Service

Konflikte werden nicht nur in der UI dargestellt, sondern durch einen eigenen Service erkannt.

```text
ConflictDetector:
Input:
- current_case_state
- accepted_delta_candidate
- field_tolerances
- provenance_priority

Output:
- conflicts[]
- conflict_severity
- suggested_resolution_question
```

Beispiel:

```text
Turn 5: temperature_max = 80 °C, provenance=user_stated
Turn 12: temperature_max = 180 °C, provenance=user_stated
```

Ergebnis:

```text
conflict_type: value_replacement
field: temperature_max
old_value: 80
new_value: 180
resolution: accept_new_value_and_invalidate_dependents
```

Bei expliziter Korrektur durch den Nutzer gilt der neue Wert als accepted. Alte abgeleitete Werte werden stale.

Bei unklarer widersprüchlicher Aussage fragt SeaLAI nach.

---

## ADR-006: Risk Evaluator ist deterministisch und erklärbar

Der Risk Evaluator ist kein freier LLM-Score.

Er ist ein deterministischer Service mit erklärbaren Ergebnissen.

```text
RiskEvaluationResult:
- risk_name
- score                  0 | 1 | 2 | 3 | 4 | 9
- label                  low | watch | moderate | high | critical | unknown
- drivers[]
- missing_inputs[]
- rule_ids[]
- explanation_short
- confidence
- ruleset_version
```

Skala:

```text
0 = niedrig / nicht relevant
1 = beobachten
2 = moderat
3 = hoch
4 = kritisch
9 = unbekannt / nicht bewertbar
```

MVP-Ansatz:

```text
Risk Evaluator = regelbasierte Heuristiken + kuratierte Lookup-Tabellen + Unknown-Handling
```

Das LLM darf Risiken sprachlich erklären oder Kandidaten vorschlagen, aber der numerische Risk Score kommt aus dem Evaluator.

Beispiel:

```text
corrosion_risk
Inputs:
- medium_category
- medium_name
- concentration
- temperature_max
- shaft_material
- housing_material
- spring_material

Wenn medium_name = salt_water und metallic_material_unknown:
score = 9
missing_inputs = [shaft_material, spring_material]
explanation_short = "Salzwasser kann korrosiv wirken; metallische Werkstoffe sind noch unbekannt."
```

---

## ADR-007: Projection Contract als eigene Backend-Schicht

Das Cockpit rendert nicht direkt aus rohem Case-State.

Zwischen Case-State und UI liegt eine Projection-Schicht:

```text
CaseState
→ ProjectionBuilder
→ CaseWorkspaceProjection
→ Frontend Cockpit
```

Die Projection-Schicht entscheidet:

- welcher Kartenzustand angezeigt wird
- welche Felder sichtbar sind
- welche Warnungen priorisiert werden
- welcher Tab aktiv oder empfohlen ist
- welche nächste Frage sichtbar wird
- welche Deep-Dive-Aktion angeboten wird

Damit bleibt das Frontend dumm und konsistent.

---

## ADR-008: Sprachunabhängige Enums, lokalisierte Labels

Interne Enum-Werte sind niemals deutsche oder englische UI-Strings.

Falsch:

```text
asset_type = "Rührwerk"
```

Richtig:

```text
asset_type = "agitator"
label_de = "Rührwerk"
label_en = "Agitator"
```

Das gilt für:

- asset_type
- motion_type
- seal_type
- medium_category
- risk_name
- readiness_label
- output_class
- provenance

Deutsch ist MVP-Primärsprache. Englisch muss ohne State-Migration möglich bleiben.

---

## ADR-009: Dokumenten- und Upload-Pfad ist eigener Input-Kanal

SeaLAI behandelt Dokumente, Fotos, Zeichnungen und Datenblätter als First-Class Inputs.

```text
DocumentInput:
- document_id
- case_id
- file_type
- file_name
- uploaded_at
- extraction_status
- extracted_candidates[]
- provenance=documented
```

Der Document Extractor erzeugt nur Proposed Deltas.

Beispiele:

- Wellendurchmesser aus Zeichnung
- vorhandene Dichtungsabmessung aus Datenblatt
- Materialangabe aus Spezifikation
- Artikelnummer aus Foto oder Dokument

Alle übernommenen Werte bleiben als `documented` markiert, bis der Nutzer oder ein Prozess sie bestätigt.

---

## ADR-010: Hersteller-Matching braucht Capability Registry

Matching basiert auf einer strukturierten Herstellerfähigkeits-Registry.

```text
ManufacturerCapability:
- manufacturer_id
- supported_asset_types[]
- supported_seal_types[]
- supported_material_families[]
- diameter_range
- pressure_range
- temperature_range
- industries[]
- certifications[]
- food_contact_capability
- pharma_capability
- atex_capability
- small_quantity_capability
- prototype_capability
- geographic_scope
- response_model
- evidence_level          self_declared | verified | platform_curated
```

MVP darf manuell kuratiert starten. Die Datenstruktur muss aber herstellerportal-fähig sein.

---

## ADR-011: LLM-Evals sind Pflicht

SeaLAI braucht eine Eval-Schicht für LLM-Kommunikation und State-Delta-Qualität.

MVP-Evals:

```text
1. Tone Compliance
   freundlich, professionell, keine Scheinsicherheit

2. Safety Language
   keine finale Freigabe, keine Garantiezusage

3. Best-Next-Question Quality
   fragt die technisch sinnvollste nächste Frage

4. Delta Extraction Accuracy
   proposed_case_delta extrahiert korrekte Werte

5. No Unauthorized State Claims
   LLM behauptet keine Werte, die nicht im State/Delta stehen

6. Deep-Dive Grounding
   Erklärung ist fallbezogen und führt zurück zur Analyse
```

Eval-Methoden:

- Golden Test Set
- schema validation
- deterministic assertions
- optional Judge-LLM mit Rubrik
- manuelle Stichproben bei Modellwechsel

---

# 1. Produktdefinition

## 1.1 SeaLAI in einem Satz

SeaLAI ist eine dialogische Diagnose- und Qualifizierungsplattform für Dichtungstechnik, die Anwender durch ein technisches Gespräch führt, ihre Dichtungssituation im Cockpit sichtbar macht und daraus eine strukturierte, herstellerreife Anfrage vorbereitet.

## 1.2 Zentrales Wertversprechen

> SeaLAI hilft Anwendern, ihre Dichtungssituation zu verstehen, bevor sie eine Dichtung anfragen.

## 1.3 Strategischer Kern

SeaLAI verkauft nicht die Dichtung.

SeaLAI verkauft:

- Klarheit
- technische Einordnung
- bessere Fragen
- weniger Unsicherheit
- eine strukturierte Herstelleranfrage
- bessere Kommunikation zwischen Anwender und Hersteller

## 1.4 Nicht-Ziele

SeaLAI ist nicht:

- ein Produktkatalog
- ein Preisvergleich
- ein Ranking-Marktplatz
- ein Formular-Assistent
- ein Ersatz für technische Herstellerfreigabe
- ein System für finale Gewährleistungsaussagen
- ein universeller Auslegungsautomat für alle Dichtungstypen

---

# 2. Grundprinzipien

## 2.1 Verstehen vor Empfehlen

SeaLAI empfiehlt nicht vorschnell. Zuerst wird die Anwendung verstanden.

Ablauf:

```text
Anwendung verstehen
→ Anlagenkontext klären
→ Dichtstelle und Bewegung bestimmen
→ Medium und Betriebsdaten erfassen
→ Risiken erkennen
→ technische Richtung ableiten
→ RFQ-Reife prüfen
→ Anfrage vorbereiten
```

## 2.2 Anlagenkontext vor Dichtungsauswahl

Eine Dichtung wird nie isoliert bewertet. Sie wird immer im Anlagen- und Funktionskontext bewertet.

Kernfrage:

```text
In welcher Anlage oder Baugruppe sitzt die Dichtung?
```

Beispiele:

- Rührwerk
- Getriebe
- Pumpe
- Mischer
- Förderschnecke
- Kompressor
- Motor
- Walze
- Rohrleitung
- Behälter
- Hydraulikzylinder
- Pneumatikzylinder
- unbekannte Sondermaschine

Der Anlagenkontext beeinflusst:

- Bewegungsart
- Dichtungstyp-Richtung
- Medienkontakt
- Druck-/Vakuumsituation
- Schmierung
- Wellenschlag / Exzentrizität
- hygienische Anforderungen
- Wartbarkeit
- Ausfallfolge
- Norm-/Compliance-Relevanz

## 2.3 LLM als Kommunikationsschicht, nicht als alleinige technische Autorität

Das LLM führt die vollständige Kommunikation.

Aber technische Wahrheit kommt aus:

- kanonischem Case-State
- Regel-/Pflichtfeldlogik
- Berechnungen
- Risiko-Gates
- Norm-Gates
- Readiness-Modell
- Herstellerfähigkeitsmodell

Formel:

```text
LLM spricht und erklärt.
Case-State und Regeln bestimmen, was gilt.
```

## 2.4 Cockpit als Transparenzebene

Das Cockpit zeigt, was SeaLAI verstanden hat, was fehlt, was kritisch ist und welcher nächste Schritt sinnvoll ist.

Es ist kein Formularfriedhof und kein Engineering-Overload.

Prinzip:

```text
Übersicht zuerst. Tiefe auf Abruf.
```

---

# 3. Zielgruppen und Startpunkte

## 3.1 Primäre Nutzer

- Konstrukteure
- Instandhalter
- technische Einkäufer
- Projekttechniker
- Maschinenbauer
- Anlagenbetreiber
- Prozessingenieure
- kleinere OEMs
- Betriebe mit Sonderfällen
- Nutzer mit Ersatzteil- oder Retrofitproblemen

## 3.2 Typische Startpunkte

SeaLAI muss folgende Einstiege aufnehmen können:

### A. Unklare Problemschilderung

```text
Unsere Dichtung fällt immer wieder aus.
```

### B. Konkrete Betriebsdaten

```text
Salzwasser, 80 °C, 4 bar, rotierende Welle.
```

### C. Anlagenfrage

```text
Wir brauchen eine Dichtung an einem Rührwerk.
```

### D. Materialfrage

```text
Ist PTFE besser als FKM?
```

### E. Dichtungstypfrage

```text
Brauche ich einen RWDR oder eine Gleitringdichtung?
```

### F. Ersatzteil-/Retrofitfall

```text
Wir haben eine alte Dichtung und finden keinen Ersatz.
```

### G. RFQ-Wunsch

```text
Ich möchte das sauber bei einem Hersteller anfragen.
```

---

# 4. Gesamt-UX: 50/50 Diagnose-Arbeitsplatz

## 4.1 Desktop Layout

```text
┌────────────────────────────────────────────────────────────────────┐
│ Header / Case Context / optionaler Fortschritt                     │
├──────────────────────────────────┬─────────────────────────────────┤
│ Kommunikationszentrale            │ Technisches Cockpit              │
│ ca. 50%                           │ ca. 50%                          │
│                                  │                                 │
│ Chat, Diagnose, Erklärung         │ Analyse, Intelligence, RFQ        │
│ offene Fragen                     │ Parameter, Risiken, Readiness     │
│ Nutzerführung                     │ fallbezogene Deep Dives           │
└──────────────────────────────────┴─────────────────────────────────┘
```

## 4.2 Mobile Layout

Mobile priorisiert den Chat.

Reihenfolge:

1. Chat
2. kompakter Cockpit-Status
3. Analyse-Karten vertikal
4. Intelligence-Tabs als horizontale Scroll-Tabs
5. Deep Dive als fokussierte Detailansicht

Mobile darf die Desktop-2x2-Struktur nicht starr erzwingen.

---

# 5. Phasenmodell

SeaLAI-Fälle laufen durch fachliche Phasen. Diese Phasen sind keine harten Screens, sondern Zustände des Diagnoseprozesses.

## 5.1 Phase 0: Orientierung

Ziel:

- Nutzer willkommen heißen
- Anliegen verstehen
- unterscheiden: Small Talk, Meta-Frage, Wissensfrage oder technischer Fall

Typische Antwort:

```text
Gerne. Beschreiben Sie kurz, wo die Dichtung eingesetzt wird oder welches Problem auftritt. Ich sortiere die Angaben und frage nur die Punkte nach, die technisch wirklich wichtig sind.
```

Cockpit:

- leerer, ruhiger Startzustand
- Hinweis: „Noch keine technische Anwendung erkannt“

## 5.2 Phase 1: Anlagenkontext klären

Ziel:

- Anlage/Baugruppe erkennen
- Funktion der Dichtung verstehen
- grobe technische Richtung bestimmen

Leitfrage:

```text
In welcher Anlage oder Baugruppe sitzt die Dichtung?
```

Beispiele:

- Rührwerk
- Getriebe
- Pumpe
- Rohrleitung
- Behälter
- Hydraulikzylinder

Cockpit-Fokus:

- Karte „Anlage & Funktion“

## 5.3 Phase 2: Dichtstelle und Bewegung klären

Ziel:

- Bewegungsart bestimmen
- Dichtstelle lokalisieren
- Dichtungspfad eingrenzen

Wichtige Unterscheidungen:

- rotierend
- statisch
- linear
- oszillierend
- unklar
- innen nach außen dichtend
- außen nach innen schützend
- Produktabdichtung
- Schmutzschutz
- Druckabdichtung

Leitfrage:

```text
Sitzt die Dichtung an einer rotierenden Welle, an einer statischen Verbindung oder an einer linearen Bewegung?
```

## 5.4 Phase 3: Medium und Umgebung erfassen

Ziel:

- Medium erkennen
- Medienrisiken verstehen
- Umgebung und Reinigungsprozesse erfassen

Wichtige Daten:

- Medium
- Konzentration
- Temperatur
- Partikel
- Reinigung/CIP/SIP
- Lebensmittel-/Pharmakontakt
- Außenumgebung
- Benetzung/Trockenlauf

## 5.5 Phase 4: Betriebsdaten und Geometrie erfassen

Ziel:

- technische Berechnungen und Vorselektion ermöglichen

Wichtige Daten:

- Wellendurchmesser
- Gehäusebohrung
- Einbaubreite
- Drehzahl
- Druck / Differenzdruck
- Temperatur min/max
- Exzentrizität / Rundlauf
- Wellenoberfläche
- Wellenhärte
- Werkstoffe
- Stückzahl

## 5.6 Phase 5: Risiken und technische Richtung ableiten

Ziel:

- relevante Risiken benennen
- technische Richtung plausibilisieren
- unklare Punkte priorisieren

Beispiele:

- Korrosion
- Trockenlauf
- PV-Belastung
- Druckgrenze
- Temperaturreserve
- chemische Beständigkeit
- Abrasion
- Hygiene/Compliance
- Montage-/Einbaurisiko

## 5.7 Phase 6: Readiness prüfen

Ziel:

- feststellen, ob eine Herstelleranfrage sinnvoll vorbereitet werden kann

Readiness-Stufen:

```text
0 = Kein technischer Fall erkannt
1 = Anwendung grob erkannt
2 = Dichtungssituation teilweise verstanden
3 = technische Richtung plausibel
4 = Anfrage vorbereitbar, aber offene Punkte sichtbar
5 = herstellerreife Anfrage
```

## 5.8 Phase 7: RFQ-Report vorbereiten

Ziel:

- strukturierte Anfrage erzeugen
- offene Punkte transparent markieren
- Herstellerdialog erleichtern

## 5.9 Phase 8: Matching / Herstellerkontakt

Ziel:

- passende Spezialisten anhand technischer Anforderungen finden
- Matching nicht sponsorgetrieben
- RFQ an passende Hersteller vorbereiten

---

# 6. Interne Routing-Klassen

SeaLAI nutzt interne Kommunikationsklassen. Der Nutzer sieht diese nicht.

```text
GREETING
freundliche Begrüßung, kein Case-Zwang

META_QUESTION
Fragen zu SeaLAI, Ablauf, Datenschutz, Herstellerkontakt, Neutralität

KNOWLEDGE_QUERY
fachliche Erklärung ohne zwingende Case-Erstellung

DOMAIN_INQUIRY
echter technischer Fall mit Case-State

DEEP_DIVE
fallbezogene Erklärung zu Anlage, Medium, Werkstoff, Dichtungstyp, Norm oder Berechnung

RECOVERY
Umgang mit Unsicherheit, Frust, Widerspruch oder unklaren Angaben
```

## 6.1 Routing-Regel

- Small Talk bleibt leichtgewichtig.
- Meta-Fragen werden beantwortet, ohne technischen Case zu erzwingen.
- Wissensfragen können beantwortet werden, ohne sofort RFQ zu starten.
- Sobald der Nutzer eine echte Anwendung beschreibt, entsteht oder aktualisiert sich ein technischer Case.
- Deep Dives dürfen den Case-Kontext nutzen, sollen aber nicht zwangsläufig neue Pflichtdaten erzwingen.

---

# 7. Kanonisches Case-Datenmodell für MVP

Dieses Datenmodell beschreibt die fachlichen Slices, die Frontend, Cockpit, LLM und Rule Engine konsistent nutzen sollten.

## 7.1 Case Identity

```text
case_id
user_id / tenant_id
case_revision
created_at
updated_at
current_phase
readiness_level
output_class
```

## 7.2 Conversation Context

```text
last_user_intent
active_route_class
active_deep_dive_type
last_assistant_summary
pending_best_next_question
conversation_tone_flags
```

## 7.3 Application Context

```text
asset_type                Rührwerk, Pumpe, Getriebe, etc.
asset_function            mischen, fördern, lagern, antreiben, abdichten
industry_context          food, pharma, chemical, water, general industry
failure_context           Leckage, Ausfall, Kontamination, Verschleiß
maintenance_context       leicht zugänglich, schwer zugänglich, regelmäßig
consequence_of_failure    niedrig, mittel, hoch, kritisch
```

## 7.4 Seal Location & Motion

```text
seal_location             Welle, Gehäuse, Deckel, Rohrleitung, Kolben, etc.
motion_type               rotary, static, linear, oscillating, unknown
shaft_orientation         horizontal, vertical, angled, unknown
sealing_direction         inside_out, outside_in, bidirectional, unknown
primary_function          product_sealing, contamination_protection, pressure_sealing, dust_protection
```

## 7.5 Operating Conditions

```text
temperature_min
temperature_max
pressure_nominal
pressure_peak
pressure_direction
vacuum_present
speed_rpm
duty_cycle
start_stop_frequency
continuous_operation
lubrication_condition
benetzung                 dauerhaft, wechselnd, trockenlaufgefährdet, unbekannt
```

## 7.6 Geometry

```text
shaft_diameter
housing_bore
installation_width
available_space
existing_seal_dimensions
shaft_runout
eccentricity
surface_finish
shaft_hardness
shaft_material
housing_material
```

## 7.7 Medium Context

```text
medium_name
medium_category           water, oil, chemical, solvent, powder, food, steam, gas, unknown
concentration
ph_value
viscosity
particles_present
abrasive_content
crystallization_risk
cleaning_media
cip_sip
food_contact
pharma_contact
atex_relevance
```

## 7.8 Material Context

```text
candidate_materials       PTFE, FKM, NBR, EPDM, etc.
material_question         e.g. PTFE vs FKM
known_incompatible_materials
required_certifications
compound_family_hint
```

## 7.9 Seal Type Context

```text
candidate_seal_types      RWDR, PTFE-RWDR, Gleitringdichtung, O-Ring, etc.
current_seal_type
requested_seal_type
seal_type_confidence
reason_for_direction
```

## 7.10 Calculations

```text
circumferential_speed
pv_load
temperature_headroom
pressure_speed_advisory
vapor_margin
extrusion_index
friction_heat_indicator
```

## 7.11 Risk Context

```text
corrosion_risk
abrasion_risk
dry_run_risk
chemical_compatibility_risk
pressure_risk
temperature_risk
speed_pv_risk
hygiene_risk
installation_risk
surface_risk
unknowns_risk
```

Risk scale:

```text
0 = not relevant / low
1 = watch
2 = moderate
3 = high
4 = critical
9 = unknown / not assessable
```

## 7.12 Provenance

Every critical value needs provenance:

```text
user_stated
documented
inferred
calculated
confirmed
web_hint
missing
```

## 7.13 RFQ Readiness

```text
readiness_level
readiness_label
missing_required_fields
blocking_unknowns
recommended_next_question
rfq_possible
rfq_report_sections_available
```

---

# 8. Cockpit: 2x2 Analyse-Tab

## 8.1 Final MVP-Kartenstruktur

```text
┌────────────────────────────┬────────────────────────────┐
│ 1. Anlage & Funktion        │ 2. Medium & Umgebung        │
├────────────────────────────┼────────────────────────────┤
│ 3. Betriebsdaten & Geometrie│ 4. Risiken & Anfrage-Reife  │
└────────────────────────────┴────────────────────────────┘
```

Diese Struktur ist verbindlich für die MVP-Analyseansicht.

---

## 8.2 Karte 1: Anlage & Funktion

Zweck:

- Diagnoseanker
- Anlagenkontext sichtbar machen
- Dichtungssituation fachlich rahmen

Daten:

- asset_type
- asset_function
- seal_location
- motion_type
- primary_function
- consequence_of_failure

Zustände:

### Empty

```text
Noch keine Anlage erkannt.
Beschreiben Sie kurz, wo die Dichtung sitzt.
```

### Partial

```text
Anlage: Rührwerk erkannt
Dichtstelle: noch unklar
Bewegung: vermutlich rotierend, unbestätigt
```

### Good

```text
Anlage: Rührwerk
Dichtstelle: rotierende Welle am Behälter
Funktion: Produktabdichtung
```

### Critical

```text
Rührwerk mit möglichem Behälterdruck.
Dichtungstyp noch nicht belastbar bestimmbar.
```

### Conflict

```text
Widerspruch: Getriebe genannt, aber CIP/Food-Kontext deutet auf Prozessanlage.
Bitte kurz klären.
```

---

## 8.3 Karte 2: Medium & Umgebung

Zweck:

- Medium und Umgebungsrisiken sichtbar machen
- Medium Intelligence anbieten

Daten:

- medium_name
- medium_category
- temperature range
- particles
- concentration
- cleaning_media
- food/pharma/atex flags
- benetzung

Zustände:

### Empty

```text
Medium noch nicht bekannt.
```

### Partial

```text
Medium: Salzwasser
Offen: Konzentration, Benetzung, Werkstoffe
```

### Good

```text
Medium: Salzwasser
Temperatur: 80 °C
Benetzung: dauerhaft
Hinweis: Korrosion/Ablagerung prüfen
```

### Critical

```text
Medium kritisch: Salzwasser + Partikel + unklare Trockenlaufphasen.
Werkstoff- und Oberflächenangaben fehlen.
```

Aktion:

```text
Medium genauer ansehen
```

---

## 8.4 Karte 3: Betriebsdaten & Geometrie

Zweck:

- technische Rechen- und Auslegungsgrundlage zeigen

Daten:

- shaft_diameter
- housing_bore
- installation_width
- speed_rpm
- pressure
- temperature_min/max
- surface_finish
- shaft_material
- shaft_hardness
- eccentricity/runout

Zustände:

### Empty

```text
Betriebsdaten fehlen noch.
```

### Partial

```text
Temperatur: 80 °C
Drehzahl: fehlt
Druck: fehlt
Geometrie: fehlt
```

### Calculable

```text
Drehzahl und Wellendurchmesser vorhanden.
Umfangsgeschwindigkeit berechenbar.
```

### Good

```text
Welle: 28 mm
Gehäuse: 34 mm
Breite: 3 mm
Drehzahl: 400 rpm
Druck: 4 bar
```

### Critical

```text
Druck und Einbaubreite könnten für Standard-RWDR kritisch sein.
Herstellerprüfung erforderlich.
```

---

## 8.5 Karte 4: Risiken & Anfrage-Reife

Zweck:

- Fallstatus komprimieren
- nächste beste Frage zeigen
- RFQ-Pfad vorbereiten

Daten:

- top risks
- readiness_level
- missing_required_fields
- blocking_unknowns
- recommended_next_question
- rfq_possible

Zustände:

### Low

```text
Anfrage-Reife: niedrig
Erst Anlage und Bewegungsart klären.
```

### Medium

```text
Anfrage-Reife: mittel
Technische Richtung erkennbar, aber Druck und Geometrie fehlen.
```

### High

```text
Anfrage-Reife: hoch
RFQ vorbereitbar. Offene Punkte werden im Report markiert.
```

### Blocked

```text
Anfrage noch nicht sinnvoll.
Blocker: Dichtstelle und Medium unklar.
```

### Critical

```text
Technisches Risiko erhöht.
Vor Herstelleranfrage sollten Trockenlauf und Wellenoberfläche geklärt werden.
```

---

# 9. Cockpit-Tabs

## 9.1 MVP-Tabs

Verbindliche MVP-Tabs:

```text
Analyse | Medium | Werkstoff | Dichtungstyp
```

Der Anlagenkontext bleibt im MVP in der Analysekarte „Anlage & Funktion“.

Optional später:

```text
Anlage | Berechnung | Normen | Anfrage
```

## 9.2 Tab-Regeln

Tabs dürfen nicht wie statische Wissensseiten wirken.

Jeder Tab muss fallbezogen sein und nach dieser Struktur arbeiten:

```text
1. Was wurde erkannt?
2. Warum ist es in diesem Fall relevant?
3. Welche Chancen/Risiken entstehen?
4. Was leitet SeaLAI daraus ab?
5. Was fehlt noch?
6. Was ist die nächste sinnvolle Frage oder Aktion?
```

## 9.3 Wann öffnet sich ein Tab?

Ein Tab kann geöffnet werden durch:

- Nutzerklick im Cockpit
- Nutzerfrage im Chat
- SeaLAI-Vorschlag mit Zustimmung oder impliziter Relevanz
- Risikoerklärung
- Materialvergleich
- Dichtungstypvergleich

## 9.4 Rückkehr zur Analyse

Jeder Deep Dive braucht eine klare Rückführung:

```text
Zurück zur Analyse
```

und eine fachliche Rückführung:

```text
Für die nächste technische Einordnung fehlt jetzt vor allem: ...
```

---

# 10. Medium Intelligence

## 10.1 Zweck

Medium Intelligence erklärt ein erkanntes Medium im konkreten Dichtungskontext.

Nicht erlaubt:

- reine Chemie-Lexikontexte
- lange Wikipedia-artige Abschnitte
- Freigabeaussagen

Erlaubt:

- fallbezogene Relevanz
- Risiken
- notwendige Klärungsfragen
- Auswirkungen auf Dichtungstyp und Werkstoffrichtung

## 10.2 Template

```text
Medium Intelligence: {medium_name}

Erkannt:
{medium_name} wurde als Medium genannt.

Relevanz im aktuellen Fall:
{fallbezogene Erklärung}

Mögliche Risiken:
- {risk_1}
- {risk_2}
- {risk_3}

Für die Dichtungsauswahl relevant:
- {factor_1}
- {factor_2}
- {factor_3}

Noch offen:
- {missing_1}
- {missing_2}

Nächste sinnvolle Frage:
{recommended_next_question}
```

## 10.3 Beispiel Salzwasser

```text
Medium Intelligence: Salzwasser

Erkannt:
Salzwasser wurde als Medium genannt.

Relevanz im aktuellen Fall:
Salzwasser ist in Dichtungsanwendungen vor allem wegen Chloridkorrosion, möglicher Ablagerungen und möglicher Partikel relevant. Entscheidend sind nicht nur Dichtlippe und Werkstoff, sondern auch Welle, Feder, Gehäuse, Gegenlauffläche und Betriebsprofil.

Mögliche Risiken:
- Korrosion metallischer Bauteile
- Ablagerungen oder Kristallisation
- Partikel-/Abrasionsbelastung
- Trockenlauf bei wechselnder Benetzung

Noch offen:
- Meerwasser oder konzentrierte Sole?
- dauerhaft benetzt oder wechselnd trocken?
- Wellen- und Gehäusewerkstoff?
- Bewegung und Druck?

Nächste sinnvolle Frage:
Handelt es sich um eine rotierende oder statische Abdichtung?
```

---

# 11. Werkstoff Intelligence

## 11.1 Zweck

Werkstoff Intelligence erklärt oder vergleicht Dichtungswerkstoffe im aktuellen Fall.

Beispiele:

- PTFE vs. FKM
- FKM vs. NBR
- EPDM bei Wasser/Dampf
- PTFE-Compounds
- FDA-/EU-konforme Werkstoffe

## 11.2 Template

```text
Werkstoff Intelligence: {material_topic}

Kurzfazit:
{short_case_based_summary}

Vergleich / Einordnung:
{structured_comparison}

Für diesen Fall relevant:
- {factor_1}
- {factor_2}

Grenze der Aussage:
{no_final_release_language}

Nächste sinnvolle Frage:
{recommended_next_question}
```

## 11.3 Beispiel PTFE vs. FKM

```text
Werkstoff Intelligence: PTFE vs. FKM

Kurzfazit:
PTFE ist häufig stark bei chemischer Beständigkeit, geringer Reibung und höheren Temperaturen. FKM ist elastischer, oft robuster in Standard-Elastomeranwendungen und meist einfacher zu montieren.

Vergleich:

Kriterium               PTFE                         FKM
Chemie                  sehr breit                   gut, aber begrenzt
Elastizität             gering                       hoch
Reibung                 niedrig                      höher
Trockenlauf             oft günstiger                häufig kritischer
Montage                 sensibler                    meist robuster
Gegenlauffläche          sehr wichtig                 wichtig
Kosten                  häufig höher                 häufig niedriger
Typischer Einsatz        anspruchsvolle Medien         Standard-Elastomerfälle

Grenze:
Ohne Medium, Temperatur, Bewegung, Druck und Gegenlauffläche ist keine belastbare Auswahl möglich.

Nächste sinnvolle Frage:
Geht es um eine rotierende Welle und kennen Sie Drehzahl und Wellendurchmesser?
```

---

# 12. Dichtungstyp Intelligence

## 12.1 Zweck

Dichtungstyp Intelligence erklärt Dichtprinzipien und grenzt sie fallbezogen ab.

Beispiele:

- RWDR
- PTFE-RWDR
- Gleitringdichtung
- O-Ring
- Hydraulikdichtung
- Pneumatikdichtung
- Labyrinthdichtung
- statische Dichtung

## 12.2 Template

```text
Dichtungstyp Intelligence: {seal_type_topic}

Ausgangslage:
{case_context}

Einordnung:
{seal_type_explanation}

Geeignet, wenn:
- {condition_1}
- {condition_2}

Kritisch, wenn:
- {risk_1}
- {risk_2}

Noch offen:
- {missing_1}

Nächste sinnvolle Frage:
{recommended_next_question}
```

## 12.3 Beispiel RWDR vs. Gleitringdichtung

```text
Dichtungstyp Intelligence: RWDR vs. Gleitringdichtung

RWDR:
- kompakte Lösung für viele rotierende Wellen
- stark abhängig von Wellenoberfläche, Schmierung, Drehzahl und Druck
- bei höherem Druck oft begrenzt

PTFE-RWDR:
- relevant bei anspruchsvolleren Medien und Temperaturen
- geringe Reibung möglich
- Montage und Gegenlauffläche kritischer

Gleitringdichtung:
- häufig relevanter bei Pumpen, höheren Drücken und anspruchsvollen Medien
- komplexer und kostenintensiver
- benötigt genaue Einbau- und Betriebsdaten

Nächste sinnvolle Frage:
Handelt es sich um eine Pumpenanwendung oder um eine einfache rotierende Welle außerhalb einer Pumpe?
```

---

# 13. Best-Next-Question-Logik

## 13.1 Ziel

SeaLAI stellt nicht viele Fragen auf einmal. SeaLAI stellt die nächste beste Frage.

## 13.2 Prioritätsrahmen

Standardpriorität:

```text
1. Anlage / Baugruppe
2. Dichtstelle / Bewegungsart
3. Funktion der Dichtung
4. Medium
5. Temperatur
6. Druck / Vakuum
7. Drehzahl / Geschwindigkeit
8. Geometrie
9. Werkstoffe / Oberfläche
10. Betriebsprofil / Trockenlauf / Benetzung
11. Normen / Hygiene / ATEX / FDA
12. Stückzahl / RFQ-Ziel
```

Diese Reihenfolge darf dynamisch angepasst werden, wenn der Nutzer bereits Daten liefert.

## 13.3 Frageformat

Eine gute SeaLAI-Frage besteht aus:

```text
kurze Einordnung + eine konkrete Frage
```

Beispiel:

```text
Gut, dann ist die Bewegungsart entscheidend. Sitzt die Dichtung an einer rotierenden Welle oder an einer statischen Verbindung?
```

## 13.4 Nicht erlaubt

Nicht SeaLAI-konform:

```text
Bitte nennen Sie alle folgenden Angaben: ...
```

Ausnahme:

Nur wenn der Nutzer ausdrücklich sagt, dass er eine vollständige Checkliste möchte.

---

# 14. Readiness-Modell

## 14.1 Readiness-Level

```text
0 Kein technischer Fall erkannt
1 Anwendung grob erkannt
2 Dichtungssituation teilweise verstanden
3 Technische Richtung plausibel
4 RFQ vorbereitbar mit offenen Punkten
5 Herstellerreife Anfrage
```

## 14.2 Mindestkriterien je Level

### Level 0

- Kein DOMAIN_INQUIRY
- nur Greeting, Meta oder allgemeine Wissensfrage

### Level 1

Mindestens:

- grober Anlagen- oder Problemkontext erkannt

Beispiel:

```text
Rührwerk mit Dichtungsproblem
```

### Level 2

Mindestens:

- Anlage/Baugruppe
- Dichtstelle oder Bewegungsart teilweise bekannt
- Medium oder Problemart bekannt

### Level 3

Mindestens:

- Anlage/Baugruppe
- Bewegungsart
- Medium
- mindestens ein wesentlicher Betriebsparameter
- grobe Dichtungstyp-Richtung möglich

### Level 4

Mindestens:

- Anlage/Baugruppe
- Dichtstelle/Bewegung
- Medium
- Temperatur
- Druck oder Hinweis „drucklos/unklar“
- Drehzahl oder statisch/linear ausreichend geklärt
- relevante Geometrie teilweise vorhanden
- offene Punkte transparent markiert

### Level 5

Mindestens:

- alle für die gewählte Dichtungssituation kritischen Pflichtfelder vorhanden oder bewusst als unbekannt markiert
- keine blockierenden Widersprüche
- Risiken beschrieben
- technische Richtung plausibel
- RFQ-Report vollständig genug für Herstellerprüfung

## 14.3 Readiness ist keine Qualitätsgarantie

Readiness bedeutet:

```text
Wie gut ist die Anfrage vorbereitet?
```

Nicht:

```text
Wie sicher passt die Dichtung?
```

---

# 15. Output-Klassen

SeaLAI-Ausgaben sollten kontrolliert einer Output-Klasse zugeordnet werden.

```text
conversational_answer
Allgemeine Antwort ohne Case-Update.

structured_clarification
Gezielte Rückfrage zur Fallklärung.

governed_state_update
Antwort mit bestätigter Aktualisierung des Case-State.

technical_preselection
Plausible technische Richtung, keine finale Freigabe.

medium_deep_dive
Fallbezogene Medium-Erklärung.

material_deep_dive
Fallbezogene Werkstoff-Erklärung oder Vergleich.

seal_type_deep_dive
Fallbezogene Dichtungstyp-Erklärung.

rfq_summary
Strukturierte Anfrage-Zusammenfassung.

candidate_shortlist
Hersteller-/Spezialistenrichtung, problem-first.

inquiry_ready
Anfrage ist herstellerreif vorbereitet.
```

---

# 16. RFQ-Report-Struktur

Der RFQ-Report ist das zentrale Ergebnis.

## 16.1 Report-Zweck

Der Report soll einem Hersteller schneller zeigen:

- worum es geht
- welche Anlage betroffen ist
- welche Daten sicher sind
- welche Daten fehlen
- welche Risiken sichtbar sind
- welche technische Richtung plausibel ist
- welche Fragen noch zu klären sind

## 16.2 Report-Abschnitte

Verbindliche MVP-Struktur:

```text
1. Kurzbeschreibung der Anwendung
2. Anlage & Funktion
3. Dichtstelle & Bewegungsart
4. Medium & Umgebung
5. Betriebsdaten
6. Geometrie & Einbauraum
7. Werkstoffe & Oberflächen
8. Erkannte Risiken
9. Berechnungen / technische Hinweise
10. Plausible technische Richtung
11. Offene Punkte / unbestätigte Annahmen
12. Fragen an den Hersteller
13. Anfrageziel / Stückzahl / gewünschte Rückmeldung
```

## 16.3 Report-Sprache

Erlaubt:

```text
technisch plausibel
für Herstellerprüfung geeignet
noch zu bestätigen
auf Basis aktueller Angaben
offene Punkte
```

Nicht erlaubt:

```text
garantiert geeignet
freigegeben
sicher passend
endgültig empfohlen
```

---

# 17. LLM-Tonalität und Sprachregeln

## 17.1 Tonalität

SeaLAI spricht:

- ruhig
- präzise
- empathisch
- fachlich
- entscheidungsführend
- nicht belehrend
- nicht verkäuferisch

## 17.2 Standardmuster

Gute Muster:

```text
Das ist ein wichtiger Hinweis.
```

```text
Für die technische Richtung ist jetzt entscheidend ...
```

```text
Das ist plausibel, aber noch nicht belastbar genug für eine Herstelleranfrage.
```

```text
Ich würde den Fall zunächst in zwei Richtungen prüfen ...
```

```text
Das reicht für den ersten Schritt. Ich markiere unklare Punkte sauber und frage gezielt weiter.
```

Schlechte Muster:

```text
Die perfekte Lösung ist ...
```

```text
Garantiert geeignet.
```

```text
Bitte füllen Sie alle Pflichtfelder aus.
```

```text
Ich bin mir sicher, dass ...
```

## 17.3 Antwortlänge

Grundsatz:

- kurz genug, um dialogisch zu bleiben
- lang genug, um den technischen Grund zu erklären

Standardantwort bei Diagnose:

```text
1 kurzer Einordnungssatz
1 technischer Grund
1 nächste Frage
```

---

# 18. Anlagenlogik / Application Intelligence im MVP

## 18.1 MVP-Regel

Application Intelligence ist im MVP keine eigene Tab-Seite, sondern Bestandteil der Analysekarte „Anlage & Funktion“.

## 18.2 Anlagenprofile als interne Muster

MVP sollte mindestens folgende Anlagenprofile kennen:

```text
Rührwerk
Getriebe
Pumpe
Mischer
Förderschnecke
statische Rohr-/Flanschverbindung
Hydraulikzylinder
Pneumatikzylinder
allgemeine rotierende Welle
unbekannte Sondermaschine
```

## 18.3 Anlagenprofil Rührwerk

Relevante Hinweise:

- rotierende Welle wahrscheinlich
- Behälterdruck/Vakuum möglich
- Wellenschlag/Exzentrizität möglich
- Reinigung/CIP/SIP möglich
- Produktkontakt möglich
- Hygiene/Food/Pharma möglich
- Kontamination kritisch

## 18.4 Anlagenprofil Getriebe

Relevante Hinweise:

- Öl-/Schmierstoffumgebung wahrscheinlich
- Schmutzschutz von außen relevant
- Wellenoberfläche/Einlaufspur wichtig
- Druck meist niedriger, aber Entlüftung/Überdruck möglich
- Temperatur durch Betrieb möglich

## 18.5 Anlagenprofil Pumpe

Relevante Hinweise:

- Medium, Druck und Drehzahl dominieren
- Trockenlauf/Kavitation/Dampfanteile möglich
- Gleitringdichtung oft relevant
- Leckagefolge kritisch
- Einbauraum und Pumpentyp wichtig

## 18.6 Anlagenprofil Förderschnecke / Mischer

Relevante Hinweise:

- Partikel/Abrasion möglich
- Produktanhaftung möglich
- langsame Rotation möglich
- Reinigung und Zugänglichkeit wichtig
- Pulver/Pasten/Schüttgut relevant

---

# 19. MVP-Grenzen

## 19.1 Deep Fidelity

MVP-Deep-Path:

```text
PTFE-RWDR
```

Hier darf SeaLAI tiefer prüfen, rechnen und strukturieren.

## 19.2 Shallow / Routing Paths

MVP-Shallow-Paths:

```text
Gleitringdichtung
klassischer RWDR
O-Ring / statisch
Hydraulikdichtung
Pneumatikdichtung
Labyrinth / Schmutzschutz
```

Diese Pfade dürfen erkannt, erklärt und an Spezialisten/RFQ überführt werden, aber nicht mit falscher Auslegungstiefe.

## 19.3 Zulässige Formulierung bei Shallow Path

```text
Dieser Fall könnte in Richtung Gleitringdichtung gehen. Für eine belastbare Auslegung sollte ein entsprechender Spezialist prüfen. Ich kann die Anfrage dafür strukturiert vorbereiten.
```

---

# 20. Matching-Prinzip

SeaLAI matcht problem-first.

## 20.1 Reihenfolge

```text
1. technische Anforderungen ableiten
2. Muss-Kriterien bestimmen
3. Herstellerfähigkeiten filtern
4. technische Passung erklären
5. RFQ vorbereiten
```

## 20.2 Sponsoring-Regel

Sponsoring darf die technische Passung nicht beeinflussen.

Erlaubt:

- transparente Sichtbarkeit
- markierte Partnerprofile
- optionale Angebotsmodelle

Nicht erlaubt:

- bezahltes technisches Ranking
- Sponsor wird als technisch besser dargestellt, wenn er es nicht ist

---

# 21. Akzeptanzkriterien

## 21.1 Produkt-Akzeptanz

Das Konzept gilt als umgesetzt, wenn:

- Nutzer natürlichsprachlich starten können
- SeaLAI nicht sofort Formularlogik erzwingt
- Anlagenkontext früh erkannt oder abgefragt wird
- die nächste Frage nachvollziehbar ist
- das Cockpit parallel sinnvolle Informationen zeigt
- Deep Dives fallbezogen sind
- Readiness sichtbar wird
- RFQ-Report erzeugt werden kann

## 21.2 Technische Akzeptanz

- Kritische Werte haben Provenienz
- Readiness kommt aus deterministischer Logik
- Berechnungen kommen aus registrierten Funktionen
- Output-Klassen sind kontrolliert
- LLM darf keine finale Freigabe behaupten
- Cockpit wird aus Case-State/Projection gespeist, nicht aus freiem Chattext

## 21.3 UX-Akzeptanz

- 50/50 Layout auf Desktop
- Chat bleibt Kommunikationszentrum
- Analyse-Tab zeigt 2x2 Karten
- Tabs sind verständlich und nicht überladen
- mobile Ansicht priorisiert Chat
- Deep Dive hat klare Rückkehr zur Analyse

---

# 22. Testfälle für Umsetzung

## 22.1 Testfall Salzwasser unscharf

Input:

```text
Ich brauche eine Dichtung für Salzwasser bei 80 Grad.
```

Erwartung:

- DOMAIN_INQUIRY erkannt
- Medium = Salzwasser
- Temperatur = 80 °C
- Anlage fehlt
- nächste Frage fragt nach Anlage/Bewegungsart
- Cockpit zeigt Medium-Hinweis
- Readiness Level 1 oder 2

## 22.2 Testfall Rührwerk

Input:

```text
Es geht um ein Rührwerk in einem Behälter.
```

Erwartung:

- asset_type = Rührwerk
- mögliche rotierende Welle inferred, nicht confirmed
- Risiken: Exzentrizität, Behälterdruck, Reinigung möglich als Hinweise
- nächste Frage nach Dichtstelle/Bewegung oder Medium

## 22.3 Testfall PTFE vs. FKM

Input:

```text
Wäre PTFE besser als FKM?
```

Erwartung:

- KNOWLEDGE_QUERY oder DEEP_DIVE, falls Case vorhanden
- Werkstoff-Tab kann aktiviert werden
- keine finale Auswahl
- Frage nach Medium/Temperatur/Bewegung

## 22.4 Testfall Pumpe Ethanol

Input:

```text
Ich suche eine Dichtung für eine Pumpe mit Ethanol bei 150 °C und 10 bar.
```

Erwartung:

- asset_type = Pumpe
- Medium = Ethanol
- Temperatur = 150 °C
- Druck = 10 bar
- Dichtungstyp-Richtung: Gleitringdichtung möglich / RWDR nicht vorschnell
- Sicherheits-/Dampf-/ATEX-Hinweise nur vorsichtig und nicht final
- Readiness abhängig von Drehzahl, Welle, Pumpentyp, Einbauraum

## 22.5 Testfall Getriebe Öl

Input:

```text
Wir haben Ölverlust an einem Getriebeausgang.
```

Erwartung:

- asset_type = Getriebe
- function = Ölabdichtung / Schmutzschutz möglich
- nächste Frage nach Welle/Drehzahl/Wellendurchmesser/Einbausituation
- Medium = Getriebeöl inferred, unbestätigt

---

# 23. Umsetzungsreihenfolge

## Phase A: Konzept in SSoT überführen

- v0.3 als Konzeptdokument speichern
- AGENTS.md / DESIGN.md Referenz prüfen
- Begriffe mit vorhandener Architektur harmonisieren

## Phase B: Frontend-Projektion definieren

- Cockpit Projection Contract erstellen
- 2x2-Karten-Schema definieren
- Tab-State definieren
- Deep-Dive-State definieren

## Phase C: Backend-State erweitern

- Application Context Slice
- Seal Location & Motion Slice
- Medium Context Slice
- Readiness Slice
- Risk Slice
- Provenance-Felder

## Phase D: LLM-Kommunikationslogik

- Systemprompt/Tonalitätsregeln
- Best-Next-Question Service
- Output-Klassen
- Deep-Dive Templates

## Phase E: Deterministische Services

- Readiness Evaluator
- Risk Evaluator
- Calculation Registry
- Application Pattern Hints
- Case invalidation rules

## Phase F: RFQ Report

- Report Schema
- Report Projection
- PDF-/Export später
- Herstelleransicht später

## Phase G: Matching

- Capability Model
- Must-have Filter
- Problem-first Ranking
- Sponsor-neutrality guard

---

# 24. Finaler Leitsatz v0.3

> SeaLAI ist eine dialogische Diagnose- und Qualifizierungsplattform für Dichtungstechnik. Das System beginnt beim Anlagenkontext, führt den Nutzer über ein empathisches und professionelles LLM-Gespräch durch die technische Klärung, visualisiert den Fall in einem 50/50-Cockpit mit 2x2-Analyse und fallbezogenen Intelligence-Tabs und erzeugt daraus eine strukturierte, herstellerreife Anfrage. Das LLM verantwortet die Kommunikation; Case-State, Regeln, Berechnungen, Risiken und Readiness sichern die technische Autorität. SeaLAI empfiehlt nicht vorschnell, sondern macht Dichtungssituationen verständlich, prüfbar und anfragereif.

