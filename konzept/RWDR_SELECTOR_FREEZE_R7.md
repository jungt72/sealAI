# RWDR Selector – Freeze & Abschlussstand R7

## Status

Dieser Stand friert die aktuelle RWDR-Implementierung im kanonischen Pfad `backend/app/agent` ein.

Der RWDR-Selector ist auf Backend-Ebene architektonisch sauber geschichtet, deterministisch aufgebaut und testseitig belastbar abgesichert. Die Fachlogik liegt nicht im Router und nicht in generischen Legacy-Pfaden, sondern in getrennten, klar abgegrenzten RWDR-Modulen.

Dieser Freeze dokumentiert:
- den umgesetzten Architekturstand
- die gültige Source of Truth
- die akzeptierten Designentscheidungen
- die bewusst offenen Restpunkte
- die nächste sinnvolle Folgephase

---

## 1. Kanonische Source of Truth

Die einzige aktive RWDR-Implementierung liegt im Pfad:

- `backend/app/agent/**`

Nicht-kanonisch und nicht als RWDR-Source-of-Truth zu verwenden:
- `backend/app/api/v1/endpoints/langgraph_v2.py`
- `backend/app/api/v1/endpoints/state.py`
- `backend/app/api/v1/fast_brain_runtime.py`
- `backend/app/api/v1/sse_runtime.py`
- `backend/app/services/fast_brain/**`
- `backend/app/services/langgraph/**`

---

## 2. Zielbild dieses Freeze-Stands

Der RWDR-Selector ist jetzt als deterministische, geschichtete Backend-Architektur umgesetzt:

1. **Verträge & Config**
2. **Deterministischer Core**
3. **Deterministische Decision-/Review-Schicht**
4. **Orchestrierung Stage 1 / Stage 2 / Stage 3**
5. **Partielle strukturierte Nachbefüllung**
6. **Kontrollierter feldgebundener Patch-Parser**
7. **Read-Model-, REST- und SSE-Härtung**

Wichtig:
- keine RWDR-Fachlogik im Router
- keine RWDR-Monolithik in `logic.py`
- keine freie generische NLP-Extraktion als Primärmechanismus
- kein zweiter Parallelpfad

---

## 3. Umgesetzte Architekturbausteine

### 3.1 Verträge und Konfiguration
**Dateien**
- `backend/app/agent/domain/rwdr.py`
- `backend/app/agent/api/models.py`
- `backend/app/agent/agent/state.py`

**Umgesetzt**
- `RWDRSelectorInputDTO`
- `RWDRSelectorInputPatchDTO`
- `RWDRSelectorDerivedDTO`
- `RWDRSelectorOutputDTO`
- `RWDRSelectorConfig`
- typed Confidence-Felder
- Rule-Carrier für:
  - surface speed
  - pressure
  - geometry
  - contamination
  - uncertainty
  - review triggers

**Zweck**
- zentrale, typed und testbare Vertrags- und Regelbasis
- kein implizites Feldmodell
- keine hart verteilten Ad-hoc-Schwellenwerte im Gesprächsfluss

---

### 3.2 Deterministischer RWDR-Core
**Datei**
- `backend/app/agent/domain/rwdr_core.py`

**Umgesetzt**
- `calculate_surface_speed(...)`
- `evaluate_pressure_tribology(...)`
- `evaluate_geometry(...)`
- `classify_contamination(...)`
- `evaluate_maintenance(...)`
- `evaluate_installation(...)`
- `evaluate_confidence(...)`
- `derive_rwdr_core(...)`

**Zweck**
- rein deterministische Ableitung der Core-Signale
- keine Dialoglogik
- keine Output-Entscheidung
- keine UI-/Transportlogik

---

### 3.3 Deterministische Decision-/Review-Schicht
**Datei**
- `backend/app/agent/domain/rwdr_decision.py`

**Umgesetzt**
- Hard Stops
- Review Flags
- Warnings
- Modifiers
- Type-Class-Entscheidung
- Reasoning-Output

**Typpriorität**
1. `rwdr_not_suitable`
2. `engineering_review_required`
3. `heavy_duty_or_cassette_review`
4. `ptfe_profile_review`
5. `pressure_profile_rwdr`
6. `rwdr_with_dust_lip`
7. `standard_rwdr`

**Zweck**
- finale fachliche Entscheidung
- strikt getrennt von Core und Orchestrierung

---

### 3.4 Stage-Orchestrierung
**Datei**
- `backend/app/agent/agent/rwdr_orchestration.py`

**Umgesetzt**
- typed Flow-State
- Stage 1 / Stage 2 / Stage 3
- Missing-Field-Ermittlung
- Next-Field-Steuerung
- Hard-Stop-Short-Circuit nach Stage 1
- kontrollierte Re-Evaluation
- Reply-Erzeugung für:
  - pending
  - review
  - hard stop
  - ready

**Zweck**
- Flow-Steuerung
- keine Core-Berechnung im Graph
- keine Decision-Logik im Router

---

### 3.5 Partial Merge / strukturierte Nachbefüllung
**Datei**
- `backend/app/agent/agent/rwdr_orchestration.py`

**Umgesetzt**
- `merge_rwdr_patch(...)`
- Merge von:
  - vorhandenem Draft
  - vorhandenem Full-Input
  - neuem Full-Input
  - neuem Partial-Patch
- feldweises Confidence-Merging
- keine implizite Löschung gültiger Werte
- Invalidation von `input/derived/output` vor Re-Evaluation

**Zweck**
- sauberer mehrturniger Backend-Pfad
- keine stillen Überschreibungen
- keine kaputte Zwischenlogik

---

### 3.6 Kontrollierter Feldparser
**Datei**
- `backend/app/agent/agent/rwdr_patch_parser.py`

**Umgesetzt**
- `FIELD_QUESTIONS`
- `next_rwdr_question(...)`
- `parse_rwdr_patch_for_field(...)`

**Eigenschaften**
- nur genau **ein erwartetes Feld** pro Turn
- nur enge, explizite Muster
- unsichere Antwort => kein Patch
- kein Halluzinieren
- kein generischer Freitext-Extraktor

**Zweck**
- sichere Backend-Brücke zwischen Nutzerantwort und `RWDRSelectorInputPatchDTO`

---

### 3.7 Graph-Integration
**Datei**
- `backend/app/agent/agent/graph.py`

**Umgesetzt**
- früher Entry-Router
- RWDR-Orchestration-Node
- Routing zwischen:
  - RWDR-Pfad
  - bestehendem Agent-Pfad

**Zweck**
- Graph orchestriert nur
- Graph berechnet keine RWDR-Fachlogik

---

### 3.8 Router-, REST- und SSE-Projektion
**Dateien**
- `backend/app/agent/api/router.py`
- `backend/app/agent/agent/sync.py`

**Umgesetzt**
- Aktivierung des RWDR-Flows über:
  - `rwdr_input`
  - `rwdr_input_patch`
- strukturierte Rückgabe von `rwdr_output`
- RWDR-Projektion in Stream-Payload
- RWDR-Read-Model in `working_profile["rwdr"]`
- JSON-sichere Serialisierung im SSE-Pfad
- Projection-only-Helfer:
  - `project_rwdr_output(...)`
  - `project_rwdr_read_model(...)`

**Zweck**
- stabiler Transport
- keine Fachlogik im Router
- keine Ad-hoc-Inline-Projektion mehr

---

## 4. Aktive Dateistruktur der RWDR-Implementierung

### Domain
- `backend/app/agent/domain/rwdr.py`
- `backend/app/agent/domain/rwdr_core.py`
- `backend/app/agent/domain/rwdr_decision.py`

### Agent Runtime
- `backend/app/agent/agent/state.py`
- `backend/app/agent/agent/rwdr_orchestration.py`
- `backend/app/agent/agent/rwdr_patch_parser.py`
- `backend/app/agent/agent/graph.py`
- `backend/app/agent/agent/sync.py`

### API
- `backend/app/agent/api/models.py`
- `backend/app/agent/api/router.py`

### Implementierungsdoku
- `konzept/rwdr_selector_runtime_implementation.md`

### Tests
- `backend/tests/agent/test_rwdr_contracts.py`
- `backend/tests/agent/test_rwdr_core.py`
- `backend/tests/agent/test_rwdr_decision.py`
- `backend/tests/agent/test_rwdr_orchestration.py`
- `backend/tests/agent/test_rwdr_graph_integration.py`
- `backend/tests/agent/test_api_models.py`
- `backend/tests/agent/test_api_router.py`

---

## 5. Akzeptierte Designentscheidungen

### 5.1 Router bleibt transport-only
`router.py` darf:
- Requests entgegennehmen
- strukturierte RWDR-Daten weiterreichen
- Outputs / Stream-Projektionen zurückgeben

`router.py` darf nicht:
- Core-Berechnungen durchführen
- Type-Class-Entscheidungen treffen
- Freitext-NLP für RWDR aufbauen

---

### 5.2 Graph bleibt orchestration-only
`graph.py` darf:
- zwischen RWDR-Pfad und bestehendem Agent-Pfad routen
- RWDR-Orchestrierung starten

`graph.py` darf nicht:
- Core- oder Decision-Regeln duplizieren
- Fachlogik aus `rwdr_core.py` oder `rwdr_decision.py` nachbauen

---

### 5.3 RWDR-Core und RWDR-Decision bleiben getrennt
- `rwdr_core.py` = Ableitung
- `rwdr_decision.py` = Entscheidung
- `rwdr_orchestration.py` = Flow

Diese Trennung bleibt verbindlich.

---

### 5.4 Partial Input nur strukturiert
Mehrturnige Nachbefüllung läuft nur über:
- `RWDRSelectorInputDTO`
- `RWDRSelectorInputPatchDTO`

Nicht zulässig als Primärmechanismus:
- breite Freitext-Heuristik
- implizite Regex-Suppe in generischen Dateien
- “wir erraten das Feld schon irgendwie”

---

### 5.5 Parser bleibt absichtlich schmal
Der Parser ist absichtlich konservativ:
- ein Feld pro Turn
- nur enge Muster
- unbekannt/unklar => kein Patch
- keine Mehrfeld-Magie

Das ist Absicht, kein Mangel.

---

## 6. Teststatus des Freeze-Stands

Der RWDR-Stand ist auf Backend-Ebene testseitig abgesichert.

### Abgedeckt
- Vertragsvalidierung
- Config-Backbone
- Core-Berechnungen und Flags
- Decision-/Review-Logik
- Stage-Orchestrierung
- Partial Merge
- Confidence-Merge
- Graph-Integration
- REST-Response-Projektion
- SSE-Projektion
- Sync-/Read-Model-Projektion
- Leer-/Teilzustände
- Regression gegen bestehende Agent-Pfade

### Qualitätsaussage
Der aktuelle Stand ist **backend-seitig belastbar** und nicht mehr nur konzeptionell.

---

## 7. Bewusst offene Restpunkte

Diese Punkte sind **nicht** offen, weil die Architektur unvollständig wäre, sondern weil sie bewusst außerhalb dieses Freeze-Scope liegen.

### 7.1 Kein Frontend-Formflow
Es gibt noch keinen dedizierten UI-Formpfad für Stage 1 / Stage 2.

Status:
- bewusst offen
- Backend ist vorbereitet

---

### 7.2 Kein dedizierter Client-spezifischer RWDR-Draft-Endpunkt
Der strukturierte Patch-Pfad läuft derzeit über `ChatRequest`.

Status:
- bewusst offen
- technisch möglich
- noch kein eigener spezialisierter Produktpfad

---

### 7.3 Kein Parser-Breitenausbau
Der Parser unterstützt bewusst nur einfache, sichere Einzelantworten.

Status:
- bewusst offen
- nicht erweitern, solange kein harter Bedarf besteht

---

### 7.4 Keine Freitext-First-Normalisierung als RWDR-Primärpfad
Der Agent kann RWDR noch nicht vollautomatisch aus freiem chaotischem Text “perfekt” befüllen.

Status:
- bewusst offen
- soll auch nicht heimlich nachgerüstet werden

---

## 8. Verbotene nächste Schritte

Diese Dinge sollen **nicht** als nächstes passieren:

- RWDR-Fachlogik in `router.py` ergänzen
- RWDR-Regeln in `logic.py` hineinschieben
- `rwdr_patch_parser.py` zu einem generischen NLP-Monster ausbauen
- parallele RWDR-Wahrheiten in anderen Pfaden erzeugen
- Frontend bauen und dabei Backend-Verträge verbiegen
- Hardcodes außerhalb des Config-/Domain-Layers verteilen

---

## 9. Empfohlene nächste Phase

Nach diesem Freeze gibt es genau zwei sinnvolle Richtungen.

### Option A – Produktiver Anschluss
Ein sauberer produktiver Client-/Form-/Tool-Pfad, der kontrolliert:
- `rwdr_input`
- `rwdr_input_patch`

liefert.

### Option B – Integrationsbetrieb
Ein realer Client oder Agent-Tooling-Layer, der den vorhandenen Stage-/Patch-Pfad bewusst nutzt, ohne neue Freitext-Magie einzuführen.

Empfehlung:
**Erst Freeze committen, dann produktiven Anschluss bauen.**

---

## 10. Definition of Done für diesen Freeze

Dieser Freeze gilt als abgeschlossen, wenn:

- die RWDR-Source-of-Truth ausschließlich im kanonischen Agent-Pfad liegt
- Verträge, Core, Decision, Orchestrierung, Merge und Parser getrennt sind
- REST-/SSE-/Read-Model-Projektion robust funktionieren
- die vorhandene Testbasis grün ist
- die Implementierungsdoku im Repo liegt
- keine neue RWDR-Fachlogik in Router oder Altpfaden gelandet ist

---

## 11. Abschlussurteil

Der RWDR-Selector ist im Backend jetzt nicht mehr nur Konzept, sondern eine geschichtete, deterministische und testbare Implementierung.

Der Architekturstand ist ausreichend stabil, um:
- eingefroren zu werden
- als Referenz für Codex zu dienen
- anschließend kontrolliert an einen produktiven Client-/Form-/Tool-Pfad angebunden zu werden

Weitere sinnvolle Arbeit sollte jetzt nicht mehr in neuer Fachlogik bestehen, sondern im sauberen produktiven Anschluss an den bereits vorhandenen strukturierten Pfad.
