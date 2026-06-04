#!/usr/bin/env bash
set -euo pipefail

cd /home/thorsten/sealai

COMPOSE_ARGS=(
  --env-file .env.prod
  -f docker-compose.yml
  -f docker-compose.deploy.yml
)

set_env_key() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env.prod; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env.prod
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> .env.prod
  fi
}

BACKEND_IMAGE_REF="$(grep '^BACKEND_IMAGE=' .env.prod | cut -d= -f2-)"
BACKEND_IMAGE_TAG="${BACKEND_IMAGE_REF%@sha256:*}"
TS="$(date +%Y%m%d-%H%M%S)"

if [[ -z "$BACKEND_IMAGE_TAG" ]]; then
  echo "!! BACKEND_IMAGE is empty in .env.prod" >&2
  exit 1
fi

if ! docker image inspect "$BACKEND_IMAGE_TAG" >/dev/null 2>&1; then
  echo "!! Local backend image not found: ${BACKEND_IMAGE_TAG}" >&2
  exit 1
fi

echo ">> Promoting local backend image to GHCR: ${BACKEND_IMAGE_TAG}"
PUSH_OUTPUT="$(docker push "$BACKEND_IMAGE_TAG" 2>&1)" || {
  echo "$PUSH_OUTPUT" >&2
  echo "!! GHCR push failed. Run: gh auth refresh -h github.com -s write:packages" >&2
  exit 1
}
echo "$PUSH_OUTPUT"

BACKEND_DIGEST="$(echo "$PUSH_OUTPUT" | grep -oP 'digest: \K\S+' | tail -1)"
test -n "$BACKEND_DIGEST"

BACKEND_IMAGE_PINNED="${BACKEND_IMAGE_TAG}@${BACKEND_DIGEST}"
ROLLBACK_FILE=".env.prod.rollback-promote-${TS}"
cp .env.prod "$ROLLBACK_FILE"
echo ">> Rollback snapshot: ${ROLLBACK_FILE}"

set_env_key BACKEND_IMAGE "$BACKEND_IMAGE_PINNED"
set_env_key BACKEND_PULL_POLICY "always"

echo ">> Validating production refs"
./ops/check-env-drift.sh prod

echo ">> Recreating backend from pinned registry image"
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
  docker compose "${COMPOSE_ARGS[@]}" up -d --no-deps backend

echo ">> Waiting for backend health"
for i in {1..30}; do
  if docker exec backend sh -lc "curl -fsS http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    echo ">> Backend healthy"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "!! Health check failed after 30 attempts — rolling back"
    cp "$ROLLBACK_FILE" .env.prod
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
      docker compose "${COMPOSE_ARGS[@]}" up -d --no-deps backend
    exit 1
  fi
  echo ">> Backend not ready yet (${i}/30)"
  sleep 2
done

BASE_URL="${BASE_URL:-https://sealingai.com}" ./ops/smoke-live-pilot-readiness.sh

echo ">> Promoted backend image:"
grep -E '^(BACKEND_IMAGE|BACKEND_PULL_POLICY)=' .env.prod
