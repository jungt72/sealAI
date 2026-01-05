# SealAI Stack Audit – LangGraph Focus

_Audit date: 2025-08-28 • Auditor: Codex (GPT-5) • Scope: full repository with emphasis on the LangGraph multi-agent system_

## 1. Scope & Context
- Evaluate backend, frontend, infrastructure, and CI with the goal of a production-ready, maintainable stack.
- Deep dive into LangGraph orchestration (supervisor vs. specialists, routing, memory, RAG, streaming).
- Identify technical debt, redundancy, dead code, and security risks; define a phased refactor plan (PR chain).

## 2. Repository Topology Snapshot
- `backend/`: FastAPI application, LangGraph services, agents, database, docs, tests.
- `frontend/`: Next.js 15 (App Router) dashboard + landing page, NextAuth for Keycloak SSO, streaming chat client.
- Infra: `docker-compose*.yml`, `Dockerfile`s, `nginx/`, `k8s/`, GitHub Actions workflows, `Makefile` for e2e tests.
- Legacy/dumps: `_audit/`, `CACHED/`, `langgraph_local/`, `node_modules/` (checked in), `.venv/`, historic scripts and dumps.

## 3. Backend Architecture (FastAPI)
### 3.1 Application entry
- `backend/app/main.py`: creates FastAPI app, wires `/api/v1`, compiles LangGraph on startup, warms LLM + long-term memory.
- Startup flow selects graph builder via `GRAPH_BUILDER` env (`supervisor` default, `consult` or `mvp` fallback).

### 3.2 API surface
- `backend/app/api/v1/api.py`: aggregates routers. Key endpoints:
  - `/api/v1/ai/ws`: WebSocket gateway (modern streaming path) backed by `app/services/chat`.
  - `/api/v1/langgraph/...`: SSE proxy over LangGraph events.
  - REST fallback `/api/v1/ai/beratung` (legacy direct invoke) still active.
  - `/api/v1/test/consult/invoke`: debug route calling outdated `invoke_consult`; currently broken (signature mismatch) and should be removed/archived.
- Auth dependencies: `app/services/auth/dependencies.py`, `app/api/v1/dependencies/auth.py` provide JWT verification and WS guarding.

### 3.3 Service layout
```
backend/app/services/
  auth/        # JWT verification helpers
  chat/        # WS orchestration (rate limiting, streaming, cancel)
  langgraph/   # core orchestration, prompts, nodes, tools
  memory/      # short-term memory helpers
  rag/         # Qdrant + BM25 orchestrator
```
- Current structure already close to desired target, but several orphaned modules remain (`graph/nodes/*`, `graph/sealai_consult_flow`, `redis_checkpointer.py`).

### 3.4 Data & persistence
- Redis: session + STM (`memory_utils`, `chat/ws_handler`). Checkpointer uses Redis when available, fallback to in-memory.
- Postgres: configured via `app/core/config.py`; user profiles fetched in `profile_node`. Alembic present.
- Qdrant: vector store for RAG and long-term memory (LTM).

## 4. LangGraph Orchestration (Multi-Agent)
### 4.1 Supervisor graph (`app/services/langgraph/graph/supervisor_graph.py`)
- State schema `ChatState`: `messages`, `intent`, `query_type`.
- Entry node `router`: uses `intent_router.classify_intent` (LLM + heuristics) to choose between consult vs. chitchat.
- `complexity_router`: classifies query simple vs. complex; simple routed to `simple_response` (LLM without RAG).
- `consult` branch embeds the Consult subgraph (see below) as a child graph.
- Tools: `ltm_search`, `ltm_store` for memory operations exposed via tool binding.
- Streaming support: `chitchat` node uses `RunnableLambda` and streaming LLM; transitions log via `wrap_node_with_logging` and `log_branch_decision`.
- Observed gaps:
  - Determinism relies on LLM routers; no explicit structured planner node.
  - `classify_intent` fallback defaults to consult, which is safe but increases latency for pure chitchat if router fails.
  - No explicit tracing hooks to LangSmith despite env placeholders.

### 4.2 Consult graph (`app/services/langgraph/graph/consult/build.py`)
Flow overview:
1. **Lite Router** → `smalltalk` short circuit (regex) or continue to consult pipeline.
2. `intake` → `profile` → `extract` → `domain_router` → `compute`.
3. Deterministic enrichment: `deterministic_calc` (physics) → `calc_agent` (LLM-based heuristics).
4. `ask_missing` gate: opens UI form via `ui_event` when mandatory params absent, otherwise proceed.
5. `validate` → `prepare_query` → `ltm` (fetch user-specific memory) → `rag` (Qdrant hybrid retrieval).
6. **Branch** on `_after_rag`: `recommend` (structured JSON, streaming) → `validate_answer` (confidence), or `explain` (Markdown summarizer).
7. `respond` (phase marker) → `summarize` (LLM summary + LTM persist) → END.

Node responsibilities:
- Parameter extraction: `extract` merges heuristic + LLM extraction; handles aliasing.
- Domain detection: `domain_router` uses LLM router with heuristics fallback; limited domain list (`rwdr`, `hydraulics_rod`).
- Memory integration: `ltm_node` merges Qdrant LTM context; `summarize_node` writes summary to Redis + Qdrant.
- UI integration: many nodes emit `ui_event` for Sidebar (missing parameters, calc snapshots).
- Logging: every node wrapped with `wrap_node_with_logging`, branch decisions logged with state snapshot.

### 4.3 Memory & Checkpointing
- Conversation STM: `consult/memory_utils.py` storing conversation history (`chat:stm:{thread_id}`) in Redis; summarization adds `summary` key.
- Checkpointer: `redis_lifespan.get_redis_checkpointer` tries multiple constructor signatures for compatibility; stored on `app.state` and reused for graph compilation.
- Duplicate legacy code: `backend/app/redis_checkpointer.py` (prior implementation) unused; should be archived.

### 4.4 Streaming & Runtime glue (`app/services/chat`)
- `ws_handler.py`: orchestrates WebSocket lifecycle, guards tokens, handles rate limiting, `remember` commands (writes to LTM), routes between direct LLM streaming and supervised graph.
- `ws_streaming.py`: ensures graph compiled, streams LangGraph events (`astream_events`), coalesces tokens, emits UI events, handles cancellations/timeouts, falls back to sync invoke or bare LLM if graph fails.
- SSE endpoint mirrors logic (`langgraph_sse.py`) for HTTP streaming.
- Observed issues:
  - Legacy WS handler in `api/v1/endpoints/ai.py` duplicates functionality without auth/rate limiting parity; should be retired post migration.
  - No LangSmith/observability integration inside streaming pipeline.

### 4.5 Telemetry & Tracing
- Logging is consistent (structlog + `wrap_node_with_logging`).
- Metrics: `app/services/langgraph/metrics.py` optional Prometheus counters exist but not wired.
- Telemetry placeholder (`tools/telemetry.py`) writes to Redis; consumed by legacy nodes only.
- LangSmith environment variables exist but code does not conditionally enable tracing.

### 4.6 Alignment with LangGraph best practices
| Practice | Status | Notes |
| --- | --- | --- |
| Explicit supervisor with declarative routing | ✅ | Supervisor graph delegates to consult graph; deterministic edges defined. |
| Persistent state via Redis checkpointer | ⚠️ Partial | Checkpointer available but not enforced (falls back silently). Need consistent namespace + error surfacing. |
| Clear IO schemas per node | ⚠️ Mixed | Consult nodes rely on open dicts; no `TypedDict` enforcement except `ConsultState`. Consider dataclasses/pydantic for clarity. |
| Minimal prompt leakage, tool separation | ⚠️ Partial | Some prompts embed context manually; ensure secrets not interpolated. |
| Observability (LangSmith / telemetry) | ❌ Missing | No integration beyond logging; add `langsmith` run tracing via env toggle. |
| Modular subgraphs | ✅ | Consult graph modular, but old `graph/nodes` modules linger. |

## 5. RAG & Long-Term Memory
- `app/services/rag/rag_orchestrator.py`: Hybrid retrieval against Qdrant, optional Redis BM25 (disabled by default). Handles embeddings (SentenceTransformer), reranking (CrossEncoder), caching via module globals.
  - Needs better error surfacing and resource management (model loading heavy at runtime, no health check).
  - Missing async/http timeouts for Qdrant fallback (currently 5s static) and no retry/backoff.
- Long-term memory tool (`tools/long_term_memory.py`): Qdrant client with prewarm and dedup; called from supervisor tools and summarizer.
  - Thread-safe initialization with RLock; fallback to logging on errors.
  - Coupled to environment defaults (`sealai_ltm`); recommend centralizing config.
- Collection naming: `rag_orchestrator` defaults to `sealai-docs`; LTM uses `sealai_ltm`. Need migration plan & consistent prefix via env.
- Missing caching layer for repeated queries; consider employing `functools.lru_cache` or Qdrant filters by chat/user.

## 6. Authentication & Security
- Backend JWT verification: `services/auth/token.py` (RS256 only), caches JWKS, enforces issuer/audience.
- WS guard (`api/v1/dependencies/auth.py`): accepts tokens via header/query/protocol; optional origin enforcement via env (`ALLOWED_ORIGIN`).
  - `WS_AUTH_OPTIONAL` defaults to `1` in `ai.py` legacy path – should be removed or set to `0`.
  - Rate limiting via Redis in `ws_handler` (per user/chat).
- Frontend uses NextAuth with Keycloak provider; middleware enforces auth on `/dashboard`.
- Keycloak Docker image built from `keycloak/` and configured through compose.
- Security gaps:
  - Secrets (.env, client JSONs) stored in repo; ensure sanitized or move to `archive/` then `.gitignore`.
  - Legacy endpoints bypass guard (`consult_invoke`, `ai.py`), no auth.
  - WebSocket allowlist not enforced by default; tighten env defaults.

## 7. Frontend Architecture (Next.js 15)
- App Router with `src/app`; landing page `page.tsx`, dashboard under `/dashboard`.
- Chat stack: `useChatThreadId`, `useAccessToken`, `useChatWs`, `ChatContainer` with streaming text merging. UI events from backend open sidebar forms.
- Components: duplicated `.save` files under `components/Chat` (artefacts). `out.css` and `node_modules` committed.
- Auth: NextAuth client, middleware ensures redirect to Keycloak.
- Observations:
  - Legacy pages (e.g. `src/app/register/page.js`) and HTML prototypes remain.
  - `node_modules/` at repo root and under `frontend/` tracked → must be removed/archived.
  - CSS build artefacts (`out.css`) and `.save` backups should be archived.
  - No unit/integration tests for frontend streaming or form logic.

## 8. Infrastructure & Operations
- Dockerfiles:
  - Backend multi-stage (wheel build → slim runtime). Installs `torch` CPU (heavy dependency—confirm necessity).
  - Frontend builds standalone Next.js server, runs as non-root.
- `docker-compose.yml`: orchestrates Postgres, Redis, Qdrant, Keycloak, backend, frontend, Nginx, plus `material-agent` & `normen-agent` stubs (FastAPI microservices returning static responses). These agents are not integrated in current LangGraph flow; consider removing or archiving to reduce deployment surface.
- `docker-compose.deploy.yml`: pins images to GHCR `latest`; lacking version pinning.
- Nginx config handles WS/SSE upgrades, Keycloak subdomain, HSTS.
- K8s manifests exist but not aligned with new structure; will need updates post refactor.
- CI: `.github/workflows/ci.yml` runs backend pytest + ruff; no frontend tests/build, no coverage gate. `deploy.yml` triggers on `build-and-push` workflow; currently expects secrets.

## 9. Technical Debt & Redundancies
- Legacy/unused modules:
  - `backend/app/api/v1/endpoints/ai.py` (legacy WS), `consult_invoke` (broken debug), `graph/sealai_consult_flow.py`, `graph/nodes/*`, `graph/mvp_graph.py` (if MVP path abandoned), `redis_checkpointer.py` (duplicate), `agents/*` (stub microservices), `tools/telemetry.py` (unused), `policies/model_routing.py` (not referenced).
  - Backup files (`*.bak`, `*.save.*`) across backend & frontend.
- Large artefacts: `node_modules/`, `.venv/`, numerous data dumps (`code_dump_*.txt`, `consultgraph_full_dump.txt`) clutter repo.
- Tests: minimal (`backend/tests/test_explain_node.py`, `tests/test_consult_e2e.py`). `.pytest_cache/` committed.
- Config sprawl: multiple `.env.*` tracked with likely secrets; duplicates referencing outdated env vars.
- Requirements: `torch==2.8.0+cpu` with `--extra-index-url`; verify actual usage (no on-device inference observed besides embeddings/rerank). Possibly remove or gate behind optional extra.

## 10. Testing & CI State
- Backend pytest exists but coverage unknown; no coverage threshold enforcement.
- No integration tests for WebSocket streaming or supervisor routing.
- Frontend lacks automated tests (unit/e2e) and lint config beyond `next lint`.
- CI does not run formatting (black), type checking (mypy), or frontend build.
- Recommendation: introduce `pytest --cov`, add WebSocket integration tests (asyncclient), create frontend Playwright/Cypress smoke tests, and expand CI jobs accordingly.

## 11. Production-Readiness Gaps
1. **Observability**: No LangSmith or OpenTelemetry tracing; limited metrics.
2. **Auth hardening**: Legacy unauthenticated endpoints, optional WS auth flag default permissive.
3. **Config management**: Secrets in repo, inconsistent env usage (`OPENAI_MODEL` vs `LLM_MODEL_DEFAULT`). Need `.env.example` alignment and Pydantic validation.
4. **Error handling**: Many try/except swallow errors (e.g., silent fallback to in-memory checkpointer); need explicit alerts.
5. **Resource management**: SentenceTransformer & CrossEncoder load synchronously on first request; warmup present but no health indicator.
6. **Redundant services**: Stub agents increase surface area; remove or replace with LangGraph nodes.
7. **Repo hygiene**: Node modules, caches, dumps inflate repo and complicate CI.
8. **Test coverage**: Critical flows (supervisor routing, RAG integration, streaming) lack automated coverage.

## 12. Refactor & Delivery Plan (PR Chain)
### PR #1 – Audit Report & Target Architecture
- Publish this audit (`docs/architecture/stack_audit_report.md`).
- Author roadmap (`docs/runbooks/dev_onboarding.md` placeholder to fill later).
- Confirm stakeholders on target directory layout (`backend/app/{api,services,config,models,utils}`) and LangGraph design principles.

### PR #2 – LangGraph Core Refactor
- Consolidate LangGraph modules under `backend/app/services/langgraph/` per target structure.
- Remove/arch archive legacy graphs (`graph/nodes`, `sealai_consult_flow`, `redis_checkpointer.py`).
- Tighten supervisor + consult graphs: add typed state objects, ensure deterministic routing, integrate LangSmith instrumentation (conditional on env).
- Normalize prompt handling (central config, limited env sprawl), ensure tool usage isolated.

### PR #3 – Cleanup & Structure Harmonization
- Remove or archive legacy endpoints (`ai.py`, `consult_invoke`), stub agents, and backup files; move to `archive/` directory per guardrails.
- Delete tracked artefacts (`node_modules`, `.venv`, dumps`), update `.gitignore`.
- Reorganize backend modules to match desired tree, align imports (black/ruff).
- Align frontend folders, prune `.save` files, unify component structure.

### PR #4 – Production Hardening, Docs & Tests
- Implement logging/metrics upgrades, enforce WS auth & rate limiting defaults, centralize config management.
- Add health checks, rate limiting to REST endpoints, and tighten Keycloak verification (origin claims etc.).
- Expand test suite: backend unit/integration (supervisor routing, rag, streaming), frontend tests (chat, sidebar interactions), coverage ≥85%.
- Extend CI: run lint/format/type, backend coverage, frontend build/tests.
- Deliver `docs/runbooks/dev_onboarding.md` with setup, env vars, deploy instructions.
- Update Docker Compose (remove deprecated services, pin versions), add `docker compose up` smoke test.

## 13. Immediate Next Steps & Risks
- **Prioritize cleanup of tracked secrets/artefacts** to avoid accidental leaks and reduce friction before large refactors.
- **Decide on stub agents**: either integrate into LangGraph as tools/nodes or remove to simplify deployments.
- **Confirm RAG dependency footprint** (torch, transformers) with infrastructure; adjust resource sizing for production.
- **Plan LangSmith rollout** for visibility into LangGraph transitions before production launch.

## 14. Residual Risks
- Redis/Qdrant unavailability currently degrades silently (graphs fallback to in-memory). Need explicit error propagation to callers for production readiness.
- Heavy model loading (SentenceTransformer, CrossEncoder) will slow cold starts; consider async warmup jobs or model serving.
- Without coverage and integration tests, refactors risk regressions in routing/streaming.

---
Prepared for SealAI leadership to serve as baseline for the upcoming refactor and production hardening program.
