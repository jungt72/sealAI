# Audit: Parameter-Form Submit -> Chat Message

## Flow A: Normales Chat-Senden (Enter/Send)
- UI Send-Handler: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:440`
  - `handleSend()` appended sofort eine User-Message + `send(content)`.
  - Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:440-474`
- Network: `useChatSseV2.send()` POST `/api/chat` (SSE)
  - Payload: `{ input, chat_id, client_msg_id }`
  - Headers: `Authorization: Bearer <token>`, `Accept: text/event-stream`, `Last-Event-ID` optional
  - Evidence: `frontend/src/lib/useChatSseV2.ts:92-131`
- Backend proxy: `/api/chat` forwards to LangGraph
  - Validates `chat_id`, `input`, `Authorization`.
  - Evidence: `frontend/src/app/api/chat/route.ts:40-149`

## Flow B: "Parameter übernehmen" (rechte Sidebar)
- UI Submit-Handler: `ParameterFormSidebar` -> `onSubmit()`
  - Evidence: `frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx:100-103`
- Handler in ChatContainer: `onParamSubmit()`
  - Clean Patch -> `patchAllParameters(cleaned)` -> toast only
  - Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:302-331`
- Network: `patchV2Parameters()` POST `/api/v1/langgraph/parameters/patch`
  - Payload: `{ chat_id, parameters }`
  - Headers: `Authorization: Bearer <token>`
  - Evidence: `frontend/src/lib/v2ParameterPatch.ts:43-61`
- State refresh: `fetchV2StateParameters()` GET `/api/v1/langgraph/state?thread_id=...`
  - Evidence: `frontend/src/lib/v2ParameterPatch.ts:68-89`

## Side-by-side Summary
- Chat-Senden → POST `/api/chat` (SSE) + optimistic user message in UI.
- Parameter übernehmen → POST `/api/v1/langgraph/parameters/patch` + optional state refresh; **keine** Chat-POST, **keine** Chat-Message in UI.

## Post-Fix Behavior (Param-Apply Chat Summary)
- Nach erfolgreichem Patch wird eine kurze Zusammenfassung erzeugt und via `/api/chat` gesendet.
- Frontend nutzt denselben Send-Flow wie normales Chat-Senden (SSE + Authorization).
- Metadata: `{ source: "param_apply", kind: "parameter_summary", keys: [...] }`.
- Evidence: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:302-355`, `frontend/src/lib/useChatSseV2.ts:92-131`

## Verifikation (Runbook)
1) Parameter in der rechten Sidebar ändern -> Klick "Parameter übernehmen".
2) Erwartung im Chat: neue Nachricht `"Parameter übernommen: ..."` erscheint.
3) Network: POST `/api/v1/langgraph/parameters/patch` **und** POST `/api/chat` (SSE) sichtbar.
4) Reload: Message bleibt erhalten, sofern Backend-Chat-History persistiert.
