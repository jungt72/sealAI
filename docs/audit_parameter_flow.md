# Audit: Parameter Flow (Right Sidebar)

## Phase 1 - Architekturkarte (Flow Map)

### A) UI -> Frontend Local/Form State
- Sidebar-Komponente: `ParameterFormSidebar` rendert die rechte Form und bekommt `parameters`, `onUpdate`, `onSubmit`, `onClose`. Evidence: `frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx:7` `frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx:90` `frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx:131`
- Formwerte liegen in `ChatContainer` als lokaler State (`paramState.values`, `paramState.dirty`). Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:82` `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:87`
- Eingaben gehen ueber `onParamUpdate`, markieren dirty und optional debounced patch. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:270` `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:281`
- Submit ("Parameter uebernehmen") ruft `onParamSubmit`, baut dirty patch. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:302`

### B) Frontend State -> Patch Request
- Patch-Request wird in `patchAllParameters` gebaut und via `patchV2Parameters` gesendet. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:247` `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:255` `frontend/src/lib/v2ParameterPatch.ts:43`
- Endpoint + Payload: `POST /api/v1/langgraph/parameters/patch` mit `{ chat_id, parameters }`. Evidence: `frontend/src/lib/v2ParameterPatch.ts:54` `frontend/src/lib/v2ParameterPatch.ts:60`
- Normalisierung/Sanitizing: `cleanParameterPatch` + `normalizeNumericInput` (filtert undef/leer, parst Numerik). Evidence: `frontend/src/lib/parameterSync.ts:77` `frontend/src/lib/normalizeNumericInput.ts:1`
- Guards: kein Patch ohne `chatId`/`token`, kein Patch bei leerem Payload, debounced optional via `NEXT_PUBLIC_AUTO_PATCH_PARAMS`. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:247` `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:270`

### C) Backend Endpoint -> Persistenz im LangGraph State
- Patch-Endpoint: `POST /api/v1/langgraph/parameters/patch`. Evidence: `backend/app/api/v1/endpoints/langgraph_v2.py:721`
- Auth: `user_id` kommt aus Keycloak JWT (`get_current_request_user`). Evidence: `backend/app/api/v1/endpoints/langgraph_v2.py:725`
- Validierung/Coercion: `sanitize_v2_parameter_patch` erlaubt nur TechnicalParameters + primitives; `merge_parameters` merged mit bestehendem State. Evidence: `backend/app/langgraph_v2/utils/parameter_patch.py:33` `backend/app/langgraph_v2/utils/parameter_patch.py:48`
- State read/write: `graph.aget_state` -> `graph.aupdate_state` mit `as_node=supervisor_policy_node`. Evidence: `backend/app/api/v1/endpoints/langgraph_v2.py:752` `backend/app/api/v1/endpoints/langgraph_v2.py:783`
- Mapping thread_id/chat_id: `_build_graph_config` nutzt `thread_id=chat_id` und Keycloak `user_id` fuer checkpointer namespace. Evidence: `backend/app/api/v1/endpoints/langgraph_v2.py:746` `backend/app/langgraph_v2/sealai_graph_v2.py:571`

### D) Backend State -> zurueck ins Frontend
- GET State: `GET /api/v1/langgraph/state?thread_id=...` liefert `parameters`. Evidence: `backend/app/api/v1/endpoints/state.py:141` `backend/app/api/v1/endpoints/state.py:188`
- Frontend Fetch: `fetchV2StateParameters` ruft GET auf und liefert `body.parameters`. Evidence: `frontend/src/lib/v2ParameterPatch.ts:68` `frontend/src/lib/v2ParameterPatch.ts:85`
- Re-Hydration: `refreshParameters` ruft GET (initial, nach Stream-Ende, nach done event) und merged via `mergeServerParameters`. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:333` `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:341` `frontend/src/lib/parameterSync.ts:51`
- SSE: Chat stream via `/api/chat` (Event `done`) triggert state refresh. Evidence: `frontend/src/lib/useChatSseV2.ts:32` `frontend/src/lib/useChatSseV2.ts:177`

## Phase 2 - Repro Script + Instrumentation

### Dev-only Logging
- Frontend flag: `NEXT_PUBLIC_PARAM_SYNC_DEBUG=1`.
  - Logs on input change and submit include field, raw/normalized value, payload keys, chat_id. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:281` `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:302`
  - Patch payload logging already in `patchV2Parameters`. Evidence: `frontend/src/lib/v2ParameterPatch.ts:48`
- Backend flag: `SEALAI_PARAM_SYNC_DEBUG=1`.
  - Patch payload, patch keys/types, state subset before/after, short user id, checkpoint thread id. Evidence: `backend/app/api/v1/endpoints/langgraph_v2.py:731` `backend/app/api/v1/endpoints/langgraph_v2.py:757`
  - State GET logs parameter keys and checkpoint info. Evidence: `backend/app/api/v1/endpoints/state.py:163`

### Script
- `ops/repro_param_flow.sh` runs PATCH -> GET with jq-filtered output and exit codes. Evidence: `ops/repro_param_flow.sh`

### Browser/UI Repro Plan
1) Page load -> expect initial parameters in right sidebar after GET state hydration.
2) Change a field -> expect local state update, dirty mark; optional debounced patch if `NEXT_PUBLIC_AUTO_PATCH_PARAMS=1`.
3) Click "Parameter uebernehmen" -> expect PATCH payload with dirty keys.
4) Reload/new tab -> expect GET state to rehydrate form (values match backend).

## Phase 3 - Bug Isolation

### Findings
- Root cause: PATCH endpoint only merged existing parameters when `snapshot.values` was a dict; if LangGraph returns a `SealAIState`, existing parameters were discarded and patch overwrote them, causing partial state loss. Evidence (before fix): `backend/app/api/v1/endpoints/langgraph_v2.py:752` previously used `snapshot.values` dict check only; fix adds `_state_values_to_dict` to merge regardless of type.

### Checked Candidates
- ID mismatch: Frontend uses the same `chatId` for PATCH and for GET `thread_id`. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:60` `frontend/src/lib/v2ParameterPatch.ts:73`
- Auth: PATCH and GET both send `Authorization: Bearer <token>`. Evidence: `frontend/src/lib/v2ParameterPatch.ts:56` `frontend/src/lib/v2ParameterPatch.ts:75`
- Merge/Overwrite (frontend): Dirty keys are protected from server merge; refresh only merges non-dirty keys. Evidence: `frontend/src/lib/parameterSync.ts:51`
- Back to form: `refreshParameters` runs on initial load + done event, applying `mergeServerParameters`. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:333` `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:352`

## Phase 4 - Fix + Tests

### Fix
- Backend now normalizes snapshot values to dict before reading existing parameters, preventing accidental drops. Evidence: `backend/app/api/v1/endpoints/langgraph_v2.py:753`
- Added debug logging for patch before/after subsets to prove state mutation and typing. Evidence: `backend/app/api/v1/endpoints/langgraph_v2.py:757`
- Added frontend debug logs for input + submit with normalized values/payload keys. Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:281`

### Tests
- Frontend unit: `mergeServerParameters` hydration behavior (dirty vs non-dirty). Evidence: `frontend/src/lib/parameterSync.test.ts:1`
- Backend integration: patch merge keeps existing values across multiple patches. Evidence: `backend/app/api/tests/test_langgraph_v2_param_sync_integration.py:71`

## Phase 5 - Verification

### Commands
- Repro script:
  - `ops/repro_param_flow.sh <chat_id>`
- Logs:
  - `docker-compose logs -f backend`
  - `docker-compose logs -f frontend`
- Tests:
  - `cd frontend && npm run test:unit`
  - `cd backend && pytest app/api/tests/test_langgraph_v2_param_sync_integration.py`

### Status
- Script not executed here (requires BEARER_TOKEN + running stack).
- Verdict: Fix applied to prevent parameter loss on PATCH when snapshot is not dict; with debug flags enabled, flow is fully observable end-to-end.
