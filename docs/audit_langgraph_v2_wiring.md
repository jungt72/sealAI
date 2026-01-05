# Audit: LangGraph v2 Wiring (SealAI)

Stand: 2025-12-16

Ziel dieses Audits: eindeutig feststellen, **welche Frontend-Route/Komponenten** das Dashboard-Chat-Eingabefeld rendern und **welchen Backend-Endpunkt** es für Send/Streaming nutzt; außerdem **“alt” vs “soll”** dokumentieren und eine “single source of truth”-Entscheidung treffen.

## Backend: LangGraph v2 → Router → Endpoint(s)

### FastAPI Mounting

- App mounted die v1-API unter `/api/v1` via `backend/app/main.py` (siehe `backend/app/main.py`).
- Unterhalb `/api/v1` wird das LangGraph v2 Router-Paket unter `/langgraph` registriert: `backend/app/api/v1/api.py:28`.

Damit liegen die v2 Endpunkte effektiv unter:

- `POST /api/v1/langgraph/chat/v2`
- `POST /api/v1/langgraph/confirm/go`
- `POST /api/v1/langgraph/parameters/patch`

### v2 Chat “Source of Truth”

**Endpoint:** `POST /api/v1/langgraph/chat/v2`  
**Implementierung:** `backend/app/api/v1/endpoints/langgraph_v2.py:106`  

**Request Schema:** `LangGraphV2Request` (`backend/app/api/v1/endpoints/langgraph_v2.py:28`)

```json
{
  "input": "string",
  "chat_id": "string",
  "user_id": "string (wird serverseitig überschrieben)"
}
```

**Threading / ConversationId:**  
- Thread-ID im Backend ist `chat_id` (wird als `thread_id` in `build_v2_config(...)` genutzt): `backend/app/api/v1/endpoints/langgraph_v2.py:60-66`.
- Der `user_id` wird stabilisiert über Auth-Identity: `request.user_id = username` (`backend/app/api/v1/endpoints/langgraph_v2.py:111-113`).

**Response (Streaming):** `text/event-stream` (`backend/app/api/v1/endpoints/langgraph_v2.py:113`)  
**SSE Events (aktuell):**
- `event: confirm_checkpoint` + JSON payload (`backend/app/api/v1/endpoints/langgraph_v2.py:89-91`)
- `event: token` + `{ "type": "token", "text": "..." }` (`backend/app/api/v1/endpoints/langgraph_v2.py:92-96`)
- `event: done` + `{ "type": "done" }` (`backend/app/api/v1/endpoints/langgraph_v2.py:97`)
- `event: error` + `{ "type": "error", "message": "..." }` (`backend/app/api/v1/endpoints/langgraph_v2.py:101-103`)

### Auth (Keycloak / JWT)

**HTTP Bearer Pflicht:** `backend/app/services/auth/dependencies.py:21-36`

- Erwartet `Authorization: Bearer <JWT>` (sonst 401).
- Verifiziert JWT gegen Keycloak JWKS (siehe `backend/app/services/auth/token.py`).
- Liefert `preferred_username` als Auth-Identity (der Wert wird als `user_id` im v2 Chat verwendet): `backend/app/services/auth/dependencies.py:34-36`.

### State / Parameter Updates (v2)

Es existiert ein v2 State Endpoint (`backend/app/api/v1/endpoints/state.py`), aber **er ist aktuell nicht in `backend/app/api/v1/api.py` included** (kein `include_router(state.router, ...)` gefunden). Dadurch ist `/api/v1/langgraph/state` ggf. nicht erreichbar, obwohl Frontend-Code dafür existiert.

### Storage: Redis / Qdrant (High-Level)

- Redis wird als LangGraph v2 Checkpointer über `AsyncRedisSaver` genutzt (`backend/app/langgraph_v2/utils/checkpointer.py`).
- Qdrant/RAG wird in `backend/app/services/rag/*` orchestriert (z.B. `rag_orchestrator.py`), und kann im v2 Graph von Nodes/Tools verwendet werden.

## Frontend: Dashboard Renderpfad → Input → API Call

### Dashboard Route & Komponenten

Renderpfad (Dashboard):

1. Route: `/dashboard`
2. Page: `frontend/src/app/dashboard/page.tsx` → rendert `DashboardClient` (`frontend/src/app/dashboard/page.tsx:5-9`)
3. Auth Gate: `frontend/src/app/dashboard/DashboardClient.tsx` (NextAuth `useSession`, `signIn("keycloak")`) (`frontend/src/app/dashboard/DashboardClient.tsx:3-23`)
4. Chat UI: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx` (`frontend/src/app/dashboard/DashboardClient.tsx:5,21-23`)
5. Input: `ChatInput` innerhalb `ChatContainer` (`frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:8,218-234`)

### Konkreter API Call (Dashboard)

Das Dashboard nutzt **SSE via Fetch-Streaming** über den Hook `useChatSseV2`.

- Hook: `frontend/src/lib/useChatSseV2.ts`
- Endpoint URL: `${window.location.origin}/api/v1/langgraph/chat/v2` (`frontend/src/lib/useChatSseV2.ts:30-34`)
- Payload: `{ input, chat_id }` (`frontend/src/lib/useChatSseV2.ts:91-101`)
- Auth Header: `Authorization: Bearer <token>` aus NextAuth Session (`frontend/src/lib/useChatSseV2.ts:94-98`, Token via `frontend/src/lib/useAccessToken.ts`)

Threading im Dashboard:

- `chatId` kommt aus `useChatThreadId()` und wird pro-authenticated Session in `sessionStorage` persistiert (`frontend/src/lib/useChatThreadId.ts:6-58`).

Zusatz-Endpunkte aus dem Dashboard-Chat:

- Confirm GO ruft direkt `POST /api/v1/langgraph/confirm/go` (`frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:166-191`).

### /chat Route (Template-Nutzung)

Es existiert eine Chat-Route mit Konversations-ID:

- `frontend/src/app/chat/page.tsx` erstellt eine neue UUID und routed nach `/chat/<id>` (`frontend/src/app/chat/page.tsx:9-17`)
- `frontend/src/app/chat/[conversationId]/page.tsx` rendert `ChatScreen` mit Prop `conversationId` (`frontend/src/app/chat/[conversationId]/page.tsx:10-17`)

Aktueller Status: `ChatScreen` ignoriert `conversationId` und rendert nur `ChatContainer` (`frontend/src/app/dashboard/ChatScreen.tsx`). Damit ist die URL-ConversationId aktuell **nicht** die tatsächliche Thread-ID für Streaming/Checkpointer; im Chat läuft stattdessen die `sessionStorage`-ThreadId Logik.

## “alt” vs “soll” (Endpoint/Template)

| Bereich | “alt / veraltet” | “soll / v2 korrekt” |
|---|---|---|
| Backend Chat Endpoint | Legacy-WS/andere Routen existieren teilweise im Repo (z.B. `backend/app/api/routes/chat.py`), aber v2 “source of truth” ist `/api/v1/langgraph/chat/v2`. | `POST /api/v1/langgraph/chat/v2` (`backend/app/api/v1/endpoints/langgraph_v2.py:106-113`) |
| Frontend Hook (Legacy) | `frontend/src/lib/useChat.ts` sendet `payload.thread_id = effectiveThreadId` an `backendLangGraphChatEndpoint()` (`frontend/src/lib/useChat.ts:450-483` und `frontend/src/lib/useChat.ts:960-992`). **Backend erwartet `chat_id`, nicht `thread_id`** → falsches Contract. | `frontend/src/lib/useChatSseV2.ts` sendet `{ input, chat_id }` (`frontend/src/lib/useChatSseV2.ts:91-101`). |
| Next.js Proxy Route (Legacy) | `frontend/src/app/api/chat/route.ts` forwardet `thread_id/user_id` an Backend v2 (`frontend/src/app/api/chat/route.ts:8-55`). **Backend erwartet `chat_id`**; `user_id` wird serverseitig aus JWT gesetzt. | Proxy (wenn genutzt) muss `thread_id → chat_id` mappen und Auth-Header weiterreichen. |
| Dashboard Template | Aktuell verwendetes Dashboard rendert `ChatContainer` (`frontend/src/app/dashboard/DashboardClient.tsx:5,21-23`) und nutzt `useChatSseV2` (korrektes Contract). | Beibehalten oder auf einen einzigen “source of truth” Hook/Proxy vereinheitlichen (Entscheidung in Phase 2). |
| Conversation Threading | `/chat/[conversationId]` existiert, aber `conversationId` wird nicht in den Chat-Thread überführt (`frontend/src/app/chat/[conversationId]/page.tsx` + `frontend/src/app/dashboard/ChatScreen.tsx`). | `conversationId` sollte als `chat_id`/ThreadId verwendet werden (URL = Thread), damit History/Links stabil sind. |

## Entscheidung: Single Source of Truth (Chat v2)

**Source of Truth für Chat v2 ist der Backend-Endpunkt**: `POST /api/v1/langgraph/chat/v2`  
Contract: `{ input, chat_id }` + `Authorization: Bearer <JWT>`; `user_id` kommt **immer** aus dem JWT (Keycloak) und wird im Backend erzwungen (`backend/app/api/v1/endpoints/langgraph_v2.py:111-113`).

Phase-2 Leitplanke:

- Alle Frontend-Templates/Hooks/Proxy-Routen müssen auf dieses Contract normiert werden (`thread_id` → `chat_id`).
- Optional (Best Practice): Frontend nutzt einen Next.js Route Handler Proxy (z.B. `/api/chat`) als Stabilitäts-/CORS-/Routing-Schicht, der nur `Authorization` durchreicht und Payload normalisiert.

## Fix umgesetzt (Phase 2)

Änderungen, um “thread_id → chat_id” konsistent auf Chat v2 zu normieren und die `/chat/[conversationId]` Route korrekt zu verdrahten:

- **Single Sender (Chat)**: `frontend/src/lib/useChatSseV2.ts` sendet nur noch an `POST /api/chat` (Next.js Proxy) und nicht mehr direkt an `/api/v1/...`.
- **Proxy hard fail + passthrough**: `frontend/src/app/api/chat/route.ts` validiert strikt `{ input, chat_id, client_msg_id?, metadata? }`, verlangt `Authorization: Bearer ...`, streamt SSE 1:1 durch und setzt `X-Accel-Buffering: no`.
- **URL = chat_id**: `/chat/[conversationId]` wird 1:1 als `chat_id` verwendet (Propagation über `frontend/src/app/dashboard/ChatScreen.tsx` → `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`).
- **Dashboard URL Override**: `frontend/src/app/dashboard/DashboardClient.tsx` akzeptiert optional `?chat_id=...` und nutzt dann diesen Thread; sonst sessionStorage fallback.
- **Backend Contract**: `backend/app/api/v1/endpoints/langgraph_v2.py` akzeptiert keinen client-provided `user_id` mehr; `user` kommt ausschließlich aus JWT. Zusätzlich: Keepalive `: keepalive\n\n` während der Graph läuft.
- **State API verfügbar**: `backend/app/api/v1/endpoints/state.py` ist versioniert und in `backend/app/api/v1/api.py` unter `/api/v1/langgraph/state` inkludiert.
