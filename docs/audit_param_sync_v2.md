# Audit: Parameter ↔ Chat/State Sync (LangGraph v2)

Date: 2025-09-29

## Scope
Frontend: SealParameters, parameter form, chat thread id, API callers, useChatSseV2, patch helpers.
Backend: langgraph_v2 endpoints, state endpoints, checkpointer/thread_id, parameter contracts, graph state.

## Current Wiring (Observed)
```
[ParameterFormSidebar]
  onChange -> ChatContainer.onParamUpdate (local React state)
  onSubmit -> ChatContainer.patchAllParameters
     -> POST /api/v1/langgraph/parameters/patch (Authorization: Bearer <token>)
     -> backend app/api/v1/endpoints/langgraph_v2.py (patch_parameters)
        -> sanitize_v2_parameter_patch (allowlist)
        -> graph.aupdate_state(config, {parameters: merged}, as_node=supervisor_logic_node)

[Chat SSE]
  ChatContainer.useChatSseV2 -> POST /api/chat (proxy) -> backend /api/v1/langgraph/chat/v2
  No state_update event handling in useChatSseV2.

[State]
  backend GET /api/v1/langgraph/state?thread_id=... exists
  Frontend does not fetch /state anywhere.
```

## Audit Questions (Answers)
1) **Single source of truth for parameters?**
   - Current: **local React state in `ChatContainer`** (`useState<SealParameters>`) is the only source.
   - Backend state (`/state`) exists but is not fetched; there is no merged client cache.

2) **Form field change call (URL/payload/headers)?**
   - `ParameterFormSidebar` calls `onUpdate` only (no network on change).
   - Submit calls `ChatContainer.patchAllParameters` → `POST /api/v1/langgraph/parameters/patch` with JSON `{ chat_id, parameters }` and `Authorization: Bearer <token>`.
   - `chat_id` is included when `chatId` is available; `as_node` is implicit (backend uses `supervisor_logic_node`).

3) **Which chat_id is used by SSE/patch/state?**
   - SSE: `useChatSseV2` uses `chatId` from `useChatThreadId` / route param.
   - Patch: `ChatContainer.patchAllParameters` uses the same `chatId`.
   - State: **not called by frontend** (but endpoint expects `thread_id`).

4) **After successful patch 200 OK, where is UI updated?**
   - UI is updated only by **local state** (optimistic set via `setParameters`).
   - No refetch of `/state` and no SSE param/state update handled.

5) **Race conditions?**
   - No rapid patching on every keystroke (patch happens on submit or `/param` command only).
   - However, **SSE streaming can update parameters in graph** without any UI refresh, causing drift.

6) **Parameter key mismatches?**
   - **Yes.** Backend allowlist in `sanitize_v2_parameter_patch` is small (e.g. `medium`, `pressure_bar`, `temperature_C`, etc.).
   - The form sends many keys outside allowlist (e.g. `nominal_diameter`, `housing_tolerance`, `roughness_ra`, `lead_pitch`, etc.), causing **400 invalid_parameters** and no state update.

7) **Backend persistence for same user+chat_id?**
   - `build_v2_config` uses `checkpoint_thread_id = f"{user_id}|{thread_id}"` and v2 checkpointer namespace.
   - `parameters/patch`, `chat/v2`, and `/state` all use `build_v2_config` with the same `chat_id`/user.
   - Therefore persistence is consistent **if** patch succeeds and keys are allowed.

## Proven Root Causes
1) **Frontend never pulls `/state`** and does not listen for param/state updates via SSE.
   - Result: UI can drift from LangGraph state; parameters from tools/graph are never reflected.
2) **Backend patch allowlist rejects most form fields.**
   - Result: patch calls return 400 for valid form fields, so LangGraph state never updates.

## Affected Files (Observed)
Frontend:
- `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`
- `frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx`
- `frontend/src/lib/useChatSseV2.ts`
- `frontend/src/lib/v2ParameterPatch.ts`
- `frontend/src/lib/types/sealParameters.ts`

Backend:
- `backend/app/api/v1/endpoints/langgraph_v2.py`
- `backend/app/api/v1/endpoints/state.py`
- `backend/app/langgraph_v2/utils/parameter_patch.py`
- `backend/app/langgraph_v2/state/sealai_state.py`

## Evidence (Command Output)
### Frontend search
```
$ rg -n "parameters/patch|langgraph/state|SealParameters|patchParameters|use.*Parameters|sessionStorage|chat_id|conversationId" frontend/src -S
frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:102:  const patchAllParameters = useCallback(async (patch: Partial<SealParameters>) => {
frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:111:    const res = await fetch("/api/v1/langgraph/parameters/patch", {
frontend/src/lib/useChatSseV2.ts:101:            chat_id: chatId,
frontend/src/lib/useChatThreadId.ts:35:      const lastKey = sessionStorage.getItem(STORAGE_CURRENT);
frontend/src/lib/langgraphApi.ts:31:  `${langgraphBackendBase()}/api/v1/langgraph/state`;
```

### Backend search
```
$ rg -n "parameters/patch|/state|chat_id|thread_id|checkpointer|parameters" backend/app -S
backend/app/api/v1/endpoints/langgraph_v2.py:426:@router.post("/parameters/patch")
backend/app/api/v1/endpoints/langgraph_v2.py:433:    chat_id = (body.chat_id or "").strip()
backend/app/api/v1/endpoints/langgraph_v2.py:445:        existing_params = state_values.get("parameters") if isinstance(state_values, dict) else {}
backend/app/api/v1/endpoints/state.py:134:@router.get("/state")
backend/app/api/v1/endpoints/state.py:196:@router.post("/state")
backend/app/langgraph_v2/utils/parameter_patch.py:8:ALLOWED_V2_PARAMETER_KEYS = {
backend/app/langgraph_v2/state/sealai_state.py:250:    parameters: TechnicalParameters = Field(default_factory=TechnicalParameters)
```

### Form entrypoint and wiring
```
Parameter form: frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx
- onChange -> onUpdate(name, value)
- onSubmit -> onSubmit()

Wiring: frontend/src/app/dashboard/components/Chat/ChatContainer.tsx
- onUpdate -> setParameters (local state)
- onSubmit -> patchAllParameters -> POST /api/v1/langgraph/parameters/patch
```

## Minimal Fix Plan
1) **Frontend:**
   - Fetch `/api/v1/langgraph/state?thread_id=...` on chat load and after SSE completion.
   - After successful patch, refresh from `/state` (or update local state from response).
   - Filter or normalize parameter keys to backend contract.
2) **Backend:**
   - Align parameter allowlist with `TechnicalParameters` model fields (including aliases) so form keys are accepted.
   - Add debug logs (guarded by env flag) for patch and state reads to track chat_id, keys, and checkpointer namespace.
3) **Tests:**
   - Backend integration: patch parameters then read `/state` returns same values for same user+chat_id.
   - Frontend unit: patch helper includes chat_id and uses expected payload; (or add ops smoke script if UI test is heavy).
