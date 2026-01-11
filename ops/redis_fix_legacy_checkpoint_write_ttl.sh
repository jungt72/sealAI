#!/usr/bin/env bash
set -euo pipefail

# Fix TTL for legacy checkpoint_write keys with TTL=-1 (no expiry).
# This script only sets EXPIRE on matching keys; it does not delete anything.
#
# Usage:
#   LANGGRAPH_CHECKPOINT_TTL=86400 ./ops/redis_fix_legacy_checkpoint_write_ttl.sh
#   FIX_TTL_SECONDS=86400 CONFIRM=1 ./ops/redis_fix_legacy_checkpoint_write_ttl.sh
#
# Notes:
# - TTL seconds are derived from FIX_TTL_SECONDS if set, otherwise from
#   LANGGRAPH_CHECKPOINT_TTL (seconds).
# - Requires Docker Compose and a running `redis` service.
# - Requires REDIS_PASSWORD if Redis auth is enabled.

REDIS_SERVICE="${REDIS_SERVICE:-redis}"
KEY_PATTERN="lg:cp:*:checkpoint_write:*"

if [[ -n "${FIX_TTL_SECONDS:-}" ]]; then
  TTL_SECONDS="${FIX_TTL_SECONDS}"
elif [[ -n "${LANGGRAPH_CHECKPOINT_TTL:-}" ]]; then
  TTL_SECONDS="${LANGGRAPH_CHECKPOINT_TTL}"
else
  echo "ERROR: Set FIX_TTL_SECONDS or LANGGRAPH_CHECKPOINT_TTL." >&2
  exit 1
fi

if ! [[ "${TTL_SECONDS}" =~ ^[0-9]+$ ]] || [[ "${TTL_SECONDS}" -le 0 ]]; then
  echo "ERROR: TTL seconds must be a positive integer." >&2
  exit 1
fi

REDIS_AUTH_ARGS=""
if [[ -n "${REDIS_PASSWORD:-}" ]]; then
  REDIS_AUTH_ARGS="-a ${REDIS_PASSWORD}"
fi

redis_cmd() {
  docker compose exec -T "${REDIS_SERVICE}" /bin/sh -c "redis-cli ${REDIS_AUTH_ARGS} $*"
}

tmp_keys="$(mktemp)"
trap 'rm -f "${tmp_keys}"' EXIT

redis_cmd "--scan --pattern \"${KEY_PATTERN}\"" > "${tmp_keys}"

total_keys=0
no_ttl_keys=0

while IFS= read -r key; do
  [[ -z "${key}" ]] && continue
  total_keys=$((total_keys + 1))
  ttl_val="$(redis_cmd "TTL \"${key}\"" | tr -d '\r')"
  if [[ "${ttl_val}" == "-1" ]]; then
    no_ttl_keys=$((no_ttl_keys + 1))
  fi
done < "${tmp_keys}"

echo "Dry run:"
echo "- Pattern: ${KEY_PATTERN}"
echo "- Total keys scanned: ${total_keys}"
echo "- Keys with TTL=-1: ${no_ttl_keys}"
echo "- TTL to apply (seconds): ${TTL_SECONDS}"

if [[ "${CONFIRM:-0}" != "1" ]]; then
  echo "Set CONFIRM=1 to apply TTL updates."
  exit 0
fi

applied=0
failed=0

while IFS= read -r key; do
  [[ -z "${key}" ]] && continue
  ttl_val="$(redis_cmd "TTL \"${key}\"" | tr -d '\r')"
  if [[ "${ttl_val}" == "-1" ]]; then
    if redis_cmd "EXPIRE \"${key}\" ${TTL_SECONDS}" >/dev/null; then
      applied=$((applied + 1))
    else
      failed=$((failed + 1))
      echo "WARN: failed to apply TTL for key: ${key}" >&2
    fi
  fi
done < "${tmp_keys}"

echo "Applied TTL to ${applied} keys. Failed: ${failed}."
