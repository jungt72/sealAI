#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/thorsten/sealai}"
BASE_URL="${BASE_URL:-https://sealingai.com}"

cd "$REPO_ROOT"

section() {
  printf '\n== %s ==\n' "$1"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'FAIL: missing dependency: %s\n' "$1" >&2
    exit 1
  }
}

need_cmd bash
need_cmd curl
need_cmd dig
need_cmd docker
need_cmd jq
need_cmd openssl

section "Ops script syntax"
bash -n ops/release-backend.sh
bash -n ops/release-frontend.sh
bash -n ops/promote-local-backend-image.sh
bash -n ops/check-domain-readiness.sh
bash -n ops/check-registry-readiness.sh
bash -n ops/issue-sealingai-cert.sh
bash -n ops/smoke-live-pilot-readiness.sh

section "Live app smoke"
BASE_URL="$BASE_URL" ops/smoke-live-pilot-readiness.sh

section "Domain readiness"
ops/check-domain-readiness.sh

section "Registry readiness"
ops/check-registry-readiness.sh

section "Result"
printf 'OK: sealingAI production readiness gate passed\n'
