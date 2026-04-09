#!/usr/bin/env bash
set -euo pipefail

cd /home/thorsten/sealai

COMPOSE_ARGS=(
  --env-file .env.prod
  -f docker-compose.yml
  -f docker-compose.deploy.yml
)

SHA="$(git rev-parse HEAD)"
SHORT_SHA="$(git rev-parse --short=8 HEAD)"
TS="$(date +%Y%m%d-%H%M%S)"
BACKEND_IMAGE_TAG="ghcr.io/jungt72/sealai-backend:${SHORT_SHA}-${TS}"

echo ">> Building ${BACKEND_IMAGE_TAG}"
docker build \
  --file backend/Dockerfile \
  --tag "${BACKEND_IMAGE_TAG}" \
  --build-arg GIT_SHA="${SHA}" \
  backend/

echo ">> Pushing ${BACKEND_IMAGE_TAG}"
docker push "${BACKEND_IMAGE_TAG}"

BACKEND_DIGEST="$(
  docker image inspect "${BACKEND_IMAGE_TAG}" \
    --format '{{range .RepoDigests}}{{println .}}{{end}}' \
  | grep '^ghcr.io/jungt72/sealai-backend@' \
  | head -n1 \
  | cut -d@ -f2
)"
test -n "${BACKEND_DIGEST}"

BACKEND_IMAGE_PINNED="${BACKEND_IMAGE_TAG}@${BACKEND_DIGEST}"
echo ">> New pinned image: ${BACKEND_IMAGE_PINNED}"

ROLLBACK_FILE=".env.prod.rollback-${TS}"
cp .env.prod "${ROLLBACK_FILE}"
echo ">> Rollback snapshot: ${ROLLBACK_FILE}"

sed -i "s|^BACKEND_IMAGE=.*|BACKEND_IMAGE=${BACKEND_IMAGE_PINNED}|" .env.prod

echo ">> Validating pinned production refs"
./ops/check-env-drift.sh prod

echo ">> Pulling backend only"
docker compose "${COMPOSE_ARGS[@]}" pull backend

echo ">> Recreating backend only"
docker compose "${COMPOSE_ARGS[@]}" up -d --no-deps backend

echo ">> Verifying image pin"
grep '^BACKEND_IMAGE=' .env.prod
docker compose "${COMPOSE_ARGS[@]}" ps backend
docker inspect backend --format '{{.Config.Image}}'

echo ">> Verifying code marker"
docker exec backend sh -lc "grep -R 'decision_basis_hash' -n /app/app 2>/dev/null | head"

echo ">> Waiting for backend health"
for i in {1..30}; do
  if docker exec backend sh -lc "curl -fsS http://127.0.0.1:8000/health" >/dev/null; then
    echo ">> Backend healthy"
    break
  fi
  echo ">> Backend not ready yet (${i}/30)"
  sleep 2
done

docker exec backend sh -lc "curl -fsS http://127.0.0.1:8000/health"

echo ">> Done"
