#!/usr/bin/env bash
set -euo pipefail

COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
REQUIRE_REDIS="${REQUIRE_REDIS:-0}"
REQUIRE_SSE_REPLAY="${REQUIRE_SSE_REPLAY:-0}"
SEALAI_SSE_REPLAY_BACKEND="${SEALAI_SSE_REPLAY_BACKEND:-}"

pass_count=0
fail_count=0
skip_count=0

pass() {
  echo "PASS: $1"
  pass_count=$((pass_count + 1))
}

fail() {
  echo "FAIL: $1"
  fail_count=$((fail_count + 1))
}

skip() {
  echo "SKIP: $1"
  skip_count=$((skip_count + 1))
}

run_check() {
  local name="$1"
  shift
  if "$@"; then
    pass "$name"
  else
    fail "$name"
  fi
}

run_check "compose config" $COMPOSE_CMD config

run_check "backend smoke" bash ops/prod_smoke_backend.sh

run_check "rag safety proof" bash ops/proof_rag_safety.sh

if [[ -z "${REDIS_PASSWORD:-}" ]]; then
  if [[ "$REQUIRE_REDIS" == "1" ]]; then
    fail "redis ttl proof (REDIS_PASSWORD missing)"
  else
    skip "redis ttl proof (REDIS_PASSWORD missing)"
  fi
else
  run_check "redis ttl proof" bash ops/proof_redis_ttl.sh
fi

if [[ "$SEALAI_SSE_REPLAY_BACKEND" == "redis" && "$REQUIRE_SSE_REPLAY" == "1" ]]; then
  if [[ -z "${REDIS_PASSWORD:-}" ]]; then
    fail "sse replay proof (REDIS_PASSWORD missing)"
  else
    if $COMPOSE_CMD exec -T redis redis-cli -a "$REDIS_PASSWORD" --scan --pattern "sse:seq:*" | grep -q . \
      && $COMPOSE_CMD exec -T redis redis-cli -a "$REDIS_PASSWORD" --scan --pattern "sse:buf:*" | grep -q .; then
      pass "sse replay proof"
    else
      fail "sse replay proof (no sse:seq:* or sse:buf:* keys found)"
    fi
  fi
else
  skip "sse replay proof (not required)"
fi

echo "Summary: PASS=${pass_count} FAIL=${fail_count} SKIP=${skip_count}"

if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi
exit 0
