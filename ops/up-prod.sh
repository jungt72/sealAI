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

# This is host boot/recovery orchestration only. It must never build or deploy
# application code. Backend-v2 application releases go through
# ops/release-backend-v2.sh, which binds code, eval, image and rollback.
COMPOSE=(docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml --profile v2 --profile frontend-container)
"${COMPOSE[@]}" pull postgres redis qdrant gotenberg tika keycloak nginx frontend
"${COMPOSE[@]}" up -d --no-build --no-recreate --remove-orphans \
  postgres redis qdrant gotenberg tika keycloak nginx frontend backend-v2

# Nginx resolves Docker upstream container IPs at startup. Refresh it after
# infrastructure recovery so public smoke does not hit stale upstreams.
echo ">> Refreshing nginx upstreams"
"${COMPOSE[@]}" restart nginx
