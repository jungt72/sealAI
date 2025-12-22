# SEALAI Phase 1 Cleanup Plan (No Deletions Yet)

## 1) Canonical Modules to Keep
- LangGraph v2 core graph + config: `backend/app/langgraph_v2/sealai_graph_v2.py:439`, `backend/app/langgraph_v2/sealai_graph_v2.py:568`
- Supervisor + frontdoor intent entry: `backend/app/langgraph_v2/nodes/nodes_supervisor.py:57`, `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:152`
- Flow nodes (design/compare/troubleshooting): `backend/app/langgraph_v2/nodes/nodes_flows.py:43`
- Confirm checkpoint node: `backend/app/langgraph_v2/nodes/nodes_confirm.py:66`
- State schema + types: `backend/app/langgraph_v2/state/sealai_state.py:220`
- v2 API endpoints (SSE + state + params patch): `backend/app/api/v1/endpoints/langgraph_v2.py:350`, `backend/app/api/v1/endpoints/state.py:136`
- Auth dependencies + JWT verification: `backend/app/services/auth/dependencies.py:21`, `backend/app/services/auth/token.py:59`
- Frontend sender + proxy: `frontend/src/lib/useChatSseV2.ts:50`, `frontend/src/app/api/chat/route.ts:27`

## 2) Deprecation Plan (Candidates)
- Legacy v1 endpoints (not mounted): `backend/app/api/v1/endpoints/ai.py:105`, `backend/app/api/v1/api.py:7-31`
- Legacy v2 graph variant: `backend/app/langgraph_v2/sealai_graph_v2_legacy.py:1-3`
- Placeholder chat endpoint: `backend/app/api/routes/chat.py:1-40`
- Legacy external agents (docker-compose): `normen-agent` and `material-agent` are gated behind a profile and should not run by default (`docker-compose.yml:99-130`).
- Backup files: `archive/legacy_phase2/backend/app/api/v1/endpoints/langgraph_v2.py.backup:1-10`, `archive/legacy_phase2/backend/app/langgraph_v2/nodes/nodes_flows.py.backup:1-10`, `archive/legacy_phase2/frontend/src/app/dashboard/components/Chat/ChatContainer.tsx.backup:1-34`
- Nginx legacy proxies for v1 WS and SSE: `/api/v1/ai/ws` and `/api/v1/chat/sse` (`nginx/default.conf:132-176`)
- Duplicate repo path `/opt/seal ai` usage: no references in repo scripts; ops scripts derive repo root from script path (`ops/up-dev.sh:4-11`).

## 3) Suggested Folder Structure (Target)
- `langgraph_v2/{graphs,nodes,tools,utils,state}` — aligns with current node/tools/utils/state split (`backend/app/langgraph_v2/nodes/nodes_flows.py:1-16`, `backend/app/langgraph_v2/tools/parameter_tools.py:1-17`, `backend/app/langgraph_v2/utils/jinja.py:1-12`, `backend/app/langgraph_v2/state/sealai_state.py:1-12`).
- `services/{auth,chat,rag,memory}` — already exists in `backend/app/services/*` (`backend/app/services/auth/dependencies.py:1-16`, `backend/app/services/chat/conversations.py:1-16`, `backend/app/services/rag/rag_orchestrator.py:1-10`, `backend/app/services/memory/memory_core.py:1-22`).
- `prompts/` for Jinja templates — already centralized (`backend/app/langgraph_v2/utils/jinja.py:11-12`, `backend/app/prompts/response_router.j2:1-4`).

## 4) Cleanup Sequence (Safe, Incremental)
1) **Document canonical endpoints**: confirm `langgraph_v2` routes are mounted and used (`backend/app/api/v1/api.py:27-31`, `frontend/src/lib/useChatSseV2.ts:30-105`).
2) **Deprecate legacy nginx proxies**: mark `/api/v1/ai/ws` and `/api/v1/chat/sse` as legacy in ops docs before removal (`nginx/default.conf:132-176`).
3) **Flag legacy code**: mark v1 endpoints and legacy graph for deletion in Phase 2 (`backend/app/api/v1/endpoints/ai.py:105-214`, `backend/app/langgraph_v2/sealai_graph_v2_legacy.py:1-3`).
4) **Consolidate backups**: collect `.backup` files into an archive folder or delete in Phase 2 after confirming no imports (`archive/legacy_phase2/backend/app/api/v1/endpoints/langgraph_v2.py.backup:1-10`, `archive/legacy_phase2/backend/app/langgraph_v2/nodes/nodes_flows.py.backup:1-10`, `archive/legacy_phase2/frontend/src/app/dashboard/components/Chat/ChatContainer.tsx.backup:1-34`).
5) **Verify no references**: run a repo-wide search for any `import` or route registration of deprecated modules (evidence of active routes is in `backend/app/api/v1/api.py:7-31`).
6) **Tests / safety checks**: rerun API smoke tests after removing legacy routes (e.g., ensure `/api/chat` and `/api/v1/langgraph/chat/v2` still stream) (`frontend/src/lib/useChatSseV2.ts:92-147`, `backend/app/api/v1/endpoints/langgraph_v2.py:350-377`).
