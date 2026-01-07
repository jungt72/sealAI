# ARCHITECTURE_ROUTES_MAP

## Website (Landing)

**Canonical entrypoint**
- Route: `/`
- File: `frontend/src/app/page.tsx`
- Layout: `frontend/src/app/layout.tsx`
- Primary UI: `frontend/src/components/ui/*`
- Data: `frontend/src/lib/strapi.ts` (fallback: `frontend/src/lib/mockData.ts`)

## Dashboard + Chat (Canonical)

**Canonical shell**
- Route: `/dashboard`
- Files: `frontend/src/app/dashboard/*`
- Chat UI canonical: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`

**Chat alias**
- Routes: `/chat`, `/chat/[conversationId]`
- Behavior: redirect to `/dashboard` (and `/dashboard?chat_id=...`)
- Layout: `frontend/src/app/chat/layout.tsx` is intentionally an empty wrapper to avoid a second UI source.

## APIs (high level)

**Active**
- `/api/chat` → `frontend/src/app/api/chat/route.ts` (SSE)
- `/api/conversations` → `frontend/src/app/api/conversations/route.ts`
- `/api/langgraph/state` → `frontend/src/app/api/langgraph/state/route.ts`
- `/api/langgraph/parameters/patch` → `frontend/src/app/api/langgraph/parameters/patch/route.ts`
- `/api/langgraph/confirm/go` → `frontend/src/app/api/langgraph/confirm/go/route.ts`
- `/api/rag/*` → `frontend/src/app/api/rag/*`
- `/api/auth/*` (access-token, sso-logout) → `frontend/src/app/api/auth/*`

**Legacy**
- `frontend/src/pages/api/auth/[...nextauth].ts` (NextAuth entry)
- `frontend/src/pages/api/langgraph/chat/stream.ts` (legacy SSE proxy; verify unused before removing)

## Minimal patch plan

1) Patch 1 (done): `/dashboard` is canonical; `/chat` layout is empty wrapper.
2) Patch 2: Deprecate/remove unused SSE proxies (`app/api/langgraph/chat/*`, `pages/api/langgraph/chat/stream.ts`, `/api/ai/chat/stream`) once confirmed unused.
3) Patch 3: Canonicalize UI primitives (remove duplicate Card implementations; keep one source + re-exports if needed).
