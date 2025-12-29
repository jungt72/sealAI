# LangGraph v2 HITL Audit

## Phase 0 — Quick Inventory (runtime wiring)
- API router wiring: `backend/app/api/v1/api.py:7` includes `langgraph_v2`, `langgraph_health`, and `state` under `/api/v1/langgraph`.
- SSE entrypoint: `backend/app/api/v1/endpoints/langgraph_v2.py:658` (`POST /api/v1/langgraph/chat/v2`).
- State fetch/patch: `backend/app/api/v1/endpoints/state.py:141` (`GET/POST /api/v1/langgraph/state`).
- Confirm + parameter patch endpoints: `backend/app/api/v1/endpoints/langgraph_v2.py:713` (`POST /confirm/go`), `backend/app/api/v1/endpoints/langgraph_v2.py:826` (`POST /parameters/patch`).

## Phase 0 — Frontend ↔ Backend Trace
- Conversation entry: `frontend/src/app/chat/[conversationId]/page.tsx:9` → `ChatScreen`.
- SSE hook: `frontend/src/lib/useChatSseV2.ts:75` (reads SSE events and emits `state_update`, `checkpoint_required`).
- API proxy routes:
  - State: `frontend/src/app/api/langgraph/state/route.ts:12` → `/api/v1/langgraph/state`.
  - Parameter patch: `frontend/src/app/api/langgraph/parameters/patch/route.ts:12` → `/api/v1/langgraph/parameters/patch`.
  - Confirm go: `frontend/src/app/api/langgraph/confirm/go/route.ts:12` → `/api/v1/langgraph/confirm/go`.
- Chat UI consumes confirm checkpoints and renders HITL controls: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:153`.

## Phase 0 — Legacy Import Scan
- Legacy v1 modules only referenced from API “gone” endpoints and archive paths; no runtime v2 imports found.
- Test-only legacy imports were present in skipped tests (ask-missing flow) and now point at the canonical graph:
  - `backend/app/langgraph_v2/tests/test_sealai_graph_v2_ask_missing_flow.py:7`
  - `backend/app/langgraph_v2/tests/test_sealai_graph_v2_discovery_coverage_ask_missing_consistency.py:10`
- No `*.save` artifacts detected in frontend/backend roots (rg scan returned none).

## Current Wiring Diagram (v2 runtime)
- UI Chat → `useChatSseV2` → `/api/chat` → `/api/v1/langgraph/chat/v2` → LangGraph v2 runtime.
- UI state/parameters → `/api/langgraph/state` + `/api/langgraph/parameters/patch`.
- HITL confirm → `/api/langgraph/confirm/go` → graph state update + resume.
- Graph factory + config: `backend/app/langgraph_v2/sealai_graph_v2.py:607` (cached graph), `backend/app/langgraph_v2/sealai_graph_v2.py:621` (config builder).

## Phase 1 — Audit Findings
### A) Graph factory + config
- Single authoritative graph factory: `backend/app/langgraph_v2/sealai_graph_v2.py:607` (`get_sealai_graph_v2`) with module-level cache.
- Config includes run_id + checkpointer thread key: `backend/app/langgraph_v2/sealai_graph_v2.py:621`.

### B) Identity + keying
- Keycloak user extraction (sub) is available via `RequestUser.sub` in `backend/app/services/auth/dependencies.py:14`.
- Checkpointer thread ID now uses `stable_thread_key(user_sub, conversation_id)`.
- Request handlers use `user.sub` when building v2 config and state operations (SSE, state, patch, confirm).

### C) SSE event contract (v2)
- Stream emits token/done/error events plus `state_update` and `checkpoint_required`.
- Error events are explicit and followed by done; `done` always emitted with final metadata.
- `state_update` payload has stable keys: `phase`, `last_node`, `parameters`, `coverage_*`, `pending_action`.

### D) Parameter sync conflict policy
- UI patches mark provenance `user` via `apply_parameter_patch_with_provenance` and never allow LLM overwrites.
- LLM/tool extraction uses provenance `llm` and only fills missing fields; it cannot override `user` values.
- Parameter provenance is returned in `/api/v1/langgraph/state` responses.

### E) Legacy tests
- Skipped tests now import the canonical v2 graph module; legacy v2 module is not required for v2 runtime.

## Risks / Bugs (current)
- Resume logic currently runs `graph.ainvoke({})` for confirm decisions; ensure LangGraph checkpoint semantics align with “resume without new user input”.
- Recommendation confirmation uses the legacy confirmation path (still supported) and re-runs the graph after approval; validate behavior under production prompt loads.

## Recommended Contract/Event Types
- `token`: `{type:"token", text:"..."}`
- `state_update`: `{type:"state_update", phase, last_node, parameters, coverage_score, coverage_gaps, pending_action, confirm_checkpoint_id, awaiting_user_confirmation}`
- `checkpoint_required`: `ConfirmCheckpointPayload` (see `docs/hitl_design.md`).
- `error`: `{type:"error", message, request_id}` followed by `done`.
- `done`: `{type:"done", chat_id, request_id, phase, last_node, awaiting_confirmation, checkpoint_id}`

## HITL Design (summary)
- High-impact gate: supervisor action `RUN_PANEL_NORMS_RAG` now routes to `confirm_checkpoint_node` before execution.
- Checkpoint payload is standardized and emitted via SSE as `checkpoint_required`.
- Confirm go supports approve/reject/edit; edits apply parameter patches and optional instructions.

## Implementation Plan Checklist
- [x] Add standardized confirm checkpoint payload + SSE event.
- [x] Scope checkpointer thread key by `user_sub:conversation_id`.
- [x] Parameter provenance merge policy (UI wins, LLM fills missing only).
- [x] Resume routing + reject node + edit handling.
- [x] Frontend HITL card + confirm/go wiring.
- [x] Backend tests for checkpoint event + confirm resume paths.
- [ ] Run full test suite (pytest + frontend build).
