#!/usr/bin/env bash
set -euo pipefail

COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
REDIS_SERVICE="${REDIS_SERVICE:-redis}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
MAX_KEYS="${MAX_KEYS:-50}"
PATTERN="${PATTERN:-lg:cp:*:checkpoint_write:*}"

fail() {
  echo "FAIL: $1"
  exit 1
}

pass() {
  echo "PASS: $1"
}

command -v docker >/dev/null 2>&1 || fail "docker is required"

auth_args=()
if [[ -n "$REDIS_PASSWORD" ]]; then
  auth_args=(-a "$REDIS_PASSWORD")
fi

keys=()
while IFS= read -r key; do
  [[ -z "$key" ]] && continue
  keys+=("$key")
  if [[ "${#keys[@]}" -ge "$MAX_KEYS" ]]; then
    break
  fi
done < <($COMPOSE_CMD exec -T "$REDIS_SERVICE" redis-cli "${auth_args[@]}" --scan --pattern "$PATTERN")

if [[ "${#keys[@]}" -eq 0 ]]; then
  pass "no keys matched $PATTERN"
  exit 0
fi

ttl_minus_one=0
ttl_minus_two=0
ttl_other=0
ttl_positive=0

for key in "${keys[@]}"; do
  ttl="$($COMPOSE_CMD exec -T "$REDIS_SERVICE" redis-cli "${auth_args[@]}" TTL "$key" | tr -d '\r')"
  case "$ttl" in
    -1) ttl_minus_one=$((ttl_minus_one + 1)) ;;
    -2) ttl_minus_two=$((ttl_minus_two + 1)) ;;
    ''|*[!0-9-]*) ttl_other=$((ttl_other + 1)) ;;
    *) if [[ "$ttl" -gt 0 ]]; then ttl_positive=$((ttl_positive + 1)); fi ;;
  esac
done

echo "TTL summary: keys=${#keys[@]} positive=${ttl_positive} minus_one=${ttl_minus_one} minus_two=${ttl_minus_two} other=${ttl_other}"

if [[ "$ttl_minus_one" -gt 0 ]]; then
  fail "found $ttl_minus_one keys without TTL (-1)"
fi

pass "no TTL=-1 for sampled keys"
