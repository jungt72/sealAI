# SealAI Current Implementation Concept - IST State

## 0. Document Metadata

- Date: 2026-05-19
- Branch: `redesign/sealai-cockpit-overview`
- Commit audited: `a3ec2dfb`
- Dirty state at audit start: clean (`git status --short` returned no files)
- Audit mode: read-first / audit-only / concept documentation
- Runtime diagnostics used: yes, read-only Docker, Qdrant, and Postgres checks
- Source-code changes made by this audit: this document only
- Deployment, ingestion, tests, restarts, DB writes, Qdrant writes, Paperless writes: not performed

Evidence:
- Baseline command output: `pwd=/home/thorsten/sealai`, branch `redesign/sealai-cockpit-overview`, head `a3ec2dfb`, clean `git status --short`.
- Runtime command output: `docker ps` showed `backend` image `ghcr.io/jungt72/sealai-backend:a3ec2dfb` healthy, `nginx` healthy, `qdrant` healthy, `paperless` healthy.
- Runtime command output: Postgres read-only count returned `sealai|paperless|indexed|7`.
- Runtime command output: Qdrant read-only summary returned `sealai_knowledge_v3` green with 83 points, `sealai_technical_docs` green with 9 points, and 83 `paperless` points in `sealai_knowledge_v3`.

## 1. Executive Summary

SealAI is currently implemented as a governed sealing-engineering runtime: a user-facing chat/workspace product that lets an LLM help with language, intake, and final wording, while deterministic backend modules own technical truth, check availability, risk semantics, RFQ readiness, and final-answer guardrails.

SealAI is not implemented as a final engineering release system, manufacturer approval system, compliance certification system, guaranteed compatibility engine, or automatic supplier dispatch system. This boundary is explicit in the repo contract and runtime guards.

Current maturity is strongest in the governed agent pipeline, deterministic RWDR and material/medium precheck hardening, backend-owned cockpit/check metrics, RFQ preview boundaries, and Paperless/RAG indexing. The biggest open implementation gap is the bridge from live Paperless/RAG evidence into persisted/operational Material Evidence Cards: Patch 9 adds a pure dry-run adapter, but no production import endpoint, card persistence, or automatic compatibility-precheck feed exists yet.

Biggest strengths:
- Clear active runtime rules: TurnEnvelope, FinalAnswerContext, deterministic engine, final guard, no raw technical LLM streaming.
- Typed backend state and projection contracts.
- Deterministic check registry with backend-owned metrics.
- Conservative material/medium compatibility prechecks with evidence gating and final approval blocked.
- Paperless and Qdrant exist and currently contain indexed Paperless-derived RAG data.
- Deployment has automated backend build/deploy and stack smoke checks.

Biggest risks and tuning candidates:
- Live Paperless/RAG evidence is indexed, but Material Evidence Cards are only validated/adapted through explicit structured payloads or dry-run candidate functions.
- Frontend cockpit types currently preserve generic check status/metrics but do not map the newest compatibility evidence metadata into the visible EngineeringCheckResult model.
- Documentation includes older SealAI/SealingAI architecture references that are partly stale relative to current hostnames, stack shape, and governed agent runtime.
- RFQ preview/export exists with consent boundaries, but supplier dispatch remains intentionally disabled and readiness from professional check groups can be deepened.

## 2. Product Concept as Implemented

SealAI is a conversation-first sealing intelligence product. The implemented UX starts with chat and builds a workspace/cockpit as technical facts become available. The active target is "Freely explain. Deterministically calculate. Only claim with evidence." (`AGENTS.md:3-7`).

The product concept as implemented:
- Users describe a sealing case in natural language.
- The backend classifies the turn, hydrates governed state, normalizes/asserts fields, runs deterministic checks, optionally retrieves evidence, and composes a guarded final answer.
- The cockpit/workspace shows known values, open points, checks, risks, RFQ/readiness state, and next questions.
- RFQ preview is a governed dossier basis, not automatic dispatch.
- Material/medium statements are precheck/orientation only and can become evidence-backed only when validated evidence card payloads are available.

Product boundaries:
- Calculated values are not release claims (`AGENTS.md:27-36`).
- Material family, compound, and product/article claims stay separate (`AGENTS.md:31-33`).
- RFQ output is a governed dossier, not just a form (`AGENTS.md:36`).
- Final release, guaranteed suitability, manufacturer approval, and compliance/certification claims are forbidden without explicit evidence and workflow (`AGENTS.md:78-90`).

## 3. Repository Map

High-level repo shape:
- `backend/app/agent`: governed agent runtime, LangGraph topology, state contracts, deterministic domain modules, communication/final-answer layer, tests.
- `backend/app/api`: v1 REST endpoints, workspace/RFQ/RAG projection endpoints.
- `backend/app/services`: auth, RAG/Paperless/Qdrant, RFQ preview, inquiry extracts, knowledge services, calculation/domain services.
- `backend/app/models`: SQLAlchemy persistence models for cases, snapshots, RAG documents, inquiry extracts, and related tables.
- `frontend/src`: Next.js app, Auth.js/Keycloak integration, BFF routes, dashboard UI, chat stream hook, workspace/cockpit mapping and tests.
- `docs/architecture` and `docs/audits`: architecture evidence, cleanup notes, previous audits, deprecated map.
- `konzept`: broader product/concept material, not always identical to current code.
- `ops`, `scripts`, `.github/workflows`, `docker-compose*.yml`, `nginx`, `paperless`: deployment, stack smoke, Paperless integration, and runtime operations.

Important source-of-truth documents:
- `AGENTS.md` is current and practical for runtime rules, safety boundaries, canonical entrypoints, and DoD.
- `frontend/DESIGN.md` is a current UX/design contract for the frontend surface.
- Older docs such as `backend/docs/audit_langgraph_stack.md`, `docs/codebase_overview.md`, and some runbooks contain useful history but include stale hostnames/services and should be treated as partial historical evidence rather than current implementation truth.

Evidence:
- Repo layout and runtime contract: `AGENTS.md:10-23`, `AGENTS.md:25-36`, `AGENTS.md:38-60`.
- Frontend design target: `frontend/DESIGN.md:1-22`.
- v1 API router composition: `backend/app/api/v1/api.py:7-47`.
- Agent canonical router composition: `backend/app/agent/api/router.py:56-84`.

## 4. Runtime / Deployment Architecture

Current deployed/runtime architecture:
- Public edge: `nginx` on ports 80/443.
- Frontend: host-managed Next.js on the Docker host, reached by nginx via `172.17.0.1:3000`; the frontend container service exists only under a Compose profile.
- Backend: FastAPI container `backend`, image `ghcr.io/jungt72/sealai-backend:a3ec2dfb`, local port bound to `127.0.0.1:8000`.
- Auth: Keycloak container behind `https://sealingai.com/realms/sealAI`.
- Data/services: Postgres 15, Redis Stack, Qdrant, Tika, Gotenberg.
- Paperless: separate Paperless container on the external `sealai_default` network.
- Monitoring: Prometheus and Grafana are present.

Build/deploy path:
- `build-and-push.yml` builds the backend Docker image from `backend/Dockerfile` and tags it by short SHA plus latest (`.github/workflows/build-and-push.yml:41-61`).
- `deploy.yml` resolves a digest-pinned backend image, updates `.env.prod` on the VPS, runs `./ops/up-prod.sh`, then `./ops/stack_smoke.sh` (`.github/workflows/deploy.yml:27-66`).
- `ops/up-prod.sh` validates `.env.prod`, prepares the backend data volume, pulls/recreates backend/keycloak/gotenberg/tika, then restarts nginx to refresh Docker upstreams (`ops/up-prod.sh:22-33`).
- `ops/stack_smoke.sh` checks backend/keycloak/redis, public `/api/agent/health`, and Keycloak OIDC metadata using default issuer `https://sealingai.com/realms/sealAI/.well-known/openid-configuration` (`ops/stack_smoke.sh:17-24`, `ops/stack_smoke.sh:166-184`).

Nginx routing:
- `/api/agent/health` and `/api/` proxy to `backend:8000`.
- `/realms/`, `/resources/`, `/login-actions/`, `/admin/` proxy to `keycloak:8080`.
- `/api/auth/` and `/api/bff/` proxy to the host frontend at `172.17.0.1:3000`.

Evidence:
- Compose services and env wiring: `docker-compose.deploy.yml:1-190`.
- Nginx host/frontend note: `nginx/default.conf:11-14`.
- Nginx backend/Keycloak/BFF routes: `nginx/default.conf:141-197`, `nginx/default.conf:247-292`.
- Paperless separate compose: `paperless/docker-compose.yml:19-39`.
- Runtime command output: `backend`, `keycloak`, `nginx`, `qdrant`, `postgres`, `redis`, `paperless`, `gotenberg`, `tika` were running; `backend` and `nginx` healthy.

## 5. Backend Architecture

The backend is a FastAPI application with a canonical agent API and a legacy/service `/api/v1` surface.

Primary backend layers:
- App startup and health: `backend/app/main.py`.
- v1 service API: `backend/app/api/v1/api.py`.
- Canonical agent API: `backend/app/agent/api/router.py`.
- Auth/JWT dependencies: `backend/app/services/auth`.
- Governed agent runtime: `backend/app/agent/api`, `backend/app/agent/graph`, `backend/app/agent/state`, `backend/app/agent/v92`.
- Deterministic domain checks: `backend/app/agent/domain`.
- RAG/Paperless/Qdrant services: `backend/app/services/rag`.
- Persistence: SQLAlchemy models in `backend/app/models`.

Production-critical endpoints:
- `/health`, `/readyz`, `/api/v1/ping`, `/api/agent/health`.
- `/api/agent/chat` and `/api/agent/chat/stream`.
- `/api/agent/workspace/{case_id}` and snapshot endpoints.
- `/api/v1/rag/*` and `/internal/rag/ingest`.
- `/api/v1/rfq/preview`, `/api/v1/rfq/preview/{preview_id}/consent`, `/api/v1/rfq/preview/{preview_id}/export`.

Persistence model:
- `cases` stores case metadata, tenant/user IDs, revision, request/engineering path, RFQ flags, and payload (`backend/app/models/case_record.py:14-68`).
- `case_state_snapshots` stores revisioned governed state JSON (`backend/app/models/case_state_snapshot.py:11-25`).
- `rag_documents` stores RAG/Paperless document metadata, status, source IDs, extracted candidates, evidence refs, provenance, and ingest stats (`backend/app/models/rag_document.py:10-35`).
- `inquiry_extracts` stores RFQ preview/extract artifacts, consent fields, and dispatch-disabled state (`backend/app/models/inquiry_extract.py:14-58`).

State persistence:
- Live governed state is Redis-scoped by tenant, owner, and case/session (`backend/app/agent/api/loaders.py:114-134`).
- Persisted governed state snapshots are written after live state save; snapshot failure logs a warning rather than breaking the turn (`backend/app/agent/api/loaders.py:199-243`).
- Workspace projection prefers snapshot state when comparable, otherwise Redis live state (`backend/app/agent/api/loaders.py:539-584`).

## 6. Auth / Tenant Model

Auth model:
- Frontend uses Auth.js/NextAuth with Keycloak provider, default issuer `https://sealingai.com/realms/sealAI`, pinned auth/token/userinfo endpoints, PKCE/state checks, and offline access for refresh tokens (`frontend/src/auth.ts:5-24`, `frontend/src/auth.ts:89-115`).
- Backend verifies Keycloak JWTs against JWKS with RS256 only, issuer validation, leeway, and audience/azp/client checks (`backend/app/services/auth/token.py:24-41`, `backend/app/services/auth/token.py:100-157`).
- FastAPI dependencies build `RequestUser` from JWT claims, roles, scopes, and optional tenant claim (`backend/app/services/auth/dependencies.py:26-34`, `backend/app/services/auth/dependencies.py:133-173`).

Tenant scoping:
- Agent state scope is `(tenant_id, owner_id, case_id)` with fallback tenant `"default"` if JWT tenant claim is absent (`backend/app/agent/api/deps.py:21-24`).
- RAG document loading is tenant-scoped and RAG admins can access shared/global scope where allowed (`backend/app/api/v1/endpoints/rag.py:105-128`).
- Qdrant filters require tenant values and allow shared/public visibility under controlled filters (`backend/app/services/rag/rag_orchestrator.py:538-617`).
- RAG retrieval hard-aborts if tenant is missing (`backend/app/agent/services/real_rag.py:54-86`).

Internal/admin boundaries:
- `/internal/rag/ingest` is protected by `X-SeaLAI-Webhook-Token` compared to configured Paperless webhook token (`backend/app/api/v1/endpoints/rag.py:131-143`, `backend/app/api/v1/endpoints/rag.py:542-568`).
- RAG upload global scope requires RAG admin (`backend/app/api/v1/endpoints/rag.py:321-341`).

Security/tuning risks:
- Missing JWT tenant claim falls back to `"default"` in agent state scope; this is functional but should be reviewed against production tenancy expectations.
- Paperless sync/webhook exists but operational token presence and timer enablement were not modified or verified in this audit.
- Some older docs mention legacy hostnames and Strapi-era paths; use current code/config for security decisions.

## 7. Conversation / Agent Architecture

User turn lifecycle:
1. Frontend sends chat to BFF stream route.
2. BFF obtains Auth.js token and forwards to backend `/api/agent/chat/stream`.
3. Backend dispatch classifies runtime mode and decides governed vs light runtime.
4. Governed runtime hydrates current state, builds GraphState input with TurnEnvelope, runs the LangGraph governed graph, persists state, and emits guarded output.
5. BFF suppresses raw backend `text_chunk`/`text_reset`, then emits visible answer stream from final guarded text and state update.
6. Frontend hook updates chat, case binding, and stream workspace.

LLM boundaries:
- Graph topology states that only `intake_observe` may call the LLM for technical observation and `governed_answer_composer` may call LLM for text-only wording; intermediate nodes are deterministic/side-effect bounded (`backend/app/agent/graph/topology.py:6-31`, `backend/app/agent/graph/topology.py:55-62`).
- `run_governed_graph_turn` states technical draft tokens stay internal until final guard (`backend/app/agent/api/governed_runtime.py:161-233`).
- SSE maps technical chunks to progress and suppresses raw answer events until final (`backend/app/agent/api/streaming.py:111-149`).
- BFF stream route drops backend `text_chunk` and `text_reset` events and streams final answer tokens only after final answer text appears (`frontend/src/app/api/bff/agent/chat/stream/route.ts:341-400`).

Turn/output contracts:
- `TurnEnvelope` validates technical turns do not direct-stream and require final guard (`backend/app/agent/v92/contracts.py:56-83`).
- `FinalAnswerContext` forces technical answers without revision into review-required status (`backend/app/agent/v92/contracts.py:123-163`).
- Frontend contracts preserve TurnEnvelope, FinalGuardResult, V9.2 dashboard, and final answer trace (`frontend/src/lib/contracts/agent.ts:47-86`, `frontend/src/lib/contracts/agent.ts:351-383`).

Final guard:
- Forbidden patterns include final release, suitability without scope, absolute material-medium compatibility, certification/compliance, root cause certainty, prompt leakage, and placeholders (`backend/app/agent/v92/final_guard.py:17-78`).
- Technical output is validated and can be blocked with deterministic fallback (`backend/app/agent/v92/final_guard.py:90-250`).
- Governed answer composer validates streaming prefix and complete answer for leakage/approval patterns (`backend/app/agent/communication/governed_answer_composer.py:136-147`, `backend/app/agent/communication/governed_answer_composer.py:432-485`).

## 8. Deterministic Sealing Engine

Canonical field model:
- Core fields include medium, sealing type, application, industry, motion, compliance requirements (`backend/app/domain/critical_field_contract.py:9-21`).
- Operating fields include pressure role split: `pressure_system_bar`, `pressure_at_seal_bar`, `pressure_delta_bar`, and `ambiguous_pressure_bar` (`backend/app/domain/critical_field_contract.py:23-49`).
- RWDR/professional fields include shaft diameter, speed, surface, roughness, hardness, runout/eccentricity, lubrication, contamination (`backend/app/domain/critical_field_contract.py:51-111`).

Check/risk model:
- Registered checks include circumferential speed, pressure x velocity, DN, temperature headroom, and pressure window (`backend/app/agent/domain/checks_registry.py:36-95`).
- RWDR professional checks cover pressure role, surface, roughness, hardness, runout/eccentricity, lubrication, and contamination (`backend/app/agent/domain/checks_registry.py:289-593`).
- Compatibility precheck is appended to registry output and exposes evidence/status metadata (`backend/app/agent/domain/checks_registry.py:606-693`, `backend/app/agent/domain/checks_registry.py:847-856`).
- Backend check metrics are computed from registry results and identify passed/failed/blocked/pending counts (`backend/app/agent/domain/checks_registry.py:859-888`).

Risk semantics:
- Risk claims are typed as measured risk, missing input risk, ambiguity risk, context advisory, and blocked claim (`backend/app/agent/domain/risk_claims.py:9-57`).
- Unsupported measured claims fail when required measured evidence is missing (`backend/app/agent/domain/risk_claims.py:92-150`).
- Risk/readiness evaluation distinguishes missing critical fields, unknowns, and conservative labels (`backend/app/agent/domain/risk_readiness.py:1-5`, `backend/app/agent/domain/risk_readiness.py:208-283`).

Material/medium compatibility:
- Compatibility statuses include supported_precheck, caution_zone, missing_input, ambiguous_input, insufficient_evidence, not_applicable, and blocked_claim (`backend/app/agent/domain/compatibility_precheck.py:24-32`).
- Evidence statuses include no_evidence, evidence_found, insufficient_evidence, conflicting_evidence, and compliance_evidence_required (`backend/app/agent/domain/compatibility_precheck.py:48-54`).
- Missing medium/material/temp and generic medium/material block strong compatibility claims (`backend/app/agent/domain/compatibility_precheck.py:763-827`, `backend/app/agent/domain/compatibility_precheck.py:857-872`).
- Compliance without card evidence is blocked (`backend/app/agent/domain/compatibility_precheck.py:829-850`).
- Valid evidence cards can support precheck only as orientation; no evidence remains insufficient (`backend/app/agent/domain/compatibility_precheck.py:874-1016`).

Question planner:
- Clarification priorities include medium, concentration, pH, material, compliance evidence, pressure roles, and RWDR fields (`backend/app/agent/runtime/clarification_priority.py:49-182`, `backend/app/agent/runtime/clarification_priority.py:423-620`).

Current limitations:
- Deterministic depth is strongest for RWDR and material/medium prechecks; broader seal-type depth exists as scaffolding but is not equally mature.
- Compatibility precheck consumes evidence card payload aliases only when cards are supplied in profile/context; it does not automatically query live Paperless/Qdrant and persist cards (`backend/app/agent/domain/compatibility_precheck.py:211-217`, `backend/app/agent/domain/compatibility_precheck.py:405-412`).

## 9. State / Projection / Cockpit Model

State model:
- State is layered: observed, normalized, asserted, evidence/governance and derived slices; raw LLM/user text does not shortcut to asserted truth (`backend/app/agent/state/models.py:4-20`).
- `FieldStatus`, `Provenance`, `EngineeringValue`, and `CaseField` carry typed field values and provenance (`backend/app/agent/state/models.py:115-164`).
- `GovernedSessionState` aggregates slices for persistence/projection (`backend/app/agent/state/models.py:1218-1289`).

Projection:
- Backend workspace projection is controlled and excludes prompt traces/raw LLM artifacts (`backend/app/api/v1/schemas/case_workspace.py:1-15`).
- `EngineeringCheckResult` includes compatibility status, evidence status, evidence refs, limitations, missing/ambiguous fields, and `final_approval_claim_allowed=false` (`backend/app/api/v1/schemas/case_workspace.py:648-693`).
- Backend projection uses registered check results and check metrics from the check registry (`backend/app/api/v1/projections/case_workspace.py:40-43`, `backend/app/api/v1/projections/case_workspace.py:1847`, `backend/app/api/v1/projections/case_workspace.py:1233-1255`).
- Workspace route loads governed projection source and projects from governed state (`backend/app/agent/api/routes/workspace.py:148-174`).

Frontend cockpit:
- `useCockpitData` returns backend `workspace.cockpit` when present; fallback cockpit is explicitly marked `frontend_non_authoritative_placeholder` (`frontend/src/hooks/useCockpitData.ts:227-245`, `frontend/src/hooks/useCockpitData.ts:179-186`).
- The view model uses backend cockpit checks when present, including backend check metrics (`frontend/src/lib/engineering/buildSealCockpitViewModel.ts:234-245`, `frontend/src/lib/engineering/buildSealCockpitViewModel.ts:297-314`).
- Gap: frontend `EngineeringCheckResult` currently contains generic evidenceFields/derivedFrom but not the newest compatibility evidence_status/evidence_refs/evidence_summary/evidence_limitations fields; raw mapping also does not map them (`frontend/src/lib/engineering/cockpitModel.ts:43-66`, `frontend/src/lib/mapping/workspace.ts:832-859`).

## 10. RAG / Paperless / Qdrant / Evidence Model

Paperless ingest:
- Paperless is running separately and connected to `sealai_default` network (`paperless/docker-compose.yml:19-39`).
- Paperless script can call internal RAG ingest webhook with document ID and token (`paperless/scripts/sealai-rag-webhook.sh:4-15`, `paperless/scripts/sealai-rag-webhook.sh:20-35`).
- A user-level timer/service definition exists for periodic Paperless to RAG sync, but this audit did not inspect systemd runtime state (`ops/systemd/user/sealai-rag-paperless-sync.service:1-6`, `ops/systemd/user/sealai-rag-paperless-sync.timer:1-12`).
- CLI wrapper `ops/bin/sealai-rag-paperless-sync` runs `sync_paperless_to_rag` and `process_pending_paperless_documents` inside the backend container (`ops/bin/sealai-rag-paperless-sync:1-23`).

RAG document sync:
- `sync_paperless_to_rag` fetches Paperless docs/tags, requires URL/token, applies tag readiness, creates/updates `RagDocument` rows with `source_system=paperless`, source IDs, evidence refs, and provenance (`backend/app/services/rag/paperless.py:208-503`).
- Pending documents are processed by `process_pending_paperless_documents` via the worker (`backend/app/services/rag/paperless.py:152-195`, `backend/app/services/jobs/worker.py:31-107`).
- RAG ingest writes chunk metadata and upserts Qdrant points with tenant/document/source metadata (`backend/app/services/rag/rag_ingest.py:980-1114`).

Retrieval:
- Governed evidence node builds deterministic evidence queries from asserted state, not raw user text, and skips/fail-opens when no tenant/assertions are available (`backend/app/agent/graph/nodes/evidence_node.py:1-31`, `backend/app/agent/graph/nodes/evidence_node.py:126-170`, `backend/app/agent/graph/nodes/evidence_node.py:309-437`).
- Retrieval uses tenant-scoped hybrid Qdrant/BM25 with shared-tenant inclusion where configured (`backend/app/services/rag/rag_orchestrator.py:840-960`).
- Real RAG service has three tiers: hybrid, BM25, empty fallback, and requires tenant (`backend/app/agent/services/real_rag.py:54-229`).

Runtime IST:
- Paperless running: yes, container `paperless` healthy, runtime image `ghcr.io/paperless-ngx/paperless-ngx:2.20.15`.
- Qdrant running: yes, container `qdrant` healthy.
- DB: `rag_documents` contains 7 indexed Paperless rows for tenant `sealai`.
- Qdrant: collection `sealai_knowledge_v3` contains 83 points with `metadata.source_system=paperless`; collection `sealai_technical_docs` contains 9 points.

Current gap:
- RAG evidence is retrieved as evidence cards/source snippets for the governed graph. Material Evidence Cards are a separate validated card schema. Patch 9 provides dry-run conversion from Paperless/RAG-like metadata into card candidates, but no automatic live conversion, persistence, or production ingestion endpoint exists.

## 11. Material Evidence / Knowledge Card Model

Validator:
- `material_evidence_cards.py` validates schema, source metadata, claim level, claim type, material/medium fields, temperature/pH/concentration constraints, final approval flags, compliance flags, and overclaim wording (`backend/app/agent/domain/material_evidence_cards.py:1-6`, `backend/app/agent/domain/material_evidence_cards.py:167-230`, `backend/app/agent/domain/material_evidence_cards.py:279-322`).
- Claim levels are restricted to L1/L2/L3 and claim types to compatibility observation/precheck, caution, limitation, incompatibility observation, compliance certificate, and manufacturer datasheet reference (`backend/app/agent/domain/material_evidence_cards.py:56-68`).
- Cards with final approval requests, compliance claims without certificate evidence, or unsafe wording are blocked/downgraded and cannot support precheck (`backend/app/agent/domain/material_evidence_cards.py:279-320`).
- Support is allowed only for supporting claim types, L2/L3, exact material and exact medium, no missing concentration, and positive verdict (`backend/app/agent/domain/material_evidence_cards.py:368-403`).

Adapter:
- `material_evidence_adapter.py` is pure dry-run only: it does not read/write Paperless, Qdrant, or DB (`backend/app/agent/domain/material_evidence_adapter.py:1-6`).
- It maps Paperless/RAG-like dictionaries into Patch-8 card candidates, preserving source system, IDs, references, tags, route, source hash, statement/excerpt, and provenance (`backend/app/agent/domain/material_evidence_adapter.py:108-160`, `backend/app/agent/domain/material_evidence_adapter.py:230-242`).
- It validates candidates through the card validator and aggregates valid/invalid/downgraded/skipped counts plus missing fields, limitations, and safety warnings (`backend/app/agent/domain/material_evidence_adapter.py:245-310`).

Integration:
- Compatibility precheck can consume evidence card aliases: `compatibility_evidence_cards`, `material_knowledge_cards`, `knowledge_cards`, `evidence_cards`, `material_evidence` (`backend/app/agent/domain/compatibility_precheck.py:211-217`).
- Only validated/supported cards can become evidence refs in precheck; invalid cards become limitations rather than support (`backend/app/agent/domain/compatibility_precheck.py:577-681`).
- Final approval remains false at both card and precheck levels.

## 12. RFQ / Readiness / Export State

RFQ readiness:
- Deterministic RFQ intent classifier detects readiness, missing fields, preview/PDF, build-basis, and external contact requests (`backend/app/agent/communication/rfq_intent.py:102-196`).
- RFQ readiness projection is conservative: consent required, dispatch/external contact false, final approval false, preview requires explicit endpoint/user intent (`backend/app/agent/communication/rfq_intent.py:45-72`, `backend/app/agent/communication/rfq_intent.py:284-346`).

RFQ preview/export:
- `/api/v1/rfq/preview` requires explicit user intent and rejects dispatch/external contact flags (`backend/app/api/v1/endpoints/rfq.py:61-112`).
- Preview response always reports dispatch/external contact false and manufacturer review required (`backend/app/api/v1/endpoints/rfq.py:229-259`).
- `RfqPreviewService` stores preview artifacts in `inquiry_extracts`, validates manufacturer view allowlist, keeps dispatch disabled, requires consent before export, and checks stale revisions (`backend/app/services/rfq_preview_service.py:494-549`, `backend/app/services/rfq_preview_service.py:577-682`).
- Legacy direct RFQ download is disabled with 410 (`backend/app/api/v1/endpoints/rfq.py:221-226`).

Graph handover:
- RFQ handover graph node is deterministic, no LLM and no dispatch side effects (`backend/app/agent/graph/nodes/rfq_handover_node.py:1-14`).
- It blocks unless governance/matching/review conditions are met, and writes only `RfqState` (`backend/app/agent/graph/nodes/rfq_handover_node.py:177-379`).

Current gap:
- RFQ preview/export is present, but true external manufacturer dispatch is not active by design.
- RFQ readiness can be improved by explicitly deriving readiness from professional check groups and evidence limitations.

## 13. Frontend Architecture

Frontend stack:
- Next.js app with Auth.js/NextAuth Keycloak integration.
- BFF routes under `/api/bff/*` bridge browser sessions to backend APIs.
- Dashboard components render chat, workspace, cockpit, RFQ, RAG document views.
- Mapping layer converts backend workspace projection into frontend view models.

Chat stream:
- `useAgentStream` sends to BFF stream endpoint, tracks case binding, progress, guarded final answer text, stream workspace, and history sync (`frontend/src/hooks/useAgentStream.ts:337-500`).
- BFF stream route forwards access token to backend and maps backend SSE into client-safe events (`frontend/src/app/api/bff/agent/chat/stream/route.ts:251-286`, `frontend/src/app/api/bff/agent/chat/stream/route.ts:320-500`).

Cockpit/workspace:
- Frontend workspace contract includes material intelligence, RFQ readiness, cockpit/check metrics, and safety flags (`frontend/src/lib/contracts/workspace.ts:81-152`, `frontend/src/lib/contracts/workspace.ts:429-450`, `frontend/src/lib/contracts/workspace.ts:600-634`).
- Workspace mapping preserves cockpit sections, checks, check metrics, completeness metrics, RFQ readiness, and older V9/V9.1 slices (`frontend/src/lib/mapping/workspace.ts:22-137`, `frontend/src/lib/mapping/workspace.ts:832-885`).
- UI fallback cockpit is explicitly non-authoritative when backend cockpit is absent (`frontend/src/hooks/useCockpitData.ts:179-186`).

UX/design:
- `frontend/DESIGN.md` describes the current design intent as a conversation-first engineering workspace, one expert speaker, stable dashboard, and non-authoritative placeholders where backend truth is missing.

Current frontend gap:
- Compatibility evidence card metadata is available in backend schema/checks but not yet fully typed/mapped/rendered in frontend cockpit check rows.

## 14. Testing & Quality

Tracked backend tests:
- `backend/app/agent/tests`: 130 tracked agent tests, including graph, runtime, final guard, communication, patch 1-9 regression files, V9.2 contracts, cockpit metrics, workspace projection, and RFQ readiness.
- `backend/tests`: 135 tracked backend tests, including migrations, auth, RAG ingest/retrieval/security, Qdrant, visibility filters, compliance, calculations, source validation, observability, and service/domain tests.
- Additional backend API/service tests live under `backend/app/api/tests`, `backend/app/services/rag/tests`, and related subtrees.

Tracked frontend tests:
- 35 tracked frontend test/spec files cover BFF stream, BFF workspace/RFQ routes, dashboard components, cockpit view model/metrics, workspace mapping, stream workspace, unsafe product copy, and auth proxy behavior.

Patch-specific regression tests present:
- Patch 1: `test_slot_truth_patch1.py`
- Patch 2: `test_pressure_truth_patch2.py`
- Patch 3: `test_cockpit_metrics_patch3.py`
- Patch 4: `test_risk_claim_evidence_gate_patch4.py`
- Patch 5: `test_rwdr_professional_checks_patch5.py`
- Patch 6: `test_material_medium_compatibility_patch6.py`
- Patch 7: `test_material_knowledge_evidence_patch7.py`
- Patch 8: `test_material_evidence_ingestion_patch8.py`
- Patch 9: `test_material_evidence_adapter_patch9.py`

Recommended future regression suite:
- Backend focused: patch 1-9 files, `test_challenge_engine.py`, `test_communication_scenario_suite.py`, `v92/test_v92_runtime_contracts.py`, `test_case_workspace_projection.py`, `backend/tests/unit/projections/test_source_validation_projection.py`.
- Frontend focused: `useAgentStream.test.tsx`, BFF stream route spec, `useCockpitData.test.tsx`, `buildSealCockpitViewModel.metrics.test.tsx`, `workspace.test.ts`, RFQ route specs.
- Ops smoke: `./ops/stack_smoke.sh` after deploy only, not during read-only concept work.

Evidence:
- Tracked test discovery output from `git ls-files`: 130 `backend/app/agent/tests` files, 135 `backend/tests` files, 35 frontend test/spec files.

## 15. Known Gaps / Tuning Candidates

P0 - correctness / safety:
- Verify tenant fallback `"default"` is acceptable for all production users, or require explicit tenant claim for governed state and RAG.
- Add a production-safe Paperless/RAG to Material Evidence Card dry-run endpoint/admin command before any write path.
- Keep frontend from presenting compatibility evidence as stronger than backend wording; current frontend does not expose evidence card limitations deeply.
- Review older docs/runbooks with stale hostnames and old stack references.

P1 - product trust / UX:
- Surface compatibility `evidence_status`, `evidence_refs`, and `evidence_limitations` in cockpit check details.
- Show blocked checks and missing fields more explicitly in user workflow.
- Make RFQ readiness visibly derive from professional check groups and evidence gaps.
- Add a visible Material Evidence Card dry-run report for admins before ingestion.

P2 - depth / capability:
- Persist validated Material Evidence Cards with source versioning and provenance.
- Convert selected Paperless/RAG chunks into validated card candidates through a controlled dry-run first, then a reviewed import.
- Broaden deterministic depth beyond RWDR into additional seal families.
- Strengthen compliance evidence distinction between general orientation cards and explicit certificates.

P3 - ops / maintainability:
- Align Paperless compose file image (`2.20.10`) with runtime image (`2.20.15`) or document external management.
- Reduce local test discovery noise from virtualenv/node_modules by documenting `git ls-files` or scoped `find` commands.
- Consolidate old architecture docs into current concept plus deprecated map.
- Verify Paperless timer/service installation state without changing it.

## 16. Architecture Decision Map

| Decision | Current implementation | Evidence | Tradeoff | Tuning option |
|---|---|---|---|---|
| Technical truth ownership | Backend deterministic state/checks own technical truth; LLM can observe/word only within guardrails | `backend/app/agent/graph/topology.py:55-62`, `backend/app/agent/v92/final_guard.py:90-227` | Safer claims, more backend complexity | Keep expanding check registry and typed projections |
| Output gating | Technical turns require TurnEnvelope, FinalAnswerContext, final guard, and guarded final stream | `backend/app/agent/v92/contracts.py:56-83`, `frontend/src/app/api/bff/agent/chat/stream/route.ts:341-400` | Some latency, stronger safety | Improve trace visibility in UI |
| State persistence | Redis live state plus Postgres snapshots | `backend/app/agent/api/loaders.py:114-243`, `backend/app/models/case_state_snapshot.py:11-25` | Resilient projection fallback, more sync logic | Add projection drift monitors |
| RAG source model | Paperless sync creates RagDocument rows and Qdrant chunks with tenant/source metadata | `backend/app/services/rag/paperless.py:428-456`, `backend/app/services/rag/rag_ingest.py:1014-1080` | Good provenance, card conversion still missing | Dry-run adapter endpoint, then reviewed card persistence |
| Material compatibility | Conservative precheck, evidence card support optional, no final approval | `backend/app/agent/domain/compatibility_precheck.py:742-1016` | Avoids unsafe compatibility claims | Persist validated cards and show evidence limits in UI |
| RFQ preview | Explicit user intent and consent, dispatch disabled | `backend/app/api/v1/endpoints/rfq.py:61-112`, `backend/app/services/rfq_preview_service.py:494-682` | Safer but less automated | Add RFQ readiness from professional check groups |
| Deployment | GHCR backend image, workflow-driven deploy, stack smoke, nginx upstream refresh | `.github/workflows/deploy.yml:27-66`, `ops/up-prod.sh:22-33` | Operationally pragmatic | Add drift reporting for runtime vs compose-managed side services |
| Frontend cockpit | Uses backend cockpit when available, fallback marked non-authoritative | `frontend/src/hooks/useCockpitData.ts:227-245`, `frontend/src/hooks/useCockpitData.ts:179-186` | Safe fallback, evidence detail not fully visible | Map/render compatibility evidence metadata |

## 17. Evidence Appendix

Key code facts:
- Runtime contract and safety: `AGENTS.md:25-36`, `AGENTS.md:78-90`.
- FastAPI startup/mounts: `backend/app/main.py:139-184`, `backend/app/main.py:285-316`.
- v1/agent routers: `backend/app/api/v1/api.py:7-47`, `backend/app/agent/api/router.py:56-84`.
- Auth/JWT: `backend/app/services/auth/dependencies.py:26-34`, `backend/app/services/auth/token.py:100-157`, `frontend/src/auth.ts:5-115`.
- Agent graph: `backend/app/agent/graph/topology.py:6-31`, `backend/app/agent/graph/topology.py:55-62`, `backend/app/agent/graph/topology.py:301-382`.
- Governed runtime/SSE/BFF: `backend/app/agent/api/governed_runtime.py:161-233`, `backend/app/agent/api/streaming.py:111-149`, `frontend/src/app/api/bff/agent/chat/stream/route.ts:341-400`.
- V9.2 contracts/final guard: `backend/app/agent/v92/contracts.py:56-83`, `backend/app/agent/v92/contracts.py:123-163`, `backend/app/agent/v92/final_guard.py:17-78`.
- State/persistence: `backend/app/agent/state/models.py:4-20`, `backend/app/agent/api/loaders.py:199-243`, `backend/app/models/case_record.py:14-68`.
- Check registry: `backend/app/agent/domain/checks_registry.py:36-95`, `backend/app/agent/domain/checks_registry.py:606-693`, `backend/app/agent/domain/checks_registry.py:859-888`.
- Compatibility precheck: `backend/app/agent/domain/compatibility_precheck.py:24-54`, `backend/app/agent/domain/compatibility_precheck.py:742-1016`.
- Material evidence validation/adapter: `backend/app/agent/domain/material_evidence_cards.py:167-403`, `backend/app/agent/domain/material_evidence_adapter.py:1-6`, `backend/app/agent/domain/material_evidence_adapter.py:245-310`.
- RAG/Paperless: `backend/app/api/v1/endpoints/rag.py:522-568`, `backend/app/services/rag/paperless.py:208-503`, `backend/app/services/rag/rag_ingest.py:980-1114`.
- Evidence node/retrieval: `backend/app/agent/graph/nodes/evidence_node.py:126-170`, `backend/app/services/rag/rag_orchestrator.py:840-960`, `backend/app/agent/services/real_rag.py:54-229`.
- RFQ preview/readiness: `backend/app/agent/communication/rfq_intent.py:45-72`, `backend/app/api/v1/endpoints/rfq.py:61-112`, `backend/app/services/rfq_preview_service.py:494-682`.
- Frontend cockpit/stream: `frontend/src/hooks/useAgentStream.ts:337-500`, `frontend/src/hooks/useCockpitData.ts:227-245`, `frontend/src/lib/engineering/buildSealCockpitViewModel.ts:234-314`.
- Deployment: `.github/workflows/build-and-push.yml:41-61`, `.github/workflows/deploy.yml:27-66`, `ops/up-prod.sh:22-33`, `ops/stack_smoke.sh:166-184`.

Runtime facts from read-only diagnostics:
- `docker ps`: `backend` image `ghcr.io/jungt72/sealai-backend:a3ec2dfb`, healthy; `nginx` healthy; `qdrant` healthy; `paperless` healthy.
- `docker compose ps`: backend digest-pinned image running; keycloak image running; nginx running; qdrant/postgres/redis running.
- Postgres read-only query: `rag_documents` has 7 indexed Paperless rows for tenant `sealai`.
- Qdrant read-only query: `sealai_knowledge_v3` has 83 points, all 83 counted with `metadata.source_system=paperless`; `sealai_technical_docs` has 9 points.

Inferences:
- SealAI is mature enough for guarded, deterministic prequalification and evidence-scoped orientation, especially RWDR and material/medium prechecks.
- The live Paperless/RAG store is active, but Material Evidence Card production ingestion is not complete because the implemented adapter is pure dry-run and no persistence/import endpoint was found.
- Frontend can show backend-owned cockpit/check metrics, but evidence-card detail visibility needs another mapping/rendering step.

Gaps:
- No live write path from Paperless/RAG into persisted Material Evidence Cards.
- No automatic compatibility precheck retrieval from Qdrant-to-card conversion.
- RFQ dispatch disabled by design.
- Some docs and compose references are partially stale against runtime.
