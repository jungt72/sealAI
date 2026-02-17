#!/bin/bash
set -u

INTERVAL=30
ONCE=false

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --interval) INTERVAL="$2"; shift 2 ;;
    --once) ONCE=true; shift ;;
    *) echo "Unknown parameter: $1"; exit 1 ;;
  esac
done

# Resolve Password
REDIS_PASS=""
if [ -f .env ]; then
  REDIS_PASS=$(grep "^REDIS_PASSWORD=" .env | cut -d= -f2 | tr -d '"' | tr -d "'")
fi

if [ -z "$REDIS_PASS" ] && [ -n "${REDIS_PASSWORD:-}" ]; then
  REDIS_PASS="$REDIS_PASSWORD"
fi

if [ -z "$REDIS_PASS" ]; then
  echo "ERROR: REDIS_PASSWORD not found in .env or environment."
  exit 1
fi

echo "Starting Redis Token Health Watcher..."

get_stats() {
  # We use tr to remove carriage returns to behave nicely with grep/awk
  STATS=$(docker compose exec -T redis redis-cli -a "$REDIS_PASS" INFO stats 2>/dev/null | tr -d '\r')
  KEYSPACE=$(docker compose exec -T redis redis-cli -a "$REDIS_PASS" INFO keyspace 2>/dev/null | tr -d '\r')
  
  HITS=$(echo "$STATS" | grep "^keyspace_hits:" | cut -d: -f2)
  MISSES=$(echo "$STATS" | grep "^keyspace_misses:" | cut -d: -f2)
  EVICTED=$(echo "$STATS" | grep "^evicted_keys:" | cut -d: -f2)
  EXPIRED=$(echo "$STATS" | grep "^expired_keys:" | cut -d: -f2)
  
  # Calculate hit rate safely
  TOTAL_OPS=$((HITS + MISSES))
  if [ "$TOTAL_OPS" -gt 0 ]; then
    HIT_RATE=$(( 100 * HITS / TOTAL_OPS ))"%"
  else
    HIT_RATE="0%"
  fi

  echo "time=$(date -u +"%Y-%m-%dT%H:%M:%SZ") hits=$HITS misses=$MISSES rate=$HIT_RATE evicted=$EVICTED expired=$EXPIRED"

  if [[ "$EVICTED" -ge "${ALERT_THRESHOLD_EVICTED_KEYS:-1}" ]]; then
    bash "$(dirname "$0")/alert.sh" \
      "Redis eviction detected: evicted_keys=${EVICTED}"
  fi
}

while true; do
  get_stats
  if [ "$ONCE" = true ]; then
    exit 0
  fi
  sleep "$INTERVAL"
done
