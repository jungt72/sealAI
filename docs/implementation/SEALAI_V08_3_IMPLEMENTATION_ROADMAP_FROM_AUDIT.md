# SeaLAI v0.8.3 Implementation Roadmap — auf Basis des IST-Audits

**Basis:** `konzept/SEALAI_V08_2_STACK_AUDIT_IST.md`  
**Zielbild:** SeaLAI v0.8.3 als event-modelled Multi-Szenario-Klärungsplattform  
**Arbeitsprinzip:** kleine, prüfbare PRs; keine Big-Bang-Umsetzung; keine produktiven Side Effects

---

## 1. Executive Summary

Der Audit zeigt eine solide v0.7/frühe-v0.8-Basis:

- FastAPI/Next.js-Stack ist produktiv vorhanden.
- Governed Case State, Snapshots, Mutation Events, Revisionen, Reducer, Konflikt-/Stale-Logik sind bereits starke Grundlagen.
- RFQ Preview mit `case_revision`-Freeze, Consent und deaktiviertem Dispatch ist bereits vergleichsweise weit.
- RAG-/Upload-Infrastruktur ist vorhanden und sicherheitstechnisch besser als viele andere Teile.
- Frontend hat Chat, Dashboard, Cockpit-Ansatz, RFQ Pane und Upload.

Aber SeaLAI ist noch kein v0.8.3-System.

Die größten Lücken sind:

```text
1. Keine v0.8.x ConversationIntent-/ResponseMode-/CaseType-/ArtifactType-Taxonomie.
2. Keine zentrale SealFamily-/SealType-Normalisierung.
3. Knowledge ist nicht RAG-first und hat keinen sichtbaren "nicht validiert"-LLM-Fallback.
4. Manufacturer Matching fehlt als transparentes paid partner network.
5. Support / Complaint / Compatibility / Failure sind überwiegend Konzept oder alte Teilseams.
6. Decision Understanding ist backendseitig teilweise vorhanden, aber nicht als UI-Kern sichtbar.
7. Alte MCP-/Compliance-/Chemical-Ausgaben können Vertrauen und Claims gefährden.
8. Tenant-/IDOR-Risiken entstehen, sobald Artifacts/Delivery/Matching erweitert werden.
```

Daraus folgt:

> Nicht zuerst Matching bauen. Nicht zuerst UI ausbauen. Nicht zuerst Support-Artefakte bauen.  
> Zuerst die Event-/Taxonomie-/Routing-Grundlage stabilisieren.

Der professionelle Umsetzungsweg ist:

```text
Repo & Konzeptgrundlage sichern
→ Event-Modeling-Blueprint
→ Test-Harness stabilisieren
→ Conversation / CaseType / ArtifactType / SealType
→ Needs + Current-State + Next-Best-Question
→ Source/Validation + RAG-first + Fallback-Labels
→ RFQ v0.8.3 finalisieren
→ Decision Understanding UI
→ Upload/IP/Claim Guards
→ Manufacturer Matching backend
→ Matching UI
→ Support/Compatibility/Complaint/Fallback-Artefakte
→ Tenant/Security/Regression
→ v0.8.3 Acceptance
```

---

## 2. Sofortige Entscheidungen

### 2.1 v0.8.3 wird aktive Umsetzungsbasis

Der Audit wurde gegen v0.8.2 erstellt. Danach wurde das Konzept auf v0.8.3 mit Event-Modeling-Overlay professionalisiert.

Daher gilt ab jetzt:

```text
Audit = IST-Zustand
v0.8.3-Konzept = SOLL-Zustand
```

Die v0.8.2-Gaps bleiben gültig, werden aber mit v0.8.3-Slices umgesetzt.

---

### 2.2 `konzept/` ist laut Audit ignoriert

Der Audit sagt:

```text
konzept/ ist in diesem Repo per .gitignore ignoriert.
```

Das ist kritisch, wenn Codex Cloud/App auf einem GitHub-Repo arbeitet.

Entscheidung:

```text
Die aktive v0.8.3-Konzeptdatei und der IST-Audit müssen in einen getrackten Pfad oder per git add -f bewusst versioniert werden.
```

Empfehlung:

```text
docs/implementation/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md
docs/implementation/SEALAI_V08_2_STACK_AUDIT_IST.md
```

Alternativ:

```bash
git add -f konzept/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md
git add -f konzept/SEALAI_V08_2_STACK_AUDIT_IST.md
```

Professioneller ist der `docs/implementation/`-Pfad, weil `konzept/` offenbar als lokale Ablage gedacht ist.

---

### 2.3 Worktree muss vor der Umsetzung bereinigt werden

Der Audit meldet:

```text
Branch: redesign/sealai-cockpit-overview
Worktree: dirty
AGENTS.md geändert
mehrere Frontend-Dateien geändert
untracked Cockpit-Dateien
untracked Datei "tatus --short"
```

Regel:

> Vor produktiver Codex-Implementierung muss geklärt werden, welche Änderungen Basis sind und welche weg können.

Kein Codex-PR sollte auf einem unklaren Worktree starten.

---

## 3. Implementierungsprinzipien

### 3.1 Event-Modeled Slice statt Feature-Monolith

Jeder PR muss einen Slice beschreiben:

```text
Trigger
→ Command
→ Event(s)
→ View/Projection
→ Given-When-Then-Test
```

Kein produktives Feature ohne Slice.

---

### 3.2 Kein Event-Sourcing-Zwang

v0.8.3 verlangt Event Modeling als Umsetzungsmethode, nicht als Stack-Ersatz.

Erlaubt:

```text
- vorhandene Tabellen weiterverwenden
- bestehende Services erweitern
- Events als Audit-/Domain-Ereignisse modellieren
- Views als DTOs/Projektionen bauen
```

Nicht erlaubt ohne expliziten Auftrag:

```text
- Event Store einführen
- vollständiges Event Sourcing bauen
- große Datenmodellmigration
- Servicebus einführen
- Stack ersetzen
```

---

### 3.3 Keine produktiven Side Effects

Codex darf während Umsetzung nicht:

```text
Services neu starten
Produktivmigrationen ausführen
Redis/Qdrant resetten
Secrets ausgeben
RFQs senden
Hersteller kontaktieren
Deployment ändern
```

---

### 3.4 Backend bleibt Wahrheit

Frontend rendert Projektionen.

Frontend darf nicht autoritativ berechnen:

```text
Readiness
Engineering Truth
Matching Score
Consent Validity
Compliance Status
Technical Fit
```

---

### 3.5 LLM ist nie Engineering Truth

LLM darf:

```text
vorschlagen
erklären
orientieren
Felder als Kandidaten extrahieren
nächste Fragen vorschlagen
Fallback-Wissen als unvalidiert liefern
```

LLM darf nicht:

```text
final freigeben
CaseField bestätigen
Compliance beweisen
Kompatibilität final beurteilen
Hersteller final ranken
Root Cause final feststellen
```

---

## 4. Phasenplan

## Phase 0 — Arbeitsgrundlage sichern

### Ziel

Codex bekommt eine saubere, versionierte, eindeutige Arbeitsbasis.

### Ergebnis

```text
- clean oder bewusst eingefrorener Worktree
- v0.8.3-Konzept trackbar
- Audit trackbar
- AGENTS.md auf v0.8.3 ausgerichtet
- Test-Harness-Baseline bekannt
```

### Warum zuerst?

Weil der Audit zeigt, dass `konzept/` ignoriert ist und der Worktree bereits dirty war. Codex darf nicht auf unsicherem Kontext bauen.

---

## Phase 1 — Event-Modeling-Blueprint und Testfähigkeit

### Ziel

v0.8.3 wird in implementierbare Slices übersetzt, bevor Code gebaut wird.

### Ergebnis

```text
konzept/event_model/ oder docs/implementation/event_model/
```

mit:

```text
00_method.md
01_personas_swimlanes.md
02_command_event_view_catalog.md
03_scenario_slices.md
04_field_origin_destination_matrix.md
05_automation_todo_views.md
06_security_boundary_map.md
07_gwt_specs.md
```

### Zusätzlich

Der lokale Testfehler `alembic.config` muss repariert oder als Environment-Setup klar dokumentiert werden, bevor Service-/Model-Tests breit genutzt werden.

---

## Phase 2 — Routing- und Domänen-Taxonomie

### Ziel

SeaLAI weiß sauber, ob eine Nachricht Small Talk, Knowledge, RFQ, Matching, Complaint, Compatibility, Failure, Replacement usw. ist.

### Ergebnis

```text
ConversationIntent
ResponseMode
CaseType
ArtifactType
```

als stabile Code-Level-Primitive, zunächst ohne DB-Migration.

---

## Phase 3 — Dichtungstyp-Achse und präzise Bedarfs-/Ist-Analyse

### Ziel

SeaLAI versteht nicht nur das Szenario, sondern auch den Dichtungstyp.

### Ergebnis

```text
SealFamily
SealType
SealApplicationProfile
Alias Normalizer
Type-specific Next-Best-Questions
```

Das ist essenziell, weil RWDR, Flachdichtung, Hydraulikdichtung, Gleitringdichtung, O-Ring und Packung völlig andere Intake-Fragen brauchen.

---

## Phase 4 — Trust Layer: Source, Validation, RAG-first, Fallback

### Ziel

Jede technische Information hat Quelle und Validierungsstatus.

### Ergebnis

```text
source_type
validation_status
RAG-first Knowledge Answer
RAG-miss detection
LLM-research fallback labeled "nicht validiert"
UI-labels für nicht validierte Information
```

Das muss vor breitem Knowledge- oder Support-Ausbau kommen.

---

## Phase 5 — RFQ v0.8.3 stabilisieren

### Ziel

Bestehende RFQ-Stärke auf v0.8.3 heben.

### Ergebnis

```text
RFQPreview aus Field Envelopes
case_revision freeze
stale handling
Consent mit no-final-release, open-points, export-intent
Export allowlist
weiterhin kein Dispatch
```

RFQ ist der stärkste bestehende Produktkern. Er sollte nicht neu gebaut, sondern gehärtet werden.

---

## Phase 6 — Decision Understanding und UI-Trust

### Ziel

SeaLAI fühlt sich für Nutzer seriös, präzise und hilfreich an.

### Ergebnis

```text
DecisionUnderstandingPanel
OpenPoints
Risks
Known / Missing / Uncertain
NextBestQuestion
Source/Validation labels
Evidence/Provenance visibility
```

---

## Phase 7 — Manufacturer Matching als Trust-System

### Ziel

SeaLAI matched nur aktive zahlende Partnerhersteller, aber transparent und technisch begründet.

### Ergebnis

```text
Partner eligibility
Capability graph
ManufacturerFitMatrix
Fit reasons
Gaps
No suitable partner
Partner-network disclosure
No paid ranking boost
```

Matching kommt erst, wenn Routing, SealType, Source/Validation und Disclosure-Regeln sauber sind.

---

## Phase 8 — Support / Compatibility / Complaint / Failure

### Ziel

SeaLAI kann reale Hersteller- und Anwenderanfragen strukturiert beantworten helfen, ohne finale Freigaben zu behaupten.

### Ergebnis

```text
CompatibilityInquiry
Oil/Lab Report Intake
ComplaintIntake
FailureAnalysisIntake
CustomerReplyDraft
InternalEngineeringNote
No final compatibility
No final root cause
No liability admission
```

---

## Phase 9 — Security, Tenant, Upload/IP, Compliance Guards

### Ziel

Vor breiter Nutzung werden die riskanten Grenzen regressionsfest.

### Ergebnis

```text
Cross-tenant negative tests
Artifact/RFQ/Upload/Consent IDOR tests
Path redaction
Prompt-injection tests
MCP compliance/chemical claim guard
No-overclaim regression
```

---

## Phase 10 — Final Acceptance

### Ziel

v0.8.3 ist nicht nur gebaut, sondern belastbar.

### Ergebnis

```text
alle Kernflows haben Slices
alle Kernflows haben Tests
keine unvalidierte LLM-Info wird Wahrheit
keine unsafe Copy
kein Matching ohne Disclosure
kein Export ohne Consent
kein Cross-Tenant-Leak
```

---

## 5. Konkreter PR-Plan

## PR 0 — Repo Baseline, SSoT und Worktree Hygiene

### Ziel

Arbeitsbasis klären und v0.8.3 als aktive Umsetzungsversion trackbar machen.

### Aufgaben

```text
- git status analysieren
- untracked/dirty Dateien klassifizieren
- "tatus --short" prüfen und ggf. entfernen, wenn klar Müll
- AGENTS.md auf v0.8.3 prüfen
- v0.8.3-Konzept in trackbaren Pfad legen
- Audit in trackbaren Pfad legen
- keine Produktlogik ändern
```

### Wahrscheinliche Dateien

```text
AGENTS.md
docs/implementation/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md
docs/implementation/SEALAI_V08_2_STACK_AUDIT_IST.md
```

### Tests / Checks

```bash
cd /home/thorsten/sealai && git status --short
```

### Akzeptanz

```text
- Codex Cloud/App kann aktive Konzeptdatei lesen.
- Audit ist versioniert oder bewusst force-added.
- Keine Produktdatei versehentlich geändert.
- Worktree-Zustand ist dokumentiert.
```

### Risiko

Niedrig, aber kritisch als Grundlage.

---

## PR 1 — Event Model Blueprint

### Ziel

v0.8.3 in konkrete Event-Modeling-Slices übersetzen.

### Aufgaben

```text
- Personas/Swimlanes definieren
- Command/Event/View-Katalog erstellen
- Szenario-Slices definieren
- Field-Origin-Destination-Matrix erstellen
- Automation-Todo-Views definieren
- Security-Boundary-Map erstellen
- Given-When-Then-Spezifikationen erstellen
```

### Dateien

```text
docs/implementation/event_model/00_method.md
docs/implementation/event_model/01_personas_swimlanes.md
docs/implementation/event_model/02_command_event_view_catalog.md
docs/implementation/event_model/03_scenario_slices.md
docs/implementation/event_model/04_field_origin_destination_matrix.md
docs/implementation/event_model/05_automation_todo_views.md
docs/implementation/event_model/06_security_boundary_map.md
docs/implementation/event_model/07_gwt_specs.md
```

### Tests / Checks

```bash
cd /home/thorsten/sealai && git status --short
```

### Akzeptanz

```text
- Jeder v0.8.3-Kernflow hat mindestens einen Slice.
- Jeder Slice hat Trigger, Command, Event(s), View, GWT-Test.
- RAG-Fallback, RFQ, Consent, Matching und Upload/Evidence sind modelliert.
- Keine Produktcodeänderung.
```

### Risiko

Niedrig, aber hoher strategischer Wert.

---

## PR 2 — Test Harness Repair

### Ziel

Backend-Service-Tests zuverlässig ausführbar machen.

### Audit-Grundlage

Der Audit meldet:

```text
backend/tests/unit/services/test_rfq_preview_service.py schlägt beim Import fehl:
alembic.config fehlt
```

### Aufgaben

```text
- Test-/Dev-Dependency prüfen
- Alembic-Testimport reparieren oder Testkonfiguration korrigieren
- keine produktive Migration
- keine Service-Neustarts
```

### Wahrscheinliche Dateien

```text
backend/requirements-dev.txt
backend/pytest.ini
pytest.ini
backend/tests/conftest.py
```

### Tests

```bash
cd /home/thorsten/sealai && python -c "import alembic.config"
cd /home/thorsten/sealai && python -m pytest backend/tests/unit/services/test_rfq_preview_service.py -q
```

### Akzeptanz

```text
- Der bisher fehlschlagende Test importiert sauber.
- Keine produktiven Einstellungen geändert.
- Keine Migration ausgeführt.
```

### Risiko

Niedrig bis mittel.

---

## PR 3 — ConversationIntent / ResponseMode Taxonomie

### Ziel

Small Talk, Knowledge und echte technische Fälle sauber trennen.

### Slice

```text
Trigger: User sends message
Command: ClassifyConversationIntent
Events:
- UserMessageReceived
- ConversationIntentClassified
- ResponseModeSelected
Views:
- ConversationFrontdoorView
- KnowledgeQuestionView
- NextBestQuestionView
```

### Aufgaben

```text
- stabile ConversationIntent-Werte einführen
- stabile ResponseMode-Werte einführen
- bestehende Pre-Gate-Klassifikation darauf mappen
- keine DB-Migration
- keine tiefen UI-Änderungen
```

### Tests

```text
- "Hallo" → small_talk, kein Case
- "Was ist FKM?" → general_sealing_question, kein Case
- "Diese Dichtung leckt schon wieder" → empathic_triage/failure candidate
- "Wir brauchen eine Dichtung für Getriebeöl" → governed domain inquiry / new_rfq candidate
- "Wer kann das herstellen?" → manufacturer_matching intent
- Off-topic → unsupported/off_topic
```

### Wahrscheinliche Dateien

```text
backend/app/domain/pre_gate_classification.py
backend/app/services/pre_gate_classifier.py
backend/app/agent/api/dispatch.py
backend/tests/unit/services/test_v083_conversation_routing.py
```

### Akzeptanz

```text
- Taxonomie ist code-level stabil.
- Alte Pre-Gate-Funktion bleibt kompatibel.
- Greetings/Knowledge erzeugen keine durable engineering case state.
```

### Risiko

Mittel, weil Routing alles Weitere beeinflusst.

---

## PR 4 — CaseType Projection Skeleton

### Ziel

v0.8.3-Szenarioachse etablieren.

### CaseTypes

```text
new_rfq
manufacturer_matching
compatibility_inquiry
complaint_case
failure_analysis
replacement_reorder
unknown_legacy_part
drawing_review
quote_comparison
compliance_certificate_request
material_substitution
emergency_mro
manufacturer_support_intake
general_knowledge
```

### Aufgaben

```text
- CaseType als Domain-/Projection-Primitive einführen
- alte request_type / engineering_path-Heuristiken darauf mappen
- Workspace Projection um CaseType ergänzen
- keine alten Felder löschen
- keine DB-Migration
```

### Wahrscheinliche Dateien

```text
backend/app/api/v1/schemas/case_workspace.py
backend/app/api/v1/projections/workspace_routing.py
backend/tests/unit/domain/test_case_type_projection.py
```

### Tests

```text
- alle CaseTypes shallow recognition
- general_knowledge erzeugt keinen technischen Case
- manufacturer_matching wird nicht blockiert, sondern als Partnernetzwerk-Fit verstanden
```

### Akzeptanz

```text
- CaseType ist in Projection sichtbar.
- Alte Seams funktionieren weiter.
- Kein Feature wird tief implementiert.
```

### Risiko

Mittel.

---

## PR 5 — ArtifactType Registry

### Ziel

Artefakte als stabile Produktprimitive einführen.

### ArtifactTypes

```text
rfq_preview
manufacturer_fit_matrix
technical_inquiry_summary
compatibility_matrix
complaint_intake
failure_analysis_intake
replacement_sheet
legacy_part_intake
drawing_review
quote_comparison
compliance_checklist
material_substitution_brief
emergency_triage
customer_reply_draft
internal_engineering_note
```

### Aufgaben

```text
- Registry / Enum / Literal-Typen einführen
- RFQ Preview als erster implementierter Adapter
- andere Artefakte als recognized_not_implemented markieren
- String drift verhindern
```

### Wahrscheinliche Dateien

```text
backend/app/domain/artifact_types.py
backend/app/models/inquiry_extract.py
backend/app/services/rfq_preview_service.py
backend/tests/unit/domain/test_artifact_type_registry.py
```

### Tests

```text
- alle ArtifactTypes registriert
- RFQ bleibt kompatibel
- unbekannte ArtifactTypes werden abgelehnt
```

### Akzeptanz

```text
- Keine breite Artifact-Engine.
- Nur stabile Typisierung.
```

### Risiko

Niedrig bis mittel.

---

## PR 6 — SealType Normalization Baseline

### Ziel

Dichtungstypen als eigene technische Achse implementieren.

### Slice

```text
Trigger: User mentions seal type
Command: NormalizeSealType
Events:
- SealTypeCandidateDetected
- SealTypeNormalized
- SealApplicationProfileUpdated
Views:
- SealApplicationProfileView
- TypeSpecificQuestionView
```

### Aufgaben

```text
- SealFamily einführen
- SealType einführen
- zentrale Alias-Normalisierung
- SealApplicationProfile read-only projection
- keine autoritative Field Confirmation
```

### Tests

```text
RWDR / WDR / Simmerring / Wellendichtring → radial_shaft_seal
Flachdichtung / Flanschdichtung → flat_gasket / flange_gasket
Stangendichtung → hydraulic_rod_seal oder uncertain nach Kontext
Kolbendichtung → hydraulic_piston_seal oder uncertain nach Kontext
Pneumatikdichtung → pneumatic seal family
O-Ring → o_ring
X-Ring → x_ring
Gleitringdichtung → mechanical_seal
Stopfbuchspackung → gland_packing
Sonderprofil → custom_profile
unbekannt → unknown_seal mit confidence note
```

### Wahrscheinliche Dateien

```text
backend/app/domain/seal_types.py
backend/app/domain/seal_type_normalization.py
backend/app/api/v1/projections/workspace_routing.py
backend/tests/unit/domain/test_seal_type_normalization.py
```

### Akzeptanz

```text
- Alias-Mapping zentral und testbar.
- Unknown bleibt unknown, nicht geraten.
- SealType beeinflusst noch keine finalen Empfehlungen.
```

### Risiko

Mittel.

---

## PR 7 — Needs Analysis / Current-State / Next Best Question

### Ziel

SeaLAI fragt präzise und empathisch statt formularhaft.

### Slice

```text
Trigger: Case or intake state updated
Command: GenerateNextBestQuestion
Events:
- IntakeConversationStateUpdated
- MissingInformationIdentified
- NextBestQuestionGenerated
View:
- NextBestQuestionView
```

### Aufgaben

```text
- Bedürfnisse des Nutzers erfassen
- Ist-Zustand erfassen
- CaseType + SealType + missing fields auswerten
- maximal 1-3 Fragen
- Emergency: genau eine wichtigste Frage
- kurze technische Begründung pro Frage
```

### Tests

```text
- keine 10-Fragen-Liste
- keine bereits beantwortete Frage
- RWDR fragt zuerst sinnvoll nach Druckdifferenz/Drehzahl/Medium
- Flachdichtung fragt nach Flansch/Norm/Druck/Temperatur
- Hydraulik fragt nach Stange/Kolben/Druck/Fluid
- Emergency fragt nur eine wichtigste Frage
```

### Wahrscheinliche Dateien

```text
backend/app/agent/runtime/clarification_priority.py
backend/app/services/decision_understanding_service.py
backend/app/api/v1/projections/case_workspace.py
backend/tests/unit/services/test_next_best_question.py
```

### Risiko

Mittel.

---

## PR 8 — SourceType / ValidationStatus Propagation

### Ziel

Jede Information hat Quelle und Validierungsstatus.

### SourceTypes

```text
rag_verified
partner_verified
manufacturer_documented
uploaded_evidence
user_stated
deterministic_calculation
llm_research_fallback
unknown
```

### ValidationStatus

```text
validated
documented
self_declared
user_stated
candidate
unvalidated
conflicting
rejected
```

### Aufgaben

```text
- Metadaten in State/Projection einführen
- bestehende CaseField/EngineeringValue-Struktur nicht zerstören
- Upload-Werte bleiben candidates/documented
- LLM-Fallback kann nie validated sein
```

### Tests

```text
- user_stated bleibt user_stated
- uploaded evidence bleibt candidate/documented
- deterministic calculation bekommt deterministic source
- fallback bekommt unvalidated
- conflict bleibt sichtbar
```

### Wahrscheinliche Dateien

```text
backend/app/agent/state/models.py
backend/app/agent/state/reducers.py
backend/app/api/v1/schemas/case_workspace.py
backend/app/api/v1/projections/case_workspace.py
backend/tests/unit/services/test_validation_status_projection.py
```

### Risiko

Mittel bis hoch, weil viele Projektionen betroffen sein können.

---

## PR 9 — Knowledge Answer RAG-first Contract

### Ziel

Allgemeine Dichtungstechnik-Fragen zuerst aus RAG/kuratierter Knowledge beantworten.

### Slice

```text
Trigger: User asks general technical question
Command: AnswerKnowledgeQuestion
Events:
- KnowledgeQuestionReceived
- KnowledgeRAGLookupRequested
- KnowledgeRAGAnswerFound or KnowledgeRAGAnswerMissing
- KnowledgeAnswerGenerated
View:
- KnowledgeAnswerView
- SourceValidationBadgeView
```

### Aufgaben

```text
- KnowledgeService auf RAG-first Contract bringen
- Factcards als curated knowledge integrieren
- RAG-miss maschinenlesbar machen
- noch kein LLM-Fallback aktivieren, falls Labels nicht fertig sind
```

### Tests

```text
- RAG/Factcard-Hit wird gelabelt
- RAG-miss wird erkannt
- keine Case-Erzeugung für "Was ist FKM?"
- keine case-specific suitability
```

### Wahrscheinliche Dateien

```text
backend/app/services/knowledge_service.py
backend/app/services/rag/rag_orchestrator.py
backend/tests/unit/services/test_knowledge_answer_rag_first.py
```

### Risiko

Hoch, weil Trust-kritisch.

---

## PR 10 — LLM Research Fallback mit Nicht-validiert-Label

### Ziel

Bei RAG-Miss darf LLM helfen, aber niemals als validierte Wahrheit.

### Slice

```text
Trigger: RAG miss and fallback allowed
Command: RunLLMResearchFallback
Events:
- KnowledgeRAGAnswerMissing
- LLMResearchFallbackUsed
- SourceValidationStatusAssigned
- KnowledgeAnswerGenerated
View:
- KnowledgeAnswerView
- SourceValidationBadgeView
```

### Aufgaben

```text
- fallback optional und config-gated
- Label: "LLM-Recherche — nicht validiert"
- use_scope: general orientation only
- nicht als CaseFieldConfirmed nutzbar
- nicht als compliance evidence nutzbar
```

### Tests

```text
- fallback nur bei RAG-miss
- fallback disabled → kein fallback
- fallback source_type=llm_research_fallback
- validation_status=unvalidated
- fallback kann kein confirmed field erzeugen
```

### Wahrscheinliche Dateien

```text
backend/app/services/knowledge_service.py
backend/app/agent/runtime/conversation_runtime.py
frontend/src/lib/contracts/workspace.ts
frontend/src/components/dashboard/*
backend/tests/unit/services/test_llm_fallback_labeling.py
```

### Risiko

Hoch.

---

## PR 11 — RFQ v0.8.3 Contract Hardening

### Ziel

Bestehende RFQ-Preview auf v0.8.3 heben.

### Aufgaben

```text
- RFQ aus Field Envelopes prüfen/härten
- SourceType/ValidationStatus in RFQ sichtbar machen
- case_revision freeze beibehalten
- stale handling beibehalten
- Consent um export_intent und ggf. partner_network_disclosure prüfen
```

### Tests

```text
- RFQPreviewGenerated
- RFQPreviewFrozenToCaseRevision
- confirmed/documented/user_stated/inferred/calculated/conflicting/missing getrennt
- stale preview blockiert consent/export
- no final technical release acknowledgement erforderlich
```

### Wahrscheinliche Dateien

```text
backend/app/services/rfq_preview_service.py
backend/app/api/v1/endpoints/rfq.py
frontend/src/components/dashboard/RfqPane.tsx
```

### Risiko

Mittel.

---

## PR 12 — Manual RFQ Export Allowlist

### Ziel

Sicherer manueller Export ohne Dispatch.

### Aufgaben

```text
- Export aus frozen preview
- allowlisted sections/documents
- keine versteckten Anhänge
- keine Herstellerkontakte
- kein automatischer Versand
```

### Tests

```text
- Export ohne Consent blockiert
- stale preview blockiert
- nur approved sections enthalten
- keine internen Pfade
- kein Dispatch
```

### Wahrscheinliche Dateien

```text
backend/app/api/v1/endpoints/rfq.py
backend/app/services/rfq_preview_service.py
backend/app/api/v1/renderers/rfq_html.py
frontend/src/app/api/bff/rfq/*
```

### Risiko

Mittel bis hoch, wegen IP/Consent.

---

## PR 13 — Decision Understanding UI

### Ziel

Decision Understanding wird sichtbarer Produktkern.

### Aufgaben

```text
- backend projection contract prüfen
- UI-Panel bauen
- Known / Missing / Risks / Next Question / Manufacturer Review Needs anzeigen
- Source/Validation Labels anzeigen
```

### Tests

```text
- Panel rendert understood_now
- Panel rendert not_yet_decidable
- Panel rendert key_risks
- Panel rendert next_best_question
- keine unsafe Copy
```

### Dateien

```text
frontend/src/components/dashboard/DecisionUnderstandingPanel.tsx
frontend/src/lib/contracts/workspace.ts
frontend/src/lib/mapping/workspace.ts
frontend/src/components/dashboard/CaseScreen.tsx
```

### Risiko

Mittel.

---

## PR 14 — Upload Evidence UI + Path Redaction

### Ziel

Uploads werden als Evidence/Kandidaten sichtbar; interne Pfade verschwinden aus User-UI.

### Aufgaben

```text
- user-facing filesystem.path entfernen oder admin-gaten
- document-derived values als candidates zeigen
- evidence refs sichtbarer machen
- prompt-injection warning nicht übertreiben, aber sauber handhaben
```

### Tests

```text
- RAG health response für normale User ohne interne Pfade
- UI zeigt candidate/documented, nicht confirmed
- parser errors safe
```

### Dateien

```text
backend/app/api/v1/endpoints/rag.py
frontend/src/lib/ragApi.ts
frontend/src/components/rag/RagDocumentGrid.tsx
```

### Risiko

Mittel.

---

## PR 15 — Compliance / Chemical / MCP Claim Guard

### Ziel

Alte overclaim-riskante Tool-Ausgaben entschärfen.

### Aufgaben

```text
- MCP compliance/chemical outputs prüfen
- user-visible Renderer/Guard ergänzen
- "geeignet", "konform", "zugelassen", "validiert" nur mit Evidence
- sonst "prüfungsrelevant", "Herstellerprüfung erforderlich"
```

### Tests

```text
- FDA overclaim wird verhindert
- ATEX overclaim wird verhindert
- Food/Pharma/Drinking Water overclaim wird verhindert
- Chemical suitability wird nicht final dargestellt
```

### Dateien

```text
backend/app/mcp/calculations/compliance.py
backend/app/mcp/calculations/chemical_resistance.py
backend/app/agent/runtime/output_guard.py
backend/tests/test_mcp_compliance_claim_guard.py
```

### Risiko

Hoch, trust-kritisch.

---

## PR 16 — Partner Eligibility + Capability Projection

### Ziel

Paid SeaLAI Partner Network als saubere Eligibility-Schicht.

### Aufgaben

```text
- vorhandene manufacturer_profiles/capability_claims prüfen
- active_paid oder is_paid_partner ableiten/ergänzen
- capabilities read-only projizieren
- verification_level sichtbar machen
- keine UI noch
```

### Tests

```text
- inactive ausgeschlossen
- unpaid ausgeschlossen
- active paid eingeschlossen
- verification_level sichtbar
```

### Dateien

```text
backend/app/services/capability_service.py
backend/app/models/*
backend/tests/unit/services/test_partner_eligibility.py
```

### Hinweis

Falls eine DB-Änderung nötig ist:

```text
Migration nur erstellen, nicht produktiv ausführen.
```

### Risiko

Mittel bis hoch.

---

## PR 17 — Manufacturer Fit Matrix Backend

### Ziel

Technische Fit-Matrix innerhalb des Partnernetzwerks.

### Slice

```text
Trigger: User requests suitable manufacturer
Command: ComputeManufacturerFitMatrix
Events:
- ManufacturerFitRequested
- PartnerCandidatesFiltered
- ManufacturerFitComputed or NoSuitablePartnerFound
- PartnerNetworkDisclosureAttached
View:
- ManufacturerFitMatrixView
- PartnerDisclosureView
```

### Aufgaben

```text
- active paid eligible partners filtern
- technischen Fit berechnen
- fit_reasons
- gaps
- missing_requirements
- no suitable partner state
- disclosure
- payment tier beeinflusst score nicht
```

### Tests

```text
- unpaid perfect partner erscheint nicht
- active paid non-fit erscheint nicht oder als gap/low fit
- no-fit supported
- sponsored/listing tier ändert score nicht
- disclosure immer vorhanden
```

### Dateien

```text
backend/app/services/problem_first_matching_service.py
backend/app/services/manufacturer_fit_matrix_service.py
backend/app/api/v1/schemas/*
backend/tests/unit/services/test_manufacturer_fit_matrix.py
```

### Risiko

Hoch.

---

## PR 18 — Manufacturer Fit UI

### Ziel

Fit-Matrix transparent anzeigen.

### Aufgaben

```text
- UI-Panel / Tab
- Partnernetzwerk-Disclosure
- Fit reasons
- Gaps
- No-fit state
- kein "bester Hersteller im Markt"
- kein automatischer Versand
```

### Tests

```text
- disclosure sichtbar
- no-fit sichtbar
- keine verbotene Copy
- kein "An Hersteller senden"
```

### Dateien

```text
frontend/src/components/dashboard/ManufacturerFitPanel.tsx
frontend/src/lib/contracts/workspace.ts
frontend/src/lib/mapping/workspace.ts
frontend/src/lib/unsafeProductCopy.spec.ts
```

### Risiko

Mittel.

---

## PR 19 — Compatibility Inquiry Artifact

### Ziel

Kompatibilitätsanfragen wie WDR + FKM + Ölbericht strukturiert bearbeiten.

### Aufgaben

```text
- compatibility_inquiry CaseType nutzen
- product designation extrahieren
- lab values als candidates
- missing values/units/methods identifizieren
- compatibility_matrix / technical_inquiry_summary erzeugen
- keine finale Kompatibilitätsfreigabe
```

### Tests

```text
- WDR AS 75x95x10 DIN 3760 FKM FDA erkannt
- Wasser/Natrium/Kalium als prüfungsrelevant
- exakte Werte/Einheiten fehlen → offene Punkte
- kein finaler Grenzwertclaim
```

### Dateien

```text
backend/app/services/compatibility_inquiry_service.py
backend/app/domain/artifact_types.py
backend/tests/unit/services/test_compatibility_inquiry.py
```

### Risiko

Mittel bis hoch.

---

## PR 20 — Customer Reply Draft + Internal Engineering Note

### Ziel

Sichere Herstellerantworten und interne Anwendungstechnik-Notizen.

### Aufgaben

```text
- customer_reply_draft generieren
- internal_engineering_note generieren
- offene Punkte sichtbar
- Hersteller-/Compoundprüfung fordern
- keine Haftungsannahme
```

### Tests

```text
- draft ist hilfreich, nicht final
- draft fragt fehlende Daten ab
- internal note enthält evidence/open points
- no liability admission
```

### Risiko

Mittel bis hoch.

---

## PR 21 — Complaint / Failure Intake

### Ziel

Reklamation und Ausfallanalyse als Intake, nicht als finale Ursache.

### Aufgaben

```text
- complaint_case
- failure_analysis
- damage pattern
- operating conditions
- photo/evidence request
- no final root cause
```

### Tests

```text
- "Dichtung nach 3 Monaten ausgefallen" → failure intake
- "leckt wieder" → complaint/failure triage
- keine RootCauseConfirmed
- keine Schuld-/Haftungsaussage
```

### Risiko

Mittel.

---

## PR 22 — Replacement / Legacy Part Intake

### Ziel

Altteil-/Ersatzteilchaos strukturieren.

### Aufgaben

```text
- replacement_reorder
- unknown_legacy_part
- Maße/Fotos/Altbezeichnung/ERP-Daten
- identity confidence
- keine 1:1-Austauschbarkeit behaupten
```

### Tests

```text
- "auf dem Teil steht nur 75x95x10" → legacy/replacement
- identity uncertain
- required photos/measures listed
```

### Risiko

Mittel.

---

## PR 23 — Compliance Certificate Checklist

### Ziel

Zertifikatsanforderungen sichtbar, aber nicht final freigeben.

### Aufgaben

```text
- compliance_certificate_request
- FDA / EU 1935 / USP VI / ATEX / TA-Luft etc.
- material family vs compound vs certificate trennen
- evidence required states
```

### Tests

```text
- "FKM FDA" ≠ Anwendung freigegeben
- certificate request artifact
- no compliance approval without evidence
```

### Risiko

Hoch, claimsensibel.

---

## PR 24 — Shallow Modes: Drawing / Quote / Material Substitution / Emergency

### Ziel

Szenarien erkennen und sicher triagieren, ohne tief zu überbauen.

### Aufgaben

```text
- drawing_review shallow
- quote_comparison shallow
- material_substitution shallow
- emergency_mro shallow
```

### Tests

```text
- drawing upload → drawing review candidate
- quotes → quote comparison candidate, keine billigste Empfehlung
- PFAS/FKM replacement → substitution risk brief, keine pauschale Alternative
- "Anlage steht" → emergency, eine wichtigste Frage
```

### Risiko

Mittel.

---

## PR 25 — Tenant / Artifact / IDOR Test Sweep

### Ziel

Cross-tenant-Leaks verhindern, bevor Artifacts und Matching breiter werden.

### Aufgaben

```text
- RFQ preview access negative tests
- consent negative tests
- upload/document negative tests
- artifact negative tests
- matching artifact negative tests
```

### Tests

```text
user A cannot read user B RFQ
user A cannot consent user B preview
user A cannot read user B artifact
user A cannot read user B document
cross-tenant IDs return 403/404
```

### Risiko

Hoch, security-kritisch.

---

## PR 26 — Observability / Audit Events

### Ziel

Business- und Trust-relevante Übergänge auditierbar machen.

### Events

```text
RFQPreviewGenerated
RFQConsentGranted
ExportGenerated
ManufacturerFitComputed
NoSuitablePartnerFound
LLMResearchFallbackUsed
ArtifactMarkedStale
TenantAccessDenied
UploadRejected
```

### Tests

```text
- audit entries enthalten tenant/case/revision/source
- keine Secrets in Logs
- fallback use ist auditierbar
```

### Risiko

Mittel.

---

## PR 27 — v0.8.3 Regression & Acceptance

### Ziel

End-to-End-Abnahme gegen Konzept.

### Aufgaben

```text
- Kernflows durchtesten
- unsafe copy sweep
- prompt injection regression
- fallback regression
- matching disclosure regression
- RFQ consent regression
- tenant regression
```

### Akzeptanz

```text
- alle Kernflows haben Slice + Tests
- kein LLM-Fallback als validated
- kein Matching ohne Disclosure
- kein Export ohne Consent
- kein automatischer Dispatch
- kein finaler Claim
```

### Risiko

Mittel.

---

## 6. Abhängigkeiten und Gating-Regeln

### Matching darf erst nach diesen PRs sichtbar werden

```text
PR 3 Conversation Routing
PR 4 CaseType
PR 6 SealType
PR 8 Source/Validation
PR 15 Claim Guard
PR 16 Partner Eligibility
PR 17 Backend Fit Matrix
```

UI erst danach:

```text
PR 18 Manufacturer Fit UI
```

---

### LLM-Fallback darf erst sichtbar werden nach

```text
PR 8 Source/Validation
PR 9 RAG-first
PR 10 Fallback labeling
```

---

### Support-/Complaint-Drafts dürfen erst sichtbar werden nach

```text
PR 8 Source/Validation
PR 15 Claim Guard
PR 19 Compatibility Inquiry
PR 20 Draft/Note
```

---

### Export darf erst erweitert werden nach

```text
PR 11 RFQ v0.8.3 Hardening
PR 12 Export Allowlist
PR 25 Tenant/Artifact IDOR Sweep
```

---

### Kein Dispatch vor v0.8.3

Auch wenn Export funktioniert:

```text
Keine automatische Herstellerkommunikation.
Keine "An Hersteller senden"-UI.
Kein echter Versand.
```

---

## 7. Teststrategie

## 7.1 Mindesttests pro PR

Jeder PR braucht:

```text
- Unit- oder Contract-Tests
- relevante Existing Tests
- keine "should work"-Behauptungen
- exakte Befehle aus /home/thorsten/sealai
```

---

## 7.2 Kern-Testgruppen

```text
Conversation Routing
CaseType Mapping
ArtifactType Registry
SealType Normalization
Next Best Question
SourceType / ValidationStatus
RAG-first Knowledge
LLM Fallback Label
RFQ Freeze / Consent / Stale
Upload/IP Safety
Compliance Claim Guard
Manufacturer Eligibility
Manufacturer Fit Matrix
Decision Understanding UI
Support / Compatibility / Complaint
Tenant / IDOR
Prompt Injection
Unsafe Copy
```

---

## 7.3 Audit-bewährte Kommandos

Diese liefen laut Audit erfolgreich:

```bash
cd /home/thorsten/sealai && python -m pytest backend/app/agent/tests/test_interaction_policy.py backend/app/agent/tests/test_output_guard.py backend/app/agent/tests/test_document_delta.py -q
```

```bash
cd /home/thorsten/sealai && python -m pytest backend/app/api/tests/test_rag_upload_limits.py backend/app/api/tests/test_rag_upload.py -q
```

```bash
cd /home/thorsten/sealai && python -m pytest backend/app/api/tests/test_rfq_endpoint.py -q
```

```bash
cd /home/thorsten/sealai && npm --prefix frontend run lint
```

```bash
cd /home/thorsten/sealai && npm --prefix frontend run test:run -- src/lib/unsafeProductCopy.spec.ts src/components/dashboard/RfqPane.test.tsx
```

---

## 7.4 Zu reparierender Test

```bash
cd /home/thorsten/sealai && python -m pytest backend/tests/unit/services/test_rfq_preview_service.py -q
```

Aktuelles Problem laut Audit:

```text
Importfehler: alembic.config fehlt
```

Das gehört in PR 2.

---

## 8. Risiko-Register

| Risiko | Schwere | Warum kritisch | Gegenmaßnahme |
|---|---:|---|---|
| Dirty Worktree / ignoriertes Konzept | hoch | Codex kann falschen Stand umsetzen | PR 0 |
| Routing Drift | hoch | Falsche Fälle erzeugen falsche Workflows | PR 3 + PR 4 |
| SealType Misclassification | hoch | falsche Fragen, falsches Matching | PR 6 |
| Knowledge ohne RAG/Fallback-Label | hoch | Halluzination/Trust-Risiko | PR 9 + PR 10 |
| Compliance/Chemical Overclaims | hoch | rechtlich/vertrauensrelevant | PR 15 |
| Matching ohne Disclosure | hoch | wirkt wie versteckte Werbung | PR 16–18 |
| Tenant/IDOR bei Artifacts | hoch | B2B-IP-Leak | PR 25 |
| Export ohne Allowlist | hoch | Dokument-/IP-Risiko | PR 12 + PR 25 |
| UI erfindet Wahrheit | mittel/hoch | Inkonsistente Produktlogik | PR 13 + Contract Tests |
| Too broad PRs | mittel | Rework und schwer reviewbar | Event-Modeled Slice-Regel |

---

## 9. Empfohlener Codex-Arbeitsmodus

### Standard

```text
Ein PR = ein Slice oder eine kleine Gruppe eng verwandter Slices.
```

### Codex Reasoning

```text
PR 0–2: High
PR 3–8: High
PR 9–10: XHigh
PR 11–15: High / XHigh
PR 16–18 Matching: XHigh
PR 19–23 Support/Compliance: XHigh
PR 25 Security: XHigh oder Pro Review
```

### Codex darf pro PR melden

```text
1. Short diagnosis
2. Slice implemented
3. Files changed
4. Why these files
5. Behavioral delta
6. Validation commands/results
7. Risks/limitations
8. Next productive patch
```

---

## 10. Sofort nächster sinnvoller Auftrag an Codex

Nicht direkt PR 3 umsetzen.

Zuerst:

```text
PR 0 — Repo Baseline, SSoT und Worktree Hygiene
```

Danach:

```text
PR 1 — Event Model Blueprint
```

Dann:

```text
PR 2 — Test Harness Repair
```

Erst danach:

```text
PR 3 — ConversationIntent / ResponseMode Taxonomie
```

Das weicht bewusst leicht vom Audit-Vorschlag ab. Der Audit empfahl Conversation Routing als nächstes. Nach Einführung des v0.8.3-Event-Modeling-Konzepts ist es professioneller, vorher SSoT und Blueprint zu sichern.

---

## 11. Ready-to-paste Prompt für PR 0

```text
You are working in /home/thorsten/sealai.

Read AGENTS.md first.
Then read:
- konzept/SEALAI_V08_2_STACK_AUDIT_IST.md
- konzept/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md if present
- konzept/SEALAI_V08_2_CODEX_IMPLEMENTATION_CONCEPT.md
- konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md

Implement only PR 0: Repo Baseline, SSoT and Worktree Hygiene.

This is a preparation PR only.

Goals:
1. Inspect current git status and branch.
2. Determine which concept/audit files are ignored by git.
3. Make the active v0.8.3 concept and the current IST audit available in a tracked location, preferably docs/implementation/.
4. Update AGENTS.md only if needed so it points to the active v0.8.3 concept and the current audit.
5. Do not change product behavior.
6. Do not modify backend/frontend business logic.
7. Do not delete files unless they are clearly accidental and you report it first in the final summary.

Do not run migrations.
Do not restart services.
Do not stop services.
Do not clear Redis or Qdrant.
Do not print secrets or .env values.
Do not deploy.
Do not contact external APIs.
Do not send RFQs.
Do not contact manufacturers.

Allowed commands:
- pwd
- git status --short
- git branch --show-current
- ls -al
- git check-ignore -v <file> || true
- safe file reads
- safe file copies into docs/implementation/

After the patch, run:
cd /home/thorsten/sealai && git status --short

Final report:
1. Short diagnosis
2. Exact files changed
3. Why these files
4. Behavioral delta, expected to be "none"
5. Validation command and result
6. Risks / limitations
7. Next productive patch
```

---

## 12. Ready-to-paste Prompt für PR 1

```text
You are working in /home/thorsten/sealai.

Read AGENTS.md first.
Then read the tracked active v0.8.3 concept and the current IST audit.

Implement only PR 1: Event Model Blueprint.

This is documentation/blueprint only.
Do not change product code.
Do not change backend logic.
Do not change frontend logic.
Do not create migrations.
Do not restart services.
Do not expose secrets.
Do not deploy.

Create the event-model blueprint under a tracked path, preferably:

docs/implementation/event_model/00_method.md
docs/implementation/event_model/01_personas_swimlanes.md
docs/implementation/event_model/02_command_event_view_catalog.md
docs/implementation/event_model/03_scenario_slices.md
docs/implementation/event_model/04_field_origin_destination_matrix.md
docs/implementation/event_model/05_automation_todo_views.md
docs/implementation/event_model/06_security_boundary_map.md
docs/implementation/event_model/07_gwt_specs.md

The blueprint must be based on:
- SeaLAI v0.8.3 concept
- current IST audit
- existing stack evidence from the audit

Acceptance:
- Every v0.8.3 core flow has at least one Slice.
- Each Slice has Trigger, Command, Event(s), View and Given-When-Then.
- RAG fallback is modeled as unvalidated.
- Manufacturer matching includes active paid partner eligibility, disclosure and no-fit.
- RFQ includes revision freeze, consent, stale and export slices.
- Upload/evidence is modeled as candidate/evidence, never truth.
- Security boundaries are explicitly modeled.

Run:
cd /home/thorsten/sealai && git status --short

Final report:
1. Short diagnosis
2. Files changed
3. Why these files
4. Behavioral delta, expected to be "none"
5. Validation command and result
6. Risks / limitations
7. Next productive patch
```

---

## 13. Ready-to-paste Prompt für PR 2

```text
You are working in /home/thorsten/sealai.

Read AGENTS.md, the active v0.8.3 concept, the IST audit, and existing backend test configuration.

Implement only PR 2: Test Harness Repair.

The audit found that:
python -m pytest backend/tests/unit/services/test_rfq_preview_service.py -q
fails during import because alembic.config is not available in the local environment.

Goal:
Make the local test harness reliable for backend/tests without production side effects.

Rules:
- Do not run migrations.
- Do not restart services.
- Do not stop services.
- Do not touch production data.
- Do not print secrets.
- Do not deploy.
- Do not change product behavior unless required for test configuration correctness.
- Prefer dev/test dependency or config fixes over application changes.

Inspect:
- backend/requirements-dev.txt
- backend/requirements.txt
- pytest.ini
- backend/pytest.ini
- backend/tests/conftest.py
- pyproject.toml/setup.cfg if present

Run validation:
cd /home/thorsten/sealai && python -c "import alembic.config"
cd /home/thorsten/sealai && python -m pytest backend/tests/unit/services/test_rfq_preview_service.py -q
cd /home/thorsten/sealai && python -m pytest backend/app/api/tests/test_rfq_endpoint.py -q

Final report:
1. Short diagnosis
2. Exact files changed
3. Why these files
4. Behavioral delta
5. Validation commands/results
6. Risks / limitations
7. Next productive patch
```

---

## 14. Definition of Done für v0.8.3

v0.8.3 gilt als umgesetzt, wenn:

```text
- Codex kann jeden Kernflow als Event-Modeled Slice zeigen.
- Small Talk und allgemeine Fragen erzeugen keinen Engineering Case.
- Echte technische Fälle werden governed geroutet.
- CaseType, ArtifactType, SealType sind stabile Primitives.
- SeaLAI fragt präzise Next-Best-Questions.
- RAG-first ist implementiert.
- LLM-Fallback ist sichtbar nicht validiert.
- RFQ Preview bleibt revision-frozen und consent-gated.
- Export ist allowlisted und ohne Dispatch.
- Decision Understanding ist im UI sichtbar.
- Manufacturer Matching nutzt nur aktive zahlende Partner.
- Payment beeinflusst den technischen Fit Score nicht.
- Partnernetzwerk-Disclosure ist immer sichtbar.
- No Suitable Partner ist möglich.
- Compatibility/Complaint/Failure sind safe Artifacts, keine finalen Claims.
- Uploads sind Evidence, nie Instructions.
- Tenant/IDOR-Tests schützen RFQ, Artifacts, Uploads, Consent und Matching.
- Compliance/Chemical Overclaims sind regressionsfest verhindert.
- Frontend zeigt keine unsafe Copy.
```

---

## 15. Harte Stop-Regeln

Sofort stoppen und menschlich entscheiden, wenn ein PR erfordert:

```text
- produktive Migration ausführen
- Daten löschen
- Service neu starten
- Secrets anzeigen/rotieren
- Hersteller kontaktieren
- RFQ senden
- Deployment ändern
- Ranking gegen Payment-Regeln ändern
- Compliance-/Materialfreigabe als final ausgeben
```

---

## 16. Wichtigstes Fazit

Der aktuelle Stack ist gut genug, um v0.8.3 umzusetzen. Aber die Umsetzung darf nicht direkt mit Matching oder Support-Drafts beginnen.

Die richtige Reihenfolge ist:

```text
SSoT sichern
→ Event Model Blueprint
→ Test Harness
→ Routing/Taxonomy
→ SealType
→ Source/Validation
→ RAG/Fallback
→ RFQ
→ UI Trust
→ Matching
→ Support/Complaint
→ Security/Acceptance
```

Das ist der Weg, der SeaLAI professionell, vertrauenswürdig und Codex-tauglich macht.
