#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${NGINX_BASE_URL:-https://sealai.net}"
BASE_URL="${BASE_URL%/}"
CHAT_ID="${CHAT_ID:-param-sync-$(date +%s)}"

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required for this script." >&2
  exit 1
fi

AUTH_TOKEN="${AUTH_TOKEN:-}"
AUTH_COOKIE="${AUTH_COOKIE:-}"

trim_token() {
  local value="$1"
  value="${value//$'\r'/}"
  value="${value//$'\n'/}"
  value="$(printf '%s' "$value" | xargs)"
  if [[ "$value" == Bearer\ * ]]; then
    value="${value#Bearer }"
  fi
  printf '%s' "$value"
}

trim_cookie() {
  local value="$1"
  value="${value//$'\r'/}"
  value="${value//$'\n'/}"
  printf '%s' "$value"
}

AUTH_TOKEN="$(trim_token "$AUTH_TOKEN")"
AUTH_COOKIE="$(trim_cookie "$AUTH_COOKIE")"

if [[ -z "$AUTH_TOKEN" && -n "${AUTH_COOKIE:-}" ]]; then
  session_json=$(curl -sS -f -H "Cookie: ${AUTH_COOKIE}" "${BASE_URL}/api/auth/session" || true)
  if [[ -n "$session_json" ]]; then
    AUTH_TOKEN=$(echo "$session_json" | jq -r '.accessToken // .access_token // .token // empty')
  fi
  AUTH_TOKEN="$(trim_token "$AUTH_TOKEN")"
fi

if [[ -z "$AUTH_TOKEN" ]]; then
  echo "ERROR: AUTH_TOKEN is required (or set AUTH_COOKIE to resolve it)." >&2
  exit 1
fi

PATCH_PAYLOAD='{"chat_id":"'"$CHAT_ID"'","parameters":{"medium":"oil","pressure_bar":2,"temperature_C":80}}'

patch_code=$(curl -sS -o /tmp/param_patch.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/langgraph/parameters/patch" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -H "X-Request-Id: smoke-param-sync" \
  -d "$PATCH_PAYLOAD" || true)

if [[ "$patch_code" != "200" ]]; then
  echo "FAIL: parameters/patch returned HTTP ${patch_code}" >&2
  cat /tmp/param_patch.json >&2 || true
  exit 1
fi

state_json=$(curl -sS -f \
  -X GET "${BASE_URL}/api/v1/langgraph/state?thread_id=${CHAT_ID}" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -H "X-Request-Id: smoke-param-sync" )

if ! echo "$state_json" | jq -e '.parameters.medium == "oil" and (.parameters.pressure_bar | tostring) == "2" and (.parameters.temperature_C | tostring) == "80"' >/dev/null; then
  echo "FAIL: state did not contain expected parameters" >&2
  echo "$state_json" | jq -c '{parameters}' >&2 || true
  exit 1
fi

echo "OK: param sync verified for chat_id=${CHAT_ID}"
