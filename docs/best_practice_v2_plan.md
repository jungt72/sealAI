# Plan: “Best Practice V2-only” Chat-Stack (SealAI)

Stand: 2025-12-16  
Scope: **Phase 1 = Audit/Plan (keine Codeänderungen außer dieser Doku)**, Phase 2 = Umsetzung in kleinen, sicheren Commits.

## Zieldefinition (“Best Practice”)

1) **V2-only Chat**: Einziger Chat-Endpunkt ist `POST /api/v1/langgraph/chat/v2` (SSE `text/event-stream`).  
2) **Frontend hat genau einen Sendepfad**: Browser → `POST /api/chat` (Next Route Handler Proxy) → Backend v2. Keine direkten Browser-Calls auf `/api/v1/...`.  
3) **Contract strikt** (Request):  
   - `{ input: string, chat_id: string, client_msg_id?: string, metadata?: object }`  
   - verboten: `thread_id/threadId`, `user_id/userId` (user_id kommt ausschließlich serverseitig aus JWT).  
4) **Threading**: URL = Thread. `chat_id` entspricht 1:1 der URL `/chat/[conversationId]`. Dashboard nutzt denselben `chat_id` (URL-Priorität > sessionStorage fallback).  
5) **SSE robust**: Proxy streamt 1:1 durch (kein Buffering), Keepalive/Heartbeat gegen Timeouts.  
6) **State API konsistent**: wenn `backend/app/api/v1/endpoints/state.py` existiert, muss Router in `api.py` included sein.  
7) **Observability**: request_id + chat_id + user in Logs (Proxy + Backend).

## Ist-Zustand (Audit)

### Backend (Source of Truth)

- v2 Chat SSE existiert: `backend/app/api/v1/endpoints/langgraph_v2.py` (`@router.post("/chat/v2")`, SSE via `StreamingResponse`).
- Erwartetes Schema aktuell: `LangGraphV2Request` enthält **`input`, `chat_id`, `user_id`** (letzteres wird serverseitig überschrieben).  
  → **Nicht Best Practice**, weil Request `user_id` enthält (auch wenn überschrieben).
- State Endpoints existieren: `backend/app/api/v1/endpoints/state.py`, **aber Router wird aktuell nicht included** (kein `include_router(state.router, ...)` in `backend/app/api/v1/api.py` gefunden).

### Frontend Sendepfade (mehr als einer)

Aktive/auffindbare Pfade:

- **Direkter Browser-Call**: `frontend/src/lib/useChatSseV2.ts` ruft `${window.location.origin}/api/v1/langgraph/chat/v2` direkt auf (verstößt gegen “einziger Sendepfad via Proxy”).
- **Proxy vorhanden**: `frontend/src/app/api/chat/route.ts` forwardet an Backend v2 und streamt durch, akzeptiert aber weiterhin Legacy-Felder (`thread_id/threadId`) und “default”-Fallbacks.
- **Legacy Hook**: `frontend/src/lib/useChat.ts` besitzt eigenen Streaming-Fetch und State-Update-Pfad (zusätzlicher Sendepfad + `thread_id` im State-Pfad).
- Weitere Legacy/Altpfade: `frontend/src/lib/useChatWs.ts` (WebSocket), diverse `thread_id`-Nutzung in State-/Parser-Code (z.B. `frontend/src/app/api/state/route.ts`).

### Threading

- `/chat/[conversationId]` existiert und übergibt `conversationId` an `ChatScreen`.  
- Dashboard verwendet standardmäßig `sessionStorage` Thread-ID via `useChatThreadId()` (URL-Priorität ist im Dashboard derzeit praktisch nicht gegeben, weil `/dashboard` keinen Thread param trägt).

## Soll-Zustand (Zielarchitektur)

**Browser**
- ruft ausschließlich `POST /api/chat` (SSE) auf, mit `{ input, chat_id, client_msg_id?, metadata? }` und `Authorization: Bearer <token>`.

**Next.js Proxy (`/api/chat`)**
- validiert strikt, verbietet Legacy-Keys, generiert `request_id`, streamt 1:1 weiter, setzt SSE-Header + `X-Accel-Buffering: no`.

**Backend v2**
- akzeptiert nur das Best-Practice-Request-Schema (kein `user_id` Feld).
- setzt `user_id` ausschließlich aus JWT.
- sendet SSE inkl. Keepalive (Kommentarframes) + konsistente Event-Typen.

## Phase 2: Implementierungsplan (Commit-Reihenfolge)

### COMMIT 1 — Frontend: v2-only Contract zentralisieren

Ziel: Kein zweiter Sendepfad neben `useChatSseV2` + Proxy.

- Entkoppeln/Entfernen: `frontend/src/lib/useChat.ts` Netzwerkpfad (entweder Datei entfernen, oder Fetch/Endpoints deaktivieren und nur noch interne Logik/Parser behalten, falls genutzt).
- `rg`-Ziel: im aktiven Sendepfad keine `thread_id/threadId` mehr.

Betroffene Dateien (voraussichtlich):
- `frontend/src/lib/useChat.ts`
- ggf. Imports, die `useChat` tatsächlich verwenden (Audit: `ChatContainer.tsx.backup` nutzt es, produktive `ChatContainer.tsx` nutzt `useChatSseV2`).

Risiko: versteckte Imports von `useChat.ts` (muss per `rg` geprüft und ggf. entfernt werden).

### COMMIT 2 — Next Proxy: `/api/chat` als einziger Network Target + Pass-Through

Ziel: Proxy als harte Contract-Grenze + SSE passthrough ohne Buffering.

- Datei: `frontend/src/app/api/chat/route.ts`
- Anforderungen:
  - `POST` only.
  - Request-Validierung: `input` non-empty string, `chat_id` non-empty string.
  - **Verbieten**: `thread_id`, `threadId`, `user_id`, `userId` → `400`.
  - Forward: `POST` an `.../api/v1/langgraph/chat/v2` mit `Authorization` 1:1, `Content-Type: application/json`, `Accept: text/event-stream`.
  - Response: `return new Response(backendResp.body, { status: backendResp.status, headers: passthroughSseHeaders })` (kein `.text()`/`.json()`).
  - Observability: `request_id = crypto.randomUUID()`; Log `request_id`, `chat_id`, `auth_present`, status. Optional: `X-Request-Id` Header zum Backend.

Status: umgesetzt (siehe `frontend/src/app/api/chat/route.ts`).

### COMMIT 3 — Frontend Hook: `useChatSseV2` ruft nur `/api/chat` auf

- Datei: `frontend/src/lib/useChatSseV2.ts`
- Änderung:
  - URL fix auf `"/api/chat"`, kein `${origin}/api/v1/...`.
  - Payload strikt: `{ input, chat_id, client_msg_id?, metadata? }`.
  - Auth: `Authorization: Bearer <token>` an `/api/chat`.

Status: umgesetzt (siehe `frontend/src/lib/useChatSseV2.ts`).

### COMMIT 4 — Threading: URL = `chat_id`

Ziel: `/chat/[conversationId]` ist stabiler Link und treibt `chat_id`.

- Sicherstellen:
  - `/chat/[conversationId]` → `ChatScreen(conversationId)` → `ChatContainer(chatId=conversationId)` → `useChatSseV2(chatId)`.
- Dashboard:
  - Wenn ein Thread in der URL verfügbar ist (z.B. `?chat_id=` oder eigener Segment-Route), dann Priorität.
  - Sonst: sessionStorage fallback einmalig (bestehend).

Status: umgesetzt (`frontend/src/app/dashboard/DashboardClient.tsx` liest `?chat_id=`, und `frontend/src/lib/useChatThreadId.ts` übernimmt optional einen preferred `chat_id`).

Betroffene Dateien:
- `frontend/src/app/chat/[conversationId]/page.tsx`
- `frontend/src/app/dashboard/ChatScreen.tsx`
- `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`
- optional Routing-Erweiterung für Dashboard Thread-URL (Design-Entscheidung).

### COMMIT 5 — Backend: State Router inkludieren + SSE Robustness

A) State Router:
- `backend/app/api/v1/api.py`: `include_router(state.router, prefix="/langgraph", tags=[...])` (oder passende Struktur).

B) SSE Robustness:
- `backend/app/api/v1/endpoints/langgraph_v2.py`:
  - Heartbeat: alle ~15s `yield b\": keepalive\\n\\n\"` (wenn keine Tokens anfallen).
  - Response Header (optional): `Cache-Control: no-cache`, `Connection: keep-alive`, ggf. `X-Accel-Buffering: no`.
  - Request Schema anpassen: `user_id` entfernen, optional `client_msg_id`, `metadata` hinzufügen.
  - Logging: request_id/chat_id/user.

Status: teilweise umgesetzt:
- Request Schema + Keepalive + Header + Logging: `backend/app/api/v1/endpoints/langgraph_v2.py`
- State Router Include: `backend/app/api/v1/api.py` + `backend/app/api/v1/endpoints/state.py`

### COMMIT 6 — Legacy endgültig entfernen/abschalten

- Frontend:
  - Entfernen ungenutzter WS/SSE Alternativen (`useChatWs.ts`, `useChat.ts`), sofern nicht mehr referenziert.
  - `rg` Assertions:
    - keine Browser-Calls auf `/api/v1/langgraph/chat/v2` (nur `/api/chat`).
    - keine `thread_id/threadId` im aktiven Chat-Request.
- Backend:
  - sicherstellen, dass keine alten Chat-Router registriert sind (nur `/api/v1/langgraph/chat/v2`).

## Risiken / Besonderheiten (vorab)

- **Nginx SSE Buffering**: muss pro Location deaktiviert sein, sonst “hängende” Streams. Minimum:
  - `proxy_buffering off;`
  - `proxy_cache off;`
  - `proxy_read_timeout 3600s;`
  - `gzip off;`
  - Optional: `add_header X-Accel-Buffering no;`
- **Auth Weitergabe**: `/api/chat` muss `Authorization` durchreichen; Backend erfordert Bearer (`backend/app/services/auth/dependencies.py`).
- **Idle Timeouts**: ohne Heartbeat kann ein Proxy idle SSE-Verbindungen trennen.
- **Tests/Contracts**: `backend/app/api/tests/test_langgraph_v2_endpoint.py` referenziert noch `thread_id` in `LangGraphV2Request` (muss in Phase 2 angepasst werden, sobald Backend-Schema “best practice” wird).
