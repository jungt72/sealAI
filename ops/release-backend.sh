#!/usr/bin/env bash
set -euo pipefail

cd /home/thorsten/sealai

COMPOSE_ARGS=(
  --env-file .env.prod
  -f docker-compose.yml
  -f docker-compose.deploy.yml
)

compose_prod() {
  env \
    -u BACKEND_IMAGE \
    -u FRONTEND_IMAGE \
    -u LANGSMITH_TRACING \
    -u LANGSMITH_API_KEY \
    -u LANGSMITH_PROJECT \
    -u LANGSMITH_ENDPOINT \
    -u SEALAI_TRACE_HASH_SALT \
    -u LANGSMITH_TRACE_SALT \
    -u LANGSMITH_CAPTURE_LLM_CONTENT \
    -u LANGSMITH_TRACE_LANGGRAPH_CHILDREN \
    -u LANGCHAIN_TRACING_V2 \
    -u LANGCHAIN_API_KEY \
    -u LANGCHAIN_PROJECT \
    -u LANGCHAIN_ENDPOINT \
    docker compose "${COMPOSE_ARGS[@]}" "$@"
}

set_env_key() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env.prod; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env.prod
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> .env.prod
  fi
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
ROLLBACK_FILE=".env.prod.rollback-${TS}"
cp .env.prod "${ROLLBACK_FILE}"
echo ">> Rollback snapshot: ${ROLLBACK_FILE}"

if PUSH_OUTPUT="$(docker push "${BACKEND_IMAGE_TAG}" 2>&1)"; then
  echo "${PUSH_OUTPUT}"
  BACKEND_DIGEST="$(echo "${PUSH_OUTPUT}" | grep -oP 'digest: \K\S+' | tail -1)"
  test -n "${BACKEND_DIGEST}"

  BACKEND_IMAGE_REF="${BACKEND_IMAGE_TAG}@${BACKEND_DIGEST}"
  BACKEND_PULL_POLICY="always"
  echo ">> New pinned image: ${BACKEND_IMAGE_REF}"
else
  echo "${PUSH_OUTPUT}" >&2
  if [[ "${ALLOW_LOCAL_BACKEND_IMAGE_FALLBACK:-0}" != "1" ]]; then
    echo "!! GHCR push failed. Fix package write permissions or rerun with ALLOW_LOCAL_BACKEND_IMAGE_FALLBACK=1 for this VPS-only deploy." >&2
    exit 1
  fi

  BACKEND_IMAGE_REF="${BACKEND_IMAGE_TAG}"
  BACKEND_PULL_POLICY="never"
  echo "!! GHCR push failed; using VPS-local backend image fallback: ${BACKEND_IMAGE_REF}" >&2
fi

set_env_key BACKEND_IMAGE "${BACKEND_IMAGE_REF}"
set_env_key BACKEND_PULL_POLICY "${BACKEND_PULL_POLICY}"

echo ">> Validating pinned production refs"
if [[ "${BACKEND_PULL_POLICY}" == "always" ]]; then
  ./ops/check-env-drift.sh prod
else
  echo "!! Skipping pinned-image drift gate for explicit local backend fallback"
fi

echo ">> Recreating backend only"
compose_prod up -d --no-deps backend

echo ">> Verifying backend image ref"
grep '^BACKEND_IMAGE=' .env.prod
grep '^BACKEND_PULL_POLICY=' .env.prod
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

echo ">> Reloading nginx to refresh backend upstream"
if docker ps --format '{{.Names}}' | grep -qx nginx; then
  ./ops/guard-nginx-reload.sh  # refuses a reload that would silently drop live V2 routing (cutover drift guard)
  docker exec nginx nginx -s reload
else
  echo ">> nginx container not running; skipping reload"
fi

if [[ "${SKIP_LIVE_SMOKE:-0}" != "1" ]]; then
  echo ">> Running live pilot readiness smoke"
  BASE_URL="${BASE_URL:-https://sealingai.com}" ./ops/smoke-live-pilot-readiness.sh
else
  echo ">> Live pilot readiness smoke skipped by SKIP_LIVE_SMOKE=1"
fi

echo ">> Done"
