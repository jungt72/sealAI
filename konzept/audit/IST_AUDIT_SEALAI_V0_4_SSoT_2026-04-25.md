# SeaLAI v0.4 SSoT Deep-Dive Ist-Audit

**Datum:** 2026-04-25  
**Basis:** `konzept/sealai_ssot_v0_4_conversational_diagnostic_cockpit.md`  
**Repo-Stand:** `1347274c Harden frontend deps and clarification guardrails`

## 1. Executive Summary

Der aktuelle Stack ist deutlich weiter als ein Prototyp: Auth, Live-Deployment, Fast-Responder/Governed-Flow, Pydantic-State-Layer, Redis/Postgres-Snapshots, Workspace-Projection, RAG-Upload, RFQ-/Matching-Slices und Guardrails sind vorhanden.

Gegen die neue v0.4-SSoT ist der Stack aber noch nicht konsistent ausgerichtet. Die größten Lücken liegen nicht in Deployment oder Basissicherheit, sondern in der fachlichen Architektur:

1. Die neue SSoT ist noch nicht als oberste Repo-Autorität verankert.
2. Case-State ist snapshot-/reducer-basiert, aber noch nicht vollständig append-only CaseEvent-basiert.
3. Das neue kanonische Datenmodell mit `asset_type`, `seal_location`, `medium_name`, `readiness_level` und Risk-Slices ist nur teilweise über ältere Felder abgebildet.
4. Das Cockpit rendert noch die alte 4-Sektionslogik statt der verbindlichen 2x2-Analyse aus v0.4.
5. Readiness existiert, ist aber noch kein Level-0-bis-5-Modell nach v0.4.
6. Risk Evaluation ist noch verteilt/implizit, nicht als eigener deterministischer `RiskEvaluator` mit Score 0/1/2/3/4/9 modelliert.
7. Deep-Dive-Tabs existieren als UI-Modus/Fallback, aber noch nicht als fallbezogene Backend-Projektion `Analyse | Medium | Werkstoff | Dichtungstyp`.
8. Hersteller-Matching existiert, aber Capability Registry und Matching-Modell sind noch nicht vollständig v0.4-kompatibel.
9. Dokumenten-Upload/RAG existiert, aber noch nicht als case-gebundener `DocumentInput -> proposed_case_delta`-Kanal.
10. LLM-Evals sind nur über verstreute Tests/Guards abgedeckt, nicht als explizite Eval-Schicht.

## 2. Bereits Tragfähig

| Bereich | Ist-Zustand | Bewertung |
|---|---|---|
| Deployment | Backend/Frontend live, Digest-Pinning, PM2, Health, Stack-Smoke | Stark |
| Auth | NextAuth/Keycloak, BFF blockt anonymen Zugriff | Stark |
| Runtime Routing | Pre-Gate, Fast Responder, Knowledge Response, Governed Flow | Teilweise v0.4-konform |
| LLM-State-Trennung | LLM schreibt ObservedExtraction, Reducer leiten downstream ab | Gute Basis |
| Output-Klassen | `conversational_answer`, `structured_clarification`, `technical_preselection`, usw. vorhanden | Nahe an v0.4 |
| Guardrails | Keine finale Freigabe, Clarification-Sprache gehärtet | Stark |
| Persistence | Redis live state, Postgres cases/snapshots, Chat-History | Gute Basis |
| Projection | `CaseWorkspaceProjection` als Backend-Readmodel vorhanden | Gute Basis, aber alt strukturiert |
| RAG/Uploads | Dokumentenendpunkte, Qdrant/Paperless-Integration | Infrastruktur vorhanden |
| RFQ/Matching | RFQ-State, Matching-State, HTML-Report, Herstellerdaten | Teilweise vorhanden |

## 3. Kritische Gaps gegen v0.4

### G1 — Authority Chain noch alt

`AGENTS.md` nennt noch `konzept/sealai_ssot_architecture_plan.md` als höchste Quelle. Die neue v0.4-Datei muss als oberste Authority eingetragen werden.

**Status:** FEHLT  
**Priorität:** P0

### G2 — Structured Double Output Pattern nicht explizit durchgängig

Der Stack nutzt ObservedExtraction und Governed Flow, aber kein durchgängiges Turn-Artefakt aus `assistant_message` plus `proposed_case_delta`. Aktuell sind Extraktion, Antwort und State-Update noch stärker graph-/node-orientiert.

**Status:** TEILWEISE  
**Priorität:** P1

### G3 — Append-only CaseEvent fehlt als produktive Wahrheit

Es gibt `mutation_events` und Snapshots, aber kein v0.4-konformes `CaseEvent` mit proposed/accepted/rejected Delta, Revision before/after, actor, source turn/document, ruleset/model.

**Status:** TEILWEISE / FEHLT  
**Priorität:** P1

### G4 — Revisions-/Stale-Modell unvollständig

Es gibt State-Revisions und `derivedArtifactsStale`, außerdem Dependency Map in Reducern. Es fehlt aber ein typed `DerivedValue`-Contract pro abgeleitetem Wert mit `valid|stale|invalid|unknown`, `derived_from_fields`, `derived_from_revision`, `calculation_id`, `ruleset_version`.

**Status:** TEILWEISE  
**Priorität:** P1

### G5 — Kanonisches v0.4 Datenmodell fehlt

Aktuelle Felder sind älter: `installation`, `movement_type`, `medium`, `pressure_bar`, `temperature_c`. v0.4 fordert u.a. `asset_type`, `asset_function`, `seal_location`, `motion_type`, `medium_name`, `medium_category`, `temperature_min/max`, `pressure_nominal/peak`, `food_contact`, `atex_relevance`.

**Status:** TEILWEISE  
**Priorität:** P1

### G6 — Cockpit 2x2 nicht umgesetzt

Backend und Frontend nutzen aktuell:

- `core_intake`
- `failure_drivers`
- `geometry_fit`
- `rfq_liability`

v0.4 fordert verbindlich:

- `application_function`
- `medium_environment`
- `operating_geometry`
- `risk_readiness`

**Status:** FEHLT  
**Priorität:** P0

### G7 — Readiness Level 0-5 fehlt

Aktuell gibt es `preliminary`, `review_needed`, `rfq_ready` und Governance-/RFQ-Status. v0.4 fordert deterministisches Level 0-5 mit klaren Mindestkriterien.

**Status:** TEILWEISE  
**Priorität:** P1

### G8 — RiskEvaluator als eigener Service fehlt

Risiken sind in Governance, MediumContext, Check-Ergebnissen und Textlogik verteilt. v0.4 verlangt ein deterministisches Ergebnisobjekt mit `risk_name`, `score`, `label`, `drivers`, `missing_inputs`, `rule_ids`, `confidence`.

**Status:** FEHLT  
**Priorität:** P1

### G9 — ConflictDetector ist kein eigener Service

Konflikte entstehen über NormalizedState/ConflictRef, aber der v0.4-Service mit Toleranzen, Provenance Priority und Resolution Question fehlt.

**Status:** TEILWEISE  
**Priorität:** P2

### G10 — Deep-Dive Tabs sind noch UI-Fallback statt Backend-Projektion

UI hat `Case`, `Compare`, `Deep Dive`; v0.4 fordert MVP-Tabs `Analyse | Medium | Werkstoff | Dichtungstyp`, jeweils fallbezogen und mit Rückführung zur Analyse.

**Status:** TEILWEISE  
**Priorität:** P1

### G11 — MVP-Deep-Path Verschiebung nicht vollständig abgebildet

Alte Architektur war stark `ms_pump`/allgemein-RWDR geprägt. v0.4 setzt MVP Deep Fidelity explizit auf `PTFE-RWDR`; Shallow Paths sollen erkannt, aber nicht über-tief ausgelegt werden.

**Status:** TEILWEISE  
**Priorität:** P1

### G12 — Dokumente sind RAG, aber noch kein case-gebundener Input-Kanal

Upload/RAG existiert. Es fehlt die v0.4-Logik `DocumentInput -> extracted_candidates -> proposed_case_delta -> Governor`.

**Status:** TEILWEISE  
**Priorität:** P2

### G13 — Capability Registry nicht v0.4-kompatibel genug

Herstellerdaten und Capability-Tabellen existieren. Das v0.4-Modell fordert explizite Supported Asset Types, Seal Types, Material Families, Range-Felder, Industrie-/Zertifikatsflags, Food/Pharma/ATEX, Small Quantity, Prototype, Geography, Response Model, Evidence Level.

**Status:** TEILWEISE  
**Priorität:** P2

### G14 — LLM-Evals fehlen als Schicht

Einzelne Tests prüfen Guardrails und Contracts. Es fehlt eine explizite Eval-Suite für Tone, Safety Language, Best-Next-Question, Delta Accuracy, No Unauthorized Claims, Deep-Dive Grounding.

**Status:** FEHLT  
**Priorität:** P2

## 4. Empfohlene Umsetzungsreihenfolge

### Phase A — Sofort

1. v0.4 SSoT ins Repo aufnehmen.
2. Authority Chain in `AGENTS.md` aktualisieren.
3. Audit-Artefakt speichern.

### Phase B — Projection Contract

1. Backend `CaseWorkspaceProjection` um v0.4-2x2 Section IDs erweitern.
2. Backend Projection Builder auf v0.4-Sections umstellen.
3. Frontend Types/Mapping auf dieselben IDs heben.
4. Tests für Section IDs und Titel ergänzen.

### Phase C — Canonical Case Slices

1. Additive v0.4-Slices in `GovernedSessionState` aufnehmen.
2. Legacy-Felder weiter mappen, aber v0.4-Felder als Zielkanon etablieren.
3. Extraction whitelist um `asset_type`, `seal_location`, `medium_name`, `temperature_min/max`, `pressure_nominal/peak` ergänzen.

### Phase D — Deterministische Evaluatoren

1. `ReadinessEvaluator` Level 0-5.
2. `RiskEvaluator` Score 0/1/2/3/4/9.
3. `ConflictDetector` Service.
4. Dependency/DerivedValue-Status härten.

### Phase E — Deep-Dive und RFQ

1. Tabs `Analyse | Medium | Werkstoff | Dichtungstyp` als Projection State.
2. Fallbezogene Deep-Dive Templates.
3. RFQ-Reportstruktur nach v0.4.

### Phase F — Matching & Documents

1. Capability Registry v0.4-Modell.
2. Problem-first matching guard.
3. DocumentInput -> proposed_case_delta.

## 5. Umsetzung in diesem Arbeitsgang

Dieser Arbeitsgang sollte mindestens Phase A vollständig und Phase B als ersten Code-Schnitt umsetzen. Danach ist der sichtbare Stack konsistent genug, um die tieferen State-/Evaluator-Phasen iterativ zu bauen.
