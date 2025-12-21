# SEALAI Phase 1 Audit Report (Wiring & Logic Verification)

## Part A — Canonical End-to-End Contract
- [Low] **Canonical sender path**: Chat UI uses `useChatSseV2` and passes chatId/token into the hook, which targets `/api/chat` (`frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:50-60`, `frontend/src/lib/useChatSseV2.ts:30`).
- [Low] **Frontend request JSON**: `/api/chat` POST is JSON with keys `input`, `chat_id`, `client_msg_id`; `Authorization: Bearer` is required, and Accept is `text/event-stream` (`frontend/src/lib/useChatSseV2.ts:92-105`).
- [Low] **Next.js proxy contract**: `/api/chat` validates only `input`, `chat_id`, `client_msg_id`, `metadata` and forwards to `backendLangGraphChatEndpoint()` with SSE headers and `Authorization` passthrough (`frontend/src/app/api/chat/route.ts:50-108`).
- [Low] **Backend endpoint target**: `backendLangGraphChatEndpoint` resolves to `/api/v1/langgraph/chat/v2` (`frontend/src/lib/langgraphApi.ts:27-28`).
- [Low] **Backend request contract**: `LangGraphV2Request` expects `input`, `chat_id`, `client_msg_id`, `metadata` and ignores extras (`backend/app/api/v1/endpoints/langgraph_v2.py:40-46`).
- [Low] **Thread handling & checkpoint scoping**: config uses `checkpoint_thread_id = f"{user_id}|{thread_id}"` and sets `configurable.thread_id` to that value (`backend/app/langgraph_v2/sealai_graph_v2.py:568-582`).
- [Low] **SSE event contract**: SSE frames use `event: <type>` + `data: <json>`, and events include `token`, `confirm_checkpoint`, `done`, `error` (`backend/app/api/v1/endpoints/langgraph_v2.py:49-52`, `backend/app/api/v1/endpoints/langgraph_v2.py:197-201`, `backend/app/api/v1/endpoints/langgraph_v2.py:236-239`, `backend/app/api/v1/endpoints/langgraph_v2.py:270-300`).
- [Low] **Backend SSE headers**: `Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, `X-Accel-Buffering: no` (`backend/app/api/v1/endpoints/langgraph_v2.py:366-370`).
- [Low] **Next.js SSE headers**: proxy response sets `Content-Type` from backend plus `Cache-Control`, `Connection: keep-alive`, `X-Accel-Buffering: no` (`frontend/src/app/api/chat/route.ts:137-142`).
- [Low] **Nginx SSE proxy**: `/api/chat` disables buffering and enforces long timeouts (`nginx/default.conf:66-87`).
- [Low] **Nginx SSE proxy for backend**: `/api/v1/langgraph/` path disables buffering and sets `X-Accel-Buffering` (`nginx/default.conf:178-192`).

**Active frontend sender paths**
- [Low] **Primary sender is `useChatSseV2`**: only the active ChatContainer imports `useChatSseV2` (`frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:10-60`).
- [Low] **Alternate sender exists only in backup**: the legacy `useChat` hook appears only in `ChatContainer.tsx.backup` (`archive/legacy_phase2/frontend/src/app/dashboard/components/Chat/ChatContainer.tsx.backup:11-34`).

## Part B — Auth & Identity (Keycloak) Correctness
- [Low] **JWT verification uses issuer + JWKS**: `REALM_ISSUER` and `JWKS_URL` are used to fetch and validate keys (`backend/app/services/auth/token.py:21-30`).
- [Low] **JWT audience enforcement**: `ALLOWED_AUDS` is enforced via `aud/azp/client_id` checks (`backend/app/services/auth/token.py:83-94`).
- [Low] **HTTP token extraction**: backend requires `Authorization: Bearer` and verifies the token (`backend/app/services/auth/dependencies.py:28-42`).
- [Low] **Next.js proxy does not parse JWT**: it checks header presence and forwards `Authorization` to backend (`frontend/src/app/api/chat/route.ts:82-107`).
- [Medium] **Current user_id claim is `preferred_username`**: `get_current_request_user` returns `preferred_username` (`backend/app/services/auth/dependencies.py:21-42`).
- [Medium] **User_id is server-controlled (not client-provided)**: backend builds state with `user_id` from dependency, not from request payload (`backend/app/api/v1/endpoints/langgraph_v2.py:75-81`).
- [Medium] **Checkpoint scoping uses user_id**: checkpoint key is derived from `user_id` and `thread_id` (`backend/app/langgraph_v2/sealai_graph_v2.py:576-582`).

**Assessment & recommendation**
- [Medium] **Stability risk**: `preferred_username` is mutable and can collide, so using it for checkpoint scoping risks state overlap if usernames change or are reused (`backend/app/services/auth/dependencies.py:21-42`, `backend/app/langgraph_v2/sealai_graph_v2.py:576-582`).
- [Medium] **Recommended**: switch checkpoint scoping to `sub` and retain `preferred_username` separately (e.g., `metadata.username`) for display (`backend/app/services/auth/dependencies.py:21-42`, `backend/app/langgraph_v2/sealai_graph_v2.py:584-587`).
- [Medium] **Not implemented in Phase 1**: switching to `sub` would require coordinated changes to auth dependencies and downstream callers; defer to Phase 1.5 with explicit migration plan (`backend/app/services/auth/dependencies.py:21-42`, `backend/app/api/v1/endpoints/langgraph_v2.py:75-81`).

## Part C — Redis Checkpointer & Memory Safety
- [Low] **Redis checkpointer initialization**: uses `LANGGRAPH_V2_REDIS_URL` or `REDIS_URL` and `AsyncRedisSaver` with a connection pool (`backend/app/langgraph_v2/utils/checkpointer.py:55-81`).
- [Low] **Serialization mode**: `decode_responses=False` to keep binary checkpoint payloads (`backend/app/langgraph_v2/utils/checkpointer.py:70-78`).
- [Medium] **Fallback to MemorySaver**: on any Redis failure or missing dependency, it returns `MemorySaver` (`backend/app/langgraph_v2/utils/checkpointer.py:85-100`).
- [Medium] **Empty namespace**: `CHECKPOINTER_NAMESPACE_V2` is an empty string, so key prefixing is disabled (`backend/app/langgraph_v2/constants.py:3`).
- [Low] **Checkpoint scoping**: `checkpoint_thread_id = f"{user_id}|{thread_id}"` provides per-user/thread isolation in the key space (`backend/app/langgraph_v2/sealai_graph_v2.py:576-582`).

**Recommendation**
- [Medium] **Namespace**: set a non-empty prefix such as `sealai:v2:` for safer multi-app isolation (`backend/app/langgraph_v2/constants.py:3`).
- [Medium] **Fail-fast in prod**: consider enforcing Redis availability in prod to avoid silent fallback state loss (`backend/app/langgraph_v2/utils/checkpointer.py:85-100`).

## Part D — Supervisor Routing Quality
- [Low] **Supervisor decision inputs**: uses `intent.goal`, `recommendation_ready`, and `recommendation_go` to select routes (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:78-94`).
- [Low] **Supervisor updates**: computes `coverage_score`, `coverage_gaps`, and `recommendation_ready` based on required parameters (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:29-75`).
- [Low] **Graph edges match supervisor outputs**: routes map from `supervisor_logic_node` to the nodes listed below (`backend/app/langgraph_v2/sealai_graph_v2.py:467-479`).

**Routing table**
- `intermediate` → `final_answer_node` → requires `intent` and `messages` for final-answer template (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:78-94`, `backend/app/langgraph_v2/sealai_graph_v2.py:467-479`, `backend/app/langgraph_v2/sealai_graph_v2.py:285-345`).
- `confirm` → `confirm_recommendation_node` → requires `coverage_score`, `coverage_gaps`, `parameters` (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:78-94`, `backend/app/langgraph_v2/nodes/nodes_confirm.py:66-81`, `backend/app/langgraph_v2/sealai_graph_v2.py:467-474`).
- `design_flow` → `calculator_node` → requires `parameters` for `shaft_diameter`, `speed_rpm`, `temperature_C`, `pressure_bar` (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:78-94`, `backend/app/langgraph_v2/nodes/nodes_flows.py:92-108`, `backend/app/langgraph_v2/sealai_graph_v2.py:467-475`).
- `comparison` → `material_comparison_node` → requires `messages` for `latest_user_text` and uses Jinja template (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:88-90`, `backend/app/langgraph_v2/nodes/nodes_flows.py:299-319`, `backend/app/langgraph_v2/sealai_graph_v2.py:467-475`).
- `troubleshooting` → `leakage_troubleshooting_node` → requires `messages` for prompt input (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:90-92`, `backend/app/langgraph_v2/nodes/nodes_flows.py:390-410`, `backend/app/langgraph_v2/sealai_graph_v2.py:467-476`).
- `smalltalk` / `out_of_scope` → `final_answer_node` → uses final-answer chain (`backend/app/langgraph_v2/nodes/nodes_supervisor.py:92-94`, `backend/app/langgraph_v2/sealai_graph_v2.py:471-478`, `backend/app/langgraph_v2/sealai_graph_v2.py:285-377`).

**Downstream edges from design flow**
- `calculator_node` → `material_agent_node` → `profile_agent_node` → `validation_agent_node` → `critical_review_node` (`backend/app/langgraph_v2/sealai_graph_v2.py:493-497`).
- `critical_review_node` routes to `discovery_schema_node` on `refine` else `product_match_node` (`backend/app/langgraph_v2/sealai_graph_v2.py:498-507`, `backend/app/langgraph_v2/nodes/nodes_flows.py:220-245`).
- `product_match_node` routes to `product_explainer_node` or `final_answer_node` (`backend/app/langgraph_v2/sealai_graph_v2.py:509-517`).

**Potential dead routes / unreachable nodes**
- [Medium] **`discovery_schema_node` and `parameter_check_node` are not in the initial design-flow path**: they are reachable only via `critical_review_node` refine path, not directly from supervisor (`backend/app/langgraph_v2/sealai_graph_v2.py:467-507`, `backend/app/langgraph_v2/nodes/nodes_flows.py:43-90`).

## Part E — RAG/Qdrant Correctness
- [Low] **Retrieval entrypoint**: `rag_support_node` invokes `search_knowledge_base` with `tenant=state.user_id`, `category="norms"` and `k=3` (`backend/app/langgraph_v2/nodes/nodes_flows.py:333-351`).
- [Low] **Tool filters**: `search_knowledge_base` maps `tenant` into `tenant_id` payload filter and forwards `metadata_filters` to `hybrid_retrieve` (`backend/app/langgraph_v2/utils/rag_tool.py:42-55`).
- [Low] **Collection selection**: `hybrid_retrieve` uses `_collection_for_tenant`, which uses `QDRANT_COLLECTION_PREFIX` (if set) or falls back to `QDRANT_COLLECTION_DEFAULT` (`backend/app/services/rag/rag_orchestrator.py:21-24`, `backend/app/services/rag/rag_orchestrator.py:104-109`).
- [Low] **Qdrant query filter**: `metadata_filters` map to a `filter.must` list in the HTTP request body (`backend/app/services/rag/rag_orchestrator.py:125-136`).

**Risks & consistency**
- [Medium] **Embedding/model mismatch between ingest and retrieval defaults**: ingest defaults to `EMBEDDING_MODEL=BAAI/bge-m3` and `QDRANT_COLLECTION=sealai-docs-bge-m3`, while retrieval defaults to `EMB_MODEL_NAME=intfloat/multilingual-e5-base` and `QDRANT_COLLECTION=sealai-docs` (`backend/app/services/rag/rag_ingest.py:11-13`, `backend/app/services/rag/rag_orchestrator.py:21-27`).
- [Medium] **Tenant scoping relies on `user_id`**: RAG tenant filtering uses `state.user_id` which is derived from `preferred_username` today (`backend/app/langgraph_v2/nodes/nodes_flows.py:346-351`, `backend/app/services/auth/dependencies.py:21-42`).

## Part F — Jinja2 Output Contract
- [Low] **Template rendering environment**: Jinja uses `StrictUndefined` with a prompts directory rooted at `backend/app/prompts` (`backend/app/langgraph_v2/utils/jinja.py:11-24`).
- [Low] **Final answer prompt assembly**: `final_answer_node` selects a template and renders it, optionally injecting `senior_policy_de.j2` (`backend/app/langgraph_v2/sealai_graph_v2.py:247-261`).
- [Low] **Final answer mapped into state**: `map_final_answer_to_state` writes `final_text` and appends an AI message (`backend/app/langgraph_v2/nodes/nodes_flows.py:525-536`).
- [Low] **Frontend rendering contract**: chat messages are rendered via `ReactMarkdown` with no `rehypeRaw` and markdown CSS styling (`frontend/src/app/dashboard/components/Chat/MarkdownMessage.tsx:88-116`).

**Template safety**
- [Medium] **StrictUndefined can raise runtime errors on missing template variables**: no local try/except around `render_template` calls in flow nodes (`backend/app/langgraph_v2/utils/jinja.py:15-37`, `backend/app/langgraph_v2/nodes/nodes_flows.py:299-319`).
- [Low] **HTML injection risk is limited**: ReactMarkdown is configured without `rehypeRaw`, so raw HTML from templates is not rendered (`frontend/src/app/dashboard/components/Chat/MarkdownMessage.tsx:88-116`).

## Part G — Cleanup Plan Summary (See `docs/cleanup_plan_phase1.md`)
- [Low] **Legacy/backup artifacts identified**: `.backup` files and legacy graph remain in tree (`backend/app/langgraph_v2/sealai_graph_v2_legacy.py:1-3`, `archive/legacy_phase2/backend/app/api/v1/endpoints/langgraph_v2.py.backup:1-10`, `archive/legacy_phase2/backend/app/langgraph_v2/nodes/nodes_flows.py.backup:1-10`, `archive/legacy_phase2/frontend/src/app/dashboard/components/Chat/ChatContainer.tsx.backup:1-34`).

## Prioritized Fix List (Top 10)
1) [Medium] Switch checkpoint scoping from `preferred_username` to `sub` with backward-compatible username retention (`backend/app/services/auth/dependencies.py:21-42`, `backend/app/langgraph_v2/sealai_graph_v2.py:576-587`).
2) [Medium] Align RAG ingestion defaults with retrieval defaults (collection + embedding model) (`backend/app/services/rag/rag_ingest.py:11-13`, `backend/app/services/rag/rag_orchestrator.py:21-27`).
3) [Medium] Add non-empty checkpointer namespace (e.g., `sealai:v2:`) (`backend/app/langgraph_v2/constants.py:3`).
4) [Medium] Decide whether Redis fallback is allowed in prod; fail fast if not (`backend/app/langgraph_v2/utils/checkpointer.py:85-100`).
5) [Medium] Resolve `discovery_schema_node` / `parameter_check_node` reachability in the main flow (`backend/app/langgraph_v2/sealai_graph_v2.py:467-507`, `backend/app/langgraph_v2/nodes/nodes_flows.py:43-90`).
6) [Medium] Normalize `tenant_id` usage for RAG and ensure tenant_id exists in payloads to avoid empty results or leakage (`backend/app/langgraph_v2/utils/rag_tool.py:42-55`, `backend/app/services/rag/rag_orchestrator.py:125-136`).
7) [Low] Remove or fix `/api/v1/chat/sse` nginx proxy target (backend route not present) (`nginx/default.conf:162-176`, `backend/app/api/v1/api.py:7-31`).
8) [Low] Remove or disable nginx `/api/v1/ai/ws` proxy since v1 ai router is not mounted (`nginx/default.conf:132-145`, `backend/app/api/v1/api.py:7-31`).
9) [Low] Document Jinja variable requirements to reduce StrictUndefined failures (`backend/app/langgraph_v2/utils/jinja.py:15-37`, `backend/app/langgraph_v2/nodes/nodes_flows.py:299-319`).
10) [Low] Review unused legacy/backup modules for deprecation path (`backend/app/langgraph_v2/sealai_graph_v2_legacy.py:1-3`, `archive/legacy_phase2/backend/app/api/v1/endpoints/langgraph_v2.py.backup:1-10`, `archive/legacy_phase2/frontend/src/app/dashboard/components/Chat/ChatContainer.tsx.backup:1-34`).

## Phase 1.5 Addendum (Targeted Fixes)
- [Low] **Auth dependency returns structured user**: RequestUser is now returned and used by chat history endpoints, resolving the `current_user.sub` mismatch (`backend/app/services/auth/dependencies.py:24-73`, `backend/app/api/v1/endpoints/chat_history.py:118-127`).
- [Low] **Configurable identity claim**: `AUTH_USER_ID_CLAIM` selects the user id claim, and username is attached to v2 config metadata (`backend/app/services/auth/dependencies.py:31-46`, `backend/app/api/v1/endpoints/langgraph_v2.py:67-77`).
- [Medium] **Checkpointer namespace is now configurable**: defaults to `sealai:v2:` via `LANGGRAPH_V2_NAMESPACE` (`backend/app/langgraph_v2/constants.py:3-6`).
- [Low] **Smoke test commands added**: new `docs/phase1_5_smoke.md` documents HTTP checks (`docs/phase1_5_smoke.md:1`).
