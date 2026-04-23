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

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

http_code() {
  curl -sS -o /tmp/smoke_resp.json -w "%{http_code}" "$@"
}

assert_status() {
  local method="$1"
  local url="$2"
  local expected="$3"
  local body="${4:-}"
  local code

  if [ "$method" = "GET" ]; then
    code=$(http_code "$url")
  else
    code=$(curl -sS -o /tmp/smoke_resp.json -w "%{http_code}" \
      -X "$method" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "$url")
  fi

  if [ "$code" = "$expected" ]; then
    pass "$method $url -> $code"
  else
    echo "response body:" >&2
    cat /tmp/smoke_resp.json >&2 || true
    fail "$method $url -> $code (expected $expected)"
  fi
}

# A) Health must stay public
assert_status "GET" "${BASE_URL}/api/health" "200"

# B) Current BFF agent stream route must exist and reject anonymous access
assert_status \
  "POST" \
  "${BASE_URL}/api/bff/agent/chat/stream" \
  "401" \
  '{"message":"ping from ci"}'

# C) Current BFF workspace route must exist and reject anonymous access
assert_status \
  "GET" \
  "${BASE_URL}/api/bff/workspace/smoke-case" \
  "401"

# D) Current BFF history route must exist and reject anonymous access
assert_status \
  "GET" \
  "${BASE_URL}/api/bff/agent/chat/history/smoke-case" \
  "401"

# E) Legacy LangGraph v2 routes must be gone
legacy_state_code=$(http_code "${BASE_URL}/api/langgraph/state?thread_id=smoke")
if [ "$legacy_state_code" = "404" ] || [ "$legacy_state_code" = "410" ]; then
  pass "GET /api/langgraph/state -> ${legacy_state_code} (legacy route retired)"
else
  fail "GET /api/langgraph/state -> ${legacy_state_code} (expected 404 or 410)"
fi

legacy_patch_code=$(curl -sS -o /tmp/smoke_resp.json -w "%{http_code}" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"smoke","parameters":{"pressure_bar":1}}' \
  "${BASE_URL}/api/langgraph/parameters/patch")
if [ "$legacy_patch_code" = "404" ] || [ "$legacy_patch_code" = "410" ]; then
  pass "POST /api/langgraph/parameters/patch -> ${legacy_patch_code} (legacy route retired)"
else
  fail "POST /api/langgraph/parameters/patch -> ${legacy_patch_code} (expected 404 or 410)"
fi
