# SeaLAI SSoT Registry

This registry is the binding map for future patches. If a file is not listed as canonical here, it must not be treated as the source of truth without an explicit architecture update.

## Product Focus

- Current engineering MVP focus: PTFE radial shaft seals (`engineering_path=rwdr`, PTFE compound family).
- SeaLAI is a structured clarification, preselection and RFQ-readiness system. It does not issue final approvals or manufacturer-independent release decisions.
- LLM output may extract, normalize and propose. Backend-owned deterministic logic decides routing, gates, readiness, calculations, risk and release status.

## Canonical Runtime

| Concern | Canonical source | Role |
| --- | --- | --- |
| Product/runtime API | `backend/app/agent/api/router.py` | Canonical `/api/agent` mount. |
| Chat turn execution | `backend/app/agent/api/routes/chat.py` | Entry for non-stream chat requests. |
| Stream execution | `backend/app/agent/api/streaming.py` | Entry for SSE/chat stream events. |
| Governed graph turn | `backend/app/agent/api/governed_runtime.py` | Backend-owned governed runtime execution. |
| Runtime dispatch | `backend/app/agent/api/dispatch.py` | Chooses fast/light/governed path. |
| Public health | `backend/app/observability/health.py` | Health truth for deployed runtime. |

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
| Backend workspace projection | `backend/app/api/v1/projections/case_workspace.py` | Canonical backend read model. Refactor target: split, but preserve public contract. |
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

## Knowledge / RAG

| Concern | Canonical source | Role |
| --- | --- | --- |
| RAG API | `backend/app/api/v1/endpoints/rag.py` | RAG upload/list/delete facade. |
| RAG ingestion | `backend/app/services/rag/rag_ingest.py` | Document ingestion. |
| RAG retrieval/orchestration | `backend/app/services/rag/rag_orchestrator.py` | Retrieval, reranking and result shaping. |
| Qdrant bootstrap | `backend/app/services/rag/qdrant_bootstrap.py` | Collection/index setup. |
| PTFE KB files | `backend/app/data/kb/*.json` | Structured PTFE knowledge data. |

## Non-Canonical / Patch With Caution

- `archive/**`, `_trash/**`, `_local_keep/**`, `backups/**`, `langgraph_backup/**`, `erpnext-stack/**`, `crm-stack/**`: historical or operational material, never source of truth for product patches.
- `konzept/archive/**` and `konzept/audit/**`: historical context only. Current concept sources are the top-level files in `konzept/`, especially `SEALAI_KONZEPT_FINAL.md`, `sealai_ssot_architecture_plan.md`, `sealai_ssot_supplement_v3.md`, and `sealai_engineering_depth_ptfe_rwdr.md`.
- `backend/tests/contract/*` files that import `app.langgraph_v2`: legacy contract residue. They are not productive SSoT and should be migrated or removed in a dedicated cleanup.
- Any frontend heuristic that derives `engineering_path`, release state, readiness or matching truth is a rendering fallback only and must not supersede backend projection fields.

## Patch Rules

1. Mutations to case truth go through `GovernedSessionState`, reducers, runtime dispatch or persistence loaders.
2. UI data must come from `CaseWorkspaceProjection`; do not add a second workspace contract.
3. PTFE-RWDR logic belongs in deterministic backend services or a small projection adapter that calls those services.
4. Compatibility routes may read and project canonical state, but must not own state transitions.
5. New product code must not import `app.langgraph_v2`, `archive`, `_trash`, `_local_keep`, or backup trees.
6. New tests should target the canonical files above unless they explicitly validate compatibility behavior.
