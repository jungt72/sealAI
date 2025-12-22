# Wiring Review (SSE v2)

## Frontend SSE Parser (`frontend/src/lib/useChatSseV2.ts`)
- ✅ Parses `event: token`, `confirm_checkpoint`, `error`, `done` and stops on error/done.
- ⚠️ Recommendation: surface `request_id` from SSE `error` payload in UI to speed up support/debug.
- ⚠️ Recommendation: keep `lastError` even after `done` if a partial stream ended with error + done (current logic returns early on error and drops remaining frames).

## Next.js Proxy (`frontend/src/app/api/chat/route.ts`)
- ✅ Generates a request_id and forwards `Authorization` + `Accept: text/event-stream` to backend.
- ✅ Sets `Cache-Control`, `X-Accel-Buffering`, and keeps SSE response streaming to client.
- ⚠️ Recommendation: if a client already supplies `X-Request-Id`, consider propagating it instead of generating a new one (optional, for distributed tracing).

## NGINX (`nginx/default.conf`)
- ✅ `/api/chat` location has buffering disabled, long timeouts, and SSE-friendly headers.
- ⚠️ Potential pitfall: HTTP/2 is enabled globally; some clients/proxies have issues with SSE over H2. If intermittent, consider `http2 off;` for `/api/chat` or ensure upstream keeps H1.
- ⚠️ `/api/v1/langgraph/` proxy does not forward `Authorization` or `X-Request-Id`; add `proxy_set_header Authorization $http_authorization;` and `proxy_set_header X-Request-Id $http_x_request_id;` if direct backend SSE is used.

## Backend SSE Endpoint (`backend/app/api/v1/endpoints/langgraph_v2.py`)
- ✅ Sets `Content-Type: text/event-stream`, `Cache-Control`, `Connection: keep-alive`, `X-Accel-Buffering: no`.
- ✅ Now logs stream exceptions with request context and returns `request_id` in error payload.

## Auth (Keycloak)
- ✅ `get_current_request_user` supports configurable claim mapping (`AUTH_USER_ID_CLAIM`).
- ⚠️ Ensure access tokens are refreshed on the UI before expiry; otherwise `/api/chat` responds 401/expired (seen in repro).

## Checkpointer (Redis)
- ✅ Redis-backed checkpointer with memory fallback is configured.
- ⚠️ If Redis is down, memory fallback resets MAI-DxO loop state across requests; monitor `langgraph_v2_checkpointer_init_failed` warnings and ensure Redis URL is set.
