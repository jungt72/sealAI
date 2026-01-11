#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LOCK_FILE="$ROOT_DIR/backend/requirements-lock.txt"
AUDIT_DIR="$ROOT_DIR/docs/audits"
JSON_OUT="$AUDIT_DIR/backend_pip_audit.json"
TXT_OUT="$AUDIT_DIR/backend_pip_audit.txt"

if ! command -v pip-audit >/dev/null 2>&1; then
  echo "pip-audit not found. Install it (e.g. pip install -r backend/requirements-dev.txt)." >&2
  exit 1
fi

if [ ! -s "$LOCK_FILE" ]; then
  echo "Missing lock file: $LOCK_FILE" >&2
  exit 1
fi

mkdir -p "$AUDIT_DIR"

pip-audit -r "$LOCK_FILE" -f json > "$JSON_OUT"

pip-audit -r "$LOCK_FILE" > "$TXT_OUT" || true

printf "Wrote %s\nWrote %s\n" "$JSON_OUT" "$TXT_OUT"
