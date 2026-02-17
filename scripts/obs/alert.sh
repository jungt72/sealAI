#!/bin/bash
set -euo pipefail

# Opt-in only
if [[ -z "${ALERT_WEBHOOK_URL:-}" ]]; then
  exit 0
fi

CHANNEL="${ALERT_CHANNEL:-discord}"
MSG="${1:-"(no message)"}"

# Never echo webhook
payload=""

if [[ "$CHANNEL" == "discord" ]]; then
  payload="{\"content\":\"🚨 SealAI Alert: ${MSG}\"}"
else
  payload="{\"text\":\"🚨 SealAI Alert: ${MSG}\"}"
fi

curl -sS -X POST \
  -H "Content-Type: application/json" \
  --data "$payload" \
  "$ALERT_WEBHOOK_URL" \
  >/dev/null || true
