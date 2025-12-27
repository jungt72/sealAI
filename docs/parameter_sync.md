# Parameter Sync (V2)

## SSOT
Client-side parameters live in `paramState` inside `ChatContainer`. The form renders from
`paramState.values`, and user edits mark keys in `paramState.dirty`.

## Dirty Merge Rules
Server refreshes (`/api/v1/langgraph/state`) merge into `paramState.values` without
overwriting keys that are still dirty on the client.

## Submit + Refresh Flow
1) User edits form fields (dirty keys tracked).
2) "Parameter übernehmen" builds a dirty-only patch, cleans empty values, and posts to
   `/api/v1/langgraph/parameters/patch` with `Authorization: Bearer <token>`.
3) After a successful patch, the client refreshes `/api/v1/langgraph/state` and clears
   dirty keys that were submitted.

## SSE Done Refresh
When the chat SSE emits `event: done`, the client triggers a `/state` refresh for the
active chat to keep the form in sync with server-side parameter updates.
