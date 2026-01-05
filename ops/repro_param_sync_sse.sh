#!/usr/bin/env bash
set -euo pipefail

require() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 2; }; }

require curl
require awk

BASE_URL="${NGINX_BASE_URL:-https://sealai.net}"
BASE_URL="${BASE_URL%/}"
CHAT_ID="${CHAT_ID:-param-sync-$(date +%s)}"
INPUT_TEXT="${INPUT_TEXT:-Param sync SSE check}"
CLIENT_MSG_ID="${CLIENT_MSG_ID:-param-sync-$(date +%s)}"
MAX_EVENTS="${MAX_EVENTS:-12}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-20}"

AUTH_TOKEN="${AUTH_TOKEN:-}"
AUTH_COOKIE="${AUTH_COOKIE:-}"
AUTH_COOKIE_FILE="${AUTH_COOKIE_FILE:-}"

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

count_dots() {
  local value="$1"
  if [[ -z "$value" ]]; then
    echo 0
    return
  fi
  printf '%s' "$value" | awk -F'.' '{print NF-1}'
}

decode_jwt_claims() {
  local token="$1"
  if ! command -v python3 >/dev/null 2>&1; then
    return
  fi
  python3 - "$token" <<'PY'
import base64
import json
import sys

token = sys.argv[1]
parts = token.split(".")
if len(parts) != 3:
    sys.exit(0)
payload = parts[1]
pad = "=" * (-len(payload) % 4)
try:
    data = base64.urlsafe_b64decode(payload + pad)
    obj = json.loads(data.decode("utf-8"))
except Exception:
    sys.exit(0)

fields = {k: obj.get(k) for k in ("iss", "aud", "azp", "exp") if k in obj}
if fields:
    print("decoded claims: " + json.dumps(fields, ensure_ascii=True))
PY
}

if [[ -n "$AUTH_COOKIE_FILE" ]]; then
  if [[ ! -r "$AUTH_COOKIE_FILE" ]]; then
    echo "ERROR: AUTH_COOKIE_FILE not readable: ${AUTH_COOKIE_FILE}" >&2
    exit 1
  fi
  AUTH_COOKIE="$(trim_cookie "$(cat "$AUTH_COOKIE_FILE")")"
fi

AUTH_TOKEN="$(trim_token "$AUTH_TOKEN")"
AUTH_COOKIE="$(trim_cookie "$AUTH_COOKIE")"

if [[ -z "$AUTH_TOKEN" && -n "${AUTH_COOKIE:-}" ]]; then
  if command -v jq >/dev/null 2>&1; then
    session_json=$(curl -sS -f -H "Cookie: ${AUTH_COOKIE}" "${BASE_URL}/api/auth/session" || true)
    if [[ -n "$session_json" ]]; then
      AUTH_TOKEN=$(echo "$session_json" | jq -r '.accessToken // .access_token // .token // empty')
    fi
    AUTH_TOKEN="$(trim_token "$AUTH_TOKEN")"
    echo "session resolved token: len=${#AUTH_TOKEN}, dots=$(count_dots "$AUTH_TOKEN")" >&2
  fi
fi

if [[ -n "$AUTH_TOKEN" ]]; then
  token_dots="$(count_dots "$AUTH_TOKEN")"
  if [[ "$token_dots" -ne 2 ]]; then
    echo "ERROR: AUTH_TOKEN is not a JWT (dots=${token_dots}). Provide a real access token or set AUTH_COOKIE to resolve it." >&2
    exit 1
  fi
fi

if [[ -z "$AUTH_TOKEN" ]]; then
  echo "ERROR: AUTH_TOKEN is required (or set AUTH_COOKIE to resolve it)." >&2
  exit 1
fi

echo "== state (before patch) =="
state_tmp="$(mktemp)"
state_code=$(curl -sS \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -o "$state_tmp" \
  -w '%{http_code}' \
  "${BASE_URL}/api/langgraph/state?thread_id=${CHAT_ID}" || true)
if [[ "$state_code" == "401" ]]; then
  echo "401 from /api/langgraph/state: token rejected" >&2
  token_dots="$(count_dots "$AUTH_TOKEN")"
  if [[ "$token_dots" -ne 2 ]]; then
    echo "token not JWT" >&2
  else
    echo "likely audience/issuer mismatch -- see decoded claims" >&2
    decode_jwt_claims "$AUTH_TOKEN" >&2
  fi
  rm -f "$state_tmp"
  exit 1
fi
if [[ "$state_code" -lt 200 || "$state_code" -ge 300 ]]; then
  echo "ERROR: /api/langgraph/state returned HTTP ${state_code}" >&2
  rm -f "$state_tmp"
  exit 1
fi
cat "$state_tmp" | { command -v jq >/dev/null 2>&1 && jq -c '{parameters: .parameters}' || cat; }
rm -f "$state_tmp"
echo

PATCH_PAYLOAD='{"chat_id":"'"$CHAT_ID"'","parameters":{"pressure_bar":2,"temperature_C":80}}'
echo "== patch parameters =="
curl -sS -f \
  -X POST "${BASE_URL}/api/langgraph/parameters/patch" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -d "$PATCH_PAYLOAD" \
  | { command -v jq >/dev/null 2>&1 && jq -c '{ok: true, parameters: .parameters}'; }
echo

echo "== sse (/api/chat) expecting state_update =="
payload=$(python3 - <<'PY'
import json, os
payload = {
  "input": os.environ.get("INPUT_TEXT", "Param sync SSE check"),
  "chat_id": os.environ.get("CHAT_ID", "param-sync"),
  "client_msg_id": os.environ.get("CLIENT_MSG_ID", "param-sync"),
}
print(json.dumps(payload, ensure_ascii=True))
PY
)

run_sse() {
  local cmd=("curl" "-sS" "-N" "-X" "POST" "${BASE_URL}/api/chat"
    "-H" "Content-Type: application/json"
    "-H" "Accept: text/event-stream"
    "-H" "Authorization: Bearer ${AUTH_TOKEN}"
    "--data" "$payload")

  if command -v timeout >/dev/null 2>&1; then
    timeout "$TIMEOUT_SECONDS" "${cmd[@]}"
  else
    "${cmd[@]}"
  fi
}

set +e
run_sse | awk -v max="$MAX_EVENTS" '
  /^event:/ { event=$2; count++; }
  /^data:/ {
    data = substr($0, 6);
    if (event == "state_update" || data ~ /"type":"state_update"/) { found=1; exit 0; }
    if (count >= max) exit 1;
  }
  END { if (!found) exit 1; }
'
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  echo "FAIL: did not observe state_update in SSE stream (chat_id=${CHAT_ID})" >&2
  exit "$rc"
fi

if [[ -n "${AUTH_COOKIE:-}" ]] && command -v jq >/dev/null 2>&1; then
  session_json=$(curl -sS -f -H "Cookie: ${AUTH_COOKIE}" "${BASE_URL}/api/auth/session" || true)
  if [[ -n "$session_json" ]]; then
    if echo "$session_json" | jq -e '.accessToken // .access_token // .token' >/dev/null 2>&1; then
      echo "dry-run: /api/auth/session has accessToken"
    else
      echo "dry-run: /api/auth/session missing accessToken field" >&2
    fi
  else
    echo "dry-run: /api/auth/session empty response" >&2
  fi
fi

echo "OK: state_update observed for chat_id=${CHAT_ID}"
