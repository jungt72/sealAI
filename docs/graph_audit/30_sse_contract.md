# Phase 3 — SSE Contract (Backend)

Quelle: `backend/app/api/v1/endpoints/langgraph_v2.py`.

## Endpoint

- POST `/api/v1/langgraph/chat/v2` streams `text/event-stream`. Siehe `backend/app/api/v1/endpoints/langgraph_v2.py:737-768`.  
- Auth: `CurrentUser.sub` wird als `user_id` gesetzt, Request‑Body `user_id` wird überschrieben `backend/app/api/v1/endpoints/langgraph_v2.py:762-764`.  

## Stream Mode

- Primär versucht: `graph.astream_events(... stream_mode=["updates","messages"], version="v2")` `backend/app/api/v1/endpoints/langgraph_v2.py:454-461`.  
- Fallback auf `["messages"]` wenn `TypeError` (LangGraph ohne updates support) `backend/app/api/v1/endpoints/langgraph_v2.py:462-469`.  

## Event Types & Payloads

Events werden über `_format_sse(event, payload)` formatiert `backend/app/api/v1/endpoints/langgraph_v2.py:295-305`.

### `message`

- Emittiert für LLM‑Tokens aus `on_chat_model_stream/on_llm_stream`. `backend/app/api/v1/endpoints/langgraph_v2.py:525-540`.  
- Payload example:
```json
{"text":"...","node":"final_answer_node","action":"on_chat_model_stream","run_id":"...","thread_id":"...","user_id":"..."}
```

### `token`

- Nur im Fallback‑Pfad wenn kein Chunk gestreamt wurde. `backend/app/api/v1/endpoints/langgraph_v2.py:676-689`.  
- Payload:
```json
{"text":"...","node":"final_answer_node","run_id":"...","thread_id":"...","user_id":"..."}
```

### `state_update`

- Delta aus `parameters` und/oder `metadata`. `backend/app/api/v1/endpoints/langgraph_v2.py:484-515`.  
- Contract: Parameter‑Änderungen werden **nur** via `state_update` emittiert (keine `parameter_update` Events), siehe Kommentar `backend/app/api/v1/endpoints/langgraph_v2.py:484-488` und Contract‑Test `backend/tests/contract/test_sse_contract.py:157-190`.  
- Payload:
```json
{"type":"state_update","delta":{"parameters":{...},"metadata":{...}},"source":"on_node_end","run_id":"...","thread_id":"...","user_id":"..."}
```

### `node_start` / `node_end`

- Emittiert zu Observability‑Zwecken. `backend/app/api/v1/endpoints/langgraph_v2.py:541-560`.  

### `ask_missing`

- Wird gesendet, wenn `awaiting_user_input=True` im finalen Redis Snapshot. `backend/app/api/v1/endpoints/langgraph_v2.py:665-667`.  
- Payload aufgebaut in `_build_ask_missing_payload` `backend/app/api/v1/endpoints/langgraph_v2.py:322-349`.  

### `error`

- On exception, mit `message` string. `backend/app/api/v1/endpoints/langgraph_v2.py:614-658`, `697-706`.  

### `done`

- Immer am Ende, optional `final_text`. `backend/app/api/v1/endpoints/langgraph_v2.py:574-599`, `691-721`.  

## Sequencing Guarantees

- Producer erzeugt Events in Queue, Consumer yieldet in Reihenfolge `backend/app/api/v1/endpoints/langgraph_v2.py:600-735`.  
- `done` wird auch im Error/Timeout Fall gesendet.  
