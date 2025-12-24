#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-${NGINX_BASE_URL:-http://localhost:3000}}"
BASE_URL="${BASE_URL%/}"

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required for this script." >&2
  exit 1
fi

if [[ -z "${BEARER_TOKEN:-}" ]]; then
  echo "ERROR: BEARER_TOKEN is required (do not include the 'Bearer ' prefix)." >&2
  exit 1
fi

CHAT_ID="${1:-${CHAT_ID:-}}"
if [[ -z "$CHAT_ID" ]]; then
  echo "ERROR: chat_id/thread_id required. Usage: $0 <chat_id>" >&2
  exit 1
fi

TOKEN="${BEARER_TOKEN}"
TOKEN="${TOKEN//$'\r'/}"
TOKEN="${TOKEN//$'\n'/}"
TOKEN="$(printf '%s' "$TOKEN" | xargs)"
TOKEN="${TOKEN#Bearer }"

PATCH_PAYLOAD=$(jq -cn \
  --arg chat_id "$CHAT_ID" \
  '{chat_id: $chat_id, parameters: {pressure_bar: 10, temperature_C: 80, medium: "Oel", dynamic_runout: 0.05, housing_diameter: 70}}')

patch_code=$(curl -sS -o /tmp/param_flow_patch.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/langgraph/parameters/patch" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-Request-Id: repro-param-flow" \
  -d "$PATCH_PAYLOAD" || true)

if [[ "$patch_code" != "200" ]]; then
  echo "FAIL: parameters/patch returned HTTP ${patch_code}" >&2
  cat /tmp/param_flow_patch.json >&2 || true
  exit 1
fi

state_json=$(curl -sS -f \
  -X GET "${BASE_URL}/api/v1/langgraph/state?thread_id=${CHAT_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-Request-Id: repro-param-flow")

echo "$state_json" | jq -c '{parameters: .parameters}'

if ! echo "$state_json" | jq -e '.parameters.pressure_bar == 10 and .parameters.temperature_C == 80 and .parameters.medium == "Oel" and .parameters.dynamic_runout == 0.05 and .parameters.housing_diameter == 70' >/dev/null; then
  echo "FAIL: state did not contain expected parameters" >&2
  echo "$state_json" | jq -c '{parameters: .parameters}' >&2 || true
  exit 1
fi

echo "OK: param flow verified for chat_id=${CHAT_ID}"
