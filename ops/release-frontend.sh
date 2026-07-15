#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=production-release-gate-check.sh
source "${SCRIPT_DIR}/production-release-gate-check.sh"
production_release_gate_check "${SCRIPT_DIR}/production_release_gate.py" deploy
# shellcheck source=production-storage-lease.sh
source /usr/local/libexec/sealai/production-storage-lease.sh
acquire_production_storage_lease

cd /home/thorsten/sealai

/bin/bash -p "${SCRIPT_DIR}/validate-production-compose-security.sh" \
  /home/thorsten/sealai/.env.prod

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

echo ">> Preparing frontend build env file (frontend/.env.production.local)"
awk -F= '
  BEGIN {
    wanted["NEXT_PUBLIC_SITE_URL"] = 1
    wanted["NEXT_PUBLIC_ANALYTICS_ENABLED"] = 1
    wanted["NEXT_PUBLIC_GTM_ID"] = 1
    wanted["NEXT_PUBLIC_GA_MEASUREMENT_ID"] = 1
    wanted["NEXT_PUBLIC_GOOGLE_CONSENT_DEFAULT"] = 1
    wanted["SITE_URL"] = 1
    wanted["NEXT_PUBLIC_API_BASE"] = 1
    wanted["NEXTAUTH_URL"] = 1
    wanted["AUTH_URL"] = 1
    wanted["AUTH_TRUST_HOST"] = 1
    wanted["KEYCLOAK_ISSUER"] = 1
    wanted["SEALAI_BACKEND_ORIGIN"] = 1
    wanted["FRONTEND_BIND_HOST"] = 1
  }
  /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
  {
    key = $1
    sub(/^[[:space:]]+/, "", key)
    sub(/[[:space:]]+$/, "", key)
    if (wanted[key]) print
  }
' .env.prod > frontend/.env.production.local

if grep -q 'sealai\.net' frontend/.env.production.local; then
  echo "!! Refusing to build frontend with legacy sealai.net values in frontend/.env.production.local" >&2
  exit 1
fi

SHA="$(git rev-parse HEAD)"
SHORT_SHA="$(git rev-parse --short=8 HEAD)"
TS="$(date +%Y%m%d-%H%M%S)"
FRONTEND_IMAGE_TAG="ghcr.io/jungt72/sealai-frontend:${SHORT_SHA}-${TS}"

echo ">> Building ${FRONTEND_IMAGE_TAG}"
docker build \
  --file frontend/Dockerfile \
  --tag "${FRONTEND_IMAGE_TAG}" \
  frontend/

echo ">> Pushing ${FRONTEND_IMAGE_TAG}"
ROLLBACK_FILE=".env.prod.rollback-${TS}"
cp .env.prod "${ROLLBACK_FILE}"
echo ">> Rollback snapshot: ${ROLLBACK_FILE}"

if PUSH_OUTPUT="$(docker push "${FRONTEND_IMAGE_TAG}" 2>&1)"; then
  echo "${PUSH_OUTPUT}"
  FRONTEND_DIGEST="$(echo "${PUSH_OUTPUT}" | grep -oP 'digest: \K\S+' | tail -1)"
  test -n "${FRONTEND_DIGEST}"

  FRONTEND_IMAGE_REF="${FRONTEND_IMAGE_TAG}@${FRONTEND_DIGEST}"
  FRONTEND_PULL_POLICY="always"
  echo ">> New pinned image: ${FRONTEND_IMAGE_REF}"
else
  echo "${PUSH_OUTPUT}" >&2
  echo "!! GHCR push failed; mutable/local production image fallbacks are forbidden" >&2
  exit 1
fi

set_env_key FRONTEND_IMAGE "${FRONTEND_IMAGE_REF}"
set_env_key FRONTEND_PULL_POLICY "${FRONTEND_PULL_POLICY}"

echo ">> Validating pinned production refs"
/bin/bash -p ./ops/check-env-drift.sh prod

echo ">> Recreating frontend only"
compose_prod --profile frontend-container up -d --no-deps --force-recreate frontend

echo ">> Verifying frontend image ref"
grep '^FRONTEND_IMAGE=' .env.prod
grep '^FRONTEND_PULL_POLICY=' .env.prod
compose_prod --profile frontend-container ps frontend

echo ">> Waiting for frontend health"
for i in {1..30}; do
  if compose_prod --profile frontend-container exec -T frontend wget -qO- http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
    echo ">> Frontend healthy"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "!! Health check failed after 30 attempts — rolling back"
    cp "${ROLLBACK_FILE}" .env.prod
    compose_prod --profile frontend-container up -d --no-deps --force-recreate frontend
    echo "!! Rollback complete — recent frontend logs:"
    compose_prod --profile frontend-container logs frontend --tail 50
    exit 1
  fi
  echo ">> Frontend not ready yet (${i}/30)"
  sleep 2
done

compose_prod --profile frontend-container exec -T frontend wget -qO- http://127.0.0.1:3000/api/health

echo ">> Reloading nginx to refresh frontend upstream"
if docker ps --format '{{.Names}}' | grep -qx nginx; then
  /bin/bash -p ./ops/guard-nginx-reload.sh  # refuses a reload that would silently drop live V2 routing (cutover drift guard)
  docker exec nginx nginx -s reload
else
  echo ">> nginx container not running; skipping reload"
fi

if [[ "${SKIP_LIVE_SMOKE:-0}" != "1" ]]; then
  echo ">> Running live pilot readiness smoke"
  BASE_URL="${BASE_URL:-https://sealingai.com}" \
    /bin/bash -p ./ops/smoke-live-pilot-readiness.sh
else
  echo ">> Live pilot readiness smoke skipped by SKIP_LIVE_SMOKE=1"
fi

echo ">> Done"
