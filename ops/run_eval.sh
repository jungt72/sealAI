#!/bin/bash -p
# Eval-REPLAY in the exact candidate image and resolved production Compose environment.
# Production data stores and tracing are explicitly disconnected; run artifacts are the
# only host-mounted output. This prevents host-venv and Compose-default profile drift.
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

[[ -f .env.prod ]] || { echo "ops/run_eval.sh: .env.prod missing" >&2; exit 2; }
TREE_HASH="$(/bin/bash -p ops/tree-hash.sh)"
GIT_SHA="$(git rev-parse HEAD)"
EVAL_IMAGE="sealai-backend-v2:eval-${TREE_HASH:0:12}"
export BACKEND_V2_IMAGE="${EVAL_IMAGE}"
export BACKEND_V2_PULL_POLICY="never"
COMPOSE=(docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml --profile v2)

"${COMPOSE[@]}" build \
  --build-arg "GATE_TREE_HASH=${TREE_HASH}" \
  --build-arg "SOURCE_GIT_SHA=${GIT_SHA}" \
  backend-v2

mkdir -p backend/sealai_v2/eval/runs
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
"${COMPOSE[@]}" run --rm --no-deps \
  --user 0:0 \
  --entrypoint sh \
  -e "EVAL_HOST_UID=${HOST_UID}" \
  -e "EVAL_HOST_GID=${HOST_GID}" \
  -e SEALAI_V2_DATABASE_URL= \
  -e SEALAI_V2_QDRANT_URL= \
  -e QDRANT_URL= \
  -e LANGSMITH_TRACING=false \
  -e LANGCHAIN_TRACING_V2=false \
  -e LANGSMITH_API_KEY= \
  -e LANGCHAIN_API_KEY= \
  -e "SEALAI_EVAL_TREE_HASH=${TREE_HASH}" \
  -e "SEALAI_EVAL_GIT_SHA=${GIT_SHA}" \
  -e SEALAI_EVAL_DIRTY=false \
  -v "${REPO_ROOT}/backend/sealai_v2/eval:/app/sealai_v2/eval:ro" \
  -v "${REPO_ROOT}/backend/sealai_v2/eval/runs:/app/sealai_v2/eval/runs" \
  backend-v2 -c '
    set +e
    python -m sealai_v2.eval "$@"
    status=$?
    chown -R "${EVAL_HOST_UID}:${EVAL_HOST_GID}" /app/sealai_v2/eval/runs
    exit "${status}"
  ' sh "$@"
