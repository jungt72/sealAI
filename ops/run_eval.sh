#!/usr/bin/env bash
# Eval-REPLAY in the exact candidate image and resolved production Compose environment.
# Production data stores and tracing are explicitly disconnected; run artifacts are the
# only host-mounted output. This prevents host-venv and Compose-default profile drift.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

[[ -f .env.prod ]] || { echo "ops/run_eval.sh: .env.prod missing" >&2; exit 2; }
TREE_HASH="$(bash ops/tree-hash.sh)"
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
"${COMPOSE[@]}" run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  --entrypoint python \
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
  -v "${REPO_ROOT}/backend/sealai_v2/eval/runs:/app/sealai_v2/eval/runs" \
  backend-v2 -m sealai_v2.eval "$@"
