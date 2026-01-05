#!/usr/bin/env bash
set -euo pipefail

# E2E smoke for Chat v2 SSE:
# Browser(ish) -> Next proxy `POST /api/chat` -> Backend `POST /api/v1/langgraph/chat/v2` -> SSE stream.
#
# Requirements:
# - Set `ACCESS_TOKEN` env var to a valid Keycloak JWT (Bearer token).
# - Ensure services are up: `docker compose up -d --build frontend backend`
#
# Logs (correlation via X-Request-Id / request_id):
# - Backend:  `docker compose logs backend --since 5m | rg \"langgraph_v2_chat_request|POST /api/v1/langgraph/chat/v2|request_id|chat_id\"`
# - Frontend: `docker compose logs frontend --since 5m | rg \"\\[api/chat\\]|/api/chat|X-Request-Id|text/event-stream\"`
#
# Expected SSE stream:
# - keepalive lines: `: keepalive`
# - events: `event: token` (data: {"text": ...}), optional `event: confirm_checkpoint`, then `event: done`

BASE_URL="${BASE_URL:-http://localhost:3000}"
CHAT_ID="${1:-}"
INPUT="${2:-}"

if [[ -z "${CHAT_ID}" ]]; then
  if command -v uuidgen >/dev/null 2>&1; then
    CHAT_ID="$(uuidgen)"
  else
    CHAT_ID="chat-$(date +%s)-$RANDOM"
  fi
fi

if [[ -z "${INPUT}" ]]; then
  INPUT="Smoke test: please reply with a short acknowledgement."
fi

if [[ -z "${ACCESS_TOKEN:-}" ]]; then
  echo "ERROR: ACCESS_TOKEN env var is required (Keycloak JWT)." >&2
  echo "Example:" >&2
  echo "  ACCESS_TOKEN='…' BASE_URL='http://localhost:3000' $0 '${CHAT_ID}' '${INPUT}'" >&2
  exit 2
fi

REQUEST_ID="$( (command -v uuidgen >/dev/null 2>&1 && uuidgen) || echo "req-$(date +%s)-$RANDOM" )"
CLIENT_MSG_ID="$( (command -v uuidgen >/dev/null 2>&1 && uuidgen) || echo "cmsg-$(date +%s)-$RANDOM" )"

json_escape() {
  python3 - <<'PY' "$1"
import json,sys
print(json.dumps(sys.argv[1]))
PY
}

INPUT_JSON="$(json_escape "${INPUT}")"
CHAT_ID_JSON="$(json_escape "${CHAT_ID}")"
CLIENT_MSG_ID_JSON="$(json_escape "${CLIENT_MSG_ID}")"

echo "== Smoke Chat v2 SSE =="
echo "BASE_URL      : ${BASE_URL}"
echo "CHAT_ID       : ${CHAT_ID}"
echo "REQUEST_ID    : ${REQUEST_ID}"
echo "CLIENT_MSG_ID : ${CLIENT_MSG_ID}"
echo
echo "---- Stream (Ctrl+C to stop) ----"

curl -N -sS -X POST "${BASE_URL}/api/chat" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "X-Request-Id: ${REQUEST_ID}" \
  --data-binary "{\"input\":${INPUT_JSON},\"chat_id\":${CHAT_ID_JSON},\"client_msg_id\":${CLIENT_MSG_ID_JSON}}"

