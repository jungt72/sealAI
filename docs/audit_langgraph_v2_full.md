# Audit: LangGraph v2 (SealAI) — Architektur, Verkabelung, Contracts, Auth, State, Streaming, Persistence

Stand: 2025-12-18  
Scope: LangGraph v2 Endpoints + Frontend-Proxy-Routen + Nginx Reverse Proxy + Auth (Keycloak/JWT) + State/Checkpointer (Redis) + RAG (Qdrant)

## Executive Summary (Findings)

1) **Akuter Bug (500) `/api/v1/langgraph/parameters/patch`**  
   Root Cause: Backend ruft `graph.aupdate_state(..., as_node="parameter_patch_ui")` auf, aber der Node existiert im kompilierten Graph nicht → `langgraph.errors.InvalidUpdateError` → 500.

2) **Auth-/Contract-Inkonsistenz bei Conversations**  
   `/api/v1/chat/conversations` erwartet in `chat_history.py` ein User-Objekt mit `.sub`, aber `get_current_request_user` liefert aktuell `str` (`preferred_username`). Ergebnis: 401 trotz verifiziertem JWT.

3) **Checkpointer Namespace ist leer**  
   `CHECKPOINTER_NAMESPACE_V2 = ""` → potentielles Collision-Risiko, wenn mehrere Graphen/Namespaces im gleichen Redis landen.

4) **Observability Lücken**  
   `langgraph/chat/v2` loggt `X-Request-Id`, `parameters/patch` aktuell nicht; Fehlerfälle werden als 500 gemappt, aber ohne serverseitigen Traceback-Log (weil Exception zu `HTTPException` gerappt wird).

---

## Komponenten & Topologie

- **Browser**: nutzt Next.js UI (SSE Chat v2 + Parameter-Sidebar + Conversations Sidebar).
- **Nginx**: Reverse Proxy für `/{frontend}` und `/api/v1/*` → Backend, inkl. SSE-Tuning (`proxy_buffering off` etc.).
- **Frontend**: Next.js (Route Handler `/api/chat`, `/api/conversations`).
- **Backend**: FastAPI `/api/v1/langgraph/*` und `/api/v1/chat/*`.
- **Keycloak**: JWT Issuer + JWKS.
- **Redis**: LangGraph Checkpointer (AsyncRedisSaver), optional weitere Stores.
- **Qdrant**: RAG Retrieval.
- **Postgres**: nicht zentral für LangGraph v2 State, aber Teil des Stacks.

---

## Phase 1 — End-to-End Verkabelungskarte

### A) Chat v2 SSE Flow

**Browser → Frontend (Next.js) → Backend (FastAPI SSE)**

1. Browser sendet `POST /api/chat` (Next.js Route Handler) mit:
   - JSON: `{ input, chat_id, client_msg_id? }`
   - Header: `Authorization: Bearer <token>`
2. `frontend/src/app/api/chat/route.ts` validiert Payload/Keys + Authorization-Header und proxyt zu:
   - Backend: `POST /api/v1/langgraph/chat/v2`
   - Headers: `Accept: text/event-stream`, `Authorization`, `X-Request-Id`
3. Backend streamt SSE Events:
   - `event: confirm_checkpoint` (optional)
   - `event: token` (chunked)
   - `event: done`
4. Nginx ist für `/api/v1/langgraph/` auf „no buffering“ konfiguriert (SSE).

Relevante Dateien:
- Frontend: `frontend/src/app/api/chat/route.ts`
- Frontend SSE Client: `frontend/src/lib/useChatSseV2.ts`
- Backend Endpoint: `backend/app/api/v1/endpoints/langgraph_v2.py` (`langgraph_chat_v2_endpoint`)
- Nginx: `nginx/default.conf` (Location `/api/v1/langgraph/`)

### B) Conversations Flow

**Browser → Frontend (Next.js) → Backend**

1. Browser ruft `GET /api/conversations` (Next.js) auf.
2. `frontend/src/app/api/conversations/route.ts` liest NextAuth Session serverseitig und extrahiert ein Access Token.
3. Next.js proxyt zu Backend:
   - `GET /api/v1/chat/conversations`
   - Header: `Authorization: Bearer <accessToken>`

Relevante Dateien:
- Frontend Route: `frontend/src/app/api/conversations/route.ts`
- Frontend Callsite: `frontend/src/components/ConversationSidebar.tsx`
- Backend Endpoint: `backend/app/api/v1/endpoints/chat_history.py`

### C) Parameters Patch Flow (aktuell 500)

**Browser → Nginx → Backend (LangGraph State Update)**

1. Browser ruft direkt `POST /api/v1/langgraph/parameters/patch` auf (kein Next.js Proxy).
2. `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx` sendet:
   - Header: `Authorization: Bearer ${token}`
   - Body: `{ chat_id, parameters }`
3. Nginx routet `/api/v1/langgraph/` direkt auf Backend `/api/v1/langgraph/`.
4. Backend Endpoint `patch_parameters`:
   - validiert/whitelistet Keys via `sanitize_v2_parameter_patch`
   - liest State via `graph.aget_state(config)`
   - merged Patch via `merge_parameters`
   - schreibt via `graph.aupdate_state(..., as_node=...)`

Relevante Dateien:
- Frontend Callsite: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx`
- Frontend Helper: `frontend/src/lib/v2ParameterPatch.ts`
- Backend Endpoint: `backend/app/api/v1/endpoints/langgraph_v2.py` (`patch_parameters`)
- Backend Patch Utils: `backend/app/langgraph_v2/utils/parameter_patch.py`

---

## Phase 1.3 — OpenAPI / Runtime Contract (relevante Pfade)

Backend OpenAPI enthält:
- `/api/v1/langgraph/chat/v2` `POST`
- `/api/v1/langgraph/confirm/go` `POST`
- `/api/v1/langgraph/parameters/patch` `POST`
- `/api/v1/langgraph/state` `GET|POST`
- `/api/v1/langgraph/health` `GET`
- `/api/v1/chat/conversations` `GET`
- `/api/v1/chat/conversations/{conversation_id}` `PATCH|DELETE`

---

## Auth & Contracts (Keycloak)

### Backend Erwartung

- HTTP: `Authorization: Bearer <JWT>` wird durch `get_current_request_user` geprüft:
  - Verifikation via JWKS (`KEYCLOAK_JWKS_URL`) und `issuer` (`KEYCLOAK_ISSUER`)
  - `aud`/`azp` Whitelist: `{"nextauth", "sealai-backend-api"}`
  - Rückgabewert ist aktuell `preferred_username` als `str`

Relevante Datei:
- `backend/app/services/auth/dependencies.py`
- `backend/app/services/auth/token.py`

### Frontend Nutzung

- **Chat SSE (`/api/chat`)**: Browser muss `Authorization: Bearer` direkt mitsenden (Next.js Route verlangt das).
- **Conversations (`/api/conversations`)**: Cookie-basierte NextAuth Session wird serverseitig gelesen, Token wird extrahiert und als Bearer ans Backend weitergereicht.
- **Parameters Patch (`/api/v1/langgraph/parameters/patch`)**: Browser sendet Bearer direkt ans Backend (über Nginx).

---

## State Model & Patch Semantik

### State (Pydantic)

- `SealAIState` (`backend/app/langgraph_v2/state/sealai_state.py`)
  - `thread_id`, `user_id`, `messages`, `parameters: TechnicalParameters`, `phase`, `last_node`, …
- `TechnicalParameters` ist **`extra="allow"`** (zukunftssicher)
- `SealParameterUpdate` ist **`extra="forbid"`** (strict) — wird vom `/state` POST genutzt

### Parameter Patch (`/parameters/patch`)

- Whitelist/Validation: `backend/app/langgraph_v2/utils/parameter_patch.py`
  - erlaubte Keys sind aktuell ein bewusst kleiner Satz (`ALLOWED_V2_PARAMETER_KEYS`)
  - nur primitive Werte (str/int/float/bool) erlaubt
- Merge: `merge_parameters(existing, patch)` (dict oder pydantic model_dump)
- Update: `graph.aupdate_state(config, {"parameters": merged}, as_node=...)`

---

## Persistence / Checkpointer / Redis

- Graph nutzt LangGraph Checkpointer via `make_v2_checkpointer_async` (`backend/app/langgraph_v2/utils/checkpointer.py`)
  - Backend: `CHECKPOINTER_BACKEND=redis` (default)
  - URL: `LANGGRAPH_V2_REDIS_URL` oder `REDIS_URL`
  - Fallback: `MemorySaver` wenn Redis nicht verfügbar
- Thread-Isolation: `build_v2_config` nutzt `checkpoint_thread_id = f"{user_id}|{thread_id}"` (`backend/app/langgraph_v2/sealai_graph_v2.py`)
  - Achtung: `user_id` ist aktuell `preferred_username`, nicht `sub`
- Namespace: `CHECKPOINTER_NAMESPACE_V2 = ""` (`backend/app/langgraph_v2/constants.py`)

Risiken / Fragen:
- TTL/Cleanup: keine explizite TTL sichtbar (hängt vom Checkpointer-Backend ab).
- Namespace leer: kann Keys kollidieren lassen, falls andere Graphen/Namespaces im gleichen Redis laufen.

---

## SSE / Streaming Contract

- Backend SSE (`/api/v1/langgraph/chat/v2`) streamt `text/event-stream`:
  - Keepalive: `: keepalive\n\n` alle ~15s
  - Events: `token`, `confirm_checkpoint`, `done`, `error`
- Frontend SSE Client (`frontend/src/lib/useChatSseV2.ts`) erwartet:
  - `event: token` → `data.text`
  - `event: confirm_checkpoint` → Objekt (wird als UI Checkpoint gerendert)
  - `event: done` beendet Streaming
- Nginx SSE Tuning: `proxy_buffering off`, `proxy_request_buffering off`, `X-Accel-Buffering: no`

---

## Phase 2 — Root Cause: 500 bei `/api/v1/langgraph/parameters/patch`

### Repro (ohne Browser-Token; direkt im Backend-Container)

Folgender Minimal-Flow reproduziert den Crash:
- `graph.aupdate_state(..., as_node="parameter_patch_ui")` wirft:
  - `langgraph.errors.InvalidUpdateError: Node parameter_patch_ui does not exist`

### Klassifikation

- **Graph wiring / node missing** (keine Auth-/Schema-Frage, kein Redis/Qdrant Problem im Ursprung).

---

## Phase 4 — Fix (minimal-invasiv)

### Änderung

- In `patch_parameters` wird `as_node` auf einen stabil vorhandenen Node gesetzt:
  - `as_node="supervisor_logic_node"`

Damit ist `aupdate_state` wieder gültig, ohne den Graph selbst zu ändern oder zusätzliche Nodes einzuführen.

### Härtung (Contract Guard)

- Stable Node Contract + Guard: `backend/app/langgraph_v2/contracts.py`
- Diagnose/Runbook: `docs/runbook_langgraph_v2.md`

### Tests (Regression)

Neu: `backend/tests/test_langgraph_parameters_patch.py`
- `test_patch_unauthorized_returns_401` (401)
- `test_patch_missing_chat_id_returns_400` (400)
- `test_patch_rejects_unknown_as_node_returns_400` (400; Contract Guard)
- `test_patch_rejects_unknown_keys_returns_400` (400)
- `test_patch_works_with_stable_node_returns_200` (200)
- `test_langgraph_v2_node_contract_contains_stable_nodes` (contractual node list)

---

## Zusätzliche Findings (nicht Teil des akuten Fixes)

1) **`/api/v1/chat/conversations` ist effektiv kaputt**  
   `backend/app/api/v1/endpoints/chat_history.py` erwartet `current_user.sub`, aber `get_current_request_user` liefert `str`.  
   → Folge: 401 trotz `JWT verified` in Logs.

2) **User-Identity für State-Isolation**  
   Kommentar in `state.py` sagt „Keycloak sub“, verwendet wird aber `preferred_username`.  
   Empfehlung: `sub` (oder stabile UUID) als `user_id` verwenden, um Kollisionen zu vermeiden.

3) **Observability**  
   Empfehlung: `parameters/patch` sollte `request_id` loggen (falls vorhanden) und Exceptions serverseitig mit Traceback loggen (ohne Tokens/Secrets).

4) **Frontend-Form vs Backend-Allowlist (Contract Drift)**  
   `ParameterFormSidebar` kann Felder wie `pressure_min`, `temp_min`, `speed_linear` etc. setzen, aber `sanitize_v2_parameter_patch` erlaubt aktuell nur eine kleine Key-Whitelist.  
   → Erwartetes Verhalten klären: entweder Allowlist erweitern (auf definierte `SealParameters`/`TechnicalParameters` Keys) oder UI auf erlaubte Keys begrenzen/normalisieren.

---

## Runbook — Verifikation / Smoke Checks

### Container Status

```bash
docker compose ps
docker ps
```

### Health

```bash
docker exec nginx curl -sS -i https://localhost/api/v1/langgraph/health -k
```

### Parameters Patch (mit Token; Token nicht loggen/persistieren)

```bash
docker exec nginx sh -lc 'curl -sS -i http://backend:8000/api/v1/langgraph/parameters/patch \\
  -X POST \\
  -H \"Content-Type: application/json\" \\
  -H \"Authorization: Bearer <TOKEN>\" \\
  -d \"{\\\"chat_id\\\":\\\"default\\\",\\\"parameters\\\":{\\\"medium\\\":\\\"oil\\\"}}\"'
```

### Backend Unit Tests

```bash
cd backend
pytest -q tests/test_langgraph_parameters_patch.py
```

Hinweis: Im laufenden `ghcr.io/jungt72/sealai-backend:latest` Container ist `pytest` aktuell nicht installiert.  
Für Smoke-Verifikation ohne `pytest` (im Backend-Container):

```bash
docker exec backend sh -lc 'python - <<\"PY\"\nimport asyncio\nfrom langgraph._internal._constants import CONFIG_KEY_CHECKPOINTER\nfrom app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2, build_v2_config\n\nasync def main():\n    graph = await get_sealai_graph_v2()\n    cfg = build_v2_config(thread_id=\"default\", user_id=\"debuguser\")\n    cfg.setdefault(\"configurable\", {})[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer\n    await graph.aupdate_state(cfg, {\"parameters\": {\"medium\": \"oil\"}}, as_node=\"supervisor_logic_node\")\n    snap = await graph.aget_state(cfg)\n    print((snap.values or {}).get(\"parameters\"))\n\nasyncio.run(main())\nPY'\n```
