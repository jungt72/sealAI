# Wiring Review (SSE v2)

## Graph (MAI-DxO)
- Entry -> frontdoor -> supervisor routing is wired via `_select_supervisor_entry` and `frontdoor_discovery_node` conditional edges (`backend/app/langgraph_v2/sealai_graph_v2.py:424`, `backend/app/langgraph_v2/sealai_graph_v2.py:496`, `backend/app/langgraph_v2/sealai_graph_v2.py:497`).
- MAI-DxO loop fans out to panels, aggregates, and loops back to supervisor policy (`backend/app/langgraph_v2/sealai_graph_v2.py:522`, `backend/app/langgraph_v2/sealai_graph_v2.py:528`, `backend/app/langgraph_v2/sealai_graph_v2.py:535`, `backend/app/langgraph_v2/sealai_graph_v2.py:538`).
- Finalization flows through `final_answer_node` to END (`backend/app/langgraph_v2/sealai_graph_v2.py:493`, `backend/app/langgraph_v2/sealai_graph_v2.py:599`).

## SSE (request_id + errors)
- request_id is accepted/created and echoed in response headers and SSE payloads (`backend/app/api/v1/endpoints/langgraph_v2.py:392`, `backend/app/api/v1/endpoints/langgraph_v2.py:410`, `backend/app/api/v1/endpoints/langgraph_v2.py:276`).
- Stream errors log with `logger.exception` and include request context in extra (`backend/app/api/v1/endpoints/langgraph_v2.py:300`, `backend/app/api/v1/endpoints/langgraph_v2.py:356`).

## Config (supervisor mode)
- `LANGGRAPH_V2_SUPERVISOR_MODE=mai_dxo` toggles only routing in `_select_supervisor_entry` (`backend/app/langgraph_v2/sealai_graph_v2.py:424`).
- `/api/v1/langgraph/chat/v2` endpoint contract remains stable (`backend/app/api/v1/endpoints/langgraph_v2.py:386`).

## Checkpointer (Redis)
- Checkpointer namespace is derived from `LANGGRAPH_V2_NAMESPACE` (`backend/app/langgraph_v2/constants.py:5`).
- Checkpointer thread_id is scoped by `user_id|thread_id` in v2 config (`backend/app/langgraph_v2/sealai_graph_v2.py:635`, `backend/app/langgraph_v2/sealai_graph_v2.py:637`).
