#!/usr/bin/env bash
set -euo pipefail

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "FAIL: missing dependency '$1'" >&2
    exit 1
  fi
}

need_cmd curl
need_cmd jq
need_cmd awk

BASE_URL="${BASE_URL:-http://localhost:3000}"
BEARER_TOKEN="${BEARER_TOKEN:-}"
THREAD_ID="${THREAD_ID:-smoke-$(date +%s)}"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

http_code() {
  curl -sS -o /dev/null -w "%{http_code}" "$@"
}

# A) Health
code=$(http_code "${BASE_URL}/api/health")
if [ "$code" = "200" ]; then
  pass "GET /api/health -> 200"
else
  fail "GET /api/health -> ${code}"
fi

# Helper for protected endpoints
expect_protected() {
  local method="$1"
  local url="$2"
  local body="$3"
  local expected="$4"
  local auth_header=()

  if [ -n "$BEARER_TOKEN" ]; then
    auth_header=( -H "Authorization: Bearer ${BEARER_TOKEN}" )
  fi

  local code
  if [ "$method" = "GET" ]; then
    code=$(curl -sS -o /tmp/smoke_resp.json -w "%{http_code}" "${auth_header[@]}" "$url")
  else
    code=$(curl -sS -o /tmp/smoke_resp.json -w "%{http_code}" \
      -X "$method" -H "Content-Type: application/json" \
      "${auth_header[@]}" \
      -d "$body" "$url")
  fi

  if [ "$expected" = "401" ]; then
    if [ "$code" = "401" ]; then
      pass "$method $url -> 401 (expected without token)"
    else
      fail "$method $url -> ${code} (expected 401)"
    fi
  else
    if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
      pass "$method $url -> ${code}"
    else
      fail "$method $url -> ${code} (expected 2xx)"
    fi
  fi
}

expected_protected="401"
if [ -n "$BEARER_TOKEN" ]; then
  expected_protected="2xx"
fi

# B) State
expect_protected "GET" "${BASE_URL}/api/langgraph/state?thread_id=${THREAD_ID}" "" "$expected_protected"

# C) Parameters Patch
patch_payload=$(jq -c -n --arg tid "$THREAD_ID" '{chat_id:$tid,parameters:{pressure_bar:1}}')
expect_protected "POST" "${BASE_URL}/api/langgraph/parameters/patch" "$patch_payload" "$expected_protected"

# C2) Normalization check (token required)
if [ -z "$BEARER_TOKEN" ]; then
  echo "SKIP: normalization check (no token)"
else
  norm_patch=$(jq -c -n --arg tid "$THREAD_ID" '{chat_id:$tid,parameters:{pressure_bar:"5.4"}}')
  norm_code=$(curl -sS -o /tmp/smoke_norm_patch.json -w "%{http_code}" \
    -X POST -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${BEARER_TOKEN}" \
    -d "$norm_patch" \
    "${BASE_URL}/api/langgraph/parameters/patch")
  if [ "$norm_code" -ge 200 ] && [ "$norm_code" -lt 300 ]; then
    pass "POST /api/langgraph/parameters/patch (normalize) -> ${norm_code}"
  else
    fail "POST /api/langgraph/parameters/patch (normalize) -> ${norm_code}"
  fi

  state_code=$(curl -sS -o /tmp/smoke_norm_state.json -w "%{http_code}" \
    -H "Authorization: Bearer ${BEARER_TOKEN}" \
    "${BASE_URL}/api/langgraph/state?thread_id=${THREAD_ID}")
  if [ "$state_code" -ge 200 ] && [ "$state_code" -lt 300 ]; then
    pass "GET /api/langgraph/state (normalize) -> ${state_code}"
  else
    fail "GET /api/langgraph/state (normalize) -> ${state_code}"
  fi

  if jq -e '.parameters.pressure_bar | type == "number"' /tmp/smoke_norm_state.json >/dev/null; then
    pass "state.parameters.pressure_bar is number (normalized)"
  else
    echo "state response:" >&2
    cat /tmp/smoke_norm_state.json >&2
    fail "state.parameters.pressure_bar is not number"
  fi
fi

# D) Confirm GO
confirm_payload=$(jq -c -n --arg tid "$THREAD_ID" '{chat_id:$tid,go:true}')
expect_protected "POST" "${BASE_URL}/api/langgraph/confirm/go" "$confirm_payload" "$expected_protected"

# E) Chat SSE (only with token)
if [ -n "$BEARER_TOKEN" ]; then
  sse_resp=$(curl -sS -i \
    -H "Authorization: Bearer ${BEARER_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    -X POST \
    -d "$(jq -c -n --arg tid "$THREAD_ID" '{chat_id:$tid,input:"ping"}')" \
    "${BASE_URL}/api/chat" || true)

  status_line=$(printf "%s" "$sse_resp" | awk 'NR==1 {print $2}')
  if [ "$status_line" = "200" ]; then
    if printf "%s" "$sse_resp" | awk 'BEGIN{found=0} /text\/event-stream/ {found=1} END{exit !found}'; then
      pass "POST /api/chat -> 200 (SSE content-type)"
    elif printf "%s" "$sse_resp" | awk 'BEGIN{found=0} /event:/ {found=1} END{exit !found}'; then
      pass "POST /api/chat -> 200 (SSE markers)"
    else
      fail "POST /api/chat -> 200 but no SSE markers"
    fi
  else
    fail "POST /api/chat -> ${status_line}"
  fi
fi

# F) Legacy v1 endpoint check
legacy_code=$(curl -sS -o /tmp/smoke_legacy.json -w "%{http_code}" "${BASE_URL}/api/v1/ai" || true)
legacy_detail=$(cat /tmp/smoke_legacy.json | jq -r '.detail // empty' || true)
if [ "$legacy_code" = "410" ] && printf "%s" "$legacy_detail" | awk 'BEGIN{found=0} /Legacy LangGraph v1 endpoint removed/ {found=1} END{exit !found}'; then
  pass "GET /api/v1/ai -> 410 (legacy disabled)"
else
  fail "GET /api/v1/ai -> ${legacy_code} (expected 410)"
fi

# Examples:
# BASE_URL=http://localhost:3000 ./ops/smoke_langgraph_v2_bff.sh
# BASE_URL=https://sealai.net BEARER_TOKEN=... ./ops/smoke_langgraph_v2_bff.sh
