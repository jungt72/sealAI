# Chat Variants Archaeology (frontend/src)

## 1. Active route graph → mounted chat container

- `/chat` (`frontend/src/app/chat/page.tsx`:3-11) immediately redirects with `router.replace(`/chat/${id}`)`.
- `/chat/[conversationId]` (`frontend/src/app/chat/[conversationId]/page.tsx`:1-13) renders `<ChatScreen conversationId={conversationId} />`.
- `ChatScreen` (`frontend/src/app/dashboard/ChatScreen.tsx`:1-10) simply renders `<Chat chatId={conversationId ?? null} />`.
- `Chat` resolves to the current chat container (`frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`:1-1300) which wires `useChatSseV2`, `useChatThreadId`, and the drawer/parameter sync logic.
- `/dashboard` and `/dashboard/[...rest]` (`frontend/src/app/dashboard/page.tsx`:1-15 and `frontend/src/app/dashboard/[...rest]/page.tsx`:1-18) redirect to `/chat`, so `DashboardClient.tsx` and its sidebar are no longer mounted anywhere routed.

This proves the **active runtime path** ends at `ChatContainer.tsx` under `app/dashboard/components/Chat`.

## 2. Candidate inventory table

| Candidate | Files | Message store | SSE hook | chat_id source | Parameter sync | Width controlled where |
|---|---|---|---|---|---|---|
| **Current V2 SSE flow** | `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx` + `ChatHistory` + `ChatInput` + `ParameterFormSidebar` + `v2ParameterPatch.ts` + `useChatSseV2.ts` | Local `useState<Message[]>` plus streaming text updates (`ChatContainer.tsx`:70-220, 320-420). | `useChatSseV2` hits `/api/chat` SSE proxy (`frontend/src/lib/useChatSseV2.ts`:1-120). | Route param override `chatId` prop → `useChatThreadId(preferred)` → sessionStorage thread per user (`frontend/src/lib/useChatThreadId.ts`:1-56). | `patchV2Parameters` + `fetchV2StateParameters` ensure `/api/v1/langgraph/parameters/patch` and `/api/v1/langgraph/state` are in sync with the drawer and `/param` commands (`ChatContainer.tsx`:140-260; `v2ParameterPatch.ts`:1-110; `ParameterFormSidebar.tsx`:80-220). | History/input wrappers capped at `max-w-[768px]` (`ChatHistory.tsx`:11-32; `ChatContainer.tsx`:470-640; `ChatInput.tsx`:70-160). |
| **Legacy dashboard backup** | `archive/legacy_phase2/frontend/src/app/dashboard/components/Chat/ChatContainer.tsx.backup` + `AdvancedInputBar.tsx` + `DashboardClient.tsx.backup` | Delegated to `useChat()` hook (state not within shown file; API assumed inside missing `@/lib/useChat`). | Unknown (presumably inside absent `useChat`). | Always `useChatThreadId()` from sessionStorage (`ChatContainer.tsx.backup`:20-32). | `useChat()` returns `parameters`, `showParameterForm`, `updateParameter`, `closeParameterForm` (but the underlying API definitions live elsewhere and no longer exist in `/lib`). | `max-w-[800px]` wrappers around prompt + sticky input (`ChatContainer.tsx.backup`:150-280) and `AdvancedInputBar.tsx`:10-50. |
| **Zero-byte saves** | `ChatContainer.tsx.save.1`, `.save.2`, `ChatHistory.tsx.save.1` | n/a (files are empty). | n/a | n/a | n/a | n/a |

## 3. Width root cause

- The current chat history/input stack uses `max-w-[768px]` wrappers everywhere:
  - History: `frontend/src/app/dashboard/components/Chat/ChatHistory.tsx`:11-28 wraps each message column in `className="w-full max-w-[768px] mx-auto px-4 py-4 ..."`.
  - Input: `ChatContainer.tsx`:470-640 wraps both the initial view and the sticky input in `div`s with `max-w-[768px]`.
  - ChatInput component enforces `style={{ maxWidth: '768px', ... }}` in its outer container/textarea (`ChatInput.tsx`:70-162).
  - Global chat layout CSS (`frontend/src/styles/chat-layout.css`:1-38) is a full-width shell but does not override the `max-w-*` wrappers from the fragments above.

- The “wider width” memory points to the backup/AdvancedInputBar pair:
  - Backup container uses `max-w-[800px]` and margin/padding around the initial prompt and sticky input (`ChatContainer.tsx.backup`:170-270).
  - `AdvancedInputBar.tsx`:11-43 wraps the textarea template with `className="w-full max-w-[800px] mx-auto"`.

Therefore, the only difference between the perceived “wider width” and today’s UI is the `max-w-[]` values within `ChatContainer`/input wrappers; no separate layout CSS or grid file is involved.

## 4. Param-sync proof

- `ChatContainer.tsx` imports `fetchV2StateParameters` and `patchV2Parameters` (`ChatContainer.tsx`:12-18). These functions interact with `/api/v1/langgraph/parameters/patch` and `/api/v1/langgraph/state` (`v2ParameterPatch.ts`:1-110).
- Patch pipeline:
  1. `onParamSubmit` calls `patchAllParameters(parameters)` after sanitizing the payload (`ChatContainer.tsx`:200-260).
  2. `patchAllParameters` sequentially waits for `patchV2Parameters` and then `runRefresh` so the client rehydrates to the backend state (`ChatContainer.tsx`:205-260).
  3. `schedulePatchOnChange` debounces when `NEXT_PUBLIC_AUTO_PATCH_PARAMS=1`.
  4. `/param` commands call `patchAllParameters(parsed)` inside `handleSend` before sending the chat message (`ChatContainer.tsx`:300-365).
- State hydration occurs:
  1. On every `chatId` change `refreshParameters()` is invoked (`ChatContainer.tsx`:170-190) and re-fetches `/api/v1/langgraph/state?thread_id=...`.
  2. After streaming stops the logic in `useEffect` calls `refreshParameters()` again (`ChatContainer.tsx`:248-260).
  3. The `ParameterFormSidebar` receives `parameters` prop from the same `useState` so inputs show the latest values (`ParameterFormSidebar.tsx`:30-220). The submit button labeled “Parameter übernehmen” triggers `onSubmit` (`ParameterFormSidebar.tsx`:118-220).
- `chat_id` used in both patch and hydration flows originates from the active route param or the sessionStorage-based identity from `useChatThreadId` (`ChatContainer.tsx`:34-60; `useChatThreadId.ts`:1-55). The same `chatId` is passed to `useChatSseV2` for SSE streaming (`ChatContainer.tsx`:55-90).

## 5. Legacy `useChat` / missing hook

- `ChatContainer.tsx.backup` imports `useChat` (`ChatContainer.tsx.backup`:10-35) and assumes it returns streaming state, parameters, and drawer helpers. However, no file `frontend/src/lib/useChat.ts` exists today (`ls frontend/src/lib` lists only the modern hooks, and `rg "@/lib/useChat" frontend/src` only hits the backup). A Git history scan (`git log --oneline frontend/src/lib | head`) shows V2 changes but the missing hook is gone.
- This proves the backup relies on a removed repository artifact; it cannot mount without reintroducing `useChat`.

## 6. Conclusion

- **Multiple implementations exist on disk**: the current V2 SSE path and a legacy backup referencing `useChat`, plus inert save files.
- **Only one runs today**: `/chat/[conversationId]` → `ChatScreen` → `ChatContainer.tsx`. Dashboard routes are redirect-only.
- **Width difference** is purely a `max-w-[768px]` vs `max-w-[800px]` value swap embedded in the container/input wrappers. The backup’s `AdvancedInputBar` (800px) is the artifact that originally gave the chat a wider feel.
- **Param sync exists solely in the current implementation** (`v2ParameterPatch` + auto-refresh + ParameterFormSidebar). The legacy module cannot be verified because its `useChat` hook was deleted.

## 7. Consolidation plan

1. **Canonicalize on `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`** (useChatSseV2 + v2ParameterPatch + drawer). Ensure all future work touches this file, not backups/save files.
2. **Archive/remove legacy artifacts**: delete `ChatContainer.tsx.backup`, `AdvancedInputBar.tsx` (if unused elsewhere), `DashboardClient.tsx.backup`, and zero-length `.save.*` files. Keep `ParameterFormModal` only if still mounted (otherwise remove it too).
3. **Normalize width**: adjust the `max-w-[768px]` wrappers to a single token (shared constant or CSS variable). If 800px is desired, change both history and input wrappers together, not a separate component.
4. **Ensure param-sync stays in sync with the active chat_id path**: document that `chatId` comes from `/chat/[conversationId]` first and falls back to `useChatThreadId`, then reuse the same hook/prop wherever the chat container is mounted (no duplicate sessionStorage work).
5. **Document and keep the helper script** `ops/print_chat_entrypoints.sh` (pure `rg` dumps, no active code) for future audits.

## 8. Evidence commands (trimmed outputs for traceability)

- Entrypoint graph: `rg -n --hidden --follow ... "ChatScreen|ChatContainer"` on `frontend/src/app` (see lines earlier).
- Width hints: `rg -n --hidden --follow "max-w-..." frontend/src/app/dashboard/components/Chat -S`.
- Param sync: `rg -n --hidden --follow "v2ParameterPatch|parameters/patch" frontend/src/app/dashboard/components/Chat -S`.
