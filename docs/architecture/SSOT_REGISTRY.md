# SeaLAI SSoT Registry

This registry is the binding map for future patches. If a file is not listed as canonical here, it must not be treated as the source of truth without an explicit architecture update.

## Product Focus

- Current architecture direction: V10 Conversational Sealing Intelligence.
- Current product focus: RWDR MVP / `Technical RWDR RFQ Brief`.
- Current public-facing product promise: sealing | Intelligence makes unclear
  RWDR inquiries manufacturer-evaluable.
- Current product principle: sealing | Intelligence does not decide the seal;
  sealing | Intelligence makes the inquiry decidable.
- V10 means: freely answer engineering knowledge questions, preserve
  conversational context, extract important facts into governed state only when
  a real sealing case is present, deterministically calculate, and only claim
  with evidence.
- The RWDR MVP means: extract RWDR inquiry facts, require user confirmation for
  liability-bearing fields, compute review signals, show missing data, create
  snapshots/revision diffs, and export a manufacturer-evaluation brief. It does
  not recommend material, product or manufacturer.
- SeaLAI is a sealing-intelligence, technical clarification, screening and
  RFQ-readiness system. It does not issue final approvals or
  manufacturer-independent release decisions.
- LLM output may classify, explain, extract, normalize and propose.
  Backend-owned deterministic logic decides routing, gates, state mutation,
  readiness, calculations, risk and release status.
- Knowledge dialogue must not create or mutate a case. Governed case intake is
  required once the user provides concrete application data or explicitly wants
  to work a case.
- Guided limited external RWDR demo is allowed only within the conditions in
  the RWDR MVP concept. Full app/public self-service remains out of scope until
  the SSoT is explicitly updated.

## Canonical Concepts

| Concern | Canonical source | Role |
| --- | --- | --- |
| Active RWDR MVP product concept | `docs/implementation/SEALAI_RWDR_MVP_PRODUCT_CONCEPT.md` | Binding product SSoT for the current MVP, guided external demo scope, Technical RWDR RFQ Brief, evidence/confirmation gates, status model, non-goals, demo script and reviewer feedback loop. |
| Active V10 architecture/runtime concept | `docs/implementation/SEALAI_V10_CONVERSATIONAL_SEALING_INTELLIGENCE_CONCEPT.md` | Binding architecture SSoT for free knowledge dialogue, semantic routing, context resolution, governed case intake, RAG, LangSmith, and deployment shape. |
| Active target architecture (V1.7) | `docs/sealing_intelligence_v1_7_universal_sealing_case_platform_blueprint.md` | Binding **architecture** blueprint: Universal Sealing Core vs Domain Pack split (RWDR = first pack), knowledge as first-class layer, tenant/governance as P0 foundation, resequenced roadmap. Wins on architecture-level conflicts. |
| Active operative contracts (V1.6) | `docs/sealing_intelligence_v1_6_mobile_first_complete_architecture_blueprint.md` | Binding **contract** layer under V1.7: mode contracts, knowledge/sheet/RFQ contracts, schemas, golden conversations. Its implementations (templates, knowledge_modes, rfq_one_pager, pocket cockpit, golden v16 tests) stay canonical. Wins on contract-level conflicts. |
| Agent operating contract | `AGENTS.md` | Practical instructions for Codex App/CLI and other coding agents. |
| SSoT registry | `docs/architecture/SSOT_REGISTRY.md` | Binding map for canonical files and patch authority. |
| Historical product context | `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md` and older implementation docs | Historical framing only. These files do not override V10 behavior or current code. |

## Canonical Runtime

| Concern | Canonical source | Role |
| --- | --- | --- |
| Product/runtime API | `backend/app/agent/api/router.py` | Canonical `/api/agent` mount. |
| RWDR/RFQ public API | `backend/app/api/v1/endpoints/rfq.py` | Canonical backend API for RWDR analyze, case read, confirmations, evaluate, brief, Markdown/PDF export, snapshots and revision diff. |
| Chat turn execution | `backend/app/agent/api/routes/chat.py` | Entry for non-stream chat requests. |
| Stream execution | `backend/app/agent/api/streaming.py` | Entry for SSE/chat stream events. |
| Governed graph turn | `backend/app/agent/api/governed_runtime.py` | Backend-owned governed runtime execution. |
| Runtime dispatch | `backend/app/agent/api/dispatch.py` | Chooses conversational/knowledge/governed path without duplicating architecture. |
| Semantic intent routing | `backend/app/services/semantic_intent_router.py`, `backend/app/services/pre_gate_classifier.py`, `backend/app/agent/prompts/communication/semantic_pre_gate_router.j2` | LLM-assisted semantic classification plus deterministic guardrails. |
| Knowledge override guard | `backend/app/agent/api/knowledge_override.py` | Hard guard that keeps general knowledge/material/comparison requests out of governed fallback unless concrete case facts exist. |
| Conversation runtime | `backend/app/agent/runtime/conversation_runtime.py`, `backend/app/agent/communication/communication_runtime_v8.py` | Fast conversational response layer for greetings, open invites, acknowledgements, and no-case knowledge bridging. |
| Final answer composition | `backend/app/agent/communication/answer_composer.py`, `backend/app/agent/communication/governed_answer_composer.py`, `backend/app/agent/prompts/governed/answer_composer.j2` | Guarded final-answer wording. |
| Public health | `backend/app/observability/health.py` | Health truth for deployed runtime. |

## Canonical RWDR MVP / RFQ Brief

| Concern | Canonical source | Role |
| --- | --- | --- |
| RWDR MVP product SSoT | `docs/implementation/SEALAI_RWDR_MVP_PRODUCT_CONCEPT.md` | Binding product doctrine, MVP scope, status model, evidence gate, RFQ brief structure and demo readiness conditions. |
| RWDR orchestrator, evidence gate, scope guard, calculations, brief model and exports | `backend/app/services/rwdr_mvp_brief.py` | Backend-owned RWDR product logic. This is the primary implementation home for the current RWDR MVP. |
| RFQ preview, consent, export and allowlisted artifact shaping | `backend/app/services/rfq_preview_service.py` | Frozen preview/export layer that embeds the `Technical RWDR RFQ Brief` without dispatch or recommendation claims. |
| RWDR API contract tests | `backend/app/api/tests/test_rwdr_golden_cases.py`, `backend/app/api/tests/test_rfq_endpoint.py` | End-to-end and route-level contract coverage for analyze, confirm, evaluate, brief, exports, snapshots and revision diff. |
| RWDR service tests | `backend/tests/unit/services/test_rwdr_mvp_brief.py`, `backend/tests/unit/services/test_rfq_preview_service.py` | Unit/contract tests for evidence confirmation, status semantics, forbidden language, PDF/Markdown export and preview behavior. |
| RWDR frontend/BFF contract | `frontend/src/lib/bff/workspace.ts`, `frontend/src/app/api/bff/rfq/**`, `frontend/src/components/dashboard/RfqPane.test.tsx` | Frontend bridge and UI coverage for the RWDR brief workflow. Rendering only; no engineering truth generation. |

RWDR customer-visible statuses are exactly:

```text
COMPLETE
NEEDS_CLARIFICATION
OUT_OF_SCOPE
```

`COMPLETE` means complete enough for manufacturer, distributor or responsible
engineer evaluation. It never means technical release, material suitability,
product recommendation or manufacturer approval.

RWDR MVP must not implement or expose:

```text
material recommendation
product recommendation
manufacturer recommendation
manufacturer listing
manufacturer routing
marketplace
automatic dispatch
final approval
life-time guarantee
certification claim
```

## Canonical State

| Concern | Canonical source | Role |
| --- | --- | --- |
| Governed case state model | `backend/app/agent/state/models.py` | SSoT state schema. |
| State reducers | `backend/app/agent/state/reducers.py` | Controlled mutation semantics. |
| Persistence | `backend/app/agent/state/persistence.py` | Stored snapshots and case persistence. |
| State loading facade | `backend/app/agent/api/loaders.py` | Preferred loading order for live/snapshot state. |

## Canonical Workspace / UI Contract

| Concern | Canonical source | Role |
| --- | --- | --- |
| Backend workspace projection facade | `backend/app/api/v1/projections/case_workspace.py` | Canonical public backend read model facade. Preserve public contract here. |
| Workspace routing projection | `backend/app/api/v1/projections/workspace_routing.py` | Deterministic request type and engineering path routing. |
| PTFE-RWDR workspace enrichment | `backend/app/api/v1/projections/ptfe_rwdr_enrichment.py` | Deterministic PTFE-RWDR read-model enrichment via V3 services. |
| Backend workspace schema | `backend/app/api/v1/schemas/case_workspace.py` | API response contract. |
| Agent workspace route | `backend/app/agent/api/routes/workspace.py` | Canonical workspace read route under `/api/agent`. |
| Compatibility workspace route | `backend/app/api/v1/endpoints/state.py` | Compatibility facade only. It may read canonical state and projection; it must not mutate canonical truth. |
| Frontend workspace contract | `frontend/src/lib/contracts/workspace.ts` | TypeScript API contract. |
| Frontend workspace mapper | `frontend/src/lib/mapping/workspace.ts` | Mapping/rendering only. Must not decide engineering truth. |

## Canonical PTFE-RWDR V3 Services

| Concern | Canonical source | Role |
| --- | --- | --- |
| Cascading calculations | `backend/app/services/calculation_engine.py` | Deterministic PTFE-RWDR calculations. |
| Application patterns | `backend/app/services/application_pattern_service.py` | Pattern candidates; user confirmation required. |
| Medium intelligence | `backend/app/services/medium_intelligence_service.py` | Medium context, not final release. |
| Advisory engine | `backend/app/services/advisory_engine.py` | Risk/advisory classification. |
| Problem-first matching | `backend/app/services/problem_first_matching_service.py` | Matching semantics and problem signature. |
| Manufacturer capability data | `backend/app/services/capability_service.py` | Manufacturer claims/capability filtering. |
| Terminology normalization | `backend/app/services/terminology_service.py` | Terms and generic concept mapping. |

These PTFE/RWDR services may support the RWDR MVP, but they do not supersede the
evidence/confirmation gate or the `Technical RWDR RFQ Brief` product boundary.

## Knowledge / RAG

| Concern | Canonical source | Role |
| --- | --- | --- |
| RAG API | `backend/app/api/v1/endpoints/rag.py` | RAG upload/list/delete facade. |
| RAG ingestion | `backend/app/services/rag/rag_ingest.py` | Document ingestion. |
| RAG retrieval/orchestration | `backend/app/services/rag/rag_orchestrator.py` | Retrieval, reranking and result shaping. |
| Qdrant bootstrap | `backend/app/services/rag/qdrant_bootstrap.py` | Collection/index setup. |
| Knowledge context builder | `backend/app/agent/communication/knowledge_context_builder.py` | Builds recent chat/material/entity/context payload for no-case knowledge answers and comparisons. |
| Knowledge answer prompt | `backend/app/agent/prompts/knowledge/answer_composer.j2` | Canonical Jinja2 structure for material explanations, follow-ups and comparisons. |
| Material comparison | `backend/app/services/knowledge/material_comparison.py` | Backend-owned material comparison support and known property framing. |
| Material/domain KB files | `backend/app/data/kb/*.json`, `backend/app/services/knowledge_service.py` | Curated structured knowledge data where implemented. |

## Conversation Context / Intent Rules

| Concern | Canonical source | Role |
| --- | --- | --- |
| Recent entity resolution | `backend/app/agent/communication/knowledge_context_builder.py`, `backend/app/services/semantic_intent_router.py` | Resolve PTFE/NBR/PEEK/FKM/etc. and anaphora such as "die beiden", "beide", "das", "damit". |
| Material question matrix | `backend/app/agent/tests/test_question_scenario_matrix.py` | Regression coverage for greetings, material explanations, follow-ups and contextual comparisons. |
| Semantic router tests | `backend/tests/unit/services/test_semantic_intent_router.py`, `backend/tests/unit/services/test_pre_gate_classifier.py`, `backend/tests/unit/services/test_material_knowledge_context_routing.py` | Regression coverage for phrasing-independent routing. |
| No-case session stability | `frontend/src/hooks/useAgentStream.ts`, `frontend/src/hooks/useAgentStream.test.tsx` | Keeps no-case conversation id stable across React remounts so follow-ups retain context. |

## Observability

| Concern | Canonical source | Role |
| --- | --- | --- |
| LangSmith helpers | `backend/app/observability/langsmith.py`, `backend/tests/unit/observability/test_langsmith_helpers.py` | Root and child trace metadata, privacy-aware content capture, route/action/case flags. |
| Quality layer | `backend/app/observability/sealai_quality.py` | Product-quality metadata and runtime transparency. |

## Deployment / Runtime Ops

| Concern | Canonical source | Role |
| --- | --- | --- |
| Compose deployment | `docker-compose.deploy.yml`, `.env.prod` on VPS | Current production wiring. Frontend runs as Docker service under `frontend-container` profile. |
| Runtime feature flags | `docker-compose.deploy.yml`, `.env.prod` on VPS | `.env.prod` is not sufficient by itself. Every active backend flag must be explicitly passed through the backend service environment, including semantic routing and LangSmith transparency flags. |
| Nginx edge | `nginx/default.conf` | Public reverse proxy. SealAI frontend routes go to Docker DNS `frontend:3000`; API routes go to `backend:8000`; Keycloak routes go to `keycloak:8080`. |
| Retired host frontend | PM2 process name `sealai-frontend` | Deprecated/stopped. Do not restart the old host Next.js process on `172.17.0.1:3000`. |

## Canonical Test Gates

| Gate | Command | Meaning |
| --- | --- | --- |
| RWDR guided-demo gate | `PYTHON_BIN=/home/thorsten/sealai/.venv/bin/python bash scripts/check_rwdr_mvp_demo.sh` | Required before claiming the guided RWDR demo path is healthy. |
| RWDR backend focus | `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py` | Required for changes touching RWDR/RFQ brief behavior. |
| V10 conversation/knowledge focus | `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_question_scenario_matrix.py backend/app/agent/tests/test_knowledge_context_builder.py backend/tests/unit/services/test_semantic_intent_router.py backend/tests/unit/services/test_pre_gate_classifier.py backend/tests/unit/services/test_material_knowledge_context_routing.py backend/app/agent/tests/test_pre_gate_runtime_dispatch.py backend/tests/unit/observability/test_langsmith_helpers.py` | Required for changes touching routing, knowledge, context or LangSmith. |
| Architecture guardrails | `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/architecture backend/app/agent/tests/test_governed_runtime_seam.py` | Required for architecture boundary changes. |
| Frontend full suite | `npm --prefix frontend run test:run` | Required for frontend behavior/copy/contract changes. |

## Non-Canonical / Patch With Caution

- `archive/**`, `_trash/**`, `_local_keep/**`, `backups/**`, `langgraph_backup/**`, `erpnext-stack/**`, `crm-stack/**`: historical or operational material, never source of truth for product patches.
- `konzept/archive/**` and `konzept/audit/**`: historical context only. Current concept sources are the top-level files in `konzept/`, especially `SEALAI_KONZEPT_FINAL.md`, `sealai_ssot_architecture_plan.md`, `sealai_ssot_supplement_v3.md`, and `sealai_engineering_depth_ptfe_rwdr.md`.
- Historical contract tests importing `app.langgraph_v2`: removed. Do not recreate them; current contract coverage belongs under `backend/tests/architecture`, `backend/tests/agent`, and `backend/app/agent/tests`.
- Historical V8/V9 implementation documents remain useful background, but they
  do not override V10 routing, conversation, deployment or LangSmith behavior.
- Historical audit reports under `docs/audits/**` are evidence of a point in
  time. They do not override the current RWDR MVP concept, V10 architecture
  concept, AGENTS.md or this registry.
- Any frontend heuristic that derives `engineering_path`, release state, readiness or matching truth is a rendering fallback only and must not supersede backend projection fields.

## Patch Rules

1. Mutations to case truth go through `GovernedSessionState`, reducers, runtime dispatch or persistence loaders.
2. UI data must come from `CaseWorkspaceProjection`; do not add a second workspace contract.
3. RWDR MVP product logic belongs in `backend/app/services/rwdr_mvp_brief.py`,
   `backend/app/services/rfq_preview_service.py` or thin adapters that call
   them.
4. Compatibility routes may read and project canonical state, but must not own state transitions.
5. New product code must not import `app.langgraph_v2`, `archive`, `_trash`, `_local_keep`, or backup trees.
6. New tests should target the canonical files above unless they explicitly validate compatibility behavior.
7. Knowledge explanations, material follow-ups and contextual comparisons must
   stay in knowledge/conversation mode unless concrete application facts are
   present.
8. Do not fix conversational routing by brittle wording checks alone. Use
   semantic intent, context resolution and deterministic hard guards.
9. Do not reintroduce host-managed SealAI frontend on port 3000. Production
   frontend is the Docker service behind Nginx.
10. Do not expand from guided RWDR demo to public self-service, manufacturer
    listing, routing or marketplace behavior without updating this registry and
    the RWDR product concept first.
