# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SealAI is a full-stack AI consulting platform for sealing technology (hydraulic/pneumatic seals). It uses a LangGraph v2 multi-agent graph to handle user conversations, with RAG-augmented knowledge retrieval and Keycloak-based authentication.

**Stack:** FastAPI + LangGraph v2 + OpenAI (backend) · Next.js 16 + NextAuth v5 (frontend) · Redis (checkpointing) · Qdrant (vector store) · PostgreSQL (long-term memory + DB) · Keycloak (OIDC auth) · Nginx (reverse proxy)

---

## Commands

### Backend

```bash
# Run all backend tests (via Docker, recommended)
docker exec -t -w /app backend python -m pytest -q

# Run a specific test file
docker exec -t -w /app backend python -m pytest app/langgraph_v2/tests/test_graph_contract_smoke.py -q

# Run tests directly (requires venv with deps installed)
cd backend && python -m pytest app/langgraph_v2/tests/ -q
cd backend && python -m pytest tests/ -q  # integration/service-level tests

# Start full stack
docker compose up

# E2E smoke tests against running backend
make e2e          # Rod-case format check
make rwdr         # RWDR pressure-tier check
make missing      # Missing-params gate check
```

### Frontend

```bash
cd frontend
npm run dev       # Start dev server (port 3000)
npm run build     # Production build
npm run lint      # ESLint
```

---

## Backend Architecture

### Entry Point & API

- **`backend/app/main.py`** — FastAPI app factory. On startup: clears dev checkpoints, bootstraps Qdrant, starts background job worker.
- **`backend/app/api/v1/api.py`** — Aggregates all routers: `langgraph_v2` (SSE chat), `rag`, `mcp`, `auth`, `chat_history`, `rfq`, `memory`.
- Main chat endpoint: `POST /api/v1/langgraph/chat/v2` (SSE streaming)

### LangGraph v2 Graph (`backend/app/langgraph_v2/`)

The core AI engine. Key files:

- **`sealai_graph_v2.py`** — Graph definition, node wiring, router functions, final-answer LangChain chain, and graph cache (`get_sealai_graph_v2()`). The `build_v2_config()` function generates per-request config with stable thread keys keyed on `(user_id, thread_id)`.
- **`state/sealai_state.py`** — `SealAIState` Pydantic model: the single source of truth passed through all nodes.
- **`contracts.py`** — API contracts, `STABLE_V2_NODE_CONTRACT` (nodes referenced externally), `HITLResumeRequest`.
- **`constants.py`** — Model tier names (`MODEL_NANO`, `MODEL_MINI`, `MODEL_PRO`), Redis namespace (`sealai:v2:`).
- **`phase.py`** — `PHASE` enum for graph execution phases.

**Graph topology (simplified):**
```
START → profile_loader_node → resume_router_node
  ├─(reject)→ confirm_reject_node → END
  ├─(resume)→ confirm_resume_node → supervisor_policy_node
  └─(frontdoor)→ frontdoor_discovery_node
      ├─(smalltalk)→ smalltalk_node → response_node → END
      └─(supervisor)→ supervisor_policy_node (orchestrator_node)
          ├─ ASK_USER → final_answer_node → END
          ├─ RUN_PANEL_CALC/MATERIAL → parallel workers → reducer_node
          │     └─(human_review)→ human_review_node [HITL interrupt] → response_node → END
          │     └─(standard)→ final_answer_node → END
          ├─ design flow → discovery_schema_node → parameter_check_node → calculator_node
          │     → material_agent_node → profile_agent_node → validation_agent_node
          │     → critical_review_node → product_match_node → final_answer_node → END
          └─ troubleshooting flow → leakage → pattern → explainer → final_answer_node → END
```

HITL is implemented via `interrupt_before=["human_review_node"]`.

### Nodes (`backend/app/langgraph_v2/nodes/`)

- **`nodes_frontdoor.py`** — Intent detection, parameter seeding, material/trade query detection via regex + LLM.
- **`nodes_supervisor.py`** — `supervisor_policy_node`: LLM-driven action routing (ASK_USER, RUN_PANEL_CALC, RUN_PANEL_MATERIAL, RUN_PANEL_NORMS_RAG, RUN_COMPARISON, RUN_TROUBLESHOOTING, REQUIRE_CONFIRM, FINALIZE). Action cost budget enforced.
- **`orchestrator.py`** — Thin wrapper delegating to `supervisor_policy_node`; exists for v3.1 compatibility.
- **`nodes_flows.py`** — Specialist nodes: `material_agent_node`, `rag_support_node`, `calculator_node`, `product_match_node`, `critical_review_node`, `validation_agent_node`, troubleshooting nodes, and the final-answer context helpers.
- **`reducer.py`** — Aggregates parallel worker results; routes to HITL gate or standard finalization.
- **`profile_loader.py`** — Loads per-user long-term memory from Postgres store into state.
- **`nodes_resume.py`** — HITL resume/reject flow (`resume_router_node`, `confirm_resume_node`, `confirm_reject_node`).

### Prompts (`backend/app/prompts/`)

Jinja2 templates (`.j2`). Selected at runtime by `_select_final_answer_template()` based on `intent.goal`:
- `final_answer_recommendation_v2.j2` — Design recommendation answers
- `final_answer_discovery_v2.j2` — Discovery/gap-filling answers
- `final_answer_smalltalk_v2.j2` — Smalltalk/greeting responses
- `final_answer_troubleshooting_v2.j2`, `final_answer_explanation_v2.j2`, `final_answer_out_of_scope_v2.j2`
- `check_1.1.0.j2` — Safety check prepended to all final prompts
- `senior_policy_de.j2` — Senior engineer persona policy
- `supervisor/` — Supervisor decision prompts

Prompts are rendered via `backend/app/langgraph_v2/utils/jinja.py` (or `backend/app/utils/jinja_renderer.py`).

### RAG (`backend/app/services/rag/`)

Hybrid retrieval: Qdrant (dense vector, `BAAI/bge-base-en-v1.5`) + BM25 (sparse). Single collection: `sealai_knowledge`. Tenant-scoped retrieval where applicable. Upload flow: `rag_ingest.py` → `rag_etl_pipeline.py` → Qdrant bootstrap.

### Auth (`backend/app/services/auth/`)

Keycloak OIDC JWT validation. `RequestUser` dataclass injected via FastAPI `Depends`. User ID resolved from configurable claim (env `AUTH_USER_ID_CLAIM`, default: `sub`). Scopes drive MCP tool access.

### MCP (`backend/app/mcp/`)

`knowledge_tool.py` — Scope-gated tool discovery. Scopes like `mcp:pim:read`, `mcp:knowledge:read` unlock tools that are injected into the final-answer LLM context.

### Long-Term Memory (`backend/app/core/memory.py`)

`AsyncPostgresStore` implements LangGraph's `BaseStore` over PostgreSQL (`store_items` table). Loaded per-user in `profile_loader_node`.

### Checkpointing

Redis-backed (`AsyncRedisSaver`) with namespace `sealai:v2:` (env `LANGGRAPH_V2_NAMESPACE`). Falls back to `MemorySaver` if Redis is unavailable. Thread key is deterministic: `stable_thread_key(user_id, thread_id)`. Dev startup auto-clears checkpoints (controlled by `DEV_CLEAR_LANGGRAPH_CHECKPOINTS_ON_STARTUP`).

---

## Frontend Architecture

### Auth

`frontend/src/auth.ts` — NextAuth v5 with Keycloak provider. **Split-DNS strategy**: authorization URL uses external `https://auth.sealai.net`, token/userinfo URLs use internal Docker `http://keycloak:8080`. Access token forwarded in session for API calls.

`frontend/src/middleware.ts` — Protects `/dashboard` and `/rag` routes; redirects unauthenticated users to `/api/auth/signin`.

### App Structure (`frontend/src/app/`)

- `dashboard/` — Main dashboard with `ChatInterface.tsx`. Sends messages to `/api/v1/langgraph/chat/v2` via SSE fetch, streams assistant tokens.
- `rag/` — RAG document management UI.
- `api/auth/[...nextauth]/` — NextAuth handler.
- `layout.tsx` — Root layout with `Providers.tsx` (NextAuth session provider).

### Key Components

- `frontend/src/components/dashboard/ChatInterface.tsx` — Main chat UI: manages messages, SSE streaming, auth guard, markdown rendering (`react-markdown` + `remark-gfm`).
- `frontend/src/components/dashboard/ChatComposer.tsx` — Input composer.
- `frontend/src/lib/ragApi.ts` — RAG document upload/list API calls.

---

## Key Environment Variables

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Required for LLM calls |
| `REDIS_URL` | LangGraph checkpointer |
| `QDRANT_URL` | Vector store |
| `DATABASE_URL` / `POSTGRES_DSN` | Postgres (long-term memory) |
| `LANGGRAPH_V2_NAMESPACE` | Checkpoint Redis key prefix (default: `sealai:v2:`) |
| `AUTH_USER_ID_CLAIM` | JWT claim for user ID (default: `sub`) |
| `SEALAI_LG_TRACE=1` | Verbose LangGraph tracing |
| `CONSULT_GRAPH_DEBUG=1` | Graph debug logging |
| `DEV_CLEAR_LANGGRAPH_CHECKPOINTS_ON_STARTUP` | Auto-clear Redis checkpoints (auto-enabled in dev) |
| `OPENAI_ROUTER_MODEL` | Override router model tier |
| `GENERATION_MODEL` | Override generation model |

Backend config is loaded via `backend/app/core/config.py` (`pydantic-settings`, reads from `.env`).

---

## Testing

- Backend unit/contract tests live in `backend/app/langgraph_v2/tests/` and `backend/tests/`.
- `backend/pytest.ini` sets `testpaths = tests`, `pythonpath = backend langchain_core_stub`.
- `langchain_core_stub/` provides lightweight stubs so graph-contract tests run without real LLM/Redis connections.
- Test files in `backend/app/langgraph_v2/tests/evaluation/` are longer-running evaluation suites.
- The `STABLE_V2_NODE_CONTRACT` frozenset in `contracts.py` is asserted by `test_graph_contract_smoke.py` — do not rename nodes listed there without updating both.
