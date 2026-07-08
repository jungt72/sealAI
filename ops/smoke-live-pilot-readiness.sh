#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://sealingai.com}"
BASE_URL="${BASE_URL%/}"
TMP_DIR="${TMPDIR:-/tmp}"
BODY_FILE="${TMP_DIR}/sealai-live-smoke-body.$$"
HEADER_FILE="${TMP_DIR}/sealai-live-smoke-headers.$$"
trap 'rm -f "${BODY_FILE}" "${HEADER_FILE}"' EXIT

pass() { printf 'PASS: %s\n' "$1"; }
fail() {
  printf 'FAIL: %s\n' "$1" >&2
  if [[ -s "${BODY_FILE}" ]]; then
    printf '%s\n' '--- response body excerpt ---' >&2
    sed -n '1,80p' "${BODY_FILE}" >&2 || true
  fi
  exit 1
}
need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing dependency: $1"
}

need_cmd curl
need_cmd jq

request_code() {
  local method="$1"
  local url="$2"
  local data="${3:-}"
  if [[ "$method" == "GET" ]]; then
    curl -k -sS --max-time 15 -D "${HEADER_FILE}" -o "${BODY_FILE}" -w '%{http_code}' "$url"
  else
    curl -k -sS --max-time 15 -D "${HEADER_FILE}" -o "${BODY_FILE}" -w '%{http_code}' \
      -X "$method" \
      -H 'Content-Type: application/json' \
      -d "$data" \
      "$url"
  fi
}

assert_code() {
  local method="$1"
  local path="$2"
  local expected="$3"
  local data="${4:-}"
  local code
  code="$(request_code "$method" "${BASE_URL}${path}" "$data")" || fail "$method $path request failed"
  if [[ "$code" != "$expected" ]]; then
    fail "$method $path -> $code, expected $expected"
  fi
  pass "$method $path -> $code"
}

assert_code_any() {
  local method="$1"
  local path="$2"
  local expected_csv="$3"
  local data="${4:-}"
  local code
  code="$(request_code "$method" "${BASE_URL}${path}" "$data")" || fail "$method $path request failed"
  IFS=',' read -r -a expected_codes <<< "$expected_csv"
  for expected in "${expected_codes[@]}"; do
    if [[ "$code" == "$expected" ]]; then
      pass "$method $path -> $code"
      return 0
    fi
  done
  fail "$method $path -> $code, expected one of $expected_csv"
}

assert_json_field() {
  local jq_expr="$1"
  local label="$2"
  if jq -e "$jq_expr" "${BODY_FILE}" >/dev/null; then
    pass "$label"
  else
    fail "$label"
  fi
}

assert_no_legacy_domain() {
  local label="$1"
  if grep -Eqi 'sealai\.net|auth\.sealai\.net' "${HEADER_FILE}" "${BODY_FILE}" 2>/dev/null; then
    fail "${label} contains legacy sealai.net reference"
  fi
  pass "${label} contains no legacy sealai.net reference"
}

printf 'SeaLAI live pilot readiness smoke (%s)\n' "$BASE_URL"

assert_code GET /api/health 200
assert_json_field '.status == "ok"' 'frontend API health reports ok'

assert_code GET /api/v2/health 200
assert_json_field '.status == "ok"' 'backend-v2 health reports ok'

assert_code_any GET /dashboard/new '200,302,307,308'
assert_no_legacy_domain 'dashboard auth boundary'
# frontend-v2 is a client-rendered Vite SPA: the server-side HTML shell never
# contains brand strings, a Next.js "__next" marker, or a server-redirected
# /login URL — auth happens client-side after the bundle loads. The stable
# markers are the Vite build output path and the SPA's mount node.
if grep -Eq '/dashboard/assets/|id="root"' "${BODY_FILE}"; then
  pass 'dashboard route serves the app SPA shell'
else
  fail 'dashboard route did not expose expected SPA shell marker'
fi

# The Next.js BFF route layer (agent/chat/stream, workspace, rag, rfq) was intentionally
# and fully removed in fb98ab5a (V2 cutover — the dashboard calls /api/v2 directly now).
# nginx has no /api/bff/ location either, so these correctly 410 via the generic /api/
# catch-all. Assert they stay retired rather than expecting the old 401 auth-boundary.
assert_code_any POST /api/bff/agent/chat/stream '404,410' '{"message":"smoke from pilot readiness"}'
assert_code_any GET /api/bff/workspace/smoke-case '404,410'
assert_code_any GET /api/bff/agent/chat/history/smoke-case '404,410'
assert_code_any GET /api/bff/rfq/smoke-case/preview '404,410'
assert_code_any GET /api/bff/rag/documents '404,410'

assert_code_any GET /api/langgraph/state?thread_id=smoke '404,410'
assert_code_any POST /api/langgraph/parameters/patch '404,410' '{"chat_id":"smoke","parameters":{"pressure_bar":1}}'

printf 'OK: SeaLAI live pilot readiness smoke passed\n'
