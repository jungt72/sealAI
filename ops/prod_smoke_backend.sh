#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
HEALTH_PATH="${HEALTH_PATH:-/api/v1/langgraph/health}"
METRICS_PATH="${METRICS_PATH:-/metrics}"
METRICS_EXPECT="${METRICS_EXPECT:-http_requests_total}"

fail() {
  echo "FAIL: $1"
  exit 1
}

pass() {
  echo "PASS: $1"
}

command -v curl >/dev/null 2>&1 || fail "curl is required"

health_url="${BASE_URL}${HEALTH_PATH}"
metrics_url="${BASE_URL}${METRICS_PATH}"

curl -fsS "$health_url" >/dev/null || fail "health check failed: $health_url"
pass "health check ok"

metrics_body="$(curl -fsS "$metrics_url" || true)"
echo "$metrics_body" | grep -q "$METRICS_EXPECT" || fail "metrics missing $METRICS_EXPECT at $metrics_url"
pass "metrics endpoint ok"

if [[ -n "${ACCESS_TOKEN:-}" ]]; then
  chat_url="${BASE_URL}/api/v1/langgraph/chat/v2"
  status="$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    -d '{"input":"ping","chat_id":"smoke","client_msg_id":"smoke"}' \
    "$chat_url" || true)"
  if [[ "$status" != "200" ]]; then
    fail "chat v2 endpoint returned ${status}"
  fi
  pass "chat v2 endpoint ok"
else
  echo "SKIP: ACCESS_TOKEN not set; chat v2 smoke check skipped"
fi
