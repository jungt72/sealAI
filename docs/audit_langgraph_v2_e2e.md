# LangGraph V2 SSE End-to-End Audit

Scope: browser UI → Next.js `/api/chat` proxy → nginx → backend `/api/v1/langgraph/chat/v2` SSE → nginx → browser. Evidence is from local source and runtime inspection on this VPS.

## Architecture (Request/Response Path)

```
[Browser UI] (ChatInput)
  POST /api/chat (SSE)  Authorization: Bearer <token>
    -> Nginx (443, https, http2)
      -> Next.js route /api/chat (proxy)
        -> Backend /api/v1/langgraph/chat/v2 (FastAPI SSE)
          <- SSE events: token | confirm_checkpoint | error | done
        <- streamed response body
      <- streamed response body
    <- SSE stream to browser
```

## Source-of-Truth Trace (File/Line References)

A) Frontend input component (message capture)
- Chat input textarea captures user input and calls `onSend` on Enter/Send button: `frontend/src/app/dashboard/components/Chat/ChatInput.tsx:96`.
- Chat input is rendered by ChatContainer: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:499`.

B) Hook/service that sends request
- SSE hook targets `/api/chat` and sends `Authorization: Bearer <token>` with JSON body `{input, chat_id, client_msg_id}`: `frontend/src/lib/useChatSseV2.ts:30`, `frontend/src/lib/useChatSseV2.ts:71`.
- SSE frame parsing logic for `event: token|confirm_checkpoint|error|done`: `frontend/src/lib/useChatSseV2.ts:32`.

C) Next.js API route proxy code
- `/api/chat` validates JSON, requires `chat_id` and `Authorization`, forwards to backend v2 endpoint, and streams response body 1:1: `frontend/src/app/api/chat/route.ts:27`.
- Backend endpoint is `backendLangGraphChatEndpoint()` → `/api/v1/langgraph/chat/v2`: `frontend/src/lib/langgraphApi.ts:27`.

D) nginx config locations affecting SSE
- `/api/chat` (Next proxy) disables buffering, sets long timeouts, disables gzip: `nginx/default.conf:66`.
- `/api/v1/langgraph/` (backend SSE path) disables buffering, long timeouts, chunked transfer, X-Accel-Buffering: `nginx/default.conf:134`.

E) Backend FastAPI router handling v2 SSE
- V2 SSE endpoint: `@router.post("/chat/v2")` with `StreamingResponse(..., media_type="text/event-stream")`: `backend/app/api/v1/endpoints/langgraph_v2.py:386`.
- SSE producer (`_event_stream_v2`) emits `token`, `confirm_checkpoint`, `error`, `done` events and keepalive comments (`: keepalive`): `backend/app/api/v1/endpoints/langgraph_v2.py:150` and `backend/app/api/v1/endpoints/langgraph_v2.py:184`.

F) Middleware/auth that validates Keycloak bearer token
- HTTP dependency extracts Bearer token and verifies JWT via Keycloak JWKS: `backend/app/services/auth/dependencies.py:49`.
- JWT verification and audience/issuer checks: `backend/app/services/auth/token.py:59`.

G) Redis checkpoint wiring + thread_id/chat_id set/validated
- Checkpointer uses `langgraph.checkpoint.redis.AsyncRedisSaver` with `LANGGRAPH_V2_REDIS_URL` and falls back to memory: `backend/app/langgraph_v2/utils/checkpointer.py:37`.
- Graph builder attaches checkpointer in config: `backend/app/api/v1/endpoints/langgraph_v2.py:68`.
- Thread/user scoping uses `checkpoint_thread_id = f"{user_id}|{thread_id}"`: `backend/app/langgraph_v2/sealai_graph_v2.py:637`.
- `chat_id` is required in Next proxy: `frontend/src/app/api/chat/route.ts:50`.
- Client thread id is generated/stored per-user in sessionStorage: `frontend/src/lib/useChatThreadId.ts:17`.

## Runtime Verification (Commands + Evidence)

Container inventory (docker-compose):
```
$ docker-compose ps
NAME      IMAGE                                   STATUS
backend   ghcr.io/jungt72/sealai-backend:latest    Up (healthy)
frontend  sealai-frontend                          Up (healthy)
nginx     nginx:latest                             Up (healthy)
redis     redis/redis-stack-server:7.4.0-v6        Up (healthy)
```

nginx config (live container):
```
$ docker exec nginx nginx -T 2>/dev/null | rg -n "api/chat|api/v1/langgraph|proxy_buffering|proxy_request_buffering|gzip"
231:  location ^~ /api/chat {
243:    proxy_buffering off;
244:    proxy_request_buffering off;
246:    gzip off;
299:  location ^~ /api/v1/langgraph/ {
308:    proxy_buffering off;
309:    proxy_request_buffering off;
```

Backend route registration (live container):
```
$ docker exec backend python -c "from app.main import app; [print(','.join(sorted(getattr(r,'methods',[]) or [])), getattr(r,'path','')) for r in app.router.routes if 'langgraph' in getattr(r,'path','')]"
POST /api/v1/langgraph/chat/v2
POST /api/v1/langgraph/confirm/go
POST /api/v1/langgraph/parameters/patch
GET /api/v1/langgraph/health
GET /api/v1/langgraph/state
POST /api/v1/langgraph/state
```

Runtime log evidence (v2 endpoint hit):
```
$ docker exec backend curl -sS -D - -o /tmp/langgraph_v2_unauth.txt -X POST http://localhost:8000/api/v1/langgraph/chat/v2 \
    -H 'Content-Type: application/json' -H 'Authorization: Bearer invalid' \
    --data '{"input":"ping","chat_id":"audit-thread"}'
HTTP/1.1 401 Unauthorized
...

$ docker logs backend --since 5m | rg -n "/api/v1/langgraph/chat/v2"
10:INFO:     127.0.0.1:38474 - "POST /api/v1/langgraph/chat/v2 HTTP/1.1" 401 Unauthorized
```

nginx /api/chat proxy reachability (missing auth yields 401 from Next route):
```
$ docker exec backend curl -k -sS -D - -o /tmp/api_chat_unauth_https.txt \
    -X POST https://nginx/api/chat -H 'Host: sealai.net' -H 'Content-Type: application/json' \
    --data '{"input":"ping","chat_id":"audit-thread"}'
HTTP/2 401
content-type: application/json
```

SSE streaming verification requires a valid Keycloak bearer token. Use `ops/verify_langgraph_v2_sse.sh` with `BEARER_TOKEN` set (see “Verification Script” section).

## Evidence: V2-Only Usage

Frontend/Next explicitly targets v2 chat:
```
$ rg -n "langgraph/chat/v2|/api/chat" frontend backend -g "*.ts" -g "*.tsx" -g "*.py"
frontend/src/lib/useChatSseV2.ts:30:const ENDPOINT_URL = "/api/chat";
frontend/src/lib/langgraphApi.ts:28:  `${langgraphBackendBase()}/api/v1/langgraph/chat/v2`;
```

No frontend references to legacy v1 SSE routes; only test scripts mention old WS path:
```
$ rg -n "langgraph/chat/v1|/api/v1/chat/sse|/api/v1/ai" frontend backend -g "*.ts" -g "*.tsx" -g "*.py"
backend/app/ws_stream_test.py:9:WS_PATH   = os.getenv("WS_PATH", "/api/v1/ai/ws")
backend/ws_test.py:10:    "wss://sealai.net/api/v1/ai/ws?token=" + os.environ.get("TOKEN", "")
```

V2 router is the only LangGraph router mounted in the API:
- `backend/app/api/v1/api.py:27` (includes `langgraph_v2.router` only).

Runtime log shows `/api/v1/langgraph/chat/v2` being hit (see previous section); no v1 routes are registered for chat streaming.

## SSE Correctness Checklist

- Content-Type: text/event-stream
  - Backend sets `media_type="text/event-stream"`: `backend/app/api/v1/endpoints/langgraph_v2.py:412`.
  - Next proxy preserves Content-Type: `frontend/src/app/api/chat/route.ts:137`.
- Cache-Control: no-cache
  - Next proxy sets `Cache-Control: no-cache, no-transform`: `frontend/src/app/api/chat/route.ts:139`.
  - nginx adds `Cache-Control` for `/api/chat` and `/api/v1/langgraph/`: `nginx/default.conf:85`, `nginx/default.conf:146`.
- Connection: keep-alive
  - Next proxy sets `Connection: keep-alive`: `frontend/src/app/api/chat/route.ts:140`.
- No proxy buffering
  - nginx `proxy_buffering off` and `proxy_request_buffering off` for `/api/chat`: `nginx/default.conf:78`.
  - nginx `proxy_buffering off` and `proxy_request_buffering off` for `/api/v1/langgraph/`: `nginx/default.conf:143`.
  - Next proxy adds `X-Accel-Buffering: no`: `frontend/src/app/api/chat/route.ts:141`.
- Timeouts long enough
  - nginx `/api/chat` read/send timeouts 3600s: `nginx/default.conf:76`.
  - nginx `/api/v1/langgraph/` read/send timeouts 86400s: `nginx/default.conf:141`.
- Keepalive/heartbeat behavior
  - Backend emits `: keepalive` every ~15s on stream timeout: `backend/app/api/v1/endpoints/langgraph_v2.py:184`.

## Security Checklist

- Authorization header propagation (browser → Next → backend)
  - Browser includes Bearer token in `/api/chat` request: `frontend/src/lib/useChatSseV2.ts:92`.
  - Next proxy enforces `Authorization: Bearer ...`: `frontend/src/app/api/chat/route.ts:82` and forwards it to backend: `frontend/src/app/api/chat/route.ts:100`.
  - nginx forwards `Authorization` for `/api/v1/` backend routes: `nginx/default.conf:126`.
- No client-supplied `user_id` accepted by backend
  - V2 request model has only `input`, `chat_id`, `client_msg_id`, `metadata`: `backend/app/api/v1/endpoints/langgraph_v2.py:41`.
  - Auth dependency derives `user_id` from JWT claims: `backend/app/services/auth/dependencies.py:70`.
- Thread ownership tied to Keycloak subject/user id
  - `checkpoint_thread_id = f"{user_id}|{thread_id}"` isolates user threads: `backend/app/langgraph_v2/sealai_graph_v2.py:637`.
  - `thread_id` is provided by client but always combined with authenticated `user_id` before accessing checkpoints: `backend/app/langgraph_v2/sealai_graph_v2.py:626`.

## Known Failure Modes (Where to Look)

- SSE buffering in nginx or upstream
  - Check `/api/chat` and `/api/v1/langgraph/` blocks for `proxy_buffering` and `gzip` (`nginx/default.conf:66`).
- Missing/invalid Authorization token
  - Next route returns 401 if missing Bearer token: `frontend/src/app/api/chat/route.ts:82`.
  - Backend JWT verify failures logged from `backend/app/services/auth/token.py:100`.
- Event framing mismatch
  - Frontend expects `\n\n`-separated SSE frames: `frontend/src/lib/useChatSseV2.ts:123`.
- HTTP/2 interactions
  - nginx enables `http2 on` for `sealai.net` (`nginx/default.conf:31`); verify intermediaries don’t buffer.
- Timeouts
  - Backend keepalive emits comments every 15s; if proxy timeouts are too short, stream can close early (`nginx/default.conf:76`).
- Pydantic/body validation
  - Next route rejects missing `input` or `chat_id`: `frontend/src/app/api/chat/route.ts:67`.
  - Backend request model ignores extra fields: `backend/app/api/v1/endpoints/langgraph_v2.py:41`.

## Verification Script

Use the provided script to verify SSE behavior through nginx and directly against backend:
- Script path: `ops/verify_langgraph_v2_sse.sh`
- Required env var: `BEARER_TOKEN`
- Optional overrides: `NGINX_BASE_URL`, `BACKEND_BASE_URL`, `MAX_EVENTS`, `TIMEOUT_SECONDS`, `CURL_INSECURE=1`.

Example:
```
BEARER_TOKEN=... \
NGINX_BASE_URL=https://sealai.net \
BACKEND_BASE_URL=http://localhost:8000 \
ops/verify_langgraph_v2_sse.sh
```

## Minimal Fixes

No code/config changes required based on current evidence. Streaming settings and auth propagation are consistent end-to-end. If you want an automated regression check, wire `ops/verify_langgraph_v2_sse.sh` into your ops runbook.
