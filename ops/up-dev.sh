#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo ">> Ensuring .env matches .env.dev before starting dev stack"
"$SCRIPT_DIR/check-env-drift.sh" dev

cd "$REPO_ROOT"
docker compose --env-file .env.dev up -d --build
