# SEALAI Phase 1 Risk Register

- **R1 [Medium] — User identity scoping uses `preferred_username`**
  Evidence: `get_current_request_user` returns `preferred_username` (`backend/app/services/auth/dependencies.py:21-42`) and checkpoint scoping uses `user_id` for `checkpoint_thread_id` (`backend/app/langgraph_v2/sealai_graph_v2.py:576-582`).
  Impact: mutable usernames can cause state collision or cross-user data overlap.
  Recommendation: switch checkpoint scoping to `sub` while retaining `preferred_username` as display metadata (`backend/app/services/auth/dependencies.py:21-42`, `backend/app/langgraph_v2/sealai_graph_v2.py:584-587`).

- **R2 [Medium] — Redis fallback to MemorySaver can silently lose state**
  Evidence: MemorySaver is returned on Redis init failure (`backend/app/langgraph_v2/utils/checkpointer.py:85-100`).
  Impact: transient Redis outages can reset conversation state.
  Recommendation: fail fast in prod or gate fallback via environment flag (`backend/app/langgraph_v2/utils/checkpointer.py:55-100`).

- **R3 [Medium] — Checkpointer namespace is empty**
  Evidence: `CHECKPOINTER_NAMESPACE_V2 = ""` (`backend/app/langgraph_v2/constants.py:3`).
  Impact: potential key collisions across deployments or shared Redis environments.
  Recommendation: set non-empty namespace prefix (e.g., `sealai:v2:`) (`backend/app/langgraph_v2/constants.py:3`).

- **R4 [Medium] — Conversation history endpoints likely fail auth**
  Evidence: chat_history expects `current_user.sub` or `current_user.user_id` (`backend/app/api/v1/endpoints/chat_history.py:118-126`), but `get_current_request_user` returns a string (`backend/app/services/auth/dependencies.py:21-42`).
  Impact: conversation listing/history likely 401s because `current_user` is not an object.
  Recommendation: align dependency return type or use `get_current_request_user` consistently as a string ID (`backend/app/api/v1/endpoints/chat_history.py:118-126`, `backend/app/services/auth/dependencies.py:21-42`).
  Failure path: frontend calls `/api/conversations` (`frontend/src/components/ConversationSidebar.tsx:97-103`), Next.js proxy calls backend `/api/v1/chat/conversations` (`frontend/src/app/api/conversations/route.ts:94-105`), which hits chat_history and fails to resolve `current_user.sub` (`backend/app/api/v1/endpoints/chat_history.py:118-126`).

- **R5 [Medium] — RAG ingest vs retrieval mismatch (collection + embedding)**
  Evidence: ingest defaults `QDRANT_COLLECTION=sealai-docs-bge-m3` and `EMBEDDING_MODEL=BAAI/bge-m3` (`backend/app/services/rag/rag_ingest.py:11-13`), while retrieval defaults `QDRANT_COLLECTION=sealai-docs` and `EMB_MODEL_NAME=intfloat/multilingual-e5-base` (`backend/app/services/rag/rag_orchestrator.py:21-27`).
  Impact: retrieval may query a different collection or incompatible embeddings, causing empty/low-quality results.
  Recommendation: align env defaults or enforce explicit config across ingest and retrieval (`backend/app/services/rag/rag_ingest.py:11-13`, `backend/app/services/rag/rag_orchestrator.py:21-27`).

- **R6 [Low] — Nginx `/api/v1/chat/sse` proxy targets non-existent backend route**
  Evidence: nginx proxies `/api/v1/chat/sse` to `/api/v1/langgraph/sse` (`nginx/default.conf:162-176`) but backend routers include only `/api/v1/langgraph` routes from `langgraph_v2`/`state`/`langgraph_health` (`backend/app/api/v1/api.py:7-31`).
  Impact: stale or confusing endpoint; potential operational confusion.
  Recommendation: remove or update proxy path to a real endpoint (`nginx/default.conf:162-176`, `backend/app/api/v1/api.py:7-31`).

- **R7 [Low] — Nginx `/api/v1/ai/ws` proxies to legacy router not mounted**
  Evidence: nginx proxies `/api/v1/ai/ws` (`nginx/default.conf:132-145`), but `ai` router is not included in the v1 API router (`backend/app/api/v1/api.py:7-31`).
  Impact: dead endpoint; may cause confusion in ops.
  Recommendation: remove or document legacy WebSocket endpoint (`nginx/default.conf:132-145`, `backend/app/api/v1/api.py:7-31`).

- **R8 [Low] — Jinja StrictUndefined can raise runtime errors on missing variables**
  Evidence: Jinja uses `StrictUndefined` and render calls are not guarded (`backend/app/langgraph_v2/utils/jinja.py:15-37`, `backend/app/langgraph_v2/nodes/nodes_flows.py:299-319`).
  Impact: missing variables can break response rendering.
  Recommendation: add template contract docs or use defensive defaults in context construction (`backend/app/langgraph_v2/utils/jinja.py:15-37`).
