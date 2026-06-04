#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/thorsten/sealai}"
BASE_URL="${BASE_URL:-https://sealingai.com}"
SKIP_FRONTEND_BUILD="${SKIP_FRONTEND_BUILD:-0}"
SKIP_LIVE_SMOKE="${SKIP_LIVE_SMOKE:-0}"

cd "${REPO_ROOT}"

section() {
  printf '\n== %s ==\n' "$1"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'FAIL: missing dependency: %s\n' "$1" >&2
    exit 1
  fi
}

need_cmd git
need_cmd bash
need_cmd npm
need_cmd curl
need_cmd jq

section "Repository"
git rev-parse --show-toplevel >/dev/null
printf 'branch: %s\n' "$(git branch --show-current)"
printf 'head: %s\n' "$(git rev-parse --short=8 HEAD)"

section "Ops script syntax"
bash -n ops/release-backend.sh
bash -n ops/release-frontend.sh
bash -n ops/promote-local-backend-image.sh
bash -n ops/check-domain-readiness.sh
bash -n ops/check-registry-readiness.sh
bash -n ops/issue-sealingai-cert.sh
bash -n ops/production-readiness-gate.sh
bash -n ops/smoke-live-pilot-readiness.sh
bash -n ops/stack_smoke.sh

section "Backend Phase-1 contract slice"
backend/.venv/bin/pytest \
  backend/tests/test_mvp_journey_contract.py \
  backend/app/agent/tests/test_case_workspace_projection.py \
  backend/tests/unit/services/test_rfq_preview_service.py \
  backend/app/api/tests/test_rfq_endpoint.py \
  backend/app/api/tests/test_rag_upload.py \
  backend/app/api/tests/test_rag_upload_limits.py \
  backend/app/api/tests/test_paperless_webhook.py \
  backend/tests/test_paperless_sync.py \
  backend/tests/agent/test_rag_injection.py \
  -q

section "Frontend lint and tests"
npm --prefix frontend run lint
npm --prefix frontend run test:run

if [[ "${SKIP_FRONTEND_BUILD}" != "1" ]]; then
  section "Frontend production build"
  npm --prefix frontend run build
else
  section "Frontend production build skipped"
  printf 'SKIP_FRONTEND_BUILD=1\n'
fi

if [[ "${SKIP_LIVE_SMOKE}" != "1" ]]; then
  section "Live pilot readiness smoke"
  BASE_URL="${BASE_URL}" ops/smoke-live-pilot-readiness.sh
else
  section "Live pilot readiness smoke skipped"
  printf 'SKIP_LIVE_SMOKE=1\n'
fi

section "Result"
printf 'OK: SeaLAI pilot readiness gate passed\n'
