#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-sealai}"
BACKEND_DATA_VOLUME="${COMPOSE_PROJECT_NAME}_backend-data"
BACKEND_RUNTIME_UID="${BACKEND_RUNTIME_UID:-1000}"
BACKEND_RUNTIME_GID="${BACKEND_RUNTIME_GID:-1000}"

prepare_backend_volume() {
  echo ">> Preparing backend runtime volume: ${BACKEND_DATA_VOLUME}"
  docker volume create "$BACKEND_DATA_VOLUME" >/dev/null
  docker run --rm \
    --user 0:0 \
    --entrypoint sh \
    -v "${BACKEND_DATA_VOLUME}:/app/data" \
    postgres:15 \
    -lc "mkdir -p /app/data/models /app/data/uploads && chown -R ${BACKEND_RUNTIME_UID}:${BACKEND_RUNTIME_GID} /app/data && chmod 2775 /app/data /app/data/models /app/data/uploads"
}

echo ">> Validating .env.prod and pinned production image refs"
"$SCRIPT_DIR/check-env-drift.sh" prod

cd "$REPO_ROOT"
prepare_backend_volume
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml pull backend keycloak
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml up -d --remove-orphans backend keycloak
