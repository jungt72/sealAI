# Phase 1 - Repository Discovery

Audit date: 2026-05-22
Workspace: `/home/thorsten/sealai`
Mode: audit-first, documentation-only. No production/source files were modified in this phase.

## Required Command Record

### `pwd`

```text
/home/thorsten/sealai
```

### `git branch --show-current`

```text
redesign/sealai-cockpit-overview
```

### `git status --short`

Verified fact: the working tree was already dirty before audit documentation was created. Existing changes are treated as user-owned and were not reverted.

```text
 D .codex
 M AGENTS.md
 M backend/app/agent/api/dispatch.py
 M backend/app/agent/api/governed_runtime.py
 M backend/app/agent/api/knowledge_override.py
 M backend/app/agent/api/routes/chat.py
 M backend/app/agent/api/streaming.py
 M backend/app/agent/api/utils.py
 M backend/app/agent/communication/active_case_process_answer.py
 M backend/app/agent/communication/answer_composer.py
 M backend/app/agent/communication/communication_runtime_v8.py
 M backend/app/agent/communication/context.py
 M backend/app/agent/communication/governed_answer_composer.py
 M backend/app/agent/communication/governed_answer_context.py
 M backend/app/agent/communication/knowledge_context_builder.py
 M backend/app/agent/communication/llm_service.py
 M backend/app/agent/communication/rfq_intent.py
 M backend/app/agent/graph/output_contract_assembly.py
 M backend/app/agent/graph/slot_answer_binding.py
 M backend/app/agent/runtime/clarification_priority.py
 M backend/app/agent/runtime/conversation_runtime.py
 M backend/app/agent/runtime/output_guard.py
 M backend/app/agent/state/projections.py
 M backend/app/agent/state/reducers.py
 M backend/app/agent/tests/test_conversation_runtime.py
 M backend/app/agent/tests/test_governed_answer_composer.py
 M backend/app/agent/tests/test_knowledge_answer_composer.py
 M backend/app/agent/tests/test_knowledge_context_builder.py
 M backend/app/agent/tests/test_output_guard.py
 M backend/app/agent/tests/test_pre_gate_runtime_dispatch.py
 M backend/app/agent/tests/test_projections.py
 M backend/app/domain/conversation_intent.py
 M backend/app/llm/registry.py
 M backend/app/observability/langsmith.py
 M backend/app/observability/sealai_quality.py
 M backend/app/services/knowledge/material_comparison.py
 M backend/app/services/knowledge_service.py
 M backend/app/services/pre_gate_classifier.py
 M backend/app/services/rag/material_evidence_dry_run.py
 M docs/architecture/SSOT_REGISTRY.md
 M frontend/package-lock.json
 M frontend/package.json
 M frontend/src/app/api/bff/agent/chat/stream/route.spec.ts
 M frontend/src/app/api/bff/agent/chat/stream/route.ts
 M frontend/src/hooks/useAgentStream.test.tsx
 M frontend/src/hooks/useAgentStream.ts
 M frontend/src/lib/contracts/agent.ts
 M frontend/src/lib/streamWorkspace.test.ts
 M frontend/src/lib/streamWorkspace.ts
 M frontend/vitest.config.ts
?? backend/app/agent/prompts/communication/semantic_pre_gate_router.j2
?? backend/app/agent/tests/test_calculation_state_ledger.py
?? backend/app/agent/tests/test_question_scenario_matrix.py
?? backend/app/agent/tests/test_v10_solution_journey.py
?? backend/app/agent/tests/test_v10_visible_golden_evaluation.py
?? backend/app/agent/v91/golden_evaluation.py
?? backend/app/agent/v92/calculation_projection.py
?? backend/app/services/semantic_intent_router.py
?? backend/tests/unit/services/test_material_knowledge_context_routing.py
?? backend/tests/unit/services/test_semantic_intent_router.py
?? docs/implementation/SEALAI_V10_CONVERSATIONAL_SEALING_INTELLIGENCE_CONCEPT.md
?? frontend/src/lib/streamWorkspaceAdapter.test.ts
?? frontend/src/lib/streamWorkspaceAdapter.ts
```

The full command output also contains many additional modified frontend/dashboard files and untracked AppleDouble-style `._*` files. The audit did not alter or clean any of them.

### `find . -maxdepth 3 -type f | sed 's#^\./##' | sort | head -300`

The command was run. The first 300 paths are dominated by `.env*` filenames, `.git/*` metadata, workflow files, and cache metadata. No `.env` file contents were opened. Relevant exact examples from the recorded output:

```text
.claude/settings.json
.codex/README.md
.dockerignore
.env
.env.backend
.env.backend.example
.env.example
.env.frontend.example
.env.keycloak.example
.env.prod
.env.prod.example
.env.shared
.env.shared.example
.git/HEAD
.github/workflows/ci.yml
.github/workflows/deploy.yml
.gitignore
```

## Detected Stack

Verified facts:

- Backend is Python 3.11+ with FastAPI, LangGraph, Pydantic v2, SQLAlchemy/Alembic, Redis, Qdrant, OpenAI SDK, Jinja2, and pytest. Evidence: `backend/requirements.txt:1-14`, `backend/requirements.txt:19-36`, `backend/requirements.txt:41-59`, `backend/requirements.txt:68-89`, `backend/requirements.txt:101-108`.
- Frontend is Next.js/React/TypeScript with Vitest. Evidence: `frontend/package.json:5-20`, `frontend/package.json:22-42`, `frontend/package.json:44-65`.
- Root `package.json` delegates dev/build/start/lint to `frontend`. Evidence: `package.json:1-7`.
- Backend pytest config sets `testpaths = tests`, `pythonpath = backend, langchain_core_stub`, and `asyncio_mode = auto`. Evidence: `backend/pytest.ini:1-7`.
- Frontend Vitest uses `jsdom`, includes `src/**/*.test.tsx`, `src/**/*.spec.ts`, and excludes `node_modules`, `.git`, and `._*`. Evidence: `frontend/vitest.config.ts:8-23`.

## Relevant Config and Environment Surfaces

Verified facts:

- Environment files exist in the repo root, including `.env`, `.env.example`, `.env.prod`, `.env.prod.example`, `.env.backend.example`, `.env.frontend.example`, `.env.keycloak.example`, and many rollback backups. Contents were not read.
- Build/deploy/config files include `Dockerfile`, `docker-compose*.yml`, `backend/alembic.ini`, root `alembic.ini`, `frontend/next.config.js`, `frontend/tsconfig.json`, and package lockfiles.
- LLM model role mapping is centralized in `backend/app/llm/registry.py`; roles can be overridden by environment variables such as `SEALAI_EXTRACTION_MODEL`, `OPENAI_ROUTER_MODEL`, and `SEALAI_GOVERNED_ANSWER_COMPOSER_MODEL`. Evidence: `backend/app/llm/registry.py:14-33`, `backend/app/llm/registry.py:36-53`, `backend/app/llm/registry.py:59-82`.
- OpenAI clients are constructed from environment-provided credentials. Evidence: `backend/app/llm/factory.py:16-25`, `backend/app/llm/factory.py:28-37`.

## SSoT and Architecture Source

Verified facts:

- Root `AGENTS.md` defines V10 as the current product architecture and names `docs/architecture/SSOT_REGISTRY.md` as the binding source-of-truth map.
- `docs/architecture/SSOT_REGISTRY.md` states the current principle that LLMs may classify/explain/extract/normalize/propose, but deterministic backend logic decides routing, gates, state, readiness, calculations, risk, and release status.
- `docs/implementation/SEALAI_V10_CONVERSATIONAL_SEALING_INTELLIGENCE_CONCEPT.md` is present but untracked in this working tree. It states the active principle: "Freely explain. Deterministically calculate. Only claim with evidence."

Documentation inconsistency:

- `frontend/AGENTS.md` still points to a V9.1 implementation concept as frontend SSoT. This conflicts with the root V10 instruction. This is a documentation risk, not direct runtime evidence.

## Candidate SealingAI Engine Files

Discovery used targeted `rg` searches for sealing, deterministic, canonical, normalize, hash, score, rank, policy, random, uuid, date/time, JSON serialization, LLM, prompt, cache, idempotency, transaction, retry, and related terms.

Primary backend runtime candidates:

- `backend/app/agent/api/routes/chat.py`
- `backend/app/agent/api/streaming.py`
- `backend/app/agent/api/dispatch.py`
- `backend/app/agent/api/governed_runtime.py`
- `backend/app/services/pre_gate_classifier.py`
- `backend/app/services/semantic_intent_router.py`
- `backend/app/agent/v92/turn_boundary.py`
- `backend/app/agent/v92/runtime_contract.py`
- `backend/app/agent/v92/final_guard.py`
- `backend/app/agent/graph/topology.py`
- `backend/app/agent/graph/nodes/intake_observe_node.py`
- `backend/app/agent/graph/nodes/normalize_node.py`
- `backend/app/agent/graph/nodes/assert_node.py`
- `backend/app/agent/graph/nodes/evidence_node.py`
- `backend/app/agent/graph/nodes/compute_node.py`
- `backend/app/agent/graph/nodes/governance_node.py`
- `backend/app/agent/graph/nodes/matching_node.py`
- `backend/app/agent/graph/nodes/rfq_handover_node.py`
- `backend/app/agent/graph/output_contract_assembly.py`
- `backend/app/agent/state/models.py`
- `backend/app/agent/state/reducers.py`
- `backend/app/agent/state/persistence.py`
- `backend/app/services/case_service.py`

Deterministic domain candidates:

- `backend/app/agent/domain/normalization.py`
- `backend/app/agent/domain/rwdr_calc.py`
- `backend/app/agent/domain/checks_registry.py`
- `backend/app/services/calculation_engine.py`
- `backend/app/services/advisory_engine.py`
- `backend/app/agent/v92/calculator_registry.py`
- `backend/app/mcp/calculations/material_limits.py`
- `backend/app/mcp/calculations/chemical_resistance.py`
- `backend/app/services/knowledge/material_comparison.py`
- `backend/app/services/knowledge/factcard_store.py`

External/nondeterministic boundary candidates:

- `backend/app/llm/factory.py`
- `backend/app/llm/registry.py`
- `backend/app/agent/evidence/retrieval.py`
- `backend/app/agent/services/real_rag.py`
- `backend/app/services/rag/rag_orchestrator.py`
- `backend/app/services/rag/bm25_store.py`
- `backend/app/services/knowledge_service.py`

Frontend contract candidates:

- `frontend/src/hooks/useAgentStream.ts`
- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- `frontend/src/lib/contracts/agent.ts`
- `frontend/src/lib/streamWorkspace.ts`

## Entry Points Into SealingAI

Verified facts:

- REST chat route imports governed runtime, dispatch, knowledge override, and final answer layer. Evidence: `backend/app/agent/api/routes/chat.py:1-27`.
- SSE stream bridge imports final answer layer and emits guarded final-state updates. Evidence: `backend/app/agent/api/streaming.py:14-16`, `backend/app/agent/api/streaming.py:949-958`.
- Governed runtime loads current state, builds graph input, runs LangGraph, persists post-graph state, and emits quality traces. Evidence: `backend/app/agent/api/governed_runtime.py:306-329`, `backend/app/agent/api/governed_runtime.py:344-393`, `backend/app/agent/api/governed_runtime.py:394-444`.
- Graph topology defines the governed path from `turn_boundary` through intake, normalization, assertion, evidence, compute, governance, matching/RFQ/output, and answer composer. Evidence: `backend/app/agent/graph/topology.py:6-63`, `backend/app/agent/graph/topology.py:301-382`.
- Frontend BFF forwards `turn_envelope`, `turn_boundary_decision`, `final_answer_context`, `nontechnical_answer_context`, `final_guard_result`, and `v92_dashboard`. Evidence: `frontend/src/app/api/bff/agent/chat/stream/route.ts:400-470`.
- Frontend hook creates a no-case conversation id client-side using `crypto.randomUUID()` or `Date.now()`/`Math.random()`. Evidence: `frontend/src/hooks/useAgentStream.ts:171-178`, `frontend/src/hooks/useAgentStream.ts:203-219`.

## Data Models and Persistence Touched

Verified facts:

- `GovernedSessionState` carries observed, normalized, asserted, derived, evidence, governance, decision, RFQ, readiness, and many V9/V10 compatibility slices. Evidence examples: `backend/app/agent/state/models.py:140-165`, `backend/app/agent/state/models.py:830-839`, `backend/app/agent/state/models.py:1139-1143`.
- `CaseRecord` has unique `case_number` and `session_id`, server timestamps, and revision. Evidence: `backend/app/models/case_record.py:17-26`.
- `CaseStateSnapshot` has unique `(case_id, revision)`, `state_json`, `basis_hash`, version columns, and server timestamp. Evidence: `backend/app/models/case_state_snapshot.py:13-25`.
- `MutationEventModel` records mutation IDs, revision before/after, payload deltas, and server timestamp; it validates revision monotonicity. Evidence: `backend/app/models/mutation_event_model.py:17-18`, `backend/app/models/mutation_event_model.py:82-85`, `backend/app/models/mutation_event_model.py:116-127`.
- `OutboxModel` persists app-generated outbox IDs and server timestamps for async side effects. Evidence: `backend/app/models/outbox_model.py:67-97`.

## External Services Used

Verified facts:

- OpenAI API: extraction, semantic routing, answer composition, optional reviewers and fallbacks. Evidence: `backend/app/llm/factory.py:16-37`, `backend/app/llm/registry.py:14-53`, `backend/app/agent/graph/nodes/intake_observe_node.py:417-493`.
- Qdrant and BM25/Redis-backed RAG retrieval. Evidence: `backend/app/agent/services/real_rag.py:54-87`, `backend/app/services/rag/rag_orchestrator.py:59-93`, `backend/app/services/rag/rag_orchestrator.py:840-1024`.
- Redis for governed state persistence and optionally LangGraph checkpointing. Evidence: `backend/app/agent/state/persistence.py:76-80`, `backend/app/agent/graph/topology.py:146-154`, `backend/app/agent/graph/topology.py:189-240`.
- Postgres/SQLAlchemy for cases, snapshots, mutation events, and outbox. Evidence: `backend/app/agent/state/persistence.py:287-425`, `backend/app/services/case_service.py:44-124`, `backend/app/services/case_service.py:232-287`.

