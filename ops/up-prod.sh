#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo ">> Ensuring .env matches .env.prod before starting prod stack"
"$SCRIPT_DIR/check-env-drift.sh" prod

cd "$REPO_ROOT"
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml up -d --build
