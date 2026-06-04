#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/thorsten/sealai}"
cd "$REPO_ROOT"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

pass() {
  printf 'PASS: %s\n' "$1"
}

warn() {
  printf 'WARN: %s\n' "$1" >&2
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing dependency: $1"
}

need_cmd docker

if [[ ! -f .env.prod ]]; then
  fail ".env.prod not found in ${REPO_ROOT}"
fi

BACKEND_IMAGE="$(grep '^BACKEND_IMAGE=' .env.prod | cut -d= -f2-)"
BACKEND_PULL_POLICY="$(grep '^BACKEND_PULL_POLICY=' .env.prod | cut -d= -f2- || true)"
BACKEND_PULL_POLICY="${BACKEND_PULL_POLICY:-always}"

if [[ -z "$BACKEND_IMAGE" ]]; then
  fail "BACKEND_IMAGE is missing in .env.prod"
fi

printf 'sealingAI registry readiness\n'
printf 'backend image: %s\n' "$BACKEND_IMAGE"
printf 'backend pull policy: %s\n' "$BACKEND_PULL_POLICY"

if [[ "$BACKEND_PULL_POLICY" != "always" ]]; then
  warn "backend pull policy is ${BACKEND_PULL_POLICY}; current deploy is VPS-local and not fully reproducible"
  printf 'Fix after GHCR scope is granted: ./ops/promote-local-backend-image.sh\n' >&2
  exit 1
fi

if [[ "$BACKEND_IMAGE" != *@sha256:* ]]; then
  fail "BACKEND_IMAGE is not pinned by digest"
fi
pass "BACKEND_IMAGE is pinned by digest"

BACKEND_IMAGE_TAG="${BACKEND_IMAGE%@sha256:*}"
if ! docker manifest inspect "$BACKEND_IMAGE_TAG" >/dev/null 2>&1; then
  fail "GHCR manifest is not reachable for ${BACKEND_IMAGE_TAG}"
fi
pass "GHCR manifest is reachable"

printf 'OK: registry readiness passed\n'
