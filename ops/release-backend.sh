#!/usr/bin/env bash
set -euo pipefail

cd /home/thorsten/sealai

COMPOSE_ARGS=(
  --env-file .env.prod
  -f docker-compose.yml
  -f docker-compose.deploy.yml
)

compose_prod() {
  env -u BACKEND_IMAGE -u FRONTEND_IMAGE -u LANGCHAIN_TRACING_V2 -u LANGCHAIN_API_KEY -u LANGCHAIN_PROJECT docker compose "${COMPOSE_ARGS[@]}" "$@"
}

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
PUSH_OUTPUT="$(docker push "${BACKEND_IMAGE_TAG}" 2>&1)"
echo "${PUSH_OUTPUT}"

BACKEND_DIGEST="$(echo "${PUSH_OUTPUT}" | grep -oP 'digest: \K\S+' | tail -1)"
test -n "${BACKEND_DIGEST}"

BACKEND_IMAGE_PINNED="${BACKEND_IMAGE_TAG}@${BACKEND_DIGEST}"
echo ">> New pinned image: ${BACKEND_IMAGE_PINNED}"

ROLLBACK_FILE=".env.prod.rollback-${TS}"
cp .env.prod "${ROLLBACK_FILE}"
echo ">> Rollback snapshot: ${ROLLBACK_FILE}"

sed -i "s|^BACKEND_IMAGE=.*|BACKEND_IMAGE=${BACKEND_IMAGE_PINNED}|" .env.prod

echo ">> Validating pinned production refs"
./ops/check-env-drift.sh prod

# Image ist lokal bereits getaggt — pull nur bei remote-only deploy nötig
echo ">> Recreating backend only"
compose_prod up -d --no-deps backend

echo ">> Verifying image pin"
grep '^BACKEND_IMAGE=' .env.prod
compose_prod ps backend
docker inspect backend --format '{{.Config.Image}}'

echo ">> Verifying code marker"
docker exec backend sh -lc "grep -R 'decision_basis_hash' -n /app/app 2>/dev/null | head"

echo ">> Waiting for backend health"
for i in {1..30}; do
  if docker exec backend sh -lc "curl -fsS http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    echo ">> Backend healthy"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "!! Health check failed after 30 attempts — rolling back"
    cp "${ROLLBACK_FILE}" .env.prod
    compose_prod up -d --no-deps backend
    echo "!! Rollback complete — check backend logs:"
    docker logs backend --tail 50
    exit 1
  fi
  echo ">> Backend not ready yet (${i}/30)"
  sleep 2
done

docker exec backend sh -lc "curl -fsS http://127.0.0.1:8000/health"

if [[ "${SKIP_LIVE_SMOKE:-0}" != "1" ]]; then
  echo ">> Running live pilot readiness smoke"
  BASE_URL="${BASE_URL:-https://sealai.net}" ./ops/smoke-live-pilot-readiness.sh
else
  echo ">> Live pilot readiness smoke skipped by SKIP_LIVE_SMOKE=1"
fi

echo ">> Done"
