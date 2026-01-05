# SEALAI Phase 0 Inventory

## Section 1 — Repo Map
- backend/app (API entry + v1 router wiring): `backend/app/main.py:76`, `backend/app/api/v1/api.py:7`
- backend/app/api (routes + v1 endpoints packages): `backend/app/api/routes/__init__.py:1`, `backend/app/api/v1/api.py:1`
- backend/app/langgraph (legacy v1 notice): `backend/app/langgraph/README.md:1`
- backend/app/langgraph_v2 (active v2 graph + nodes): `backend/app/langgraph_v2/sealai_graph_v2.py:1`
- backend/app/services (auth/chat/rag/memory): `backend/app/services/auth/dependencies.py:1`, `backend/app/services/chat/conversations.py:1`, `backend/app/services/rag/rag_orchestrator.py:1`, `backend/app/services/memory/memory_core.py:1`
- backend/app/prompts (Jinja templates; example): `backend/app/prompts/final_answer_v2.j2:1`
- frontend/src/app (Next.js app router): `frontend/src/app/layout.tsx:1`
- frontend/src/components (UI components): `frontend/src/components/ConversationSidebar.tsx:1`
- frontend/src/lib (client data + API helpers): `frontend/src/lib/useChatSseV2.ts:1`, `frontend/src/lib/langgraphApi.ts:1`
- frontend/src/styles (chat + global styles): `frontend/src/styles/chat-markdown.css:1`
- ops (stack scripts + abuse remediation bundle): `ops/up-dev.sh:1`, `ops/abuse_10D287D_2C/REMEDIATION.md:1`
- nginx (reverse proxy configs): `nginx/default.conf:1`, `nginx/backend.conf:1`, `nginx/streaming.conf:1`
- docker-compose*.yml (compose variants): `docker-compose.yml:1`, `docker-compose.override.yml:1`, `docker-compose.deploy.yml:1`, `docker-compose.biz.yml:1`

## Section 2 — LangGraph V2 Core
- State schema (core fields include messages, user_id, thread_id, run_id): `backend/app/langgraph_v2/state/sealai_state.py:222`
- Intent + working memory fields in state schema (supervisor_decision, response fields, etc.): `backend/app/langgraph_v2/state/sealai_state.py:33`, `backend/app/langgraph_v2/state/sealai_state.py:194`
- V2 StateGraph builder and compile: `backend/app/langgraph_v2/sealai_graph_v2.py:439`, `backend/app/langgraph_v2/sealai_graph_v2.py:543`
- Node registrations for v2 graph (frontdoor, supervisor, design, comparison, troubleshooting, final_answer): `backend/app/langgraph_v2/sealai_graph_v2.py:444`, `backend/app/langgraph_v2/sealai_graph_v2.py:461`
- Supervisor logic + routing (supervisor_logic_node / supervisor_route): `backend/app/langgraph_v2/nodes/nodes_supervisor.py:57`, `backend/app/langgraph_v2/nodes/nodes_supervisor.py:78`
- Supervisor routing wired into graph conditional edges: `backend/app/langgraph_v2/sealai_graph_v2.py:467`
- Graph cache + accessor for compiled graph (singleton per process): `backend/app/langgraph_v2/sealai_graph_v2.py:550`, `backend/app/langgraph_v2/sealai_graph_v2.py:559`
- Graph config includes user/thread metadata and checkpointer thread_id: `backend/app/langgraph_v2/sealai_graph_v2.py:579`, `backend/app/langgraph_v2/sealai_graph_v2.py:584`
- Tool binding (parameter extraction tool bound to ChatOpenAI in frontdoor): `backend/app/langgraph_v2/nodes/nodes_discovery.py:90`, `backend/app/langgraph_v2/tools/parameter_tools.py:17`

## Section 3 — Chat API & Streaming
- V2 SSE chat endpoint (`/api/v1/langgraph/chat/v2`) with SSE headers: `backend/app/api/v1/endpoints/langgraph_v2.py:350`, `backend/app/api/v1/endpoints/langgraph_v2.py:366`
- SSE keepalive + event types (token, confirm_checkpoint, done, error): `backend/app/api/v1/endpoints/langgraph_v2.py:176`, `backend/app/api/v1/endpoints/langgraph_v2.py:201`, `backend/app/api/v1/endpoints/langgraph_v2.py:238`, `backend/app/api/v1/endpoints/langgraph_v2.py:278`, `backend/app/api/v1/endpoints/langgraph_v2.py:300`
- Next.js proxy endpoint (`/api/chat`) forwards to backend v2 and preserves SSE headers: `frontend/src/app/api/chat/route.ts:96`, `frontend/src/app/api/chat/route.ts:137`
- Frontend client calls `/api/chat` with Authorization + Accept `text/event-stream`: `frontend/src/lib/useChatSseV2.ts:30`, `frontend/src/lib/useChatSseV2.ts:92`
- Frontend uses `useChatSseV2` in chat container (runtime call path): `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:58`
- Nginx SSE proxying for `/api/chat` and `/api/v1/langgraph/` (no buffering, long timeouts): `nginx/default.conf:66`, `nginx/default.conf:178`
- Legacy v1/WS endpoints implemented in code (`/api/v1/ai/beratung`, `/api/v1/ai/ws`): `backend/app/api/v1/endpoints/ai.py:114`, `backend/app/api/v1/endpoints/ai.py:158`

## Section 4 — Redis Memory / Checkpoint
- V2 checkpointer uses AsyncRedisSaver + ConnectionPool with MemorySaver fallback (backend selector + URL env): `backend/app/langgraph_v2/utils/checkpointer.py:55`, `backend/app/langgraph_v2/utils/checkpointer.py:70`, `backend/app/langgraph_v2/utils/checkpointer.py:93`
- Checkpointer namespace constant (empty string): `backend/app/langgraph_v2/constants.py:3`
- Checkpointer scoping by user_id + thread_id (`checkpoint_thread_id = f"{user_id}|{thread_id}"`): `backend/app/langgraph_v2/sealai_graph_v2.py:579`
- Graph state/config attaches checkpointer into `configurable`: `backend/app/api/v1/endpoints/langgraph_v2.py:67`, `backend/app/api/v1/endpoints/state.py:127`
- Redis conversation metadata keys + TTL semantics: `backend/app/services/chat/conversations.py:1`, `backend/app/services/chat/conversations.py:20`, `backend/app/services/chat/conversations.py:50`
- Redis STM history keys + TTL/expire on write: `backend/app/services/memory/conversation_memory.py:18`, `backend/app/services/memory/conversation_memory.py:38`, `backend/app/services/memory/conversation_memory.py:45`
- In-memory fallback explicitly returned when Redis unavailable: `backend/app/langgraph_v2/utils/checkpointer.py:100`

## Section 5 — Auth / Identity Flow
- NextAuth Keycloak provider + JWT session tokens: `frontend/src/app/api/auth/[...nextauth]/route.ts:14`, `frontend/src/app/api/auth/[...nextauth]/route.ts:28`
- Client uses NextAuth session to extract access token for API calls: `frontend/src/lib/useAccessToken.ts:3`, `frontend/src/lib/useAccessToken.ts:29`
- Chat UI requires authenticated session + token before streaming: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:51`, `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:58`
- Backend Keycloak config values (issuer/JWKS/client): `backend/app/core/config.py:62`
- JWT verification uses Keycloak JWKS and allowed audiences: `backend/app/services/auth/token.py:21`, `backend/app/services/auth/token.py:75`
- API user_id is derived from `preferred_username` claim: `backend/app/services/auth/dependencies.py:42`
- user_id bound into LangGraph state and config for v2: `backend/app/api/v1/endpoints/langgraph_v2.py:75`, `backend/app/langgraph_v2/sealai_graph_v2.py:584`

## Section 6 — RAG / Qdrant Layer
- Embedding models (defaults + env-driven for RAG and ingest): `backend/app/core/config.py:37`, `backend/app/services/rag/rag_orchestrator.py:26`, `backend/app/services/rag/rag_ingest.py:12`
- Qdrant client initialization (RAG + LTM): `backend/app/services/rag/rag_orchestrator.py:21`, `backend/app/services/memory/memory_core.py:28`
- Collection names + tenant prefixing: `backend/app/services/rag/rag_orchestrator.py:21`, `backend/app/services/rag/rag_orchestrator.py:104`, `backend/app/services/memory/memory_core.py:35`, `backend/app/services/rag/rag_ingest.py:11`
- Filters/namespaces for retrieval (category/tenant + metadata filters): `backend/app/langgraph_v2/utils/rag_tool.py:42`, `backend/app/langgraph_v2/nodes/nodes_flows.py:346`, `backend/app/services/rag/rag_orchestrator.py:125`
- Retriever entrypoints used by agents/graphs: `backend/app/langgraph_v2/utils/rag_tool.py:49`, `backend/app/langgraph_v2/nodes/nodes_flows.py:346`
- Ingestion pipeline (QdrantVectorStore.from_documents): `backend/app/services/rag/rag_ingest.py:26`
- Qdrant bootstrap/collection creation checks: `backend/app/services/rag/qdrant_bootstrap.py:49`

## Section 7 — Jinja2 / Output
- Jinja environment + prompt directory (PROMPTS_DIR) + render helper: `backend/app/langgraph_v2/utils/jinja.py:11`, `backend/app/langgraph_v2/utils/jinja.py:27`
- Prompt templates for response routing: `backend/app/prompts/response_router.j2:1`
- Final answer draft + mapping to state/messages: `backend/app/langgraph_v2/nodes/nodes_flows.py:520`, `backend/app/langgraph_v2/nodes/nodes_flows.py:525`
- Final answer prompt assembly (template selection + policy injection): `backend/app/langgraph_v2/sealai_graph_v2.py:247`
- SSE token stream becomes assistant text in UI and rendered as Markdown: `backend/app/api/v1/endpoints/langgraph_v2.py:201`, `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:313`, `frontend/src/app/dashboard/components/Chat/ChatHistory.tsx:37`, `frontend/src/app/dashboard/components/Chat/MarkdownMessage.tsx:89`

## Section 8 — Duplicates / Legacy Signals
- LangGraph v1 marked as legacy and relocated to archive: `backend/app/langgraph/README.md:3`
- Legacy v2 graph variant kept alongside current graph: `backend/app/langgraph_v2/sealai_graph_v2_legacy.py:3`, `backend/app/langgraph_v2/sealai_graph_v2_legacy.py:111`
- Backup of v2 endpoint implementation: `archive/legacy_phase2/backend/app/api/v1/endpoints/langgraph_v2.py.backup:1`
- Backup of v2 nodes flow implementation: `archive/legacy_phase2/backend/app/langgraph_v2/nodes/nodes_flows.py.backup:1`
- Backup of frontend chat container: `archive/legacy_phase2/frontend/src/app/dashboard/components/Chat/ChatContainer.tsx.backup:1`
- Legacy chat/WS endpoints (v1) still present in codebase: `backend/app/api/v1/endpoints/ai.py:105`
- Placeholder chat endpoint using v1 compile path: `backend/app/api/routes/chat.py:1`
