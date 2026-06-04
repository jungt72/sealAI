# SealAI Repo IST-Audit

Audit-Datum: 2026-05-18
Audit-Scope: `sealai-active` als aktives Git-Repo. Workspace-Wurzel ist kein Git-Repo; `_vps_patch`, `sealai-local*`, `sealai-comm-audit` und andere Kopien wurden nicht als aktive Runtime-Evidenz gewertet.
Arbeitsmodus: read-first, keine Codeänderungen. Einzige Änderung: diese neue Audit-Datei.

## 1. Executive Verdict

1. Das Repo ist deutlich mehr als eine Chat-/Prompt-Fassade: FastAPI, LangGraph-Graph, governed State, V9.2-Modelle, deterministische Berechnungen, RAG/Evidence, SSE und Dashboard-Projektionen sind vorhanden.
2. Der kanonische User-Turn ist aber nicht ein einziger sauberer Orchestrator: vor dem governed Graph existieren Fast-, Knowledge-, RFQ- und Active-Case-Bypass-Pfade.
3. LangGraph ist produktiv verdrahtet, aber der Graph ist eher linear mit Conditional-Cycle als moderne, semantische Turn-Orchestrierung mit expliziten Subgraphs/Fan-out.
4. V9.2-State-Modelle sind stark, aber UI-Stream-Projektion und Workspace-Projektion sind nicht vollständig einheitlich; V9.2-Daten erscheinen teils als eigene Stream-Form, teils über ältere Workspace-Synthese.
5. Die deterministische Engine ist vorhanden, aber fachlich noch schmal: RWDR-Oberflächengeschwindigkeit/PV und einzelne O-Ring-/Gasket-/Material-/Compliance-Checks, keine umfassende Sealing Engine.
6. Claim-/Evidence-/Calculation-Guards existieren als mehrere Schichten, aber nicht als ein zentraler, finaler Guard-Node nach adversarial review und vor finalem Streaming.
7. Live Streaming existiert über SSE; technische LLM-Composer-Tokens können als `preview_only` vor vollständiger Endvalidierung sichtbar werden.
8. Devil's-Lawyer/Challenge ist vorhanden, aber primär deterministisch und nicht als dedizierter adversarial LLM Review Node vor finalen Empfehlungen.
9. Das Dashboard ist fachlich deutlich besser als generischer Chat, aber noch fragmentiert zwischen Chat, Workspace, Stream Workspace, Cockpit, Decision Understanding und RFQ-Panes.
10. Verifikation ist aktuell blockiert: lokales `python3` hat kein `pytest`, Frontend-`vitest` ist im aktiven `frontend`-Workspace nicht ausführbar.

## 2. Repo Map

| Bereich | Pfad | Zweck | Reifegrad |
|---|---|---|---|
| FastAPI App | `backend/app/main.py` | App Factory, Health, CORS, Router-Mounts, LangGraph-Warmup | vorhanden |
| Legacy API | `backend/app/api/v1/api.py` | RAG, MCP, State, RFQ, Chat History | teilweise legacy |
| Agent API | `backend/app/agent/api/*` | Chat, Stream, Workspace, Review, Dispatch, Runtime | vorhanden |
| LangGraph | `backend/app/agent/graph/topology.py` | Governed StateGraph mit Nodes und Redis/InMemory Checkpointer | vorhanden |
| State | `backend/app/agent/state/models.py` | Observed/Normalized/Asserted/Governance + V9.2 Slices | stark vorhanden |
| V9.2 Engine | `backend/app/agent/v92/*` | SealSystem, Engineering, Calculation, EvidenceGraph, Review, Dossier | teilweise vorhanden |
| Deterministische Rechnungen | `backend/app/services/calculation_engine.py`, `backend/app/mcp/calculations/*`, `backend/app/mcp/calc_engine.py` | RWDR/Gasket/O-Ring/Material/Compliance-Checks | teilweise |
| LLM Clients | `backend/app/llm/factory.py`, `backend/app/llm/registry.py` | OpenAI Sync/Async Clients, Rollenmodell | vorhanden |
| Jinja2 | `backend/app/agent/prompts/*`, `backend/prompts/*` | PromptRegistry, Renderer, Gate, Composer Templates | vorhanden |
| RAG/Evidence | `backend/app/services/rag/*`, `backend/app/agent/evidence/*`, `backend/app/mcp/knowledge_tool.py` | Qdrant/BM25/tenant-scoped retrieval | vorhanden |
| Auth/Tenant | `backend/app/services/auth/*`, `frontend/src/auth.ts` | JWT/Keycloak, roles, tenant claim, BFF auth token | vorhanden |
| Dashboard | `frontend/src/components/dashboard/*`, `frontend/src/hooks/useAgentStream.ts` | Chat, Cockpit, RFQ, Decision Understanding, stream state | vorhanden |
| Frontend BFF | `frontend/src/app/api/bff/*` | Next.js proxy to FastAPI, SSE mapping, RFQ/RAG/workspace | vorhanden |
| Tests | `backend/tests/*`, `backend/app/agent/tests/*`, `frontend/src/**/*.test.*` | breite Unit/Contract Tests | vorhanden, lokal nicht ausführbar |
| CI/CD/Deploy | `Dockerfile*`, `docker-compose*.yml`, `nginx/*` | Container, Compose, Nginx | vorhanden |
| Observability | `backend/app/observability/*`, `backend/app/core/metrics.py` | Prometheus, LangSmith, quality traces | vorhanden |

## 3. Tatsächlicher User-Turn Flow

```text
Dashboard ChatComposer
  -> useAgentStream()
  -> Next BFF POST /api/bff/agent/chat/stream
  -> FastAPI POST /api/agent/chat/stream
  -> event_generator()
  -> _resolve_runtime_dispatch()
      -> unsafe instruction guard
      -> PreGateClassifier / conversation route / v7-v8 runtime action
      -> possible FastResponder / KnowledgeService / RFQ readiness / light runtime bypass
      -> else governed runtime
  -> run_governed_graph_turn()
      -> load GovernedSessionState from Redis/Postgres fallback
      -> build GraphState with pending_message + tenant/session
      -> LangGraph astream/ainvoke
          intake_observe -> normalize -> assert -> medium_intelligence
          -> evidence -> compute -> v92_engineering -> challenge -> governance
          -> matching -> rfq_handover -> dispatch -> norm -> export_profile
          -> manufacturer_mapping -> dispatch_contract -> v92_dossier
          -> output_contract -> governed_answer_composer
      -> persist governed state
  -> assemble state_update payload
  -> SSE events: progress/text_chunk/text_reset/state_update/[DONE]
  -> useAgentStream updates chat + streamWorkspace
  -> dashboard fetches durable workspace projection separately
```

Belege: `frontend/src/hooks/useAgentStream.ts`, `frontend/src/app/api/bff/agent/chat/stream/route.ts`, `backend/app/agent/api/routes/chat.py`, `backend/app/agent/api/dispatch.py`, `backend/app/agent/api/governed_runtime.py`, `backend/app/agent/graph/topology.py`.

## 4. Backend / FastAPI Audit

FastAPI ist in `backend/app/main.py` sauber als App Factory aufgebaut. Es mountet Legacy `/api/v1` und den kanonischen Agent-Router unter `/api/agent`. Beim Startup wird `get_governed_graph()` aufgerufen; das ist echte Runtime-Verdrahtung, nicht nur Testcode.

Der Agent-Chat hat zwei Endpunkte: `POST /api/agent/chat` mit `ChatResponse` und `POST /api/agent/chat/stream` mit `StreamingResponse`. Der Request ist minimal: `message`, `session_id`. Die Response ist dagegen breit und legacy-kompatibel (`reply`, `answer_markdown`, `structured_state`, `ui`, `assertions`, `proposed_case_delta`, RFQ-Felder).

Harte Lücke: `_resolve_runtime_dispatch()` entscheidet viele Pfade vor dem governed Graph. FastResponder, KnowledgeService, RFQ readiness, light conversation und active-case side/process answers können den Graph bewusst umgehen. Das ist funktional gewollt, aber architektonisch ist damit nicht jeder User-Turn durch dieselbe State/Engine/Guard-Kette geführt.

## 5. Frontend / Dashboard Audit

Frontend-Technologie: Next.js App Router, React, TypeScript, Tailwind, Framer Motion, Zustand, NextAuth. BFF-Routen proxyen FastAPI (`frontend/src/lib/bff/backend.ts`).

Das Dashboard ist fachlich reich: `CaseScreen.tsx`, `SealCockpit.tsx`, `DecisionUnderstandingPanel.tsx`, `ParameterWorkspaceTab.tsx`, `RfqPane.tsx`, `ManufacturerFitPanel.tsx`. Es zeigt Parameter, offene Punkte, Medium-Kontext, Material Intelligence, Gegenindikatoren, RFQ-Vorschau, Consent und Review-Bedarf.

Lücke: Die UI hat zwei State-Kanäle: live `streamWorkspace` aus SSE und durable `workspace` über `/workspace/{case_id}`. Das ist brauchbar, aber es erhöht Risiko für stale/abweichende Anzeigen. `streamWorkspace.ts` erwartet `ui.v92`, während `project_for_ui()` in `backend/app/agent/state/projections.py` keine V9.2-Tile im `UiProjection` definiert; V9.2 kommt eher über andere Projektionen oder ältere Workspace-Synthese.

## 6. LLM / Prompting / Jinja2 Audit

LLM-Clients sind über `backend/app/llm/factory.py` und `backend/app/llm/registry.py` rollenbasiert angebunden. OpenAI Async/Sync Clients werden per Env-Key konfiguriert. Jinja2 ist vorhanden: `backend/app/agent/prompts/__init__.py` nutzt `StrictUndefined`; `backend/prompts/builder.py` ebenfalls.

Produktiver LLM-Einsatz:
- `intake_observe_node.py`: technische Extraktion, nur in ObservedState.
- `runtime/gate.py` und `dispatch.py`: Routing/Pre-Gate/V8 Decision.
- `KnowledgeService`/Medium-Komponenten: Wissensantworten.
- `governed_answer_composer.py`: finaler text-only Composer.

Gut: JSON-Parsing und Guarding sind vorhanden. `GovernedAnswerComposer` validiert JSON Output, Länge, interne Leaks und verbotene Freigabe-Sprache. Streaming validiert Prefixe.

Lücke: Prompt-Versionierung ist gemischt. Es gibt Prompt-Version/Hash-Konstanten, aber kein durchgängiges Prompt-Hashing pro gerendertem Prompt und kein zentrales Audit-Log jeder Prompt-Input/Output-Instanz. Ältere `FAST_GUIDANCE_PROMPT_TEMPLATE` ist als Python-String in `backend/app/agent/prompts/__init__.py` enthalten, trotz Registry-Invariante.

## 7. State & Deterministic Engine Audit

State ist stark modelliert. `GovernedSessionState` enthält Observed, Normalized, Asserted, Derived, Evidence, Governance, Decision, Challenge, V9.2 SealSystem, Engineering, Calculation, Standards, EvidenceGraph, Compound, DocumentEvidence, FailureObservation, Review, Dossier, Matching, RFQ, Dispatch und Conversation Messages.

Persistenz: `backend/app/agent/state/persistence.py` speichert Redis session-scoped mit TTL und bietet Postgres-Snapshot-Funktionen. `CaseRecord` und `CaseStateSnapshot` existieren mit Revisionen (`backend/app/models/case_record.py`, `backend/app/models/case_state_snapshot.py`). `MutationEvent` enthält before/after Revisionen.

Engine: `compute_node.py` ruft `CascadingCalculationEngine` nur bei `shaft_diameter_mm` + `speed_rpm` auf. V9.2 baut CalculationState mit `input_snapshot_hash`, `output_snapshot_hash`, stale handling und Guards. O-Ring- und Gasket-Checks existieren, aber kein breiter Engineering-Core für alle Dichtsysteme.

## 8. LangGraph / Orchestration Readiness

LangGraph ist vorhanden und verdrahtet. `topology.py` baut `StateGraph(GraphState)`, registriert Nodes, nutzt Redis/InMemory Checkpointer und streamt `values`, `updates`, `custom`.

Was fehlt für Zielbild-LangGraph:
- kein expliziter Semantic Boundary Node als erster Graph-Knoten; Pre-Gate liegt vor dem Graph.
- kein Candidate Extraction + CaseState Revision als klar benannte Phasen im Graph; vergleichbare Funktion existiert verteilt in intake, reducers, case_delta.
- keine echten Subgraphs/Fan-out-Struktur für Knowledge, Engine, Evidence, Review.
- kein finaler Guard-Node nach Composer; Guards liegen verteilt in Composer, Renderer, FinalAnswerLayer.

## 9. Devil's-Lawyer / Adversarial Review Readiness

Vorhanden: `challenge_node.py`, `domain/challenge_engine.py`, `domain/critical_review.py`, `v92.review`, RFQ-Handover-Checks und UI-Gegenindikatoren. Das ist ein guter deterministic critic.

Nicht gefunden: ein dedizierter adversarial LLM Reviewer Node zwischen Draft Composer und finaler Antwort, der technische Claims gegen State, Evidence, Calculation und CommunicationPolicy prüft. Der sinnvollste Einfügepunkt ist nach `governed_answer_composer_node` und vor `END`, mit Output in `ReviewState`/`answer_trace`, danach optional Revision Composer und finaler Guard.

## 10. Streaming & Live UX Audit

Backend streamt SSE über `StreamingResponse`. `run_governed_graph_turn(... collect_progress=True)` nutzt LangGraph `astream(... stream_mode=["values", "updates", "custom"])`. Custom events werden in `streaming.py` als `progress`, `text_chunk`, `text_reset` gemappt.

Kritisches Risiko: `GovernedAnswerComposer.stream()` sendet Chunks während der LLM-Generierung. Die vollständige Antwort wird erst am Ende mit `_validate_complete_answer()` validiert. Prefix-Guards fangen harte Muster ab, aber semantisch riskante Claims, die nicht regex-erkannt werden, können im Live-Stream sichtbar werden, bevor Endvalidierung/Repair greift. `text_reset` kann danach korrigieren, aber der ungeprüfte Draft war bereits sichtbar.

## 11. Governance / Claim / Evidence / Safety

Stark vorhanden:
- ClaimLevel in `v92/models.py`.
- CalculationGuardResult und no-final-claim-Boundary.
- StandardsState mit `metadata_only_no_norm_text` und `conformity_claim_allowed=False`.
- DocumentEvidenceState mit `prompt_injection_findings`.
- `final_answer_guard.py`, `claim_guard.py`, `runtime/output_guard.py`, `response_renderer.py`.
- Auth/Roles/Tenant in `services/auth/dependencies.py`; artifact IDOR guard in `artifact_access_policy.py`.

Risiken:
- Guards sind verteilt, nicht ein zentraler, testbarer `FinalClaimGuard` über den gesamten finalen Stream.
- Fast/Knowledge-Pfade haben andere Guard-Flächen als governed Graph.
- Human Review existiert als State/Endpoint/Workflow-Element, aber nicht durchgängig als LangGraph `interrupt()`-basierter Produktworkflow.
- Es wurden keine aktiven `.env`/`.pem`/`private_key.json` Dateien im `sealai-active` Scope bis maxdepth 4 gefunden; Secret-Inhalte wurden nicht gelesen.

## 12. Tests, Evals, CI

Tests sind breit vorhanden: Graph-Node-Tests, routing, reducer, state facade, RAG upload security, SSE contract, MCP calculator, compliance, prompt registry, frontend hook/component tests.

Gefundene wichtige Tests: `backend/app/agent/tests/graph/test_output_contract_node.py`, `backend/app/agent/tests/test_response_renderer.py`, `backend/tests/test_rag_upload_security.py`, `backend/tests/test_mcp_compliance_claim_guard.py`, `frontend/src/hooks/useAgentStream.test.tsx`, `frontend/src/components/dashboard/SealCockpit.test.tsx`.

Lokal nicht verifiziert: `python3 -m pytest ...` scheitert mit `No module named pytest`. `npm test` im `frontend` scheitert mit `vitest: command not found`, obwohl `vitest` in `devDependencies` steht. Keine Dependencies wurden installiert.

Fehlende Golden Cases im Sinne des Zielbilds: End-to-end Tests für "Smalltalk darf CaseState nicht mutieren", "Streaming sendet keine ungeprüften technischen Claims", "Devil's-Lawyer blockiert riskante Empfehlung", "Mediumwechsel markiert Materialscreening stale" sind als vollständige E2E-Kette nicht eindeutig gefunden; Teiltests existieren.

## 13. V9.2 Gap Matrix

| Baustein | Status | Evidenz | Risiko | Priorität | Aufwand | Empfehlung |
|---|---|---|---|---|---|---|
| Semantic Boundary / Intent Router | teilweise | `api/dispatch.py`, `runtime/gate.py` | liegt vor Graph, mehrere Bypässe | P0 | M | als Graph-kompatiblen TurnBoundary-Orchestrator kapseln |
| Candidate Extraction | vorhanden | `intake_observe_node.py` | LLM/regex schreibt nur Observed, gut | P1 | S | Schema/coverage erweitern |
| CaseState Revision | teilweise | `persistence.py`, `case_record.py`, `mutation_event_model.py` | Redis/Postgres/Graph-Revisionslogik komplex | P0 | M | Revision als Pflicht im TurnEnvelope |
| SealSystemGraph Resolver | teilweise | `v92/orchestrator.py`, `SealSystemState` | keine echte Graph-Ontologie | P1 | M | Resolver als eigenen Node stärken |
| Deterministic Engineering Orchestrator | teilweise | `v92_engineering_node.py`, `orchestrator.py` | fachlich schmal | P0 | L | Engine-Contract vor LLM technisch verpflichtend |
| Calculators / Rules | teilweise | `compute_node.py`, `mcp/calculations/*` | nur Teilfälle | P1 | L | Calculator registry + snapshot tests |
| EvidenceGraph / StandardsRegistry | teilweise | `EvidenceGraphState`, `StandardsState`, `evidence_node.py` | Evidence lifecycle lückenhaft | P1 | M | EvidenceGate zentralisieren |
| Risk & Completeness Engine | teilweise | `CompletenessMatrix`, `risk_readiness.py` | UI/Backend mehrere Quellen | P1 | M | eine canonical projection |
| CommunicationPlan | teilweise | `TurnContextContract`, `v91_final_answer_context` | verteilt | P1 | M | `FinalAnswerContext` als Turn-Artefakt erzwingen |
| Jinja2 Prompt Rendering | vorhanden | `PromptRegistry`, templates | ein alter Python-String-Prompt | P2 | S | alle produktiven Prompts in Registry |
| LLM Draft Composer | vorhanden | `governed_answer_composer.py` | finaler Draft kann streamen | P0 | M | Draft nicht live zeigen, nur geprüfte finale Segmente |
| Devil's-Lawyer Reviewer | teilweise | `challenge_node.py`, `critical_review.py` | kein LLM adversarial review | P1 | M | Reviewer Node nach Composer |
| Revision Composer | fehlt | nicht gefunden | riskante Drafts werden fallback/reset statt sauberer Revision | P2 | M | optional nach Reviewer |
| ClaimGuard/EvidenceGate/CalculationGuard | teilweise | `claim_guard.py`, `v92.models`, `output_guard.py` | verteilt | P0 | M | zentraler final guard |
| Final Answer Streaming | teilweise | `streaming.py`, `useAgentStream.ts` | ungeprüfte Chunks möglich | P0 | M | status events live, Antwort erst nach final guard |
| Dashboard Cards / RFQ Dossier | vorhanden/teilweise | `SealCockpit.tsx`, `RfqPane.tsx` | V9.2 nicht vollständig einheitlich | P1 | M | V9.2 Cockpit contract angleichen |

## 14. Top 20 Findings

1. ID F01; Severity Critical; Titel: Ungeprüfte technische LLM-Chunks können live sichtbar werden. Evidenz: `governed_answer_composer.py`, `streaming.py`, `useAgentStream.ts`. Empfehlung: technische Antwort erst nach kompletter Composer-Validierung + finalem Guard streamen. DoD: Test beweist, dass verbotene technische Claims nie als `text_chunk` erscheinen.
2. ID F02; Severity Critical; Titel: Mehrere Bypass-Pfade umgehen den governed Graph. Evidenz: `api/dispatch.py`, `routes/chat.py`. Empfehlung: ein TurnBoundary-Orchestrator soll jeden Pfad mit State/ClaimPolicy annotieren. DoD: jede Antwort hat ein einheitliches `FinalAnswerContext`.
3. ID F03; Severity High; Titel: Kein zentraler finaler Guard-Node nach Composer. Evidenz: Guards verteilt in `output_guard.py`, `final_answer_guard.py`, `governed_answer_composer.py`. Empfehlung: `final_claim_guard_node` vor `END`. DoD: alle Antwortpfade laufen durch denselben Guard.
4. ID F04; Severity High; Titel: Devil's-Lawyer ist deterministisch/Challenge, nicht adversarial Review vor finaler Empfehlung. Evidenz: `challenge_node.py`, kein Reviewer Node nach Composer. Empfehlung: adversarial reviewer mit structured verdict. DoD: riskante Empfehlung wird blockiert/revidiert.
5. ID F05; Severity High; Titel: V9.2 UI-Projektion ist nicht einheitlich. Evidenz: `streamWorkspace.ts` erwartet `ui.v92`, `UiProjection` enthält kein `v92`. Empfehlung: ein canonical V9.2 UI contract. DoD: Stream und Workspace verwenden dasselbe Schema.
6. ID F06; Severity High; Titel: Engine fachlich noch zu schmal für Plattformanspruch. Evidenz: `compute_node.py` RWDR-trigger, `mcp/calc_engine.py` Gasket subset. Empfehlung: Calculator registry und coverage map. DoD: O-Ring/RWDR/static/seal-type cases haben registrierte checks.
7. ID F07; Severity High; Titel: Pre-Gate/Routing liegt außerhalb LangGraph-State. Evidenz: `api/dispatch.py`. Empfehlung: Routingentscheidung als State-Artefakt persistieren. DoD: Turn replay rekonstruiert Routing.
8. ID F08; Severity Medium; Titel: Prompt Registry nicht vollständig eingehalten. Evidenz: `FAST_GUIDANCE_PROMPT_TEMPLATE` in Python. Empfehlung: in Jinja2 verschieben. DoD: Test verbietet produktive Prompt-Strings.
9. ID F09; Severity Medium; Titel: Prompt auditability nur teilweise. Evidenz: Version/Hash-Konstanten, kein per-render hash. Empfehlung: rendered prompt hash in trace. DoD: jeder LLM call hat prompt_version/input_hash/output_schema.
10. ID F10; Severity Medium; Titel: Human Review kein durchgängiger Interrupt-Workflow. Evidenz: Review-Modelle/Endpoint vorhanden, LangGraph `interrupt()` nicht produktiv gefunden. Empfehlung: Review als Graph interrupt. DoD: pending review pausiert Turn und resume ist getestet.
11. ID F11; Severity Medium; Titel: State Ownership komplex durch Redis, Postgres Snapshots, BFF Case IDs. Evidenz: `persistence.py`, BFF generiert UUID. Empfehlung: TurnEnvelope mit explicit case_revision. DoD: stale UI kann Revision mismatch anzeigen.
12. ID F12; Severity Medium; Titel: Knowledge path kann ohne governed mutation antworten. Evidenz: `KnowledgeService` branch in `dispatch.py`. Empfehlung: Knowledge replies mit active-case side policy vereinheitlichen. DoD: Smalltalk/knowledge mutiert nicht, technical side question beschädigt State nicht.
13. ID F13; Severity Medium; Titel: Evidence lifecycle gaps werden erkannt, aber nicht final blockierend zentralisiert. Evidenz: `v92/orchestrator.py` lifecycle_gaps, `EvidenceGraphState`. Empfehlung: EvidenceGate final. DoD: document-backed claim ohne valid evidence wird blockiert.
14. ID F14; Severity Medium; Titel: Norm-/Compliance-Claims sind gut begrenzt, aber FinalAnswerGuard muss das zentral erzwingen. Evidenz: `StandardsState.claim_boundary`, `claim_guard.py`. Empfehlung: standards guard in final pipeline. DoD: "konform" ohne review ist unmöglich.
15. ID F15; Severity Medium; Titel: RFQ preview stärker als Review workflow. Evidenz: `RfqPane.tsx`, RFQ endpoints, consent. Empfehlung: Expert approval scope in RFQ Dossier aufnehmen. DoD: Export erst nach consent + review scope.
16. ID F16; Severity Medium; Titel: Testausführung lokal kaputt. Evidenz: `No module named pytest`, `vitest: command not found`. Empfehlung: dev/test bootstrap fix dokumentieren. DoD: ein Befehl führt Backend+Frontend Contract Tests aus.
17. ID F17; Severity Medium; Titel: Stale calculation handling vorhanden, aber nicht als Turn-blocking UX-Regel eindeutig. Evidenz: `stale_derived_value_ids`, `CalculationGuardResult`. Empfehlung: stale status in final guard + dashboard. DoD: geänderter Input blockt alte Empfehlung.
18. ID F18; Severity Low; Titel: Legacy-Kompatibilität bläht Response-Vertrag. Evidenz: `ChatResponse` sehr breit. Empfehlung: v2 TurnEnvelope parallel einführen. DoD: Frontend liest primär v2 contract.
19. ID F19; Severity Low; Titel: Secret-Dateiklassen im Scope nicht gefunden, aber Nginx/Certbot außerhalb maxdepth kann sensible Artefakte enthalten. Evidenz: Secret scan maxdepth 4 leer, Workspace enthält Certbot-Pfade außerhalb aktiven Scope-Kontext. Empfehlung: Gitignore/secret scan CI. DoD: CI blockt private keys.
20. ID F20; Severity Low; Titel: Observability vorhanden, aber LLM evals nicht als Produkt-Golden-Cases sichtbar. Evidenz: `observability`, `tests/quality`, keine vollständigen scenario eval reports. Empfehlung: Golden case suite. DoD: 8 Zielbild-Fälle laufen in CI.

## 15. Empfohlene Architekturpfade

Pfad A - Minimaler stabiler MVP-Fix: Bestehende Architektur behalten. Addiere zentralen `FinalAnswerContext`, finalen Guard, keine ungeprüften technischen Streams, V9.2 UI contract alignen. Vorteil: schnell, wenig Risiko. Aufwand: M. Sinnvoll, wenn Live-Demo/MVP stabilisiert werden muss.

Pfad B - Professioneller LangGraph-Orchestrator: Pre-Gate, runtime action, case revision, deterministic engine, evidence, challenge, answer composer und final guards in einen klaren Graph-/Subgraph-Turn überführen. Bestehende Nodes bleiben, Dispatch wird Boundary Node. Vorteil: sauberer Replay/State/Streaming. Aufwand: L. Sinnvoll für Sprint-Architektur.

Pfad C - Full governed engineering architecture: Voller V9.2-Core mit Calculator Registry, EvidenceGraph, StandardsRegistry, Review Interrupt Workbench, Dossier, evals, tenant audit logs. Vorteil: Plattformfähigkeit. Aufwand: XL. Sinnvoll, wenn SealAI produktiv als governed Application-Engineering-Plattform betrieben werden soll.

## 16. Priorisierte Roadmap

1-3 Tage:
- FinalAnswerContext als Pflichtartefakt pro Pfad definieren.
- Streaming ändern: technical `text_chunk` nur nach finaler Guard-Freigabe oder nur nontechnical/status live.
- V9.2 `ui` contract zwischen Backend und `streamWorkspace.ts` angleichen.
- Lokale Test-Runtime reparieren, ohne Dependency-Upgrade.

Sprint 1:
- Zentraler User-Turn Orchestrator als dünne Schicht um Dispatch + Graph.
- Deterministische Engine Outputs vor jedem technischen LLM Composer verpflichtend.
- FinalClaimGuard/EvidenceGate/CalculationGuard als ein letzter Guard.
- Devil's-Lawyer Review Node minimal einführen, zunächst structured deterministic + optional LLM.
- Tests für Smalltalk-no-mutation, stale medium/material, no-final-claim, no-unsafe-stream.

Sprint 2:
- Calculator Registry für RWDR, O-Ring, statisch/flansch, Material/Medium.
- EvidenceGraph lifecycle + Standards metadata als echte Gate Inputs.
- Review interrupt / expert workbench MVP.
- Golden Case Eval Suite.

Sprint 3:
- Subgraphs für Knowledge, Failure/Leakage, RFQ, Evidence.
- Scenario fork/revision comparison.
- Audit log per LLM call/prompt hash/claim decision.

Später:
- Small/Nano Router erst nach eval-basierter Accuracy.
- Full RFQ Dossier export pipeline.
- LangSmith/OpenAI eval dashboards als Produkt-QA.

## 17. Offene Fragen an mich

1. Soll `sealai-active` verbindlich das einzige aktive Repo sein, oder müssen `sealai-comm-audit`/`sealai-frontpage-hero` als parallele Arbeitsstände abgeglichen werden?
2. Darf Sprint 1 die Streaming-Semantik ändern, sodass technische Antworttokens erst nach finalem Guard erscheinen und vorher nur Status-Events live laufen?
3. Ist das kurzfristige Produktziel Demo/MVP-Stabilität oder bereits auditierbare V9.2-Plattformfähigkeit mit Expert Review als Pflichtworkflow?
