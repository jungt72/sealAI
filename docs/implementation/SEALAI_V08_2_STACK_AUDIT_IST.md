# SeaLAI v0.8.2 Stack Audit — IST-Zustand

## 1. Executive Summary

Der aktuelle Stand ist eine tragfähige v0.7/Früh-v0.8-Basis, aber noch kein v0.8.2-System. Grob geschätzt sind etwa 40 % der v0.8.2-Zielfähigkeiten produktiv oder testbar umgesetzt, weitere 20 % sind als ältere/teilweise passende Seams vorhanden, und der Rest ist Konzept-only.

Die größten implementierten Stärken sind:

- FastAPI/Next.js-Stack mit Keycloak-/NextAuth-Anbindung, BFF-Pattern und tenant-bezogenen Backend-Abhängigkeiten.
- Governed State Layer mit `CaseRecord`, Snapshots, Mutation Events, Revisionen, Reducern, Konflikt-/Stale-Logik und LLM-Delta-Trennung.
- RFQ-Preview mit `case_revision`-Freeze, Consent-Grenze, Open-Points-Acknowledgement und standardmäßig deaktiviertem Dispatch.
- RAG-/Upload-Infrastruktur mit Qdrant, Redis-Rate-Limit, Datei-/Magic-Checks, Tenant-Scope, Pfad-Redaktion und dokumentbasierten Kandidaten.
- Frontend-Arbeitsfläche mit Chat, Cockpit-Ansatz, RFQ-Preview-/Consent-UI, Upload im Chat und BFF-Proxying.

Die größten fehlenden Blöcke sind:

- Keine v0.8.2-`ConversationIntent`-/`ResponseMode`-Taxonomie und keine v0.8.2-`CaseType`-/`ArtifactType`-Architektur als stabile Produktprimitive.
- Keine erste Klasse für `SealFamily`, `SealType`, Alias-Normalisierung und `SealApplicationProfile`; vorhanden sind ältere Engineering Paths und Heuristiken.
- General-Knowledge läuft nicht RAG-first; der aktuelle Knowledge-Pfad nutzt kuratierte PTFE-Factcards und hat keinen sichtbaren LLM-Research-Fallback mit Nicht-validiert-Label.
- Manufacturer Matching erfüllt nicht die v0.8.2-Regeln für aktive bezahlte SeaLAI-Partner, transparente Partnernetzwerk-Offenlegung, No-Fit-State und technische Fit-Matrix.
- Support-, Complaint-, Failure-, Compatibility- und Compliance-Certificate-Workflows sind überwiegend Konzept-only oder alte Teilseams ohne v0.8.2-Artefakte.

Die größten Risiken sind:

- Vertrauens-/Compliance-Risiko durch alte MCP-/Knowledge-Ausgaben mit potentiell final klingender Eignungs-, Konformitäts- oder Empfehlungssprache.
- Produkt-Routing-Risiko durch v0.7-Intent-/Request-Type-Seams, die v0.8.2-Szenarien blockieren oder falsch klassifizieren können.
- Tenant-/IDOR-Risiko in künftigen Dispatch-/Artifact-Pfaden, insbesondere weil `InquiryDelivery` keinen eigenen `tenant_id` hat.
- UI-Risiko durch unvollständige Decision-Understanding-Darstellung, nicht vollständig geprüfte Copy und teils uncommitted Cockpit-Dateien im Worktree.
- Entwicklungsrisiko durch doppelte Auth-Seams, mehrere State-Fassaden und eine lokal unvollständige Python-Testumgebung für `backend/tests` (`alembic.config` fehlt).

Codex kann die weitere Umsetzung PR-für-PR fortsetzen. Der sinnvollste nächste Schritt ist kein großer Rewrite, sondern eine additive v0.8.2-Routing-/Taxonomie-PR mit Tests und ohne Migration, die Fast-Responder, Knowledge und Governed Inquiry sauber trennt.

## 2. Repository & Stack Snapshot

- Arbeitsverzeichnis: `/home/thorsten/sealai`
- Branch: `redesign/sealai-cockpit-overview`
- Git-Status beim Start: bereits dirty. Vorhanden waren Änderungen an `AGENTS.md` und mehreren Frontend-Dateien sowie untracked Cockpit-Dateien (`frontend/src/components/dashboard/SealCockpit.tsx`, `frontend/src/lib/engineering/*`) und eine untracked Datei `"tatus --short"`. Diese Audit-Aufgabe hat nur diesen Bericht neu angelegt.
- Weitere `AGENTS.md`: `./AGENTS.md`, `./frontend/AGENTS.md`.

Detected backend stack:

- FastAPI/Starlette/Uvicorn: `backend/app/main.py`, `backend/app/api/v1/api.py`, `backend/app/agent/api/router.py`, `backend/requirements.txt`.
- SQLAlchemy/Alembic/Postgres: `backend/app/database.py`, `backend/app/models/*`, `backend/alembic/versions/*`, `backend/requirements.txt`.
- Redis: Live/governed state, RAG upload rate-limit, compose service; evidence in `backend/app/agent/api/loaders.py`, `backend/app/api/v1/endpoints/rag.py`, `docker-compose.yml`.
- Qdrant/RAG: `backend/app/services/rag/*`, `backend/app/api/v1/endpoints/rag.py`, `docker-compose.yml`.
- LangGraph/LangChain/OpenAI: `backend/requirements.txt`, `backend/app/agent/*`, `backend/app/agent/runtime/conversation_runtime.py`, `backend/app/agent/runtime/gate.py`.
- Auth: Keycloak/JWKS backend dependencies and NextAuth frontend; evidence in `backend/app/services/auth/dependencies.py`, `backend/app/api/v1/dependencies/auth.py`, `frontend/src/auth.ts`, `frontend/src/proxy.ts`.
- Upload/document parsing: `backend/app/api/v1/endpoints/rag.py`, `backend/app/services/rag/utils.py`, `backend/app/services/rag/rag_ingest.py`.
- RFQ: `backend/app/services/rfq_preview_service.py`, `backend/app/api/v1/endpoints/rfq.py`, `frontend/src/components/dashboard/RfqPane.tsx`.

Detected frontend stack:

- Next.js App Router, React 18, NextAuth v5 beta, Vitest, ESLint, Tailwind/PostCSS; evidence in `frontend/package.json`.
- BFF routes for agent chat, workspace, RFQ, RAG and medium intelligence under `frontend/src/app/api/bff/*`.
- Dashboard/chat/cockpit/RFQ UI under `frontend/src/components/dashboard/*`.
- RAG document UI under `frontend/src/components/rag/RagDocumentGrid.tsx`.

Detected data stores:

- Postgres: `postgres` service in `docker-compose.yml`; SQLAlchemy models and Alembic migrations.
- Redis: `redis-stack-server` service, live state/checkpoint/rate-limit usage.
- Qdrant: vector storage service and RAG orchestrator.
- Local upload/model volumes: `RAG_UPLOAD_DIR`, `HF_HOME`, `FASTEMBED_CACHE_PATH` are configured by key name in compose/config. Werte wurden nicht ausgegeben.

Detected LLM/RAG stack:

- OpenAI SDK and LangChain/OpenAI dependencies are present.
- Local embedding stack (`fastembed`, `sentence-transformers`, CPU Torch) is configured.
- RAG retrieval exists but is not wired as the primary general sealing knowledge path.
- LLM document processing flags default to disabled in `backend/app/core/config.py`.

Detected deployment/development setup:

- `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.deploy.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `nginx/*`, `ops/*.service`.
- Compose contains required secret key names. A literal Grafana admin password key exists in `docker-compose.yml` and should be treated as deployment hygiene risk; value is intentionally not reproduced here.
- No service was restarted, stopped, migrated or contacted.

Evidence files:

- `AGENTS.md`
- `konzept/SEALAI_V08_2_CODEX_IMPLEMENTATION_CONCEPT.md`
- `konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md`
- `frontend/DESIGN.md`
- `frontend/AGENTS.md`
- `backend/app/main.py`
- `backend/app/api/v1/api.py`
- `backend/requirements.txt`
- `frontend/package.json`
- `docker-compose.yml`

## 3. Concept Alignment Scorecard

| Area | Target in v0.8.2 | Current state | Status: implemented / partial / missing / unclear | Evidence files | Risk | Recommended next action |
|---|---|---|---|---|---|---|
| A. Conversation Intelligence Layer | `ConversationIntent`, `ResponseMode`, Small Talk ohne Case, General Knowledge ohne Case, empathic triage, Needs/Current-State, NBQ | Fast responder, deterministic pre-gate, knowledge path und conversation runtime existieren. Taxonomie ist v0.7 und nicht v0.8.2; Frontend bindet immer `case_bound`; Light runtime kann persistieren. | partial | `backend/app/domain/pre_gate_classification.py`, `backend/app/services/pre_gate_classifier.py`, `backend/app/services/fast_responder_service.py`, `backend/app/services/knowledge_service.py`, `backend/app/agent/api/routes/chat.py`, `frontend/src/app/api/bff/agent/chat/stream/route.ts` | high | Additive v0.8.2 Intent/Mode-Taxonomie und Fast/Knowledge/Governed-Threshold-Tests. |
| B. Scenario architecture | Stabile `CaseType`-Szenarien für RFQ, Matching, Compatibility, Complaint, Failure, Replacement, etc. | Alte `request_type`- und `engineering_path`-Heuristiken vorhanden. Kein v0.8.2-`CaseType`-Enum/Modell. Manufacturer-Fragen teils blockiert. | partial | `backend/app/models/case_record.py`, `backend/app/api/v1/schemas/case_workspace.py`, `backend/app/api/v1/projections/workspace_routing.py`, `backend/app/services/pre_gate_classifier.py` | high | `CaseType` als Domain-Schema/Classifier-Projektion einführen, zunächst ohne DB-Migration. |
| C. Artifact architecture | `ArtifactType` mit RFQ, fit matrix, compatibility matrix, complaint intake, failure intake, drafts, notes | `InquiryExtractModel.artifact_type` ist String mit Check für `manufacturer_inquiry`, `technical_summary`, `rfq_preview`. Nur RFQ Preview ist praktisch umgesetzt. | partial | `backend/app/models/inquiry_extract.py`, `backend/alembic/versions/c7d8e9f0a1b2_add_rfq_preview_consent_fields.py`, `backend/app/services/rfq_preview_service.py` | high | Artifact registry in Code einführen und RFQ Preview als ersten konkreten Adapter behalten. |
| D. Seal type architecture | `SealFamily`, `SealType`, Alias-Normalisierung, SealApplicationProfile, type-specific intake | Engineering paths (`rwdr`, `static`, `hyd_pneu`, etc.) und Heuristiken existieren. Keine v0.8.2-SealType-Architektur. | partial | `backend/app/domain/engineering_path.py`, `backend/app/api/v1/projections/workspace_routing.py`, `backend/app/agent/state/reducers.py`, `backend/app/agent/data/sts/sealing_types.json` | high | SealType normalizer mit Alias-Tests für RWDR, Flachdichtung, Hydraulik, Pneumatik, O-Ring, Gleitring, Packung, Sonderprofil. |
| E. RAG, knowledge, LLM fallback | RAG-first, RAG-miss, fallback optional und sichtbar nicht validiert, Source/Validation-Metadaten | RAG-Infrastruktur existiert. General Knowledge nutzt PTFE-Factcards, nicht Qdrant-RAG. Kein v0.8.2-Fallback-Label-Flow. | partial | `backend/app/services/rag/rag_orchestrator.py`, `backend/app/services/knowledge_service.py`, `backend/app/services/knowledge/factcard_store.py`, `backend/app/agent/runtime/conversation_runtime.py` | high | Knowledge answer service auf RAG-first contract setzen; fallback nur labeled und nicht authoritative. |
| F. Governed engineering state | `CaseField`, `FieldStatus`, `EngineeringValue`, provenance, evidence, confidence, conflicts, units, revisions, events, projections | Starke Basis vorhanden: Reducer, Snapshot, Mutation Events, CaseService, Stale/Conflict, deterministic calculations. Source/Validation-Status noch nicht v0.8.2-vollständig. | implemented/partial | `backend/app/agent/state/models.py`, `backend/app/agent/state/reducers.py`, `backend/app/services/case_service.py`, `backend/app/models/mutation_event_model.py`, `backend/app/api/v1/projections/case_workspace.py` | medium | Source/Validation-Metadata ergänzen und Projections vereinheitlichen. |
| G. RFQ governance | Preview, Export, revision freeze, stale handling, explicit consent, no dispatch | Preview/consent/revision freeze gut umgesetzt. Export/Download bewusst deaktiviert. Stale-Consent-Block vorhanden. Kein vollständiges Export-/Document-Allowlist-Flow. | implemented/partial | `backend/app/services/rfq_preview_service.py`, `backend/app/api/v1/endpoints/rfq.py`, `backend/app/services/inquiry_extract_service.py`, `frontend/src/components/dashboard/RfqPane.tsx` | medium | RFQ Export als manuelle, allowlisted Datei-Generierung ergänzen; Dispatch weiter deaktiviert lassen. |
| H. Manufacturer matching | Nur aktive bezahlte SeaLAI-Partner, capabilities, technical fit, gaps, no-fit, disclosure, no paid boost | Capability- und alte Matching-Seams existieren; keine `active_paid`-Eligibility, keine produktive Fit-Matrix/API/UI, keine Partnernetzwerk-Offenlegung. Tests verhindern Sponsored-Score-Einfluss in einem alten Service. | partial | `backend/app/services/capability_service.py`, `backend/app/services/problem_first_matching_service.py`, `backend/app/agent/domain/fit_score.py`, `backend/app/agent/data/manufacturers/pilot_manufacturers.json` | high | Partner eligibility + fit matrix als backend-only Projection mit disclosure/no-fit testen. |
| I. Support/compatibility/complaint/failure modes | Compatibility, oil/lab report, complaint intake, failure intake, customer draft, internal note, no final root cause/liability | Alte RCA-/Knowledge-/Chemical-Seams existieren. Keine v0.8.2-Szenarien/Artefakte/Flows. | partial/missing | `backend/app/api/v1/projections/workspace_routing.py`, `backend/app/services/knowledge/*`, `backend/app/mcp/calculations/chemical_resistance.py`, `backend/app/services/medium_intelligence_service.py` | high | Erst Compatibility Inquiry und Failure Intake als schmale Artefakte mit Claim-Guard bauen. |
| J. Upload/document/IP safety | Upload endpoints, file limits, parser safety, redaction, candidates, prompt-injection, LLM gating, evidence, tenant isolation | Upload-Seam ist vergleichsweise stark. Datei-/Magic-/Size-Checks, Tenant-Scope, path redaction, candidates und LLM-gating sind vorhanden. Health UI/BFF kann Pfadstruktur anzeigen; Prompt-injection Schutz ist getestet, aber nicht vollständig in allen UI-Artefakten sichtbar. | implemented/partial | `backend/app/api/v1/endpoints/rag.py`, `backend/app/services/rag/utils.py`, `backend/app/services/rag/rag_ingest.py`, `frontend/src/components/rag/RagDocumentGrid.tsx`, `backend/tests/agent/test_rag_injection.py` | medium | User-facing Health-Felder redigieren und document candidate/evidence UI stärker an RFQ/Case anbinden. |
| K. Compliance awareness | FDA, EU 1935/2004, EU 10/2011, ATEX, EHEDG, USP VI, drinking water, TA-Luft, GMP ohne Overclaim | Moderne norm modules sind cautious. Alte MCP-Compliance/chemical helpers enthalten potentiell überclaimende Texte. Keine breite Compliance Engine, wie gefordert. | partial | `backend/app/services/norm_modules/fda_food_contact.py`, `backend/app/services/norm_modules/eu_food_contact.py`, `backend/app/mcp/calculations/compliance.py`, `backend/app/mcp/calculations/chemical_resistance.py`, `backend/app/agent/runtime/output_guard.py` | high | Alte MCP-Ausgaben hinter Claim-Guard/Renderer bringen oder intern labeln; Tests für user-visible compliance copy. |
| L. Frontend | Chat, cockpit/workspace, rails/tabs, Decision Understanding, field status/provenance/evidence, RFQ, consent, matching, support artifacts, fallback label, safe copy | Chat, workspace, cockpit Ansatz, RFQ Preview und consent vorhanden. Decision Understanding nicht first-class gerendert; matching/support/fallback labels fehlen. Untracked Cockpit-Dateien machen Produktstatus unsicher. | partial | `frontend/src/components/dashboard/CaseScreen.tsx`, `frontend/src/components/dashboard/ChatPane.tsx`, `frontend/src/components/dashboard/SealCockpit.tsx`, `frontend/src/components/dashboard/RfqPane.tsx`, `frontend/src/lib/mapping/workspace.ts` | medium/high | Frontend contract für Decision Understanding + source/validation labels ergänzen; Copy-Test erweitern. |
| M. Security/tenant/auth | Keycloak/NextAuth, backend checks, tenant/org scoping, IDOR tests, upload/RFQ/artifact/consent access checks | Auth-Seams existieren, viele tenant/user checks vorhanden. Doppelte Auth-Implementierungen und einzelne Modelle/Pfade brauchen Review. `InquiryDelivery` ohne tenant_id ist künftiges Risiko. | partial | `backend/app/services/auth/dependencies.py`, `backend/app/api/v1/dependencies/auth.py`, `backend/app/services/rfq_preview_service.py`, `backend/app/api/v1/endpoints/rag.py`, `backend/app/models/inquiry_delivery.py`, `frontend/src/auth.ts` | high | Tenant-bound artifact/dispatch model review, IDOR tests für RFQ/artifacts/uploads erweitern. |
| N. Tests and validation | Routing, consent, tenant, upload, prompt injection, matching, fallback labels, seal-type normalization, frontend | Viele Tests vorhanden, aber Lücken in v0.8.2-Taxonomie, SealType, fallback labels, partner matching, support/complaint artifacts. Ein Backend-Testpfad scheitert lokal wegen fehlendem `alembic.config`. | partial | `backend/app/agent/tests/*`, `backend/tests/*`, `frontend/src/**/*.test.*`, `frontend/src/lib/unsafeProductCopy.spec.ts` | medium | Test-Matrix an v0.8.2 PR-Reihenfolge koppeln; lokale Testumgebung für `backend/tests` reparieren. |

## 4. Current Product Reality

Actually implemented:

- Authentifizierter Dashboard-Chat über Frontend-BFF zu Backend-Agent-Stream.
- Fast responses für Greetings/Meta/Blocked über Pre-Gate und FastResponder ohne strukturierte Case-State-Antwort.
- General-Knowledge-Antworten aus kuratierten Factcards, vor allem PTFE/RWDR-nahe Inhalte.
- Governed Inquiry für technische Nutzereingaben mit State-Snapshot, CaseRecord, Revision, Reducern, LLM-Delta-Seam und Mutation Events.
- Dokumentupload in RAG mit Datei-/Tenant-Schutz und optionalem document delta als Kandidat für einen Case.
- RFQ Preview aus governed case state, frozen auf `case_revision`, mit Open Points, Field Envelopes, Evidence und Consent Boundary.
- Frontend RFQ Pane mit stale/current-Anzeige, No-final-release-/Open-points-/Export-Intent-Checkboxen.
- Workspace Projection mit Cockpit-/Deep-Dive-/Governance-/RFQ-/Medium-Seams.
- Deterministische Berechnungs- und Normmodule in Teilen.

Only partially implemented:

- Conversation Intelligence: Pre-Gate existiert, aber nicht als v0.8.2-Intent/Mode-Architektur.
- Needs/current-state analysis: einzelne Profile, questions und summaries existieren, aber kein vollständiger v0.8.2-NBQ-Flow.
- Scenario support: alte Request Types und Engineering Paths statt v0.8.2-CaseTypes.
- Seal type support: RWDR/O-Ring/Gasket/Packing/Mechanical-Seal-Heuristiken, aber keine breite SealType-Normalisierung.
- RAG: Infrastruktur stark, aber Knowledge-Antworten nicht RAG-first.
- Manufacturer Matching: ältere Capability-/Fit-Seams, aber kein SeaLAI-Partnernetzwerk-Matching.
- Compliance awareness: cautious neue Normmodule, aber alte MCP-Ausgaben können unsafe wirken.
- Frontend Cockpit: Arbeitsfläche vorhanden, aber teils untracked und ohne vollständige Decision-Understanding-/Artifact-Darstellung.

Concept only / not implemented:

- Vollständige `CaseType`-Liste aus v0.8.2.
- Vollständige `ArtifactType`-Liste aus v0.8.2.
- `SealFamily` / `SealType` als stabile Produktprimitive.
- LLM-Research-Fallback mit sichtbarem Nicht-validiert-Label.
- Partnernetzwerk-Fit-Matrix mit `active_paid` Eligibility, Disclosure und No-Fit.
- Complaint Intake, Failure Analysis Intake, Compatibility Matrix, Replacement Sheet, Legacy Part Intake, Quote Comparison, Material Substitution Brief, Emergency Triage, Customer Reply Draft und Internal Engineering Note als eigene Artefakte.
- Vollständige UI für Manufacturer Fit, Support/Complaint-Artefakte und fallback validation labels.

Unclear:

- Ob alle Agent-/MCP-Ausgaben, insbesondere alte compliance/chemical tools, sicher durch Output Guards laufen, bevor sie user-visible werden.
- Ob untracked Frontend-Cockpit-Dateien als beabsichtigte aktuelle Produktbasis gelten.
- Ob alle Case-/Artifact-Lesewege dauerhaft tenant-/owner-geschützt bleiben, wenn kommende Artifact-/Dispatch-Flows ergänzt werden.
- Ob root `package.json` noch produktiv relevant ist oder nur Altbestand; es weicht deutlich von `frontend/package.json` ab.

## 5. Architecture Findings

Backend authority/governor:

- Der Backend-Governor ist real und relativ stark. `CaseService` kapselt Case-Erzeugung, Snapshot-Schreiben, Revisionserhöhung, Mutation Events und Validierung kritischer Engineering Values.
- LLM-Deltas erscheinen als vorgeschlagene Case Deltas und werden nicht direkt als authoritative truth gespeichert.
- Reducer in `backend/app/agent/state/reducers.py` übernehmen Normalisierung, Konfliktlogik, Stale-Propagation und Governance-Ableitung.
- Die v0.8.2-Metadaten `source_type` und `validation_status` sind noch nicht als durchgängige Produktprimitive vorhanden.

State model:

- `CaseRecord` hat `tenant_id`, `user_id`, `case_revision`, alte Routing-/Phase-Felder und JSON `payload`.
- `CaseStateSnapshot` speichert revisionierte `state_json`.
- `MutationEventModel` speichert tenant-bezogene akzeptierte/abgelehnte Deltas und revision before/after.
- `InquiryExtractModel` speichert RFQ-/Inquiry-Artefakte mit `tenant_id`, `case_revision`, Consent-Feldern und disabled dispatch.
- `InquiryDelivery` ist für künftige Versand-/Delivery-Pfade kritisch, weil kein eigener `tenant_id` vorhanden ist.

LLM boundaries:

- Gute Trennung im governed path: LLM darf vorschlagen, Backend reduziert und persistiert.
- Conversation Runtime kann direkte OpenAI-Antworten für Light Modes erzeugen; sie ist laut Code ohne RAG/LangGraph/Graph-State. Das passt nicht vollständig zur v0.8.2-Regel für RAG-first technische Wissensantworten.
- Output Guards existieren und werden getestet, aber die Abdeckung alter MCP-/Knowledge-Tools ist nicht eindeutig.

Frontend/backend truth separation:

- Frontend rendert Backend-Projections und BFF-Daten; es besitzt nicht den authoritative Engineering State.
- `buildSealCockpitViewModel.ts` leitet UI-Summaries und Statusanzeigen ab. Das ist für Darstellung akzeptabel, muss aber bei Readiness/Truth/Matching weiter klar backend-getrieben bleiben.
- `WorkspaceView` enthält noch kein vollständiges v0.8.2 Decision-Understanding- oder Source/Validation-Contract.

Projections:

- Backend hat `DecisionUnderstandingProjection` in `backend/app/api/v1/schemas/case_workspace.py`.
- `case_workspace.py` erstellt Cockpit, Deep Dive, Governance, RFQ und Medium Context.
- Frontend mapping rendert Decision Understanding nicht als zentrales Produktobjekt.

Event/revision model:

- Revisionsmodell ist implementiert und RFQ Preview nutzt frozen `case_revision`.
- Stale handling für RFQ Preview Consent ist implementiert.
- Eventlog ist vorhanden, aber v0.8.2-Artefakt- und Matching-Revisionierung fehlt noch weitgehend.

RAG and knowledge handling:

- Upload/ingest/retrieve ist vorhanden, tenant-scoped und getestet.
- Knowledge answers nutzen Factcards, nicht Qdrant-RAG als erste Quelle.
- RAG-miss und LLM-research fallback sind nicht als v0.8.2-user-visible flow implementiert.

Upload/document handling:

- Dateiarten, Größen, Magic-Signatures, Pfadnormalisierung, Error-Redaktion und Kandidaten-Erzeugung sind vorhanden.
- Dokumente können einen case-bound document delta liefern, bleiben aber Kandidaten.
- Frontend/RAG Health kann Pfadinformationen weiterreichen; für user-visible UI sollte das redigiert werden.

Auth/tenant model:

- Keycloak/NextAuth-Seams sind implementiert.
- Backend-Routen nutzen `RequestUser` mit `tenant_id`.
- RAG und RFQ haben konkrete tenant/user checks.
- Es gibt zwei Backend-Auth-Abhängigkeitsschichten (`services/auth/dependencies.py`, `api/v1/dependencies/auth.py`), was Drift-Risiko schafft.

## 6. Scenario Readiness

| CaseType | Current implementation status | Evidence | Missing pieces | Minimal next patch |
|---|---|---|---|---|
| `new_rfq` | partial | RFQ Preview, governed state, workspace RFQ readiness | Kein v0.8.2-CaseType; intake noch nicht seal-type-spezifisch vollständig | `CaseType.new_rfq` in routing projection und tests ergänzen, ohne DB-Migration. |
| `manufacturer_matching` | partial | CapabilityService, ProblemFirstMatchingService, pilot manufacturers | Keine `active_paid` Eligibility, keine fit matrix API/UI, keine disclosure/no-fit | Backend `manufacturer_fit_matrix` Projection aus bestehenden Claims bauen. |
| `compatibility_inquiry` | partial | Knowledge services, chemical matrix, medium intelligence | Kein CaseType, keine compatibility matrix, keine compound-specific caution envelope | Compatibility classifier + technical inquiry summary mit no-final-compatibility claim. |
| `complaint_case` | missing/partial | Alte RCA-/failure markers in workspace routing | Kein complaint intake, kein no-liability draft, keine evidence checklist | Schmaler `complaint_case` classifier + intake fields + tests. |
| `failure_analysis` | partial | `rca_failure_analysis` old request type, failure/damage fields in tests/projections | Kein v0.8.2 failure-analysis artifact, keine root-cause boundary als Artifact | `failure_analysis_intake` Projection ohne final root cause. |
| `replacement_reorder` | partial | `retrofit`/`spare_part_identification` alte request types | Kein replacement sheet, kein reorder-price-boundary | `replacement_reorder` CaseType mapping und missing-data list. |
| `unknown_legacy_part` | partial | `spare_part_identification` old seam | Kein legacy part intake artifact, keine photo/drawing evidence flow | Legacy-part classifier + artifact skeleton. |
| `drawing_review` | missing | Upload/RAG kann Zeichnungen/PDFs speichern | Kein drawing-review scenario, no drawing review artifact | Shallow recognition + refusal/needs-evidence message. |
| `quote_comparison` | missing | Keine produktive Quote-Comparison-Seam gefunden | Kein scenario, kein artifact, keine comparison policy | Nur Klassifikation + boundary response, keine technische Rangentscheidung. |
| `compliance_certificate_request` | partial | Norm modules FDA/EU food contact, old compliance MCP | Kein CaseType/Checklist, alte overclaim-riskante Ausgaben | Compliance checklist artifact mit evidence-required states. |
| `material_substitution` | missing/partial | Material/chemical services vorhanden | Kein scenario, keine substitution brief boundary | Shallow classifier + “manufacturer review required” note. |
| `emergency_mro` | missing/partial | Capability claims haben `emergency_capable` Feld | Kein emergency triage flow, keine 1-question emergency rule | Emergency classifier + single next-best-question test. |
| `manufacturer_support_intake` | missing | Keine spezifische Support-Intake-Seam gefunden | Kein scenario/artifact/recipient consent | Classifier + support-intake skeleton without dispatch. |
| `general_knowledge` | partial | KnowledgeService, FactCardStore, pre-gate knowledge query | Nicht RAG-first, kein fallback label, nicht vollständige source/validation model | Knowledge answer contract mit source label und RAG-miss handling. |

## 7. Dichtungstyp Readiness

Current status:

- Es gibt alte technische Achsen (`engineering_path`) und Heuristiken, aber keine v0.8.2-`SealFamily`-/`SealType`-Architektur.
- Unterstützt sind vor allem RWDR-nahe Fälle, statische Dichtungen, Hydraulik/Pneumatik grob, Mechanical Seal grob, O-Ring/Gasket/Packing in Reducer-Required-Fields.
- `frontend` zeigt Cockpit-/Parameteransichten, aber keine stabile SealType-Normalisierung als UI-/Backend-Contract.

Supported seal-type evidence:

- RWDR/WDR/Simmerring/radial shaft seal: Marker in `workspace_routing.py`, PTFE/RWDR-Factcards, RWDR tests.
- Flat gasket/flange gasket: alte `static`/`gasket`-Heuristiken und deterministic gasket calculations.
- Hydraulic/pneumatic seals: `hyd_pneu` engineering path und markers, aber keine Trennung rod/piston/wiper/pneumatic in v0.8.2-Taxonomie.
- O-Ring: Reducer/test Seams und O-ring groove calculation, aber keine v0.8.2-SealType-Alias-Registry.
- X-Ring: kein klarer produktiver Support gefunden.
- Mechanical seal/Gleitringdichtung: Marker und engineering path `ms_pump`, aber keine type-specific intake checklist nach v0.8.2.
- Gland packing/Stopfbuchspackung: Reducer erwähnt `packing`; keine breite Alias-/Intake-Architektur.
- Custom profiles/Sonderprofil: keine stabile Architektur gefunden.
- Unknown seal handling: allgemeine unknown/unclear paths existieren, aber kein v0.8.2 `unknown_seal` Profile.

Alias normalization:

- Aktuell sind Alias-Regeln verteilt in Routing-/Heuristik-Code, nicht als testbare zentrale Normalisierung.
- Deutsche und englische Begriffe sind teils enthalten (`Wellendichtring`, `Simmerring`, `Gleitring`, `Hydraulik`, `Pneumatik`), aber nicht vollständig.

Type-specific intake:

- Es gibt kleine type-specific required field mappings in Reducern.
- Es fehlt eine schmale, testbare v0.8.2-Fragenprofil-Schicht pro SealType.

Minimal next patch:

- Neues Domain-Modul `seal_type_normalization` ohne Migration.
- `SealFamily`/`SealType` Literals oder Enums in Code.
- Alias tests für RWDR/WDR/Simmerring, Flachdichtung/Flanschdichtung, Stangen-/Kolbendichtung, pneumatische Varianten, O-Ring/X-Ring, Gleitringdichtung, Stopfbuchspackung, Sonderprofil, Unknown.
- Projection eines `SealApplicationProfile` aus bestehendem State, zunächst read-only.

## 8. RAG & LLM-Fallback Readiness

Is RAG implemented?

- Ja. Qdrant-Retrieval, ingest, upload, BM25-Seams, tenant filters und tests sind vorhanden.

Is RAG used for general sealing knowledge?

- Nicht als primary flow nachweisbar. `KnowledgeService` nutzt `FactCardStore` und PTFE-Factcards. `conversation_runtime.py` sagt explizit, dass Conversation Mode ohne RAG/LangGraph/Graph-State läuft.

Is RAG-miss detected?

- Teilweise in RAG-Services und KnowledgeService als “keine kuratierte Wissensbasis gefunden”. Ein v0.8.2-RAG-miss-Contract für user-visible Knowledge Answers ist nicht vorhanden.

Is LLM fallback implemented?

- Conversation Runtime kann OpenAI direkt nutzen. Ein expliziter “LLM research fallback” nach RAG-miss mit source/validation labels wurde nicht gefunden.

Is fallback clearly labeled not validated?

- Nein, nicht als durchgängiger produktiver Contract. Prompt-/Output-Guard-Seams existieren, aber keine v0.8.2-Fallback-Label-Struktur.

Can fallback information accidentally become authoritative?

- Im governed path ist das Risiko begrenzt, weil LLM-Deltas vorgeschlagen und reduziert werden. Im Light/Conversation/Knowledge path ist das Risiko für user-visible Orientierung höher, weil kein RAG-first/fallback-label Contract existiert. Persistenz als Case truth wurde für Fast/Knowledge nicht direkt gefunden, aber Light mode kann governed snapshots erzeugen.

What needs to change?

- Ein einziger Knowledge Answer Service sollte RAG-first, Factcard/curated knowledge, RAG-miss und optional fallback orchestrieren.
- Response muss `source_type`, `validation_status`, `use_scope` und `not_final_release` maschinenlesbar und UI-sichtbar liefern.
- Fallback darf nur als note/candidate gespeichert werden, nie als confirmed case field.

## 9. Manufacturer Matching Readiness

Is a partner model present?

- Teilweise. `manufacturer_profiles` und `manufacturer_capability_claims` existieren per Migration/Service. Pilot-Manufacturer JSON existiert für Agent-Seams.

Is `active_paid` modeled?

- Nein. Es gibt `account_status`, `active` und `listing_tier`, aber keine v0.8.2-Eligibility “active paid SeaLAI partner”.

Are capabilities modeled?

- Ja, teilweise. Capability claims können Typ, Engineering Path, Material Family, Payload, Source, Confidence und Emergency Capability speichern.

Is technical fit implemented?

- Teilweise. `problem_first_matching_service.py` und `fit_score.py` berechnen deterministic fit in alten Strukturen.

Is paid ranking prevented?

- Teilweise. Tests im alten Problem-First-Matching stellen sicher, dass ein `sponsored` flag den Score nicht beeinflusst. Die v0.8.2-Regel “Payment bestimmt nur Eligibility, nicht Score” ist aber nicht als Partnernetzwerk-Contract implementiert.

Is disclosure implemented?

- Nein. Kein produktiver Disclosure-Text “Only active SeaLAI partner manufacturers ... not a full-market comparison” als API/UI-Contract gefunden.

Is no-fit supported?

- Nicht als v0.8.2-Produktzustand gefunden. Alte Fit-Services können vermutlich niedrige Scores liefern, aber kein klarer “No suitable SeaLAI partner found” Contract.

Smallest safe implementation path:

1. Read-only Partner Eligibility Service aus vorhandenen Profile/Claims ableiten.
2. Neues Projection-Objekt `manufacturer_fit_matrix` mit `network_disclosure`, `fit_band`, `fit_reasons`, `gaps`, `missing_requirements`, `verification_level`.
3. Tests: paid/listing tier darf Score nicht erhöhen; inactive/unpaid erscheint nicht; no-fit wird explizit zurückgegeben.
4. Erst danach UI-Rendering, ohne Kontakt/Dispatch.

## 10. RFQ & Consent Readiness

RFQ preview current state:

- Implementiert und relativ stark. `RfqPreviewService` baut preview payloads aus latest snapshot und CaseRecord.
- Preview wird auf `case_revision` eingefroren und pro Revision wiederverwendet.
- Payload trennt bestätigte, dokumentierte, user-stated, inferred, calculated, conflicting, missing und open Felder.
- Manufacturer view wird allowlisted.

Export current state:

- Download endpoint gibt 410 und ist deaktiviert, bis document allowlist/preview freeze vollständig sind. Das ist sicherer als ein halber Export.

Revision freeze current state:

- Implementiert für preview und consent. Consent gegen stale preview wird abgelehnt, wenn `case_revision` nicht mehr passt.

Consent current state:

- Consent erfordert shared sections, intended recipients, acknowledgement no final release und bei open points acknowledgement open points.
- `dispatch_enabled` bleibt false.
- Payload setzt `automatic_dispatch_allowed=False`.

Stale handling current state:

- Backend blockiert stale consent.
- Frontend zeigt stale/current Status und deaktiviert Consent bei stale preview.

Dispatch risks:

- Kein aktiver automatischer Versand gefunden.
- `InquiryDelivery` existiert als Modell mit `sent` status possibility, aber ohne `tenant_id`. Bei künftiger Aktivierung ist das ein hohes Governance-/Tenant-Risiko.

Unsafe copy risks:

- RFQ Pane ist überwiegend vorsichtig.
- Frontend-Copy-Test prüft einige verbotene Phrasen, ist aber lückenhaft: pluralisierte oder indirekte Empfehlungssprache kann durchrutschen.
- Chat empty state enthält “Empfehlungen” in allgemeiner Form; nach `AGENTS.md` ist “Empfehlung ableiten” ausdrücklich unsafe. Das sollte enger formuliert werden.

## 11. Support / Complaint / Compatibility Readiness

Compatibility inquiries:

- Teilweise möglich über Knowledge/chemical/material/medium services, aber nicht als v0.8.2-Szenario.
- Keine compound-specific validation boundary als strukturiertes Artifact gefunden.

Oil/lab report style inquiry:

- Upload und document candidate extraction existieren. Ein spezifischer Oil-/Lab-Report Intake mit Werte/Einheiten/Methode/Evidence ist nicht vollständig implementiert.

Complaint intake:

- Kein v0.8.2 complaint intake Artifact gefunden.
- Alte RCA-/failure routes können ähnliche Fälle technisch erfassen, aber ohne Complaint-spezifische Liability-/Customer-Reply-Grenzen.

Failure analysis:

- Teilweise. Failure/RCA ist als alte request type/projection vorhanden.
- Final-root-cause-Verbot ist konzeptionell und prompt-/guard-gestützt, aber nicht als failure-analysis artifact contract umgesetzt.

Customer reply draft:

- Kein produktiver v0.8.2-Draft-Artefakt gefunden.

Internal engineering note:

- Kein produktives v0.8.2-Artefakt gefunden.

No-final-claim safety:

- Output Guard und RFQ Boundary helfen.
- Alte chemical/compliance helpers können Formulierungen erzeugen, die ohne Renderer/Guard final wirken.

## 12. Upload / IP / Prompt Injection Readiness

Upload parsing:

- Implementiert für PDF/TXT/MD/DOCX-artige Dateien mit Content-Type-, Extension- und Magic-Checks.
- Size limits und page/chunk limits sind konfigurierbar.

Evidence handling:

- `RagDocument` speichert provenance, evidence refs, extracted candidates, status und ingest stats.
- Upload mit `case_id` kann document delta candidates erzeugen.

Document-derived candidates:

- Implementiert als Kandidaten/Proposed Fields, nicht direkte truth.
- Das passt zur v0.8.2-Regel “Uploads are data, never instructions”.

Prompt injection defense:

- Tests existieren (`backend/tests/agent/test_rag_injection.py`).
- LLM document content processing defaults sind off.
- Vollständige UI-/Artifact-Kennzeichnung von untrusted document-derived values ist noch ausbaufähig.

Path redaction:

- Backend redigiert interne Pfade in Fehlern/Status teilweise.
- RAG Health Contract und Frontend-Typ enthalten `filesystem.path`; UI-Hinweise nennen einen internen Upload-Pfad. User-facing Redaction sollte konsistenter werden.

Tenant isolation:

- Upload/list/delete/reingest nutzen tenant/user checks.
- Global upload scope ist admin-gebunden.

LLM processing gating:

- Config defaults deaktivieren dynamische LLM-Metadaten- und Dokumentcontent-Verarbeitung.
- Das ist gut für Pilot Safety.

## 13. Security / Tenant / Auth Findings

| Severity | Finding | Evidence | Risk | Recommended action |
|---|---|---|---|---|
| high | `InquiryDelivery` hat keinen eigenen `tenant_id`. | `backend/app/models/inquiry_delivery.py` | Künftige Versand-/Delivery-Artefakte könnten schwer tenant-isoliert auditierbar sein. | Vor jeder Dispatch-/Delivery-Erweiterung tenant_id additiv modellieren und IDOR tests ergänzen. |
| high | Alte MCP-Compliance/Chemical-Ausgaben können overclaimen. | `backend/app/mcp/calculations/compliance.py`, `backend/app/mcp/calculations/chemical_resistance.py` | User könnte “konform”, “zugelassen”, “geeignet” als finale Freigabe verstehen. | Tool-Ausgaben über guarded renderer/source labels führen oder intern halten. |
| high | v0.8.2-Partnernetzwerk-Disclosure fehlt. | `backend/app/services/problem_first_matching_service.py`, `frontend/src/lib/mapping/workspace.ts` | Matching könnte als neutral/full-market missverstanden werden. | Disclosure/no-fit/active-paid als Pflichtfelder im backend projection contract. |
| medium | Doppelte Auth-Seams im Backend. | `backend/app/services/auth/dependencies.py`, `backend/app/api/v1/dependencies/auth.py` | Drift zwischen HTTP/WS/BFF/Auth-Pfaden möglich. | Auth-Zuständigkeit dokumentieren und gemeinsame Tests für scopes/tenant claims. |
| medium | Frontend-BFF emittiert immer `case_bound`; FastResponder erzeugt backendseitig zwar keine CaseState-Antwort, aber UX kann Case-Erzeugung suggerieren. | `frontend/src/app/api/bff/agent/chat/stream/route.ts`, `backend/app/agent/api/routes/chat.py` | Small Talk kann produktseitig wie Case Intake wirken. | BFF erst nach backend state/case event binden oder `session_bound` von `case_bound` trennen. |
| medium | Light runtime kann governed snapshots persistieren. | `backend/app/agent/api/routes/chat.py`, `backend/app/agent/api/loaders.py`, `backend/app/agent/state/persistence.py` | Unklare Grenze zwischen Conversation/Exploration und durable case. | Tests für “greeting/general knowledge creates no CaseRecord” und klare mode persistence policy. |
| medium | Root/front package versions divergieren. | `package.json`, `frontend/package.json` | Build-/dependency confusion möglich. | Root package role klären; produktiv nur einen Frontend-Stack referenzieren. |
| medium | RAG Health kann filesystem path im Contract enthalten. | `frontend/src/lib/ragApi.ts`, `frontend/src/components/rag/RagDocumentGrid.tsx` | Interne Pfadstruktur user-visible. | Pfad serverseitig entfernen oder nur admin/debug-gated anzeigen. |
| medium | `.env*`-Dateien sind im Repo-Verzeichnis vorhanden. | `ls -al` Snapshot | Secrets Exposure Risiko, auch wenn Werte nicht geprüft/ausgegeben wurden. | Secret hygiene prüfen; falls committed/exposed: Rotation. |
| low | Compose enthält secret key names und einen literal default key. | `docker-compose.yml` | Deployment-Hygiene Risiko. | Production secret handling prüfen; keine Defaults für sensitive admin credentials. |

## 14. Test Coverage Map

| Test area | Existing tests found | Missing tests | Suggested test file | Priority |
|---|---|---|---|---|
| Fast responder / pre-gate | `backend/tests/unit/domain/test_pre_gate_classification.py`, `backend/tests/unit/services/test_pre_gate_classifier.py`, `backend/app/agent/tests/test_pre_gate_runtime_dispatch.py` | v0.8.2 `ConversationIntent` and no-case durable persistence tests | `backend/tests/unit/services/test_v082_conversation_routing.py` | high |
| General knowledge | `backend/app/services/knowledge/test_factcard_store.py`, `backend/tests/test_kb_services.py` | RAG-first, RAG-miss, fallback label tests | `backend/tests/unit/services/test_knowledge_answer_rag_first.py` | high |
| CaseType taxonomy | Old workspace routing tests | Full v0.8.2 CaseType classification matrix | `backend/tests/unit/domain/test_case_type_normalization.py` | high |
| ArtifactType taxonomy | RFQ preview tests | Artifact registry tests for all v0.8.2 artifact types | `backend/tests/unit/domain/test_artifact_type_registry.py` | high |
| Seal type normalization | `backend/app/agent/tests/test_rwdr_slice.py`, `test_engineering_path.py`, `test_sts_loader.py` | RWDR/Flachdichtung/Hydraulik/Pneumatik/O-Ring/X-Ring/Gleitring/Packung/Sonderprofil aliases | `backend/tests/unit/domain/test_seal_type_normalization.py` | high |
| Governed state | `backend/app/agent/tests/test_reducers.py`, `test_conflict_detection_reducer.py`, `test_stale_state_invalidation.py`, `backend/tests/unit/services/test_case_service.py` | v0.8.2 source_type/validation_status propagation | `backend/tests/unit/services/test_validation_status_projection.py` | high |
| RFQ preview/consent | `backend/app/api/tests/test_rfq_endpoint.py`, `backend/tests/unit/services/test_rfq_preview_service.py` | Local environment currently cannot import `backend/tests` due missing `alembic.config`; export allowlist tests | Existing RFQ test files | high |
| Upload safety | `backend/app/api/tests/test_rag_upload.py`, `test_rag_upload_limits.py`, `backend/tests/test_rag_upload_security.py` | User-facing path redaction for health UI/BFF | `backend/app/api/tests/test_rag_health_redaction.py`, `frontend/src/lib/ragApi.test.ts` | medium |
| Prompt injection | `backend/tests/agent/test_rag_injection.py` | Artifact-specific prompt injection tests | `backend/tests/agent/test_document_artifact_injection.py` | high |
| Manufacturer matching | `backend/tests/unit/services/test_problem_first_matching_service.py`, `backend/app/agent/tests/test_fit_score.py` | active_paid eligibility, disclosure, no-fit, payment no score influence in v0.8.2 matrix | `backend/tests/unit/services/test_manufacturer_fit_matrix.py` | high |
| Compliance overclaim | `backend/app/agent/tests/test_output_guard.py`, `backend/tests/unit/services/test_fda_food_contact_module.py`, `test_eu_food_contact_module.py` | MCP compliance user-visible guard tests | `backend/tests/test_mcp_compliance_claim_guard.py` | high |
| Frontend RFQ | `frontend/src/components/dashboard/RfqPane.test.tsx` | stale/error/rendering and disclosure states | Same file | medium |
| Frontend unsafe copy | `frontend/src/lib/unsafeProductCopy.spec.ts` | Plural/variant copy and cockpit/RAG files included | Same file | medium |
| Frontend Decision Understanding | None found as first-class UI | Rendering contract tests | `frontend/src/components/dashboard/DecisionUnderstandingPanel.test.tsx` | high |
| Tenant/IDOR | `backend/tests/agent/test_conversation_tenant_scope.py`, `backend/tests/agent/test_tenant_persistence_boundary.py`, auth tests | Artifact/RFQ/consent/upload cross-tenant negative tests | `backend/tests/security/test_artifact_tenant_scope.py` | high |

Validation commands run:

- `python -m pytest backend/app/agent/tests/test_interaction_policy.py backend/app/agent/tests/test_output_guard.py backend/app/agent/tests/test_document_delta.py -q` → passed, 101 tests.
- `python -m pytest backend/app/api/tests/test_rag_upload_limits.py backend/app/api/tests/test_rag_upload.py -q` → passed, 18 tests.
- `python -m pytest backend/app/api/tests/test_rfq_endpoint.py -q` → passed, 1 test.
- `python -m pytest backend/tests/unit/services/test_rfq_preview_service.py -q` → failed during import: `backend/tests/conftest.py` imports `alembic.config`, but local environment has no module `alembic.config`.
- `npm --prefix frontend run lint` → passed.
- `npm --prefix frontend run test:run -- src/lib/unsafeProductCopy.spec.ts src/components/dashboard/RfqPane.test.tsx` → passed, 2 files / 3 tests.

## 15. Immediate Risks

1. Matching/Recommendation Trust Risk: Manufacturer matching is not yet the v0.8.2 paid-partner-network flow. Any UI wording suggesting neutral recommendations or best manufacturer would violate the concept.
2. Compliance Overclaim Risk: Legacy MCP compliance/chemical tools contain language that can be read as final suitability or approval.
3. Scenario Drift Risk: v0.7 routing classes and old request types can route new v0.8.2 scenarios incorrectly or block them.
4. Seal-Type Misclassification Risk: Without central SealType normalization, RWDR/O-Ring/Gasket/Hydraulic/Pneumatic/Mechanical Seal cases can receive wrong intake questions.
5. RAG/Fallback Trust Risk: General knowledge is not RAG-first and has no visible fallback validation labels.
6. Durable-State Boundary Risk: The distinction between conversation session, light runtime persistence and real case creation is not user/product-clean enough.
7. Tenant Future Risk: `InquiryDelivery` lacks tenant id before any dispatch capability is added.
8. Frontend Product Risk: Decision Understanding is backend-modeled but not first-class in UI; current Cockpit state includes untracked files.

## 16. Recommended PR Roadmap

### PR 1 — v0.8.2 Conversation Routing Taxonomy

- Goal: Introduce read-only `ConversationIntent` and `ResponseMode` mapping over existing pre-gate without migration.
- Files likely touched: `backend/app/domain/pre_gate_classification.py`, `backend/app/services/pre_gate_classifier.py`, `backend/app/agent/api/dispatch.py`, tests.
- Tests to add/run: routing matrix for greetings, general knowledge, RFQ, matching, complaint, failure, compatibility; no durable case for greeting.
- Risk level: medium.
- Why now: It unblocks every scenario PR and reduces wrong case creation.

### PR 2 — CaseType Projection Skeleton

- Goal: Add v0.8.2 `CaseType` as backend domain/projection field, mapped from old request types.
- Files likely touched: `backend/app/api/v1/schemas/case_workspace.py`, `workspace_routing.py`, projection tests.
- Tests to add/run: all CaseTypes shallow recognition.
- Risk level: medium.
- Why now: Scenario architecture needs a stable axis before artifacts and UI.

### PR 3 — ArtifactType Registry

- Goal: Add code-level `ArtifactType` registry with RFQ preview as first implemented artifact and others as recognized/not implemented.
- Files likely touched: domain module, `InquiryExtract` service constants, RFQ tests.
- Tests to add/run: registry list and RFQ compatibility tests.
- Risk level: low/medium.
- Why now: Prevents string drift and clarifies concept-only artifacts.

### PR 4 — SealType Normalization Baseline

- Goal: Add `SealFamily`, `SealType`, alias normalizer and `SealApplicationProfile` read-only projection.
- Files likely touched: new backend domain module, `workspace_routing.py`, tests.
- Tests to add/run: RWDR/WDR/Simmerring, flat/flange gasket, hydraulic rod/piston, pneumatic, O-/X-ring, mechanical seal, packing, custom, unknown.
- Risk level: medium.
- Why now: Intake and matching depend on the technical object axis.

### PR 5 — Next Best Question Baseline

- Goal: Centralize 1-3 question policy using CaseType + SealType + current-state missing fields.
- Files likely touched: clarification priority/runtime/projection tests.
- Tests to add/run: emergency asks one question; no repeated known fields; type-specific first question.
- Risk level: medium.
- Why now: Makes SeaLAI feel like a sealing engineer instead of a generic form.

### PR 6 — Knowledge Answer RAG-First Contract

- Goal: Add source/validation-labeled knowledge answer flow using RAG/curated first and explicit RAG-miss.
- Files likely touched: `knowledge_service.py`, RAG orchestrator adapter, frontend contract.
- Tests to add/run: RAG hit, RAG miss, fallback disabled.
- Risk level: high.
- Why now: Reduces hallucination and meets v0.8.2 knowledge rules.

### PR 7 — LLM Research Fallback Labeling

- Goal: Optional fallback response object with `source_type=llm_research_fallback`, `validation_status=unvalidated`, general orientation only.
- Files likely touched: knowledge service, UI labels, tests.
- Tests to add/run: fallback cannot become confirmed case field.
- Risk level: high.
- Why now: Must be safe before enabling fallback behavior.

### PR 8 — SourceType / ValidationStatus Propagation

- Goal: Add v0.8.2 metadata to case fields/projections without destructive migration.
- Files likely touched: state models, reducers, workspace schemas, frontend mapping.
- Tests to add/run: document/user/calculated/inferred/conflict propagation.
- Risk level: medium/high.
- Why now: Needed by RFQ, fallback, upload and UI trust labels.

### PR 9 — RFQ Export Allowlist

- Goal: Implement manual preview export from frozen revision, still no dispatch.
- Files likely touched: RFQ endpoint/service/renderer/frontend.
- Tests to add/run: stale block, allowlist sections, no hidden attachments.
- Risk level: medium.
- Why now: Builds on strong RFQ preview seam.

### PR 10 — Manufacturer Fit Matrix Backend Projection

- Goal: Read-only partner fit matrix with disclosure, no-fit, gaps and no paid score boost.
- Files likely touched: capability service, new matching projection, tests.
- Tests to add/run: active_paid eligibility, no-fit, sponsored/listing tier no score effect.
- Risk level: high.
- Why now: v0.8.2 needs matching, but trust rules must come first.

### PR 11 — Manufacturer Fit UI

- Goal: Render backend matrix with mandatory SeaLAI partner-network disclosure.
- Files likely touched: workspace contract/mapping/dashboard components/tests.
- Tests to add/run: disclosure visible, no “best market” copy.
- Risk level: medium.
- Why now: UI only after backend projection is governed.

### PR 12 — Compatibility Inquiry Artifact

- Goal: Technical inquiry summary / compatibility matrix skeleton with no final compatibility.
- Files likely touched: scenario routing, artifact service/projection, tests.
- Tests to add/run: oil report/lab values candidates, missing compound evidence.
- Risk level: medium/high.
- Why now: High pilot value and bounded scope.

### PR 13 — Complaint and Failure Intake Artifacts

- Goal: Add complaint/failure intake artifacts, no liability admission, no final root cause.
- Files likely touched: case type routing, artifact projections, frontend rendering.
- Tests to add/run: leakage/swelling/cracking/repeated failure; customer draft absent unless explicit.
- Risk level: medium/high.
- Why now: Extends beyond RFQ while preserving safety.

### PR 14 — Upload Evidence UI Hardening

- Goal: Show document-derived values as candidates with evidence and remove user-visible filesystem paths.
- Files likely touched: RAG API/BFF/frontend RAG grid/chat delta UI.
- Tests to add/run: path redaction, candidate labels, tenant guard.
- Risk level: medium.
- Why now: Direct IP/security pilot readiness improvement.

### PR 15 — Compliance Claim Guard for MCP/Tools

- Goal: Wrap legacy compliance/chemical outputs with non-final labels or restrict exposure.
- Files likely touched: MCP knowledge tool/renderers/output guard/tests.
- Tests to add/run: FDA/ATEX/EHEDG/TA-Luft/“geeignet” overclaim cases.
- Risk level: high.
- Why now: Trust-critical before broader technical answers.

### PR 16 — Decision Understanding UI

- Goal: Render backend Decision Understanding as first-class cockpit panel.
- Files likely touched: workspace contract/mapping, dashboard component, tests.
- Tests to add/run: known/missing/risks/next question/manufacturer review needs.
- Risk level: medium.
- Why now: This is central to v0.8.2 USP and already modeled backend-side.

### PR 17 — Tenant/Artifact Access Test Sweep

- Goal: Add negative cross-tenant tests for RFQ preview/consent/artifacts/uploads.
- Files likely touched: tests primarily; small service guard fixes if needed.
- Tests to add/run: IDOR by case_id/preview_id/document_id.
- Risk level: high.
- Why now: Needed before exports, matching artifacts or delivery paths.

### PR 18 — Local Test Environment Repair

- Goal: Make `backend/tests` import path/dependencies reliable without production side effects.
- Files likely touched: dev requirements/test config only.
- Tests to add/run: RFQ unit tests and alembic model tests.
- Risk level: low.
- Why now: Current audit found `alembic.config` missing in local env for `backend/tests`.

## 17. First 3 Codex Implementation Prompts

### Prompt 1 — Conversation Routing Taxonomy

You are working in `/home/thorsten/sealai`. Read `AGENTS.md`, `konzept/SEALAI_V08_2_CODEX_IMPLEMENTATION_CONCEPT.md`, `konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md`, and relevant backend tests before editing.

Implement only PR 1: add a v0.8.2 conversation routing taxonomy on top of the current pre-gate without migrations. Add stable code-level `ConversationIntent` and `ResponseMode` values matching the v0.8.2 concept, map existing pre-gate results into them, and add tests proving greetings/meta/general knowledge do not create durable engineering case state while real technical domain inputs still route governed.

Do not run migrations. Do not restart/stop services. Do not clear Redis or Qdrant. Do not print secrets or `.env` values. Do not deploy or contact external APIs. Do not send RFQs or contact manufacturers.

Required tests: focused backend routing tests for small talk, general sealing question, new RFQ, manufacturer matching intent, compatibility inquiry, complaint, failure analysis, replacement/legacy part, and off-topic/unsupported. Run only safe local pytest commands.

Final report format: changed files, behavior implemented, tests run/results, risks/limitations, next suggested PR.

### Prompt 2 — CaseType Projection Skeleton

You are working in `/home/thorsten/sealai`. Read `AGENTS.md`, the active v0.8.2 concept, the pilot-readiness concept, and existing workspace routing/projection files before editing.

Implement only PR 2: introduce v0.8.2 `CaseType` as a backend domain/projection primitive without database migration. Map current routing/request-type heuristics to the v0.8.2 CaseTypes and expose the projected CaseType in the workspace projection. Do not delete old request_type fields; keep compatibility and add tests.

Do not run migrations. Do not restart/stop services. Do not touch production data. Do not print secrets. Do not deploy. Do not call external APIs. Do not send RFQs or contact manufacturers.

Required tests: all v0.8.2 CaseTypes must be recognized as implemented, partial, or shallow-recognized according to code behavior. Include negative tests for manufacturer matching not being blocked when framed as SeaLAI partner-network fit.

Final report format: changed files, mapping table, tests run/results, known gaps, next suggested PR.

### Prompt 3 — SealType Normalization Baseline

You are working in `/home/thorsten/sealai`. Read `AGENTS.md`, `konzept/SEALAI_V08_2_CODEX_IMPLEMENTATION_CONCEPT.md`, `konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md`, and relevant state/routing tests before editing.

Implement only PR 4: add a read-only backend seal type normalization baseline. Create code-level `SealFamily` and `SealType` definitions, a central alias normalizer, and a minimal `SealApplicationProfile` projection from existing state/routing data. Do not migrate the database and do not change authoritative persistence semantics.

Do not restart/stop services. Do not clear Redis or Qdrant. Do not print secrets. Do not deploy. Do not contact external APIs. Do not send RFQs or contact manufacturers.

Required tests: RWDR/WDR/Simmerring/radial shaft seal; flat/flange gasket; hydraulic rod and piston seal; pneumatic rod and piston seal; O-Ring; X-Ring; mechanical seal/Gleitringdichtung; gland packing/Stopfbuchspackung; custom profile; unknown seal. Add projection tests showing unknowns remain uncertain, not guessed.

Final report format: changed files, normalization table, tests run/results, limitations, next suggested PR.

## 18. Appendix: Evidence Index

Binding documents:

- `AGENTS.md`
- `konzept/SEALAI_V08_2_CODEX_IMPLEMENTATION_CONCEPT.md`
- `konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md`
- `frontend/DESIGN.md`
- `frontend/AGENTS.md`

Repo/config/deployment:

- `pytest.ini`
- `backend/pytest.ini`
- `backend/requirements.txt`
- `backend/requirements-dev.txt`
- `package.json`
- `frontend/package.json`
- `docker-compose.yml`
- `docker-compose.dev.yml`
- `docker-compose.deploy.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `nginx/default.conf`
- `ops/sealai-stack.service`

Backend entrypoints/routes:

- `backend/app/main.py`
- `backend/app/api/v1/api.py`
- `backend/app/api/v1/endpoints/rag.py`
- `backend/app/api/v1/endpoints/rfq.py`
- `backend/app/api/v1/endpoints/mcp.py`
- `backend/app/agent/api/router.py`
- `backend/app/agent/api/routes/chat.py`
- `backend/app/agent/api/routes/workspace.py`
- `backend/app/agent/api/routes/history.py`
- `backend/app/agent/api/routes/review.py`

Auth/security:

- `backend/app/services/auth/dependencies.py`
- `backend/app/services/auth/token.py`
- `backend/app/api/v1/dependencies/auth.py`
- `frontend/src/auth.ts`
- `frontend/src/proxy.ts`
- `frontend/src/lib/bff/auth-token.ts`
- `frontend/src/lib/bff/http.ts`

Models/migrations/state:

- `backend/app/models/case_record.py`
- `backend/app/models/case_state_snapshot.py`
- `backend/app/models/mutation_event_model.py`
- `backend/app/models/inquiry_extract.py`
- `backend/app/models/inquiry_delivery.py`
- `backend/app/models/rag_document.py`
- `backend/app/agent/state/models.py`
- `backend/app/agent/state/reducers.py`
- `backend/app/agent/state/persistence.py`
- `backend/app/services/case_service.py`
- `backend/alembic/versions/f2d9c4a8b6e1_add_cases_and_case_state_snapshots.py`
- `backend/alembic/versions/b8c4d6e2f901_make_case_tenant_ids_not_null.py`
- `backend/alembic/versions/c7d8e9f0a1b2_add_rfq_preview_consent_fields.py`
- `backend/alembic/versions/91f0c2d4a6b8_create_manufacturer_capability_tables.py`
- `backend/alembic/versions/c4d7e8f9a0b1_add_atex_capability_flag.py`

Conversation/routing/knowledge:

- `backend/app/domain/pre_gate_classification.py`
- `backend/app/services/pre_gate_classifier.py`
- `backend/app/services/fast_responder_service.py`
- `backend/app/services/knowledge_service.py`
- `backend/app/services/knowledge/factcard_store.py`
- `backend/app/services/knowledge_case_bridge_service.py`
- `backend/app/agent/api/dispatch.py`
- `backend/app/agent/runtime/gate.py`
- `backend/app/agent/runtime/conversation_runtime.py`
- `backend/app/agent/runtime/clarification_priority.py`
- `backend/app/agent/runtime/reply_composition.py`
- `backend/app/agent/runtime/output_guard.py`
- `backend/app/agent/prompts/renderer/base.j2`
- `backend/app/data/kb/SEALAI_KB_PTFE_factcards_gates_v1_3.json`

Workspace/projections/seal:

- `backend/app/api/v1/schemas/case_workspace.py`
- `backend/app/api/v1/projections/case_workspace.py`
- `backend/app/api/v1/projections/workspace_routing.py`
- `backend/app/api/v1/projections/ptfe_rwdr_enrichment.py`
- `backend/app/domain/engineering_path.py`
- `backend/app/domain/sealing_material_family.py`
- `backend/app/agent/data/sts/sealing_types.json`
- `backend/app/agent/domain/requirement_class.py`
- `backend/app/services/decision_understanding_service.py`
- `backend/app/services/medium_intelligence_service.py`

RAG/upload:

- `backend/app/services/rag/rag_orchestrator.py`
- `backend/app/services/rag/rag_ingest.py`
- `backend/app/services/rag/utils.py`
- `backend/app/services/rag/rag_schema.py`
- `backend/app/services/rag/qdrant_bootstrap.py`
- `backend/app/services/rag/bm25_store.py`
- `backend/app/services/rag/render.py`
- `backend/app/prompts/rag_synthesizer.j2`
- `backend/app/prompts/rag_metadata_extractor.j2`
- `backend/app/prompts/rag_platinum_extractor.j2`

RFQ/consent/artifacts:

- `backend/app/services/rfq_preview_service.py`
- `backend/app/services/inquiry_extract_service.py`
- `backend/app/api/v1/renderers/rfq_html.py`
- `backend/app/templates/rfq_template.html`
- `frontend/src/components/dashboard/RfqPane.tsx`
- `frontend/src/app/api/bff/rfq/[caseId]/preview/route.ts`
- `frontend/src/app/api/bff/rfq/[caseId]/preview/[previewId]/consent/route.ts`
- `frontend/src/app/api/bff/rfq/[caseId]/document/route.ts`

Manufacturer matching/capabilities:

- `backend/app/services/capability_service.py`
- `backend/app/services/problem_first_matching_service.py`
- `backend/app/agent/domain/fit_score.py`
- `backend/app/agent/graph/nodes/matching_node.py`
- `backend/app/agent/graph/nodes/manufacturer_mapping_node.py`
- `backend/app/agent/graph/nodes/rfq_handover_node.py`
- `backend/app/agent/data/manufacturers/pilot_manufacturers.json`

Compliance/calculations/MCP:

- `backend/app/services/norm_modules/base.py`
- `backend/app/services/norm_modules/fda_food_contact.py`
- `backend/app/services/norm_modules/eu_food_contact.py`
- `backend/app/services/norm_modules/certification.py`
- `backend/app/services/norm_modules/din_3760_iso_6194.py`
- `backend/app/services/norm_modules/registry.py`
- `backend/app/mcp/calculations/compliance.py`
- `backend/app/mcp/calculations/chemical_resistance.py`
- `backend/app/mcp/calculations/oring_groove.py`
- `backend/app/mcp/calc_engine.py`
- `backend/app/mcp/knowledge_tool.py`

Frontend routes/BFF/UI:

- `frontend/src/app/(app)/dashboard/page.tsx`
- `frontend/src/app/(app)/dashboard/[caseId]/page.tsx`
- `frontend/src/app/(app)/dashboard/new/page.tsx`
- `frontend/src/app/(app)/rag/page.tsx`
- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- `frontend/src/app/api/bff/agent/chat/history/[caseId]/route.ts`
- `frontend/src/app/api/bff/agent/session/[caseId]/case-delta/route.ts`
- `frontend/src/app/api/bff/agent/session/[caseId]/override/route.ts`
- `frontend/src/app/api/bff/workspace/[caseId]/route.ts`
- `frontend/src/app/api/bff/rag/documents/route.ts`
- `frontend/src/app/api/bff/rag/documents/[documentId]/route.ts`
- `frontend/src/app/api/bff/rag/documents/[documentId]/health-check/route.ts`
- `frontend/src/app/api/bff/rag/documents/[documentId]/reingest/route.ts`
- `frontend/src/components/dashboard/CaseScreen.tsx`
- `frontend/src/components/dashboard/ChatPane.tsx`
- `frontend/src/components/dashboard/ChatComposer.tsx`
- `frontend/src/components/dashboard/DashboardShell.tsx`
- `frontend/src/components/dashboard/SealCockpit.tsx`
- `frontend/src/components/rag/RagDocumentGrid.tsx`
- `frontend/src/lib/contracts/workspace.ts`
- `frontend/src/lib/mapping/workspace.ts`
- `frontend/src/lib/engineering/buildSealCockpitViewModel.ts`
- `frontend/src/lib/engineering/sealCockpitViewModel.ts`
- `frontend/src/lib/engineering/sealCockpitMock.ts`
- `frontend/src/lib/ragApi.ts`
- `frontend/src/lib/unsafeProductCopy.spec.ts`

Representative tests inspected or run:

- `backend/app/agent/tests/test_interaction_policy.py`
- `backend/app/agent/tests/test_output_guard.py`
- `backend/app/agent/tests/test_document_delta.py`
- `backend/app/agent/tests/test_case_workspace_projection.py`
- `backend/app/agent/tests/test_rwdr_slice.py`
- `backend/app/agent/tests/test_fit_score.py`
- `backend/app/api/tests/test_rag_upload.py`
- `backend/app/api/tests/test_rag_upload_limits.py`
- `backend/app/api/tests/test_rfq_endpoint.py`
- `backend/tests/unit/services/test_rfq_preview_service.py`
- `backend/tests/unit/services/test_problem_first_matching_service.py`
- `backend/tests/unit/services/test_fda_food_contact_module.py`
- `backend/tests/unit/services/test_eu_food_contact_module.py`
- `backend/tests/agent/test_rag_injection.py`
- `backend/tests/agent/test_tenant_persistence_boundary.py`
- `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts`
- `frontend/src/components/dashboard/RfqPane.test.tsx`
- `frontend/src/components/dashboard/CaseScreen.test.tsx`
- `frontend/src/components/dashboard/ChatComposer.test.tsx`
- `frontend/src/hooks/useCockpitData.test.tsx`
- `frontend/src/lib/mapping/workspace.test.ts`
- `frontend/src/lib/unsafeProductCopy.spec.ts`
