# Phase 3 — Frontend SSE Bridge / Drift Check

Quelle: `frontend/src/lib/useChat.ts`, `frontend/src/lib/langgraphApi.ts`.

## Expected Event Types (TS)

Union: `message`, `token`, `ask_missing`, `discovery_form`, `parameter_update`, `state_update`, `done`, `error`. `frontend/src/lib/useChat.ts:382-390`.  
Hinweis: Backend emittiert Parameter‑Deltas nur via `state_update` (keine `parameter_update` Events) `backend/app/api/v1/endpoints/langgraph_v2.py:484-515`, abgesichert durch `backend/tests/contract/test_sse_contract.py:157-190`.  

## Normalization

- Raw SSE blocks werden geparst (`event:` header, `data:` JSON) `frontend/src/lib/useChat.ts:439-462`.  
- `normalizeEvent` nutzt `evt.event` oder `evt.data.type` als source‐of‐truth `frontend/src/lib/useChat.ts:503-509`.  
- Mapping deckt Backend‑Events ab: `message`, `token`, `ask_missing`, `parameter_update`, `state_update`, `done`, `error` `frontend/src/lib/useChat.ts:510-571`.  
- Backend‑Events `node_start/node_end` sind **nicht in TS Union** → werden in `normalizeEvent` als unknown droppped `frontend/src/lib/useChat.ts:572-573`.  

## State Pull + SSE Deltas

- Initialer State Pull GET `/api/v1/langgraph/state?thread_id=...` `frontend/src/lib/useChat.ts:608-651` via `STATE_ENDPOINT` `frontend/src/lib/langgraphApi.ts:30-31`.  
- SSE `state_update` merged `delta.parameters`/`delta.metadata` in lokalen State `frontend/src/lib/useChat.ts:830-843`.  
- Zusätzlich wird `parameter_update` (Legacy) einzeln gemerged, falls vorhanden `frontend/src/lib/useChat.ts:845-867`.  

## Drift / Notes

- `node_start/node_end` werden vom Frontend ignoriert (nicht im TS Union; `normalizeEvent` droppt unknown) `frontend/src/lib/useChat.ts:382-390`, `frontend/src/lib/useChat.ts:572-573`.  
