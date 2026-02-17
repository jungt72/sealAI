#!/bin/bash
set -u

SINCE="5m"
INTERVAL=10
ONCE=false

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --since) SINCE="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --once) ONCE=true; shift ;;
    *) echo "Unknown parameter: $1"; exit 1 ;;
  esac
done

echo "Starting Nginx 429 Watcher (since=$SINCE, interval=${INTERVAL}s)..."

count_logs() {
  # We use docker logs as fallback if access.log isn't mounted/parseable directly easily
  # Ideally we'd parse access.log if mounted, but for 'minimal' docker logs is standard.
  # We filter for the specific log format or just status codes if possible.
  # Assuming default/json logs, we grep.
  
  LOGS=$(docker compose logs --since="$SINCE" nginx 2>&1)
  
  TOTAL=$(echo "$LOGS" | grep -c "HTTP/1.1\"")
  OK=$(echo "$LOGS" | grep -c "HTTP/1.1\" 200")
  RL=$(echo "$LOGS" | grep -c "HTTP/1.1\" 429")
  ERR=$(echo "$LOGS" | grep -E -c "HTTP/1.1\" 5[0-9][0-9]")
  
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "time=$TIMESTAMP total=$TOTAL ok=$OK rl_429=$RL err_5xx=$ERR"

  if [[ "$RL" -ge "${ALERT_THRESHOLD_429:-10}" ]]; then
    bash "$(dirname "$0")/alert.sh" \
      "Nginx rate limiting spike: ${RL} requests returned 429 in last interval"
  fi
}

while true; do
  count_logs
  if [ "$ONCE" = true ]; then
    exit 0
  fi
  sleep "$INTERVAL"
done
