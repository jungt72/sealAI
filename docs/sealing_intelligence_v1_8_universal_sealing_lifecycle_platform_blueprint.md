# sealing | Intelligence V1.8 — Universal Sealing Lifecycle Platform

**Architecture & Orchestration Blueprint (verbindliche Schicht über V1.6/V1.7)**

**Stand:** 2026-06-06
**Produkt:** sealing | Intelligence / sealingAI
**Produktidentität:** Engineering-Intelligence-Plattform für die **gesamte industrielle Dichtungstechnik** — über den **gesamten Lebenszyklus** einer Dichtstelle
**Erster produktionsreifer Domain Pack:** Radialwellendichtringe (RWDR)
**Zielgruppe dieses Dokuments:** Architektur-Review und **Claude Code** (Audit-first im bestehenden Monorepo; Read-only-Audit-Auftrag in §10.1, Prüf-Checkliste in Anhang A)

---

## Verhältnis zu V1.6 und V1.7

V1.8 ersetzt weder V1.6 noch V1.7 — es verdichtet und erweitert:

```text
V1.6  = operative Contracts (Mode-Contracts, Schemas, UX-Regeln, Golden Conversations) — bleiben in Kraft.
V1.7  = Architektur-Schicht (Universal Core/Domain Pack, Wissensarchitektur, Security P0,
        Sequenzierung) — bleibt in Kraft, soweit V1.8 nichts ausdrücklich ändert.
V1.8  = (a) macht das Orchestrierungsmodell VERBINDLICH (§7 ersetzt V1.7 §7),
        (b) erweitert das Produkt um die zweite Lebenszyklus-Hälfte (Solution Companion),
        (c) korrigiert die Moat-Mechanik (Outcome-Records),
        (d) ergänzt Modes, Schnellpfad, Betriebsfenster, Persona-Konfiguration,
        (e) ordnet die Prioritäten neu.
Konfliktregel: V1.8 > V1.7 > V1.6 auf Architektur-/Orchestrierungsebene.
V1.6 gewinnt auf Contract-Ebene, soweit V1.8 §5/§6 nichts Abweichendes definiert.
```

### Delta-Übersicht V1.7 → V1.8

```text
Produktschnitt        V1.7: endet an der RFQ-Übergabe
                      V1.8: begleitet die Dichtstelle bis Betrieb/Ausfall (Lifecycle)
Agentenmodell         V1.7: Liste von ~23 Agenten, Implementierung offen
                      V1.8: Module + Proposal-Interface + Call-Budget 3–5/Turn, verbindlich
Orchestrierung        V1.7: implizit ("Router · State Gate · Dirty Scheduler")
                      V1.8: LangGraph als constrained runtime, Turn-DAG, Topologie fixiert
Zustand               V1.7: Event-Sourcing benannt, Ausführungszustand ungeregelt
                      V1.8: zwei Zustandswelten strikt getrennt (Event Store vs. Checkpointer)
Jinja2                V1.7: ein Satz in der Binding Rule
                      V1.8: zwei Rollen mit verbindlichen Konventionen
Wissens-Moat          V1.7: Herstellerfeedback zur RFQ-Qualität
                      V1.8: + Feld-Outcome-Records als dritte, wertvollste Quelle
Modes                 V1.8 neu: standard_part_fast_path · solution_explanation ·
                      installation_guidance · operation_qna · incident_intake
Cockpit               V1.8 neu: Betriebsfenster-Projektion (deterministisch)
Datenmodell           V1.8 neu: Lifecycle-Status · SolutionProfile · Outcome-Record ·
                      Multi-Positionen-Vorsorge · Origins datasheet_extracted/outcome_observation
Persona               V1.7: implizit Endanwender
                      V1.8: konfigurierbar (end_user · distributor_inside_sales · oem_engineering)
```

---

## 0. Executive Summary

sealingAI bleibt ein **case-aware Engineering-Intelligence-Workspace für Dichtungstechnik**: kein Chatbot, kein Katalog, kein Konfigurator, kein automatisches Auslegungssystem, keine finale Freigabestelle.

V1.8 erweitert das Produkt um die Erkenntnis aus der Branchenanalyse: Die teuersten Pains der Dichtungstechnik liegen **nach** der Anfrage — Einbaufehler als dominante vermeidbare Ausfallursache, Wiederholausfälle ohne Asset-Gedächtnis, Wissensabfluss durch Renteneintritte, und die Frage „Was habe ich da verbaut, wo sind die Grenzen, warum leckt es schon wieder?". Hersteller-Konfiguratoren beginnen erst, wenn der Nutzer seine Parameter bereits kennt, und enden im eigenen Katalog. sealingAI besetzt beide Lücken davor und danach:

```text
Die Anbahnungshälfte (V1.6/V1.7): chaotische Situation → strukturierter Case → herstellerbewertbare RFQ.
Die Begleithälfte (V1.8 neu):     Angebot/Datenblatt → SolutionProfile → Betriebsfenster →
                                  Einbauführung → Betrieb → Soll-Ist-Diagnose → Outcome-Record.
Der Nutzer kann mit SEINER Lösung chatten — geerdet auf Datenblatt, Herstellerantwort und Case,
niemals auf Vermutung.
```

Gleichzeitig macht V1.8 das Orchestrierungsmodell verbindlich: ein deterministischer Turn-DAG mit eingebetteten, schema-gebundenen LLM-Entscheidungspunkten. Module schlagen vor; das State Gate schreibt; Jinja2 strukturiert; Berechnungen sind Code.

```text
Anfragen passieren ein- bis zweimal im Jahr pro Maschine.
Verstehen, Einbauen und Betreiben sind Daueraufgaben.
Wer die zweite Hälfte besitzt, besitzt die Beziehung — und die Outcome-Daten, die kein Hersteller hat.
```

---

## 1. Leitprinzipien

### 1.1 Produktidentität

```text
sealingAI ist die Intelligence-Plattform für industrielle Dichtungstechnik.
Sie erkennt Dichtungstyp, Anwendung, Medium, Betriebsbedingungen, Risiken und fehlende Parameter,
erzeugt daraus prüfbare technische Entscheidungs- und Anfrageunterlagen —
und begleitet die gewählte Lösung über Einbau und Betrieb bis zur Ausfallanalyse.
```

### 1.2 Die zwei Breiten (unverändert aus V1.7)

```text
Plattform-Breite  → einmal bauen, für alle Dichtungstypen, von Anfang an.
Domänen-Tiefe     → sequenziell bauen, ein Dichtungstyp nach dem anderen.
```

### 1.3 Die zwei Hälften des Lebenszyklus (neue Bauregel)

```text
Anbahnung (inquiring → rfq_sent → quoted) und Begleitung (solution_selected → installed →
in_operation → incident → replaced/closed) teilen sich EIN Case-Modell, EIN State Gate,
EINE Envelope-Mechanik. Die Begleithälfte ist kein zweites Produkt und keine zweite Pipeline —
sie ist derselbe Case in späteren Zuständen.
```

### 1.4 Safety-Formel (erweitert)

```text
sealingAI entscheidet nicht die Dichtung.
sealingAI macht die Dichtungssituation verständlich, strukturiert und herstellerbewertbar —
und macht die gewählte Lösung verstehbar, einbaubar nach Herstellerangabe und diagnostizierbar.
Erklärung ist niemals Freigabe. „Laut Datenblatt" ist Pflichtrahmen jeder Lösungsaussage.
Der Hersteller bzw. der verantwortliche Ingenieur bewertet final.
```

### 1.5 Binding Product Rule (erweitert)

```text
Der Chat führt.
Das Cockpit dokumentiert.
Das Pocket Cockpit verdichtet.
Das Sheet strukturiert.
Knowledge erklärt.
Der RFQ-Brief übergibt.
Das Betriebsfenster vergleicht.
Das State Gate entscheidet.
Module schlagen vor — niemals schreiben sie.
Jinja2 kontrolliert Output-Struktur, nicht Formulierungsvielfalt.
RAG belegt, schreibt aber keine Case-Wahrheit.
Berechnungen sind Code, niemals LLM.
Der Hersteller bewertet final.
```

### 1.6 Workflow, nicht Agent (neuer Grundsatz)

```text
sealingAI ist ein Workflow-System mit eingebetteten LLM-Entscheidungspunkten —
kein autonomes Agentensystem.
Der Standard-Turn ist ein DAG. Schleifen existieren nur über den Nutzer (nächster Turn).
Es gibt keinen Supervisor-LLM, keine Subagenten, keine Agent-zu-Agent-Übergaben.
Die Zerlegung des Dichtungsfalls ist bekannt und deterministisch — sie heißt Dirty Scheduler.
```

### 1.7 Diagnose statt Ausführung (erweitert)

```text
Anbahnung:  Chatbot redet über den Fall. sealingAI strukturiert den Fall sichtbar mit
            und stellt nur die nächste wichtige Frage.
Begleitung: Mit verbauter Lösung wird Diagnose zum Soll-Ist-Vergleich
            (Anforderungsprofil vs. Lösungslimits) statt zum Kaltstart.
```

### 1.8 Implementierungsformel (unverändert)

```text
Master Blueprint ≠ Big-Bang-Implementation.
Audit-first → kleinster Patch → Tests → nächster Patch.
Bestehende Strukturen bevorzugen. Keine parallele Architektur erfinden.
```

---

## 2. Schichten-Referenzarchitektur

Das 7-Schichten-Modell aus V1.7 §2 bleibt in Kraft. V1.8 ergänzt die horizontale Dimension:

```text
Lebenszyklus (horizontal über alle Schichten):
inquiring → rfq_sent → quoted → solution_selected → installed → in_operation
                                                        │              │
                                                        └── incident ──┘ → replaced/closed
```

Bewertungslegende aktualisiert:

```text
grün : Engine, Routing, State Gate, Projektion, Streaming — strukturell vorhanden, verdrahten.
gelb : Wissensschicht (Kaltstart) UND Outcome-Loop (neu) — die beiden teuren, bewusst
       aufzubauenden Schichten. Der Outcome-Loop ist die Korrektur der Disanalogie zu
       Legal-Plattformen: sealingAI bekommt keine Dokumentkorpora geschenkt — es muss
       seine Wahrheit aus Fällen, Datenblättern und Feld-Outcomes selbst akkumulieren.
grau : LLM-Fundament und Security/Tenant (P0).
```

---

## 3. Universal Sealing Core vs. Domain Pack

### 3.1 Universal Sealing Core — Ergänzungen (typ-agnostisch)

Zusätzlich zu V1.7 §3.1 stellt der Core bereit:

```text
- Case-Lifecycle-Status als Event-Folge (Zustandsmaschine, §6.3)
- SolutionProfile: zweites Envelope-Bündel je Case (Kandidat/Angebot/gewählt/verbaut), §6.4
- Datenblatt-/Angebots-Ingestion: document_analysis → SolutionProfile-Kandidaten
  (pending_confirmation), Quelle+Seite als Pflicht-Herkunft
- Operating-Window-Check: deterministischer Vergleich Anforderungsprofil vs. Lösungslimits
  (reiner Code; Kompatibilitäts-RICHTUNG aus der Querschnitts-Wissensschicht)
- Outcome-Events und Outcome-Records (§6.5)
- Standardteil-Schnellpfad-Mechanik: generischer Maß-/Normabgleich; die Normtabellen
  selbst liefert der Pack
- Multi-Positionen-Vorsorge im Schema (§6.6) — Ausbau erst P3, Blockade-Verbot sofort
- Persona-Konfiguration (end_user · distributor_inside_sales · oem_engineering):
  steuert Frageton, Einheiten-Defaults, RFQ-Adressierung — keine eigene Pipeline
```

### 3.2 Domain Pack Contract V2 (Interface)

Erweitert V1.7 §3.3 um Orchestrierungs- und Lifecycle-Hooks. Kein Umbau am Core für neue Typen.

```python
from typing import Protocol, Sequence

class DomainPack(Protocol):
    pack_id: str
    display_name: str
    classification_signals: Sequence[str]

    # V1.7 (unverändert)
    def required_fields(self) -> list[str]: ...
    def optional_fields(self) -> list[str]: ...
    def parameter_schema(self) -> dict: ...
    def calculations(self, case) -> list["ComputedValue"]: ...        # PURE CODE
    def failure_modes(self, case) -> list["ReviewFlag"]: ...
    def question_policy(self, case) -> "PendingQuestion | None": ...
    def risk_flags(self, case) -> list["ReviewFlag"]: ...
    def rfq_template_id(self) -> str: ...

    # V1.8 neu — Orchestrierung
    def dirty_rules(self) -> dict[str, set[str]]: ...                 # Pack-Trigger-Tabelle
    def modules(self) -> list["AnalysisModule"]: ...                  # Pack-Module (CODE/LLM/HYBRID)
    def prompt_partials(self) -> dict[str, str]: ...                  # Jinja2-Blöcke für Core-Templates

    # V1.8 neu — Lifecycle
    def standard_part_tables(self) -> "StandardPartIndex | None": ... # z. B. DIN 3760/3761-Maßreihen
    def solution_limit_schema(self) -> dict: ...                      # typisierte Limit-Felder fürs Betriebsfenster
    def installation_knowledge(self) -> "InstallationGuide": ...      # Schrittwissen je Typ
    def outcome_taxonomy(self) -> list["OutcomePattern"]: ...         # Ausfallbild-Taxonomie je Typ
```

### 3.3 Repo-Zielstruktur (Vorschlag — Claude Code auditiert zuerst, ob Äquivalente existieren)

```text
core/
  sealing_case/    model.py · state.py · lifecycle.py · solution.py · evidence.py · rfq.py · risk.py
  analysis/        modules.py (AnalysisModule, Proposal) · operating_window.py (CODE)
  routing/         router.py · mode_detection.py · classification.py
  projection/      cockpit.py · pocket_cockpit.py · operating_window_view.py
  persistence/     events.py · snapshot.py · idempotency.py · outcome.py

orchestration/     graph.py (Turn-DAG) · dirty_rules.py · streaming.py · tiers.py
                   # NUR Verdrahtung — Nodes ≤ ~15 Zeilen, Logik in core/

prompts/
  base/            system_core.j2 · case_header.j2 · solution_header.j2
  modes/ modules/ compose/

domains/
  registry.py
  rwdr/            schema.py · classify.py · calculations.py · failure_modes.py · questions.py ·
                   standard_parts.py · installation.py · outcome_taxonomy.py · rfq_template.j2

knowledge/
  cross_cutting/   materials.py · media.py · standards.py
  domain/rwdr/
  outcomes/        records.py · aggregation.py (Governance §8)

frontend/
  cockpit/         UniversalCaseCockpit.tsx · ParameterGrid.tsx · EvidenceChips.tsx ·
                   OperatingWindow.tsx · SolutionPanel.tsx
  pocket/          PocketCockpit.tsx
```

**Anti-Pattern (unverändert + erweitert):** keine RWDR-Logik in der Plumbing; kein zweites UI je Typ; **kein Graph oder Node je Dichtungstyp**; **keine Lifecycle-Parallelpipeline**.

### 3.4 RWDR Domain Pack V1.8 (Ergänzungen zum ersten Pack)

```text
standard_part_tables()    : DIN-3760/3761-Maßreihen + Werkstoffklassen → Bezeichnungs-Schnellpfad
solution_limit_schema()   : temp_min/max_continuous · temp_peak_short · v_max je Werkstoff ·
                            p_max an Dichtkante · dry_run_capable · Medienklassen-Eignung (Richtung)
installation_knowledge()  : Wellenvorbereitung (Rauheit, Härte, Fase, drallfreie Lauffläche) ·
                            Einbaurichtung/Werkzeug · Schmierung ja/nein/womit · Sauberkeit ·
                            Anlaufhinweise — als Schrittwissen mit Herstellerangaben-Rahmen
outcome_taxonomy()        : Einlaufrille · Lippenverhärtung/-verschleiß · thermische Schädigung ·
                            Mediumsangriff/Quellung · Montageschaden (Schnitt/Umklappen) ·
                            Trockenlaufspur · Drall-Leckage
```

### 3.5 Rule of Three (unverändert)

Keine spekulative Abstraktion über RWDR hinaus; gemeinsame Abstraktionen werden bei Pack #2 extrahiert. Gilt ausdrücklich auch für Lifecycle-Bausteine (z. B. `InstallationGuide` erst generalisieren, wenn O-Ring-Einbauwissen vorliegt).

---

## 4. Wissensarchitektur (Moat — korrigierte Mechanik)

### 4.1 Querschnittliches Wissen (unverändert aus V1.7 §4.1, ab Tag 1 breit)

Zusatzeinordnung: Statische Material-/Medien-/Normtabellen sind **Table Stakes** (öffentlich verfügbar, jeder Hersteller hat sie). Sie sind notwendig, aber nicht der Moat.

### 4.2 Domänenspezifisches Wissen (erweitert)

```text
+ Einbauwissen je Typ (installation_knowledge)
+ Ausfallbild-Bibliothek je Typ, verknüpft mit outcome_taxonomy
```

### 4.3 Outcome-Records — die dritte und wertvollste Wissensquelle (neu)

```text
Definition: strukturiertes Tupel {Anforderungsprofil, gewählte Lösung, Einbaudatum,
            Laufzeit, Ausfallbild (Taxonomie), Verdachtsursache, Evidenz (Foto)}
Entstehung: installed-Event + incident_intake/replaced-Event (§5/§6)
Wirkung:    speist failure_modes()-Bibliothek · kalibriert risk_flag-Schwellen ·
            schärft Richtwerte der Querschnittsschicht · priorisiert Next-Best-Questions
Alleinstellung: Cross-Hersteller-Felddaten je Anwendungsprofil. Hersteller sehen nur
            reklamierte Ausfälle der EIGENEN Produkte. Diesen Datensatz hat niemand.
Governance: Roh-Outcomes gehören dem Tenant. In die globale Schicht wandern ausschließlich
            aggregierte, anonymisierte Richtwerte ab definierter Mindestmenge (§8).
```

### 4.4 RAG-Contract (erweitert)

```text
- Single-Collection-Retrieval, Payload-Partitionierung; Pflicht-Payload:
  Quelle · Typ · Norm · Gültigkeit · Domäne/Querschnitt-Flag · Sichtbarkeit (global | tenant:<id>)
- Neuer Scope solution_docs: Datenblätter/Angebote des Cases als tenant-gescopte
  Retrieval-Quelle (Pflicht-Payload: Dokument-ID, Seite, Gültigkeit)
- Scoped Retrieval je Mode/Tier (kein Full-Retrieval auf Tier 0/1)
- Filter werden SERVERSEITIG im Retriever konstruiert — niemals aus LLM-Output
- RAG erzeugt ausschließlich rag_supported_note — niemals confirmed facts, niemals Freigabe
- Source-Display mit Herkunfts-/Status-Chips im Cockpit (inkl. „Datenblatt S. n")
```

### 4.5 Kompoundierung — zwei Schleifen

```text
Schleife 1 (V1.7, bleibt):  Hersteller bewertet RFQ → strukturiertes Feedback zur Anfragequalität
                            → verbessert Fragenlogik und RFQ-Vollständigkeit.
Schleife 2 (V1.8, neu):     Lösung wird verbaut und betrieben → Outcome-Record
                            → verbessert Ausfallbibliothek, Risiko-Flags, Richtwerte.
Schleife 1 optimiert die Anfrage. Schleife 2 optimiert das Urteil. Erst beide zusammen
lösen die Moat-These ein.
```

---

## 5. Produkt- und UX-Contracts

V1.6-Contracts (Modes, Beispiele, Golden Conversations) bleiben vollständig in Kraft. V1.8 ergänzt:

### 5.1 Oberflächenrollen (erweitert)

```text
Chat            führt; in der Begleithälfte beantwortet er Lösungsfragen geerdet („laut Datenblatt …").
Desktop-Cockpit dokumentiert; enthält neu das Betriebsfenster und das Solution-Panel.
Pocket Cockpit  verdichtet; in_operation-Zustand: recognized · solution · next_check · status.
Sheet           strukturierte Eingabe, unverändert durch das State Gate.
Knowledge       erklärt; lösungsbezogen nur mit Quelle.
RFQ-Brief       übergibt, unverändert.
Betriebsfenster vergleicht Anforderung und Lösungslimit, Feld für Feld — deterministisch.
```

### 5.2 Mobile-First Oily-Hands Contract (unverändert)

Zusatz-North-Star Begleithälfte: aus „verbaut + sifft wieder" in < 4 min eine Soll-Ist-Hypothese mit Foto-/Messführung oder ein vorbereiteter Reklamations-/Anfragefall.

### 5.3 Mode-Übersicht (typ-agnostisch, erweitert)

Bestehende Modes aus V1.6/V1.7 §5.3 unverändert, plus:

```text
standard_part_fast_path   Maß-/Norm-Treffer → Bezeichnung + Kompakt-Checkliste in < 60 s;
                          Abzweig „voller Case/RFQ" jederzeit. Kein Bypass am State Gate vorbei.
solution_explanation      Warum-/Was-wäre-wenn-Fragen gegen SolutionProfile + Case +
                          Querschnittswissen. Unbeantwortbares → vorgeschlagene Herstellerfrage
                          (ManufacturerQuestionAgent, zweiter Einsatzort), niemals Vermutung.
installation_guidance     Schrittführung Einbau aus Pack-Wissen + Datenblatt; jeder Schritt
                          per Chip quittierbar → dokumentiert im Case (Asset-Gedächtnis).
operation_qna             „Worauf achten?" / „Wie kündigt sich Ausfall an?" — Ausfallbilder
                          des Packs, bezogen auf DIESE Lösung.
incident_intake           Leckage am verbauten Teil: re-used leakage_diagnosis mit
                          SolutionProfile als Referenz (Soll-Ist) → erzeugt Outcome-Event.
```

### 5.4 No-Go-Phrasen (erweitert)

V1.6/V1.7-Liste unverändert, plus für die Begleithälfte:

```text
- jede Eignungs-/Freigabeformulierung zur verbauten Lösung („ist geeignet", „können Sie bedenkenlos")
- Lösungsaussagen ohne Quellrahmen („laut Datenblatt/Herstellerangabe/Norm …" ist Pflicht)
- Ferndiagnose als Gewissheit („die Ursache ist") statt Hypothese mit Prüfschritt
```

### 5.5 RFQ One-Pager Contract (unverändert + Vorsorge)

Readiness-Stufen, Mindestkern, offene Punkte, Snapshot je case_revision unverändert. Schema-Vorsorge: Das Template iteriert über `positions[]` (Default: eine Position) — Mehrpositionen-Ausbau erst P3.

### 5.6 Operating-Window-Contract (neu)

```text
Erzeugung   : 100 % deterministisch (OperatingWindowCheck, Code). Kein LLM in der Berechnung.
Inhalt      : je Limit-Feld → Anforderung (Case, mit Status) · Limit (Solution, mit Quelle) ·
              Marge · Flag (✓ | ⚠ klären | ⚠ kritisch).
Richtung    : Medienverträglichkeit als RICHTUNG aus der Querschnittsschicht, nie als Freigabe.
Interaktion : jede ⚠-Zeile erzeugt ein review_flag und öffnet per Tap den Lösungs-Chat
              mit vorbereiteter Frage.
Degradation : fehlende Limits → Zeile „Limit unbekannt" + vorgeschlagene Herstellerfrage,
              niemals stilles Auslassen.
```

### 5.7 Standardteil-Schnellpfad-Contract (neu)

```text
Trigger     : Klassifikation + Maße treffen eine Pack-Normtabelle (z. B. DIN 3760 BA 35×52×7).
Leistung    : Standardbezeichnung + Werkstoffklassen-Hinweis + Kompakt-Checkliste
              (Medium ok? Welle ok? Schutzlippe? Temperatur?) in < 60 s.
Grenze      : Checkliste ist Erklärwissen; jede Unsicherheit → Abzweig voller Case.
Begründung  : Over-Processing von Katalogware verletzt das eigene Kriterium
              „strikt besser als ChatGPT + Google" in der Gegenrichtung.
```

### 5.8 Persona-Konfiguration (neu)

```text
end_user                 : Du-/Sie-Ton nach Markt, SI-Einheiten, RFQ im eigenen Namen.
distributor_inside_sales : Triage-optimiert (P-H1–P-H3): schnelle Rückfragenlisten,
                           RFQ „im Namen des Endkunden", Fall-Weiterleitung.
oem_engineering          : Normen-/Doku-Schwerpunkt, Toleranz-/Nutkontext.
Persona ändert Ton, Defaults und Adressierung — NIEMALS Pipeline, Gate oder Safety-Formel.
GTM-Entscheidung (Erstkunde Händler-Innendienst vs. Endanwender) ist offen und gehört
explizit getroffen — sie bestimmt Golden-Conversation-Prioritäten, nicht die Architektur.
```

---

## 6. Daten- und Zustandsmodell (Core, typ-agnostisch)

### 6.1 Field Envelope (unverändert aus V1.6/V1.7)

### 6.2 Status / Origin (erweitert)

```text
status : unverändert (confirmed · pending_confirmation · explicitly_unknown · rejected ·
         conflicting · not_applicable · visual_candidate · sketch_candidate ·
         rag_supported_note · calculated · agent_inferred_review_flag)
origin : + datasheet_extracted    (Quelle: Dokument-ID + Seite, Pflicht)
         + outcome_observation    (Quelle: Outcome-Event)
         (bestehende Origins inkl. manufacturer_response unverändert)
```

### 6.3 Case-Lifecycle (neu, Event-basiert)

```text
Zustände   : inquiring · rfq_sent · quoted · solution_selected · installed · in_operation ·
             incident · replaced · closed
Mechanik   : Statusübergänge sind Case Events im Event Store (V1.6-Mechanik unverändert).
Wirkung    : Lifecycle-Status ist Trigger-Dimension des Dirty Schedulers (§7.5) und
             Sichtbarkeits-Dimension der Modes (§5.3).
```

### 6.4 SolutionProfile (neu)

```json
{
  "solution_id": "sol_01",
  "label": "Angebot Hersteller A, Pos. 1",
  "state": "selected",
  "fields": [
    { "field": "material", "value": "FKM", "status": "confirmed",
      "origin": "datasheet_extracted", "source_doc": "doc_17", "source_page": 2 },
    { "field": "temp_max_continuous_c", "value": 150, "status": "confirmed",
      "origin": "datasheet_extracted", "source_doc": "doc_17", "source_page": 2 },
    { "field": "dry_run_capable", "value": false, "status": "pending_confirmation",
      "origin": "manufacturer_response" }
  ]
}
```

```text
Regeln: gleiche Envelope-/Status-/Origin-Mechanik wie das Anforderungsprofil; Befüllung über
document_analysis (Kandidaten = pending_confirmation) und manufacturer_response; mehrere
SolutionProfiles je Case erlaubt (technischer Vergleich, KEIN Ranking als Empfehlung).
```

### 6.5 Outcome-Record (neu)

```json
{
  "case_id": "…", "tenant_id": "…", "position_id": "pos_1",
  "solution_ref": "sol_01",
  "installed_at": "2026-03-02", "runtime_hours_estimate": 2100,
  "event": "incident",
  "outcome_pattern": "lip_hardening_thermal",
  "suspected_cause": "temp_peaks_above_continuous_limit",
  "evidence_refs": ["photo_88"],
  "confidence": "medium"
}
```

### 6.6 Multi-Positionen-Vorsorge (neu, nur Schema)

```text
Case.positions[] : optionale Liste von Dichtstellen-Positionen; Default genau eine.
Pflicht heute    : kein Modul, keine Projektion, kein Template darf hart „genau 1" annehmen.
Ausbau           : P3 (Asset-Klammer Maschine → Dichtstellen → Cases).
```

### 6.7 Conflict Envelope, Degradation, Multi-Output Envelope (unverändert)

```text
AssistantTurnEnvelope = ChatReply + CockpitPatch + PocketCockpitPatch + CaseUnderstandingPatch +
                        RFQBriefPatch + OperatingWindowPatch(optional) + ActionChips +
                        PendingQuestion + Trace
```

---

## 7. Orchestrierungsmodell (verbindlich — ersetzt V1.7 §7)

### 7.1 Framework-Entscheidung

```text
LangGraph 1.x als CONSTRAINED RUNTIME — genutzt für genau vier Dinge:
  Durable Execution je Turn · Multi-Mode-Streaming (messages/updates/custom) ·
  interrupt() für Human Escalation · Send-API + Reducer für parallelen Fan-out.
NICHT genutzt: LangChain-Prompt-/Chain-/Hub-Abstraktionen und Agent-Prebuilts im Core-Turn.
Prompts = Jinja2 im Repo. Schemas = Pydantic. Modellzugriff = dünner eigener Adapter.

Disziplinregel (Exit-Strategie): Jeder Graph-Node ist ≤ ~15 Zeilen und ruft eine pure
Funktion aus core/ auf. 90 % der Tests treffen core/ ohne Graph-Runtime. Framework-Austausch
muss ein Orchestrierungs-Refactor bleiben, nie ein Produkt-Rewrite.
```

### 7.2 Zwei Zustandswelten (strikt getrennt)

```text
┌──────────────────────────────┬──────────────────────────────────────────┐
│ Case-Wahrheit (Business)      │ Turn-Ausführung (Execution)              │
├──────────────────────────────┼──────────────────────────────────────────┤
│ Postgres Event Store:         │ LangGraph-Checkpointer (Postgres):       │
│ Case Events (append-only),    │ Node-Zustand EINES Turns,                │
│ Snapshots, RFQ-Snapshots,     │ Interrupt-Punkte, Resume-Cursor          │
│ Outcome-Records,              │                                          │
│ Idempotency-Keys, Tenant-Scope│                                          │
│ Lebensdauer: dauerhaft        │ Lebensdauer: Turn + Debug-Retention (TTL)│
│ Einziger Schreiber: State Gate│ Schreiber: Runtime                       │
│ Quelle für Projektion & RFQ   │ NIE Quelle für Geschäftsdaten            │
└──────────────────────────────┴──────────────────────────────────────────┘
Turn-Protokoll: ingest lädt Snapshot → Graph akkumuliert PROPOSALS →
state_gate committet Events atomar → Projektionen aus dem NEUEN Snapshot.
thread_id = case_id:turn_id. Retention-Job räumt Checkpoints nach N Tagen.
```

### 7.3 Turn-Graph (Topologie, verbindlich)

```text
user turn ─► ingest ─► route ─► [Tier 0: smalltalk/ui_help/boundary/fast_path-Kurzform] ─► compose_fast ─► END
(SSE: ack    (Code)    (1 LLM,
 <100 ms)              fast, structured)
                          │ case path
                          ▼
                  state_gate_intake     (Code: Kandidaten validieren, Konflikte, Pending-Slot)
                          ▼
                  dirty_scheduler       (Code: Feld×Lifecycle → Modul-Set → Send-Fan-out)
              ┌───────────┼──────────────────────┬───────────────┐
              ▼           ▼                      ▼               ▼
        cross_impact   calc_engine /        pack_module      rag_retrieve
        (LLM)          operating_window     (LLM o. Code)    (Code, scoped)
                       (PURE CODE)
              └───────────┴──────────────────────┴───────────────┘   ein Superstep,
                          ▼   Reducer: list-append auf proposals      Branch-Timeouts,
                  state_gate_merge      (Code: Proposals → Events, COMMIT;                weiche
                          │              Eskalations-Check → ggf. interrupt())            Degradation
                          ▼
                  question_policy       (Pack-Code; optional 1 Fast-LLM für Formulierung)
                          ▼
                  compose               (1 LLM, schema-gebunden, streamt; No-Go-Linter als Post-Check)
                          ▼
                  project_and_persist   (Code: Patches als Diffs, Trace, Envelope final)
                          ▼
                         END
Eigenschaften: DAG pro Turn (kein Recursion-Limit nötig) · LLM-Budget Tier 1: 3–5 Calls,
Tier 0: 0–1 · interrupt() ausschließlich am state_gate_merge bei Risiko/Safety/Compliance.
Hintergrund-Graphen (Tier 2): visual_evidence · sketch_to_case · document_analysis · rfq ·
incident-Analyse — Ergebnisse treffen als spätere Patches ein.
```

### 7.4 Module statt Agenten

Die Agentenliste aus V1.7 §7.1/7.2 ist ein **fachliches Verantwortungsregister**, keine Deployment-Liste. Implementierung:

```python
class AnalysisModule(Protocol):
    module_id: str
    triggers: set[str]                       # Felder/Ereignisse/Lifecycle-Zustände
    tier: Literal[0, 1, 2]
    def run(self, case, ctx, rag=None) -> list["Proposal"]: ...

class Proposal(BaseModel):
    module: str
    kind: Literal["field_candidate", "review_flag", "rag_note",
                  "calculated_value", "question_suggestion", "conflict_hint",
                  "outcome_hypothesis"]
    field: str | None
    value: Any | None
    status_suggestion: FieldStatus
    confidence: Literal["low", "medium", "high"]
    rationale_short: str                     # ≤ 200 Zeichen
    evidence_refs: list[str] = []
```

```text
Drei Modularten:
  CODE   : CalculationEngine · OperatingWindowCheck · SheetValidation · Readiness-Check ·
           No-Go-Linter · Konfliktdetektion · Pocket-Projektion
  LLM    : cross_impact (konsolidiert: Medium+Application+OperatingCondition+Material) ·
           pack_impact (konsolidiert je Pack) · adversarial (DevilsAdvocate, bewusst separat) ·
           regulatory (nur bei Norm-Feldern) · solution_explainer · rfq_quality ·
           manufacturer_question · visual_evidence (Vision) · knowledge_explainer
  HYBRID : measurement_guidance · installation_guidance (Schrittwissen Code, Formulierung LLM)

Eisernes Gesetz: Alles Berechenbare ist Code. „calculated" ist nur als deterministisches
Ergebnis glaubwürdig.
Konsolidierungsregel: Erst konsolidieren, dann per Eval splitten — ein Modul wird nur dann
eigener LLM-Call, wenn Golden-Evals Interferenz im Sammel-Prompt nachweisen.
Jeder LLM-Call: structured output (Pydantic-validiert), genau EIN Retry mit kompaktierter
Fehlermeldung. Das State Gate ist der alleinige Übersetzer Proposal → Case Event.
```

### 7.5 Dirty Scheduler (deterministisch)

```text
Mechanik : pure Funktion compute_modules(dirty_set, lifecycle_status, pack) → Modul-Set;
           Fan-out via Send; jeder Branch erhält slim_ctx (nur themenrelevante Envelopes +
           Case-Kurzkopf), nie den ganzen Case.
Beispiele (Core ∪ Pack):
  medium changed                 → cross_impact, rag_media
  speed_rpm changed              → cross_impact, calc_engine (Pack)
  solution_field changed         → operating_window_check (CODE), solution_explainer-Scope
  lifecycle → installed          → installation_guidance verfügbar
  lifecycle = in_operation + Leckagesignal → incident_intake-Pfad (Soll-Ist), failure_modes(Pack)
  photo + mobile + kurz          → mobile_triage, visual_evidence@tier2, pocket_projection
  event: rfq_requested           → rfq-Hintergrundgraph
Fehlerbild : Branch-Timeout/Fehler → review_flag „Analyse X nicht verfügbar" statt Turn-Abbruch.
```

### 7.6 Tier-Modell (Latenzklassen)

```text
Tier 0 (<1 s, sync)        : smalltalk · ui_help · pending_slot_micro · boundary ·
                             standard_part_fast_path-Kurzantwort. Fast-Model oder Code.
Tier 1 (1–6 s, sync+SSE)   : Standard-Case-Turn (Topologie §7.3).
Tier 2 (async, Background) : Vision · Sketch · Dokumente · RFQ · Incident-Tiefenanalyse.
                             Kein leerer Spinner: Tier 0/1 antwortet sofort, Tier 2 patcht nach.
```

### 7.7 Jinja2 — zwei Rollen, verbindliche Konventionen

```text
Rolle 1 — Prompt-Assembly (Input):
  Alle Prompts als versionierte Templates im Repo (prompts/), Environment mit StrictUndefined,
  trim/lstrip. Logikarm: if/for/include/extends über strukturierte Daten — keine Berechnungen,
  keine Geschäftsregeln im Template. Pack-Partials via {% include %}.
  Nutzereingaben und Upload-Inhalte sind AUSSCHLIESSLICH Variablen, nie Template-Quelltext;
  Rendering in markierte Untrusted-Delimiter. template_id@semver + Prompt-Hash je LLM-Call
  in den Turn-Trace.
Rolle 2 — Output-Composition (Output):
  RFQ One-Pager: Struktur/Tabellen/Werte/Offene-Punkte 100 % deterministisch aus dem Snapshot;
  LLM liefert nur begrenzte Textslots (structured-output-Felder, längenvalidiert).
  Garantie: Im RFQ steht nichts, was nicht im Case steht.
  Cockpit/Pocket/Betriebsfenster: reine Code-Projektionen (kein LLM, kein Jinja2 nötig).
  ChatReply: LLM-generiert, schema-gebunden, No-Go-Linter als deterministischer Post-Check
  (ein Regenerate mit Hinweis, sonst Fallback).
```

### 7.8 Streaming-/SSE-Vertrag

```text
Konsum: graph.astream(stream_mode=["updates","custom","messages"]) → typisierte SSE-Events;
Frontend sieht nie LangGraph-Interna.
Eventtypen + Budgets (Tier 1, mobil):
  ack            < 100 ms   (ingest, Code)
  progress/chip  < 1 s      (route fertig: Mode + extrahierte Felder als Chips)
  cockpit_patch  ~ 2–4 s    (state_gate_merge)
  token          ab ~2–5 s  (compose, kontinuierlich)
  envelope_final Ende
Anforderungen: Python ≥ 3.11 (get_stream_writer in async) · Vertragstest
„gestreamtes Endergebnis ≡ invoke()-Ergebnis".
```

### 7.9 Modell-Tiering (Konfiguration, nicht Code)

```text
FAST   : route · pending_slot_micro · smalltalk · Frage-/Pocket-Formulierung
MID    : cross_impact · pack_impact · regulatory · compose · solution_explainer
STRONG : adversarial · rfq_quality · manufacturer_question · document_analysis · incident-Tiefe
VISION : visual_evidence · sketch_to_case
Zuordnung module_id → model_ref in Konfiguration; Provider-neutraler Adapter;
Goldens laufen je module_id × model_ref.
```

### 7.10 Module/Orchestrierung dürfen nicht (Verbotsliste, ersetzt V1.7 §7.4)

```text
- finale Chat-Antwort direkt schreiben (Composer + Jinja2 tun das)
- State direkt mutieren (nur State Gate); kein Modul besitzt Schreib-Tools
- RAG-Notes als confirmed facts ausgeben; Material-/Produktfreigabe geben; Hersteller ranken
- wegen normaler Lücken Human Escalation auslösen
- ein Supervisor-/Planner-LLM sein oder Module per LLM auswählen
- Agent-zu-Agent-Übergaben oder Subagenten-Hierarchien bilden
- den LangGraph-Checkpointer als Case-/Geschäftsdatenspeicher nutzen
- mehr als 5 LLM-Calls in einem Tier-1-Turn auslösen
- pro Dichtungstyp eigene Graphen/Nodes/Pipelines anlegen
- offene Evaluator-Loops fahren (RFQ-Quality: genau EIN Pass)
- Berechnungen per LLM ausführen
- Temporal o. Ä. in den Chat-Hot-Path ziehen (Kandidat nur für P2/P4-Langläufer)
```

### 7.11 Observability, Goldens, Evals

```text
Turn-Trace (Postgres, je Turn): mode · dirty_set · je LLM-Call {template_id@version,
prompt_hash, model_ref, tokens, latency, proposals[]} · gate_decisions[] · envelope_hash ·
SSE-Timing. Prompt-Volltexte verschlüsselt, tenant-gescoped, TTL.
Golden Conversations in zwei Betriebsarten:
  REPLAY (CI, jeder PR): aufgezeichnete LLM-Antworten → deterministische Regression für
  Scheduler, Gate, Projektionen, Composer, No-Go-Linter, Betriebsfenster.
  LIVE (nightly/Release): echte Modelle → Drift; Metriken: Mode-Confusion-Matrix,
  Feld-Extraktion Precision/Recall, Proposal-Qualität je Modul, RFQ-Vollständigkeit,
  No-Go-Treffer = 0, Fast-Path-Trefferquote.
```

---

## 8. Sicherheit, Tenant und Governance (Fundament, P0 — konkretisiert)

```text
- Tenant-Scope als PFLICHTPARAMETER im Repository-Layer jeder Case-/Datei-/Evidence-/RFQ-/
  Outcome-Operation; es existiert keine API ohne. IDOR/Cross-Tenant = P0-Blocker.
- Vektor-Store: eine Collection, Payload-Partitionierung; Tenant-/Sichtbarkeits-Key als
  indizierter Keyword-Filter; Filter ausschließlich serverseitig im Retriever konstruiert.
- Kein Modul hat Schreib-Tools; Retrieval wird vor-gefetcht und in den Prompt gerendert
  (pre-fetch statt Tool-Roundtrips).
- Untrusted-Content-Pipeline: Uploads/Dokumente → Extraktion → Daten-Blöcke in markierten
  Delimitern; injizierter Inhalt kann maximal Proposals erzeugen, die als review_flag
  sichtbar werden — nie still Case-Wahrheit schreiben.
- Outcome-Daten-Governance: Roh-Outcomes strikt tenant-gescoped; globale Schicht erhält nur
  aggregierte, anonymisierte Richtwerte ab definierter Mindestmenge je Aggregat.
- interrupt()-Resume auth-gebunden (Tenant + Rolle).
- Vollständige Audit-Trails über Tool-Calls, Dateizugriffe, Modulaktionen, Gate-Entscheide.
- Secrets nie in Logs; keine Nutzung vertraulicher Kundendaten für Modelltraining.
- Governance-Grenze sichtbar: keine finale technische/Material-/Compliance-Freigabe;
  ATEX/FDA/WRAS/KTW/DVGW nur erklärend; Liability-Hinweis dauerhaft unter dem Chat-Input.
```

---

## 9. Sequenzierung & Roadmap V1.8

```text
P0 — Fundament & grüner Stack
     • Tenant-Pflichtparameter im Repo-Layer + serverseitige Vektor-Filter (Blocker).
     • Zustandswelten trennen: Geschäftsdaten raus aus dem Checkpointer; thread_id-Konvention;
       Retention-Job.
     • Turn-Graph auf Topologie §7.3; Nodes ≤ ~15 Zeilen, Logik nach core/; SSE-Vertrag §7.8
       inkl. ack < 100 ms.
     • RWDR-Killer-Flow durchgängig (Chat → Cockpit → Pocket → Gate → RFQ One-Pager).
     Beweis: realer RWDR-Fall schneller, verständlicher, besser als ChatGPT+Google+Formular.

P1 — RWDR auf echte Tiefe + Solution Companion Stufe 1
     • Proposal-Schema + Gate-Übersetzer; Call-Konsolidierung (cross_impact, pack_impact,
       adversarial); Jinja2-Konventionen; Replay-Goldens in CI.
     • SolutionProfile + Datenblatt-Ingestion + Operating-Window-Projektion +
       solution_explanation + standard_part_fast_path.
     • RFQ One-Pager perfektionieren; Berechnungen/Ausfallmodi/Risiko-Flags belastbar.
     Beweis: Die Engine trägt einen Typ bis zur RFQ — und der Nutzer kann seine
     Lösung verstehen (Betriebsfenster + geerdeter Lösungs-Chat).

P2 — Wissens-Moat (beide Schleifen)
     • Querschnittswissen breit; Herstellerfeedback-Schleife (RFQ-Qualität).
     • installation_guidance + operation_qna + incident_intake + Outcome-Records +
       Aggregations-Governance.
     Beweis: Wissen verbessert sich messbar pro abgeschlossenem Fall UND pro Feld-Outcome.

P3+ — Domänen-Expansion + Asset-Klammer
     O-Ring → Flachdichtung → Hydraulik/Pneumatik → GLRD → Profile/Packung.
     Bei Pack #2: gemeinsame Abstraktionen EXTRAHIEREN (Rule of Three, inkl. Lifecycle-Bausteine).
     Asset-Klammer (Maschine → Dichtstellen → Cases) + Multi-Positionen-RFQ.
     Schema-Vorsorge (§6.6) gilt ab sofort.

P4 — Partner-/Hersteller-Workspace (Portal)
     Strukturierte, reviewfähige RFQ-Fälle + (neu) Outcome-Kontext als Mehrwert;
     Matching-Logik und interne Wissensbasis bleiben geschützt.
```

---

## 10. Claude Code Implementation Discipline

```text
- Immer audit-first: bestehende Strukturen, Response-Contracts, Frontend-Rendering, State Gate,
  Routing, Prompts, Tests kartieren — mit Path+Line-Evidenz.
- Keine parallele Architektur erfinden, wenn äquivalente Strukturen existieren.
- Nie „baue alles" in einem Patch. Jeder Patch enthält Tests oder begründet deren Fehlen.
- API/SSE-Kompatibilität je Änderung prüfen; jede DTO-Erweiterung serialisierbar und
  frontend-kompatibel; UI-Änderungen brechen weder Desktop noch Mobile.
- Core und Domain Pack getrennt halten; RWDR-Spezifik nie in die Plumbing.
- Orchestrierung: Nodes dünn, Logik in core/; Checkpointer nie als Datenbank;
  Verbotsliste §7.10 ist Review-Kriterium jedes Patches.
```

### 10.1 Direct Claude Code Task Prompt — READ-ONLY DEEP AUDIT (V1.8)

```text
Task
Perform a READ-ONLY deep audit of the sealingAI monorepo against
docs/sealing_intelligence_v1_8_universal_sealing_lifecycle_platform_blueprint.md
(V1.8), which layers on top of the V1.6 contracts and V1.7 architecture.
Do NOT modify any code, config, or docs in this pass.

Goal
Produce an evidence-based map of where the current runtime already satisfies V1.8,
where it deviates, and the smallest-patch plan to close the gaps — so implementation
can proceed in small audited patches afterwards.

Audit dimensions (work through Annex A checklist; every finding needs path + line evidence)
A. Core/Pack boundary: which modules are type-agnostic (Core), which are RWDR-specific;
   any RWDR logic living in plumbing.
B. State worlds: inventory everything persisted in the LangGraph checkpointer vs. the
   case event store; flag any business data read from checkpoints; thread_id convention;
   retention.
C. Turn orchestration: actual graph topology vs. §7.3; node thickness (logic inside nodes
   vs. core/); LLM-call count per representative turn; loops/recursion limits in the hot path;
   interrupt usage.
D. Module/Proposal discipline: do analysis steps return typed proposals or mutate state;
   single-writer property of the State Gate; structured-output validation + retry policy;
   any LLM-performed calculations.
E. Prompt ownership: where prompts live (repo Jinja2 vs. inline strings vs. framework
   abstractions); StrictUndefined; untrusted-content handling; template versioning in traces.
F. Streaming: stream modes consumed; SSE event vocabulary exposed to the frontend;
   time-to-first-event on mobile path; stream≡invoke equivalence test presence.
G. Security/Tenant (P0): tenant scoping enforced at repository layer vs. call sites;
   vector-store filter construction (server-side vs. LLM-influenced); module tool surface
   (any write tools); upload/document trust pipeline; secrets in logs.
H. Lifecycle readiness (V1.8 delta): schema headroom for lifecycle status, SolutionProfile,
   outcome records, positions[]; existing hooks (manufacturer_response origin,
   document_analysis) and what blocks the §6 extensions.
I. Modes & contracts: implemented modes vs. V1.6 §5.3 + V1.8 §5.3 additions; No-Go-linter
   existence; golden conversations runnable in REPLAY mode.
J. Tests & observability: per-turn trace contents vs. §7.11; coverage of core/ without
   the graph runtime.

Method
1. Read-only. 2. Evidence = repo path + line range per claim. 3. Run existing test suites
and report exact commands + results (running tests is allowed; writing is not).
4. Where the blueprint and the repo use different names for an equivalent structure,
map them explicitly instead of declaring a gap.

Expected artifacts (single audit report, markdown)
1. Audit matrix: every Annex A check → status {erfüllt | teilweise | fehlt | n/a} + evidence.
2. Core/Pack boundary map and state-worlds inventory.
3. Prompt inventory (location, templating, versioning) and mode inventory.
4. Gap list keyed to V1.8 acceptance criteria (§11), each with severity (P0/P1/P2)
   and blast radius.
5. Smallest-patch plan: ordered list of patches (P0 first), each with scope, files touched,
   test plan, API/SSE compatibility note. No patch may mix dimensions.
6. Risks & open questions (max 10), including any place where V1.8 conflicts with
   existing behavior that golden conversations depend on.
```

### 10.2 Anschließende Patch-Disziplin

```text
Erst nach Freigabe des Audit-Reports: Patches strikt in der Reihenfolge des Patch-Plans,
einer pro Dimension, jeder mit Tests, jeder gegen die Verbotsliste §7.10 und die
Akzeptanzkriterien §11 geprüft. Golden-REPLAY muss nach jedem Patch grün sein.
```

---

## 11. Acceptance Criteria V1.8

Erfüllt V1.6 (Abschnitt 32) und V1.7 (Abschnitt 11) **plus**:

```text
Orchestrierung
 1. Der Standard-Turn ist ein DAG gemäß §7.3; kein Supervisor-LLM, keine Subagenten,
    keine Loops im Hot Path.
 2. Analyse-Schritte liefern ausschließlich typisierte Proposals; einziger Schreiber von
    Case-Wahrheit ist das State Gate.
 3. Tier-1-Turns lösen maximal 5 LLM-Calls aus; Tier 0 maximal 1; Berechnungen sind Code.
 4. Geschäftsdaten liegen ausschließlich im Event Store; der Checkpointer enthält nur
    Turn-Ausführung und unterliegt einer Retention.
 5. Graph-Nodes sind dünne Adapter; die Kernlogik ist ohne Graph-Runtime testbar
    (REPLAY-Goldens in CI grün).
 6. Alle Prompts liegen als versionierte Jinja2-Templates im Repo (StrictUndefined);
    template_id@version und Prompt-Hash stehen je LLM-Call im Turn-Trace.
 7. Der SSE-Vertrag §7.8 ist erfüllt: ack < 100 ms, erster verwertbarer Fortschritt < 1 s
    mobil, stream≡invoke-Test vorhanden.
 8. Untrusted-Inhalte werden nur als Daten-Variablen in Delimitern gerendert; kein Modul
    besitzt Schreib-Tools.

Lifecycle / Solution Companion
 9. Ein Case trägt einen Lifecycle-Status als Event-Folge; Modes und Dirty-Rules sind
    lifecycle-sensitiv.
10. Ein Case kann ≥ 1 SolutionProfile mit Datenblatt-Herkunft tragen; jedes Limit-Feld hat
    Status, Origin und Quelle (Dokument + Seite).
11. Die Betriebsfenster-Projektion zeigt je Limit-Feld Anforderung, Limit, Marge, Flag —
    vollständig deterministisch; fehlende Limits erzeugen eine Herstellerfrage statt
    stillen Auslassens.
12. solution_explanation antwortet ausschließlich geerdet (Profil/RAG/Norm, mit Quell-Chips)
    und erzeugt für Unbeantwortbares eine vorgeschlagene Herstellerfrage — nie eine Vermutung.
13. Standardfälle (Maß+Norm-Treffer) erreichen in < 60 s Bezeichnung + Checkliste,
    mit jederzeitigem Abzweig in den vollen Case.
14. Ein Incident am verbauten Teil erzeugt einen Soll-Ist-Diagnosepfad und ein
    strukturiertes Outcome-Event.
15. Kein neuer Pfad umgeht das State Gate; die Safety-Formel (Erklärung ≠ Freigabe,
    „laut Datenblatt"-Rahmen) ist in allen Begleit-Modes durchgesetzt.

Wissen & Governance
16. Outcome-Records existieren als Schema + Persistenz; Roh-Outcomes sind tenant-gescoped;
    globale Aggregation erfolgt nur anonymisiert ab Mindestmenge.
17. Der RAG-Scope solution_docs existiert tenant-gescoped mit Pflicht-Payload;
    alle Vektor-Filter werden serverseitig konstruiert.

Schema-Vorsorge
18. Kein Modul, keine Projektion, kein Template nimmt hart „genau eine Position" an
    (positions[]-Vorsorge), auch wenn der Ausbau erst P3 erfolgt.
```

---

## 12. Final Product Sentence

```text
sealingAI ist die Plattform für die gesamte Dichtungstechnik — über den gesamten Lebenszyklus.
Eine universelle Engine versteht jede Dichtungssituation, ein austauschbarer Domain Pack
liefert die fachliche Tiefe, und die gewählte Lösung bleibt verstehbar: belegt, begrenzt,
einbaubar nach Herstellerangabe, diagnostizierbar im Soll-Ist.
RWDR ist der erste Beweis, nicht die Grenze.
```

```text
Chat führt. Pocket Cockpit verdichtet. Cockpit dokumentiert. Sheet strukturiert.
Knowledge erklärt. RFQ übergibt. Betriebsfenster vergleicht. State Gate entscheidet.
Module schlagen vor. Outcomes lehren. Der Hersteller bewertet final.
```

---

## Anhang A — Audit-Checkliste für Claude Code (Read-only, Evidenz = Path + Line)

```text
ORC-01  Existiert ein Turn-Graph? Topologie vs. §7.3 (Knoten, Reihenfolge, Fan-out, Superstep).
ORC-02  Node-Dicke: Anteil Geschäftslogik in Nodes vs. core/; größte Nodes mit Zeilenzahl.
ORC-03  LLM-Call-Zählung eines repräsentativen Tier-1-Turns (Trace oder Code-Pfadanalyse).
ORC-04  Loops/Recursion-Limits im Hot Path? Supervisor-/Planner-LLM? Agent-Handoffs?
ORC-05  Send/Fan-out vorhanden? Reducer auf parallel beschriebenen State-Keys?
ORC-06  interrupt()-Nutzung: wo, wovon ausgelöst, Resume-Autorisierung.
ORC-07  Structured Output: Schema-Validierung + Retry-Policy je LLM-Call.
ORC-08  Berechnungen: vollständige Liste; jede LLM-basierte Berechnung ist ein Befund.
ORC-09  Konsolidierungsstand: welche Analyse-Prompts existieren; Mapping auf
        cross_impact/pack_impact/adversarial/regulatory.
STA-01  Inventar Checkpointer-Inhalte; jede Geschäftsdaten-Lesung aus Checkpoints ist P0-Befund.
STA-02  Event Store: Append-only? Snapshots? Idempotency-Keys? Einziger Schreiber = Gate?
STA-03  thread_id-Konvention; Checkpoint-Retention vorhanden?
PRM-01  Prompt-Inventar: Ort (Repo-Jinja2 / Inline / Framework), je Prompt.
PRM-02  StrictUndefined? Untrusted-Delimiter für Uploads/Dokumente? User-String je als Template?
PRM-03  Template-Versionierung + Prompt-Hash im Trace?
PRM-04  RFQ-Composer: deterministische Struktur + LLM-Textslots? Oder freies LLM-Schreiben?
PRM-05  No-Go-Linter vorhanden, Phrasenliste vs. V1.6/V1.8 §5.4, Post-Check-Verhalten.
STR-01  Konsumierte stream_modes; SSE-Event-Vokabular zum Frontend; LangGraph-Interna sichtbar?
STR-02  Zeit bis erstem Event auf Mobile-Pfad (Messung oder Code-Pfad); ack-Mechanik.
STR-03  stream≡invoke-Äquivalenztest vorhanden?
SEC-01  Tenant-Pflichtparameter im Repository-Layer (nicht nur Call-Sites)? IDOR-Pfadprüfung
        je Case/Datei/Evidence/RFQ-Endpunkt.
SEC-02  Vektor-Store: Collection-Layout, Tenant-Key indiziert, Filter-Konstruktion serverseitig?
SEC-03  Tool-Oberfläche der Module: existieren Schreib-Tools? Pre-fetch vs. Tool-Roundtrips.
SEC-04  Secrets/Prompt-Volltexte in Logs? Verschlüsselung/TTL der Traces?
KNW-01  Wissensschicht: Trennung Querschnitt vs. Domäne im Code? Pflicht-Payload beim Indexieren?
KNW-02  rag_supported_note-Statuspfad: kann RAG je confirmed schreiben? (Gate-Code prüfen)
LIF-01  Schema-Headroom: Lifecycle-Status, SolutionProfile, Outcome, positions[] —
        was blockiert §6 heute konkret?
LIF-02  Hooks: manufacturer_response-Origin und document_analysis vorhanden und nutzbar?
LIF-03  Harte „genau 1 Position"-Annahmen in Modulen/Projektionen/Templates auflisten.
MOD-01  Mode-Inventar vs. V1.6 §5.3 + V1.8 §5.3; Router-Erweiterbarkeit für 5 neue Modes.
MOD-02  standard-part-Erkennung: existiert Maß-/Normabgleich irgendwo?
PCK-01  Core/Pack-Grenze: RWDR-Spezifik in Plumbing? DomainPack-Interface-Stand vs. §3.2.
PCK-02  Registry-Mechanik: Pack-Auflösung zur Laufzeit (seal_type → pack)?
TST-01  Testpyramide: Anteil Tests gegen core/ ohne Graph-Runtime; Goldens REPLAY-fähig?
TST-02  Turn-Trace-Inhalte vs. §7.11; Eval-Metriken (Mode-Confusion, Extraktion) vorhanden?
```

---

## Anhang B — Begleitdokumente

```text
sealingai_orchestrierung_langgraph_architektur.md      (Herleitung + Begründung §7)
sealingai_branchenfit_v17_solution_companion.md         (Herleitung + Begründung Lifecycle/§4–§6)
Bei Abweichungen gilt: V1.8 (dieses Dokument) ist die verbindliche Verdichtung.
```
