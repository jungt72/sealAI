#!/bin/bash
set -u

SINCE="10m"
THRESHOLD=5
FAIL_ON_SPIKE=false

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --since) SINCE="$2"; shift 2 ;;
    --threshold) THRESHOLD="$2"; shift 2 ;;
    --fail) FAIL_ON_SPIKE=true; shift ;;
    *) echo "Unknown parameter: $1"; exit 1 ;;
  esac
done

echo "Checking Keycloak Logs (since=$SINCE)..."

LOGS=$(docker compose logs --since="$SINCE" keycloak 2>&1)

LOGIN_ERRORS=$(echo "$LOGS" | grep -c "LOGIN_ERROR")
INVALID_GRANT=$(echo "$LOGS" | grep -c "invalid_grant")
REFRESH_ERRORS=$(echo "$LOGS" | grep -c "REFRESH_TOKEN_ERROR")
WARNINGS=$(echo "$LOGS" | grep -c "WARN")

TOTAL_ERRORS=$((LOGIN_ERRORS + INVALID_GRANT + REFRESH_ERRORS))

echo "time=$(date -u +"%Y-%m-%dT%H:%M:%SZ") login_error=$LOGIN_ERRORS invalid_grant=$INVALID_GRANT refresh_error=$REFRESH_ERRORS warnings=$WARNINGS"

if [[ "$LOGIN_ERRORS" -ge "${ALERT_THRESHOLD_LOGIN_ERRORS:-3}" ]]; then
  bash "$(dirname "$0")/alert.sh" \
    "Keycloak LOGIN_ERROR spike: ${LOGIN_ERRORS} events detected"
fi

if [[ "$INVALID_GRANT" -ge "${ALERT_THRESHOLD_INVALID_GRANT:-3}" ]]; then
  bash "$(dirname "$0")/alert.sh" \
    "Keycloak invalid_grant spike: ${INVALID_GRANT} events detected"
fi

if [ "$TOTAL_ERRORS" -ge "$THRESHOLD" ]; then
  echo "ALERT: Keycloak error spike detected ($TOTAL_ERRORS >= $THRESHOLD)"
  if [ "$FAIL_ON_SPIKE" = true ]; then
    exit 1
  fi
fi
