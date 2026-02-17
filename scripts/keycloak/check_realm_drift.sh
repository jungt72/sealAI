#!/bin/bash
set -euo pipefail

BASELINE="$HOME/sealai/docs/ops/keycloak/realm-export/sealAI-realm.sanitized.json"
TMP="$(mktemp)"

# Ensure we are in the right directory for the export script
cd ~/sealai

# Generate current state to temp file
bash scripts/keycloak/export_realm.sh --stdout > "$TMP"

if ! diff -q "$BASELINE" "$TMP" >/dev/null; then
  echo "DRIFT DETECTED: Keycloak realm differs from baseline."
  diff -u "$BASELINE" "$TMP" | head -n 80
  rm "$TMP"
  exit 1
fi

echo "OK: No realm drift detected."
rm "$TMP"
