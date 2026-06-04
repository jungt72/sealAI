# SealAI V9.1 Stack Deep-Dive Audit

Status: 2026-05-13
Active SSoT: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md`
Scope: aktueller Code-Stack gegen V9.1 Final Zielbild

## Executive Verdict

Der Stack ist nicht grüne Wiese und nicht kaputt. Er enthält bereits starke V8/V9-Bausteine:

- harte Runtime-Grenze vor LangGraph über `RuntimeAction`
- geschichtetes Case-State-Modell mit `ObservedState -> NormalizedState -> AssertedState -> Derived/Governance/Decision`
- RAG mit Tenant-/Shared-Tenant-Policy, Paperless-Sync und manuellem Sync-Endpunkt
- Medium-, Material- und Challenge-Intelligence als reale Backend-Funktionen
- RFQ Preview/Export als consent-gated, dispatch-blocked Boundary
- Frontend-Workspace mit Chat, Parameterformular, RAG-UI, Tabs und BFF-Stream

Aber: V9.1 Final ist noch nicht die Laufzeitarchitektur. Der Code hat viele richtige Inseln, aber noch keine klare V9.1-Kette:

```text
SemanticBoundaryDecision
-> LLMFreedomDecision / RedFlags
-> ResponsePolicy / KnowledgePolicy
-> CandidateFact
-> FieldGovernance
-> IntelligenceState / TabState
-> QuestionPlan
-> CommunicationPlan
-> FinalAnswerContext
-> Final Composer
-> ClaimGuard + EvidenceGate + CommunicationGuard
```

Die aktuelle Produktwirkung leidet deshalb an genau dem, was der Nutzer im Browser beschrieben hat: Die App hat ein LLM angebunden, wirkt aber in konkreten Fällen stellenweise wie ein Routing-/Formularsystem. Das liegt weniger am Modell und mehr daran, dass der Stack noch nicht zwischen freier Erklärung, kontrollierter Zusage, Case-Mutation, RAG-Pflicht, Intelligence-Tab und nächster sinnvoller Frage in einem V9.1-Vertrag entscheidet.

Umbauempfehlung: kein Big-Bang-Rewrite. Die bestehenden Seams bleiben, aber V9.1 bekommt eine explizite Vertragsschicht und wird schrittweise in Dispatch, State, Challenge, Composer und Workspace-Projektion eingebaut.

## Evidence Map

### Zielbild und Agentenregeln

- `AGENTS.md`
  - setzt V9.1 Final als aktive Mission
  - schützt `RuntimeAction` vor LangGraph als harte Boundary
  - verlangt "Frei erklären. Zusagen kontrollieren."
  - verbietet rohe Chat-Historie als Case Truth
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md`
  - definiert die finale Produkt- und Runtime-Architektur
  - enthält die Zielschemas für Semantic Boundary, Freedom Decision, Case/Intelligence State, QuestionPlan, CommunicationPlan, Claim/Evidence/Communication Guards
- `docs/architecture/SSOT_REGISTRY.md`
  - markiert V9.1 Final als einzige aktive Produkt-SSoT

### Aktuelle Runtime

- `backend/app/agent/api/dispatch.py`
  - produktiver Pre-LangGraph-Seam
  - nutzt V8/V7 `TurnDecision` und `RuntimeAction`
  - enthält RAG-/Knowledge-Retriever und Runtime-Dispatch
- `backend/app/agent/communication/communication_runtime_v8.py`
  - klassifiziert grob in smalltalk/meta/knowledge/side-question/governed/blocking
  - optionaler LLM-Vorschlag ist stark begrenzt
  - noch kein V9.1 `SemanticBoundaryDecision`
- `backend/app/agent/communication/v7_contracts.py`
  - `RuntimeAction` ist eine gute Hard Boundary
  - `ClaimLevel` ist noch alte V7/V8-Taxonomie, nicht V9.1 L0-L4
- `backend/app/agent/communication/orchestrator.py`
  - existierende Human Communication Layer mit ModeRouter, ContextAssembler, Guard
  - gut als Übergangsschicht, aber nicht V9.1 Final Composer Pipeline
- `backend/app/agent/communication/llm_service.py`
  - promptet `LLMResponseContract`, nicht V9.1 `FinalAnswerContext`

### Case State und Governance

- `backend/app/agent/state/models.py`
  - starke mehrschichtige State-Basis
  - `ObservedExtraction` ist nahe an V9.1 `CandidateFact`, aber nicht exakt
  - `CaseField` hat Provenance, Status, Evidence, Confidence, Revision
  - fehlt als explizite V9.1 SSoT: `RawConversationHistory`, `ConversationTaskState`, `IntelligenceState`, `TabState`, `DialogueDebt`, `QuestionPlan`, `CommunicationPlan`
- `backend/app/agent/state/reducers.py`
  - kontrollierte Mutationssemantik vorhanden
- `backend/app/agent/graph/nodes/intake_observe_node.py`
  - schreibt nur ObservedState; gute V9.1-Grundlage
  - Kandidaten fehlen aber noch mit `source_message_id`, `source_quote`, `extraction_method`, `requires_user_confirmation`

### Graph, Challenge und Antwort

- `backend/app/agent/graph/topology.py`
  - bestehende technische LangGraph-Strecke: observe, normalize, assert, evidence, compute, challenge, governance, rfq, dispatch, output, governed answer
  - noch keine V9.1 Nodes für QuestionPlan/CommunicationPlan/FinalAnswerContext
- `backend/app/agent/domain/challenge_engine.py`
  - erzeugt Findings, Hypothesen und genau eine `NextBestQuestion`
  - gute V9-Vorstufe
  - V9.1 will `QuestionNeed[]` plus `QuestionPlan`, nicht nur isolierte NextBestQuestion
- `backend/app/agent/communication/governed_answer_composer.py`
  - guter Composer-Seam
  - Kontext ist aber noch `GovernedAnswerContext`, nicht V9.1 `FinalAnswerContext`
- `backend/app/agent/communication/guard.py`
  - prüft final approval, solution recommendation, fabricated evidence/claim IDs
  - aktuell Mischform aus ClaimGuard/CommunicationGuard
  - V9.1 braucht getrennte ClaimGuard, EvidenceGate, CommunicationGuard

### Knowledge / RAG / Paperless

- `backend/app/services/knowledge_service.py`
  - FactCards + RAG + optionaler LLM-Fallback
  - spricht bereits über Quelle, Validierung und Scope
  - noch keine formale V9.1 `KnowledgePolicy`
- `backend/app/agent/services/real_rag.py`
  - tenant_id ist Pflicht, harte Abbruchlogik gegen Cross-Tenant-Leakage
  - Hybrid -> BM25 -> Empty Fallback
- `backend/app/services/rag/rag_orchestrator.py`
  - Shared-Tenant `sealai` wird bei Retrieval zugemischt
  - private Sichtbarkeit über `user_id`-Filter
- `backend/app/services/rag/paperless.py`
  - Paperless bleibt Content Source
  - Sync nur bei explizitem RAG-Tag wie `sealai:rag`
  - fehlender Tag oder fehlendes Dokument deaktiviert lokale RAG-Records
- `backend/app/api/v1/endpoints/rag.py`
  - manueller Admin-Sync: `POST /api/v1/rag/sync-paperless?process=true`
  - interner Webhook: `POST /api/v1/internal/rag/ingest`
- `backend/app/agent/rag/paperless_tags.py`
  - vereinfachter Tag `sealai:rag` ist akzeptiert
  - Zusatzmetadaten werden konservativ aus Titel/Dateiname inferiert

### Medium, Material, RFQ

- `backend/app/services/medium_intelligence_service.py`
  - Registry-basierte Medium Intelligence existiert
  - teils noch englische Summary/Rationale, daher UI-/Kommunikationsdrift
- `backend/app/agent/services/medium_research.py`
  - Medium Deep Dive mit RAG, optional Web, Composer, Limitations
  - gute Grundlage für V9.1 Medium Intelligence
- `backend/app/agent/services/material_intelligence.py`
  - erzeugt Material-Kandidaten, Plausibility Class, Gründe, Cautions, Blocking Unknowns, RFQ-Relevanz
  - gute V9.1-Vorstufe
  - Score-Werte existieren intern und sind teils projektiert; V9.1 warnt gegen sichtbare Prozent-/Score-UX
- `backend/app/services/rfq_preview_service.py`
  - RFQ Preview/Export ist eingefroren, consent-gated, no-dispatch
  - `dispatch_enabled=False`, `automatic_dispatch_allowed=False`, no final technical release
  - gut. Muss aber V9.1 Intelligence/Challenge/QuestionPlan sauberer aufnehmen

### Frontend / BFF / UI

- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
  - streamt Backend-SSE in UI-SSE
  - mappt `state_update`, `answer_markdown`, `reply`, workspace, RFQ Readiness
- `frontend/src/hooks/useAgentStream.ts`
  - lädt History, streamt Chat, bindet Case, erzeugt GA-/SEO-Events `case_started` und `rfq_started`
- `frontend/src/components/dashboard/ChatPane.tsx`
  - Chat ist kartenarm und LLM-artiger geworden
  - bei frischem Start zentrierter Composer
- `frontend/src/components/dashboard/CaseScreen.tsx`
  - Chat links/mittig, Workspace rechts, Resizer vorhanden
  - Parameter-Submit kann ohne Case einen Chatturn starten; mit Case wird Patch-Agent-Override genutzt
- `frontend/src/components/dashboard/SealCockpit.tsx`
  - Tabs und Medium Intelligence werden clientseitig zusätzlich geladen
  - das ist funktional, aber V9.1 will Intelligence stärker als Backend-`TabState`/Workspace-Projektion
- `frontend/src/app/(app)/rag/page.tsx`
  - RAG-Upload UI vorhanden
  - Paperless-Sync selbst ist nicht als Frontend-Button sichtbar
- `frontend/src/lib/analytics/events.ts`
  - GA/GTM-Events sind vorbereitet und consent/env-gated

## Gap Matrix

| Area | Ist-Zustand | V9.1 Ziel | Severity |
| --- | --- | --- | --- |
| Semantic Boundary | V8 Runtime intent + regex/LLM proposal | typed `SemanticBoundaryDecision` mit intent, domain relevance, case binding, off-topic, utility, low-signal, red flags | P0 |
| LLM Freedom | implizit über RuntimeAction/ModeRouter | explizite `LLMFreedomDecision` mit allow/restrict/block und Gründen | P0 |
| ResponsePolicy | verteilt über dispatch/orchestrator/fallbacks | zentrale Policy pro Turn: answer-only, answer-then-resume, graph, ask, defer, block | P0 |
| CandidateFact | `ObservedExtraction` ist ähnlich | V9.1 CandidateFact mit source refs, quote, confidence, confirmation need | P0 |
| Field Governance | starke Reducer vorhanden | explizite `FieldGovernanceDecision` und auditierbare Revision Events pro Candidate | P1 |
| KnowledgePolicy | FactCards/RAG/Fallback vorhanden | entscheidet wann RAG Pflicht, optional, verboten, fehlend oder Fallback erlaubt ist | P1 |
| IntelligenceState | Medium/Material/Challenge existieren getrennt | ein kanonischer serverseitiger `IntelligenceState` mit Medium/Material/Challenge/Document/Compliance/Failure | P1 |
| TabState | Frontend rendert Projektionen | Backend-owned `TabState`/Workspace-Projektion als Quelle für Tabs | P1 |
| QuestionPlan | `NextBestQuestion` aus Challenge | `QuestionNeed[]` plus `QuestionPlan` mit Ziel, Grund, Blocker, expected answer, one-question policy | P0 |
| CommunicationPlan | kein zentrales Objekt | entscheidet Antwortstruktur, Tiefe, Ton, Frage, Tab-Hinweis, Recovery | P0 |
| FinalAnswerContext | `GovernedAnswerContext` / LLMResponseContract | V9.1 Kontext aus Policy, Intelligence, QuestionPlan, Tabs, allowed claims, evidence, dialogue debt | P0 |
| Guards | CommunicationGuard macht vieles | getrennte ClaimGuard, EvidenceGate, CommunicationGuard mit klaren Verantwortungen | P1 |
| RFQ | Boundary stark | V9.1 Challenge/Material/Medium/QuestionPlan in Preview als Kontext, nicht Vorgabe | P1 |
| Paperless/RAG | technisch vorhanden | als Document Intelligence im V9.1 State sichtbar, mit manual sync UX und readiness | P2 |
| Frontend UX | Chat/Workspace funktional | Chat zeigt knappe Kommunikation; Tabs zeigen tiefe Intelligence; keine Formularbot-Wirkung | P1 |
| Tests | viele V7/V8/V9 Tests | V9.1 Golden Conversations + Boundary Evals fehlen als explizite Suite | P1 |
| Domain Routing | sealingai.com teilweise sauber | backend default `frontend_origin` noch `sealai.net`; Env-Beispiele haben Duplikate | P2 |

## Wichtigste Findings

### P0. Die V9.1-Laufzeitverträge fehlen als Code

Die Final-Konzeptbegriffe sind in AGENTS und Konzept vorhanden, aber nicht als stabile Python-/TypeScript-Contracts. Dadurch "weiß" der Stack nicht explizit, ob er gerade frei erklären, kontrolliert antworten, RAG erzwingen, Case-Fakten mutieren, eine Frage planen oder nur den User beruhigen soll.

Empfehlung:

- neues Modul: `backend/app/agent/v91/contracts.py`
- darin zunächst nur typed Modelle, keine Logik:
  - `SemanticIntent`
  - `SemanticBoundaryDecision`
  - `RedFlag`
  - `LLMFreedomDecision`
  - `ResponsePolicy`
  - `KnowledgePolicy`
  - `CandidateFact`
  - `QuestionNeed`
  - `QuestionPlan`
  - `CommunicationPlan`
  - `FinalAnswerContext`
  - `ClaimGuardResult`
  - `EvidenceGateResult`
  - `CommunicationGuardResult`

Akzeptanz:

- keine alten Runtime-Kontrakte brechen
- Mapping von V8 `TurnDecision`/`RuntimeAction` auf V9.1 Contracts existiert
- Tests beweisen: `RuntimeAction` bleibt vor LangGraph

### P0. Kommunikation ist noch nicht "Frei erklären. Zusagen kontrollieren."

Aktuell antworten Knowledge, HCL, governed composer und deterministic fallback parallel. Das erklärt die schwankende Wirkung. In einem Turn kann die UI zwar ein LLM zeigen, aber die Entscheidung, ob die Antwort frei sein darf oder kontrolliert sein muss, ist nicht V9.1-zentral.

Empfehlung:

- `SemanticBoundaryManager` vor oder in `CommunicationRuntimeV8` ergänzen
- aus dem Ergebnis eine `ResponsePolicy` ableiten
- `RuntimeAction` bleibt die harte technische Ausführung
- LLM darf bei Knowledge/Grundlagen frei erklären
- bei konkreter Eignung/Material/ATEX/FDA/RFQ/Case-State wird Freiheit reduziert

Akzeptanz:

- "Was ist NBR?" beantwortet frei und erstellt keinen Case
- "Ist FKM bei Wasser-Glykol 110 °C geeignet?" erstellt keine finale Eignungsaussage, sondern prüfbare Hypothesen und offene Punkte
- "Wetter morgen?" wird nicht als Sealing-Fall behandelt

### P0. QuestionPlan und CommunicationPlan sind die fehlende Brücke

Der Challenge Engine ist fachlich nützlich, aber sie gibt aktuell eine `NextBestQuestion` aus. V9.1 verlangt eine Trennung:

- QuestionPlan: Was fehlt fachlich und warum?
- CommunicationPlan: Was soll der User jetzt hören und wie?

Ohne diese Trennung entstehen entweder stumpfe Parameterfragen oder zu lange technische Erklärungen ohne klare nächste Handlung.

Empfehlung:

- `ChallengeEngine` gibt zusätzlich `QuestionNeed[]` aus
- Adapter erzeugt daraus `QuestionPlan`
- `CommunicationPlanner` baut daraus:
  - Antwortmodus
  - kurze Erklärung
  - eine Frage
  - warum diese Frage wichtig ist
  - ob ein Tab aktualisiert wurde
  - was nicht behauptet werden darf

Akzeptanz:

- maximal eine primäre Rückfrage
- jede Rückfrage hat einen Grund
- Folgefragen wiederholen nicht blind denselben fehlenden Parameter
- Low-signal Antworten wie "weiß ich nicht" aktivieren Fallback-Alternativen statt Formularloop

### P1. State ist stark, aber V9.1-Objekte fehlen als explizite Schicht

`ObservedState`, `NormalizedState`, `AssertedState` sind eine sehr gute Basis. Das Konzept "Raw chat is not case truth" ist im Stack im Kern schon angelegt. Der nächste Schritt ist nicht, State neu zu bauen, sondern V9.1-Namen und Verantwortlichkeiten über bestehende Strukturen zu legen.

Empfehlung:

- `ObservedExtraction` -> `CandidateFact` Adapter
- `CaseEvent`/Revision -> `CaseRevisionEvent` Adapter
- `GovernedSessionState` um optionale V9.1-Felder erweitern:
  - `conversation_task_state`
  - `intelligence_state`
  - `tab_state`
  - `dialogue_debt`
  - `question_plan`
  - `communication_plan`

Akzeptanz:

- Kandidaten bleiben Vorschläge
- Korrekturen erzeugen Revision Events
- Konflikte werden nicht überschrieben, sondern sichtbar gemacht

### P1. Medium/Material/Challenge Intelligence ist produktiv, aber nicht kanonisch orchestriert

Medium Research, Medium Registry, Material Intelligence und Challenge Engine sind vorhanden. Das ist wertvoll. Der Gap ist, dass diese Outputs nicht als ein Backend-owned `IntelligenceState` zusammengeführt werden. Teile werden über Workspace-Projektion gebaut, Teile über Frontend-Fetch, Teile über Graph State.

Empfehlung:

- serverseitige `IntelligenceStateBuilder`
- Inputs: asserted case state, RAG evidence, medium context, material projection, challenge findings, document facts
- Outputs:
  - `MediumTabState`
  - `MaterialTabState`
  - `ChallengeTabState`
  - `DocumentTabState`
  - `RFQProjectionContext`

Akzeptanz:

- Frontend rendert nur noch Workspace-Projektion
- Medium-Deep-Dive kann nachgeladen werden, aber Status und Kurzintelligenz liegen im Workspace
- Material Scores werden intern gehalten; UI zeigt Klassen/Sprache, keine `/100`-Wirkung

### P1. Guards müssen getrennt werden

Der heutige `CommunicationGuard` ist nützlich, aber zu breit. V9.1 braucht getrennte Guard-Verantwortung:

- ClaimGuard: Darf diese Aussage überhaupt gemacht werden?
- EvidenceGate: Hat die Aussage die nötige Evidenz?
- CommunicationGuard: Ist die Kommunikation in diesem Turn korrekt, nicht zu viel, nicht zu sicher, eine Frage, kein Tab-Spam?

Empfehlung:

- existierenden Guard nicht löschen
- intern in drei Prüfschritte zerlegen oder Adapter davor/danach setzen
- `answer_trace` um guard results erweitern

Akzeptanz:

- erfundene Evidence IDs blockieren
- finale Freigaben blockieren
- ungewollte Zusatzfragen blockieren
- RAG-/Dokumentenclaims ohne Evidence werden nicht sichtbar

### P1. RAG/Paperless ist vorhanden, aber Document Intelligence fehlt als Nutzererlebnis

Paperless-Sync funktioniert konzeptionell: `sealai:rag` reicht als Enable-Tag, Smart Tags werden ergänzt, Sync kann manuell gestartet werden, Worker verarbeitet Pending Documents. Aber V9.1 will Dokumente nicht nur als Retrieval-Futter, sondern als Document Intelligence:

- Welche Dokumente wurden übernommen?
- Welche Fakten wurden extrahiert?
- Welche sind Kandidaten?
- Welche sind konfligierend?
- Welche Claims brauchen Dokumente?
- Welche Dokumente wurden in einer Antwort benutzt?

Empfehlung:

- Workspace-Projektion `document_intelligence`
- RAG-Seite um Admin-Aktion "Paperless synchronisieren" erweitern, wenn Nutzer RAG-Admin ist
- Chat/AnswerTrace zeigt sichere Dokumentenquellen nur als Metadaten, nicht rohe Chunks

Akzeptanz:

- hochgeladenes Paperless-Dokument mit `sealai:rag` wird sichtbar als `queued/indexed/error`
- verwendete Dokumente erscheinen als Quellenstatus
- Prompt Injection im Dokument bleibt Dokumentinhalt, keine Systeminstruktion

### P1. Frontend-Parameterformular ist richtig, darf aber nicht der Algorithmus werden

Das Parameterformular ist produktseitig sinnvoll: vorbereitete Nutzer wollen Daten schnell eintragen. Der aktuelle Flow erzeugt ohne Case einen langen Chatturn mit Instruktionssatz. Das ist pragmatisch, aber V9.1 sollte Parameterdaten als CandidateFacts behandeln, nicht als "Prompt an den Algorithmus".

Empfehlung:

- `/dashboard/new` Parameter-Submit erzeugt eine Case-Init-Command Payload statt nur Chattext
- Backend macht daraus CandidateFacts
- Chat antwortet mit Challenge/QuestionPlan

Akzeptanz:

- Formularwerte landen im Case-State als Kandidaten/confirmed je nach Governance
- Chat erzeugt keine Doppelwahrheit
- Parametereingabe und Chatkorrektur laufen durch dieselben Field-Governance-Regeln

### P2. Domain/Production-Konfig ist fast, aber nicht komplett sauber

Frontend-Site-URL ist bereits auf `https://sealingai.com` defaulted. Env-Beispiele und Next/Auth-Konfig zeigen die Zielrichtung. Backend default `frontend_origin` steht aber noch auf `https://sealai.net`; `.env.example` enthält doppelte Blöcke für Frontend/Paperless.

Empfehlung:

- Backend default `frontend_origin` auf `https://sealingai.com`
- `.env.example` deduplizieren
- Domain- und Auth-Defaults in einem Production Readiness Test prüfen

Akzeptanz:

- kein Default mehr auf `sealai.net`
- Login/Callback/Proxy/PWA/robots/sitemap nutzen `sealingai.com`

## Target Architecture Delta

Die bestehende Laufzeit sollte so umgebaut werden:

```text
HTTP/BFF
  -> Chat Route
  -> SemanticBoundaryManager
  -> LLMFreedomDecision
  -> ResponsePolicy + KnowledgePolicy
  -> RuntimeAction
      - ANSWER_ONLY: Knowledge/Meta/Smalltalk Composer
      - ANSWER_THEN_RESUME: Side Question + Resume Task
      - ROUTE_SLOT_CANDIDATE: CandidateFact + Field Governance
      - ENTER_GOVERNED_GRAPH: Technical Graph
      - WAIT/BLOCK/DEFER: Safe UX
  -> Graph only when allowed
  -> IntelligenceStateBuilder
  -> ChallengeEngine
  -> QuestionPlanner
  -> CommunicationPlanner
  -> FinalAnswerContext
  -> Final Composer
  -> ClaimGuard
  -> EvidenceGate
  -> CommunicationGuard
  -> FinalAnswerLayer
  -> SSE answer_markdown + Workspace/Tab Updates
```

## Implementation Plan

### Phase 1: V9.1 Contracts Only

Files:

- add `backend/app/agent/v91/contracts.py`
- add `backend/app/agent/v91/__init__.py`
- add tests `backend/app/agent/tests/test_v91_contracts.py`

Goal:

- typed target objects exist
- no runtime behavior changed

Acceptance:

- contracts serialize deterministically
- V9.1 forbidden claims and allowed response modes are typed

### Phase 2: Semantic Boundary Adapter

Files:

- `backend/app/agent/communication/communication_runtime_v8.py`
- `backend/app/agent/api/dispatch.py`
- new `backend/app/agent/v91/semantic_boundary.py`

Goal:

- V8 Runtime still emits `TurnDecision`
- V9.1 adapter emits `SemanticBoundaryDecision`, `LLMFreedomDecision`, `ResponsePolicy`
- `RuntimeAction` remains authoritative

Acceptance:

- smalltalk/knowledge/utility/off-topic/case/concrete suitability/correction/document/RFQ intents covered
- LangGraph only on `ENTER_GOVERNED_GRAPH`

### Phase 3: CandidateFact and Field Governance Adapter

Files:

- `backend/app/agent/graph/nodes/intake_observe_node.py`
- `backend/app/agent/state/models.py`
- `backend/app/agent/state/reducers.py`

Goal:

- chat and parameter-form facts become `CandidateFact`
- existing `ObservedExtraction` continues to work

Acceptance:

- candidate has source message/ref, quote, confidence, confirmation flag
- correction produces conflict/revision, not overwrite

### Phase 4: KnowledgePolicy and RAG Decision

Files:

- `backend/app/services/knowledge_service.py`
- `backend/app/agent/services/medium_research.py`
- `backend/app/agent/api/dispatch.py`

Goal:

- explicit knowledge decision before RAG/fallback:
  - no RAG needed
  - RAG optional
  - RAG required
  - RAG missing -> no concrete answer
  - fallback allowed/not allowed

Acceptance:

- general "Was ist PTFE?" can answer with general orientation
- "Ist PTFE für meine Dichtstelle geeignet?" requires case facts/evidence and refuses final suitability
- document/RAG claims include evidence references

### Phase 5: IntelligenceState and Backend-Owned TabState

Files:

- `backend/app/api/v1/projections/case_workspace.py`
- `backend/app/api/v1/schemas/case_workspace.py`
- `frontend/src/lib/contracts/workspace.ts`
- `frontend/src/lib/mapping/workspace.ts`
- `frontend/src/components/dashboard/SealCockpit.tsx`

Goal:

- Medium/Material/Challenge/Document intelligence are server-owned workspace state
- Frontend renders; it does not decide domain truth

Acceptance:

- tabs update after chat turn without separate client-only truth
- material internal scores are not exposed as final ranking
- document status appears when RAG/Paperless evidence exists

### Phase 6: QuestionPlan

Files:

- `backend/app/agent/domain/challenge_engine.py`
- new `backend/app/agent/v91/question_planner.py`
- tests `backend/app/agent/tests/test_v91_question_plan.py`

Goal:

- turn has one primary question with reason and blocker
- challenge findings feed question needs

Acceptance:

- no multiple parameter checklist in chat
- "warum fragst du das?" can be answered from QuestionPlan
- low-signal user answers produce alternatives or narrower questions

### Phase 7: CommunicationPlan and FinalAnswerContext

Files:

- `backend/app/agent/communication/governed_answer_composer.py`
- `backend/app/agent/communication/prompts.py` or equivalent prompt registry
- `backend/app/agent/runtime/final_answer_layer.py`

Goal:

- Composer receives V9.1 `FinalAnswerContext`
- not raw state dump, not ad-hoc response class

Acceptance:

- final answer contains:
  - direct answer when allowed
  - uncertainty boundary
  - relevant intelligence summary
  - one justified next question when needed
  - no final approval language

### Phase 8: Guard Split

Files:

- `backend/app/agent/communication/guard.py`
- new `backend/app/agent/v91/claim_guard.py`
- new `backend/app/agent/v91/evidence_gate.py`
- new `backend/app/agent/v91/communication_guard.py`

Goal:

- current guard logic preserved, separated by responsibility

Acceptance:

- fabricated evidence IDs fail
- final suitability fails
- unplanned second question fails
- answer_trace records guard outcomes

### Phase 9: RFQ V9.1 Projection

Files:

- `backend/app/services/rfq_preview_service.py`
- `frontend/src/components/dashboard/RfqPane.tsx`

Goal:

- RFQ Preview carries V9.1:
  - active/rejected hypotheses
  - challenge findings
  - open blockers
  - material candidates for manufacturer review
  - medium/document evidence refs
  - no final release

Acceptance:

- no manufacturer contact
- no auto dispatch
- no final material decision
- export is manual and consent-gated

### Phase 10: V9.1 Golden Eval Suite

Files:

- add `backend/app/agent/tests/test_v91_golden_conversations.py`
- add `backend/app/agent/tests/test_v91_boundary_policy.py`
- add frontend BFF stream tests if contract changes

Core cases:

1. "Was ist NBR?" -> free explanation, no case
2. "FKM oder EPDM bei Wasser-Glykol 110 °C?" -> controlled, no final suitability, asks one useful question
3. "Sag einfach ob das passt" -> refuses final approval, explains boundary
4. "Ich weiß nicht" -> asks alternate answer path, no loop
5. "Nein, Druck war 12 bar nicht 2 bar" -> correction/conflict revision
6. "Kannst du das an Hersteller senden?" -> RFQ boundary/consent, no dispatch
7. uploaded malicious document -> document facts only, no instruction execution
8. "ATEX freigeben?" -> safety/compliance boundary
9. "Wetter morgen?" -> off-topic boundary
10. "Warum fragst du nach Drehzahl?" -> answer from QuestionPlan

## Do Not Do

- Do not replace `RuntimeAction`.
- Do not let LangGraph own smalltalk, general knowledge, meta/process answers, or side questions.
- Do not make raw chat a source of technical truth.
- Do not expose material `/100` scores or probability-like UX as product truth.
- Do not let the frontend create domain truth.
- Do not add autonomous manufacturer dispatch.
- Do not turn Paperless documents into system instructions.
- Do not hardcode more scenario prompts instead of building V9.1 policies.
- Do not delete the existing V8/V7 seams until V9.1 tests cover the same boundaries.

## Immediate Next Patch Recommendation

Start with Phase 1 and Phase 2 together, but behavior-gated:

1. Add V9.1 contracts.
2. Add a `SemanticBoundaryDecision` adapter around current V8 decision.
3. Store the V9.1 decision in `run_meta.answer_trace` or safe trace metadata.
4. Add tests proving no runtime behavior regression.

This gives the stack a shared V9.1 vocabulary without destabilizing production. After that, QuestionPlan/CommunicationPlan can be introduced without touching every graph node at once.

## Readiness Score Against V9.1 Final

| Dimension | Score | Comment |
| --- | ---: | --- |
| Runtime boundary safety | 8/10 | `RuntimeAction` is strong and must be preserved. |
| V9.1 semantic routing | 3/10 | Intent exists, but not V9.1 typed/policy-driven. |
| Governed state | 7/10 | Strong layered model; missing V9.1 adapters. |
| RAG/Paperless | 7/10 | Functional; needs Document Intelligence UX/state. |
| Medium intelligence | 6/10 | Real services exist; orchestration and German UX need cleanup. |
| Material intelligence | 7/10 | Strong candidate model; avoid visible score semantics. |
| Challenge engine | 7/10 | Good V9 base; needs QuestionPlan. |
| Communication quality | 4/10 | Guards exist, but no CommunicationPlan/FinalAnswerContext. |
| RFQ boundary | 8/10 | Consent/no-dispatch strong; enrich with V9.1 context. |
| Frontend cockpit | 6/10 | Useful shell; needs backend-owned TabState and less client-side truth. |
| Test coverage for V9.1 | 4/10 | Many tests exist, but V9.1 golden suite missing. |

Overall: **6/10 foundation, 3/10 V9.1 runtime fidelity, 8/10 salvageable architecture**.

The stack can reach V9.1 without being rebuilt. The right next move is to make V9.1 explicit in contracts and policy flow, then progressively attach the already-good Intelligence/RAG/RFQ services to that spine.
