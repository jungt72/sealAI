# Phase 1.5 Smoke Tests

Run from repo root.

- Health endpoint
  - Command: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/langgraph/health`
  - Expected: `200`

- Chat v2 SSE (requires a valid Bearer token)
  - Command:
    ```bash
    curl -N -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -H "Accept: text/event-stream" \
      -d '{"input":"ping","chat_id":"smoke-chat"}' \
      http://localhost:3000/api/chat
    ```
  - Expected: HTTP 200 and SSE frames with `event: token` then `event: done`.

- Conversation list (frontend proxy to backend)
  - Command:
    ```bash
    curl -s -o /dev/null -w "%{http_code}\n" \
      -H "Authorization: Bearer $TOKEN" \
      http://localhost:3000/api/conversations
    ```
  - Expected: `200` for valid token, `401` if token is missing/expired.
