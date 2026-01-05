# UI Param Sync Audit (LangGraph v2)

## Scope
- Parameter form: right sidebar in chat UI
- Patch endpoint: POST `/api/v1/langgraph/parameters/patch`
- State endpoint: GET `/api/v1/langgraph/state`
- Chat stream: POST `/api/chat` (Next.js proxy to backend `/api/v1/langgraph/chat/v2`)

## Key Components (Frontend)
- Parameter form UI: `frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx`
  - Submit button label: "Parameter übernehmen"
- Chat + param state owner: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`
  - Holds `parameters` state and `onParamSubmit` handler
  - Owns refresh + patch pipeline
- Chat ID derivation: `frontend/src/lib/useChatThreadId.ts`
  - Uses `sessionStorage` keyed by authenticated identity
  - Accepts `preferredChatId` (URL/route overrides storage)
- Chat streaming hook: `frontend/src/lib/useChatSseV2.ts`
  - POST `/api/chat` with `{ input, chat_id, client_msg_id }`
- Patch/state helpers: `frontend/src/lib/v2ParameterPatch.ts`
  - POST `/api/v1/langgraph/parameters/patch` with `{ chat_id, parameters }`
  - GET `/api/v1/langgraph/state?thread_id=<chat_id>`
- Route sources of `chat_id`:
  - `/chat/[conversationId]` → `frontend/src/app/chat/[conversationId]/page.tsx`
  - `ChatScreen` passes `conversationId` → `ChatContainer` (`frontend/src/app/dashboard/ChatScreen.tsx`)
  - Dashboard query param `?chat_id=` → `frontend/src/app/dashboard/DashboardClient.tsx`
  - Fallback: `useChatThreadId` sessionStorage

## Parameter übernehmen Handler (Exact Flow)
- UI submit: `ParameterFormSidebar` `onSubmit` prop
  - `frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx`
- ChatContainer handler:
  - `onParamSubmit` → `patchAllParameters(parameters)`
  - `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`
- Patch path:
  - `patchAllParameters` → `patchV2ParametersAndFetchState`
  - `frontend/src/lib/v2ParameterPatch.ts`
  - POST `/api/v1/langgraph/parameters/patch`
    - body: `{ chat_id: chatId, parameters: cleaned }`
  - GET `/api/v1/langgraph/state?thread_id=<chatId>`
- **chat_id used:** `chatId` from `ChatContainer` (prop or sessionStorage)
- **endpoint used:** direct `/api/v1/langgraph/...` (not `/api/chat` proxy)

## Chat ID Derivation (Cross-app)
- `ChatContainer`:
  - `const storedChatId = useChatThreadId(chatIdProp ?? null)`
  - `const chatId = chatIdProp ?? storedChatId`
- `/chat/[conversationId]` route:
  - conversationId → `ChatScreen` → `ChatContainer(chatId=conversationId)`
- `/dashboard?chat_id=...` route:
  - `DashboardClient` passes query param to `ChatContainer`
- Fallback:
  - `useChatThreadId` creates/persists `thread-<uuid>` in `sessionStorage`

## Hydration From Backend State
- Initial load:
  - `ChatContainer` `useEffect` calls `refreshParameters()` when `chatId/token` set
  - `refreshParameters` → `fetchV2StateParameters` → `setParameters`
- After streaming ends:
  - `useEffect` watches `streaming` transition → `refreshParameters()`
- After patch:
  - `patchV2ParametersAndFetchState` returns state → `setParameters(updated)`
- UI prefill from custom events:
  - `window` events `sealai:ui` / `sealai:form:patch` can merge `prefill/params`

## Dataflow Diagram (UI)
```
URL /chat/[conversationId]
  -> ChatScreen(conversationId)
    -> ChatContainer(chatId=conversationId)
      -> useChatThreadId(preferredChatId)
         -> sessionStorage (identity scoped)
      -> useChatSseV2(chatId)
         -> POST /api/chat (proxy) -> backend /api/v1/langgraph/chat/v2
      -> ParameterFormSidebar(parameters)
         "Parameter übernehmen"
           -> onParamSubmit()
             -> patchAllParameters(parameters)
               -> POST /api/v1/langgraph/parameters/patch {chat_id, parameters}
               -> GET /api/v1/langgraph/state?thread_id=<chat_id>
               -> setParameters(state.parameters)
      -> refreshParameters()
         -> GET /api/v1/langgraph/state?thread_id=<chat_id>
         -> setParameters(state.parameters)
```

## Notes / Potential Mismatch Risks
- **Two chat_id sources** in UI:
  - `chatIdProp` (route/query) vs sessionStorage fallback
  - In `/chat/[conversationId]`, URL wins; in `/dashboard`, sessionStorage can become the canonical id when no query param is present.
- **Direct `/api/v1/...` calls** in UI (no Next.js proxy) for patch/state.
- **Secondary/legacy forms**:
  - `frontend/src/app/dashboard/components/Sidebar/SidebarForm.tsx` uses `useChatThreadId()` independently and `patchV2Parameters` (same endpoint). Not used by right sidebar, but can diverge from URL if mounted elsewhere.

## Code Pointers (Primary)
- `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`
- `frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx`
- `frontend/src/lib/v2ParameterPatch.ts`
- `frontend/src/lib/useChatThreadId.ts`
- `frontend/src/lib/useChatSseV2.ts`
- `frontend/src/app/chat/[conversationId]/page.tsx`
- `frontend/src/app/dashboard/DashboardClient.tsx`
