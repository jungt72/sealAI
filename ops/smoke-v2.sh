#!/bin/bash -p
# ops/smoke-v2.sh — V2 cutover smoke (staging Phase 2 + prod Phase 3 step 5).
#
#   BASE_URL=https://sealingai.com:8443 ./ops/smoke-v2.sh           # staging
#   BASE_URL=https://sealingai.com      ./ops/smoke-v2.sh           # prod (post-flip)
#   TOKEN=<bearer> ./ops/smoke-v2.sh                                # + authed leg
#
# Unauthed leg: SPA serving + CSP, /api/v2 health/framing, unauth chat → 401 (distinct messages
# for 502/503 misconfigurations), V1 regression (/, /api/health, Keycloak well-known).
# Authed leg (TOKEN set): chat round-trip, memory view (claim-alignment proof), briefing with
# Geltungsrahmen, forget-all cleanup.
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ops/lib/verified-tls.sh
source "${SCRIPT_DIR}/lib/verified-tls.sh"

BASE_URL="${BASE_URL:-https://sealingai.com}"
BASE_URL="${BASE_URL%/}"
WORK_DIR=""
BODY_FILE=""
HEADER_FILE=""
trap 'if [[ -n "${WORK_DIR}" ]]; then rm -rf -- "${WORK_DIR}"; fi' EXIT

pass() { printf 'PASS: %s\n' "$1"; }
fail() {
  printf 'FAIL: %s\n' "$1" >&2
  if [[ -s "${BODY_FILE}" ]]; then
    printf '%s\n' '--- response body excerpt ---' >&2
    sed -n '1,40p' "${BODY_FILE}" >&2 || true
  fi
  exit 1
}
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "missing dependency: $1"; }
need_cmd curl
need_cmd jq
need_cmd mktemp
sealai_configure_tls_client || exit $?
sealai_validate_https_origin "$BASE_URL" BASE_URL || exit $?
WORK_DIR="$(mktemp -d /tmp/sealai-v2-smoke.XXXXXX)"
BODY_FILE="${WORK_DIR}/body.txt"
HEADER_FILE="${WORK_DIR}/headers.txt"

request_code() {
  local method="$1" url="$2" data="${3:-}" auth="${4:-}"
  local args=("${SEALAI_CURL_TLS_ARGS[@]}" -sS --max-time 30 -D "${HEADER_FILE}" -o "${BODY_FILE}" -w '%{http_code}')
  [[ -n "$auth" ]] && args+=(-H "Authorization: Bearer ${auth}")
  if [[ "$method" == "GET" ]]; then
    curl "${args[@]}" "$url"
  else
    curl "${args[@]}" -X "$method" -H 'Content-Type: application/json' ${data:+-d "$data"} "$url"
  fi
}

# --- SPA serving --------------------------------------------------------------------------------
code="$(request_code GET "${BASE_URL}/dashboard")"
[[ "$code" == "308" ]] || fail "/dashboard expected 308, got ${code}"
grep -qi '^location: .*/dashboard/' "${HEADER_FILE}" || fail "/dashboard 308 missing Location → /dashboard/"
pass "/dashboard → 308 /dashboard/"

code="$(request_code GET "${BASE_URL}/dashboard/")"
[[ "$code" == "200" ]] || fail "/dashboard/ expected 200, got ${code}"
grep -qi '^content-security-policy: ' "${HEADER_FILE}" || fail "/dashboard/ missing CSP header"
grep -qi "default-src 'self'" "${HEADER_FILE}" || fail "/dashboard/ CSP not strict (no default-src 'self')"
sealai_assert_security_headers "$HEADER_FILE" true \
  || fail '/dashboard/ is missing required security headers'
pass "/dashboard/ → 200 + HSTS, strict CSP, XCTO, referrer, and permissions policy"

asset="$(grep -oE '/dashboard/assets/[A-Za-z0-9._-]+\.js' "${BODY_FILE}" | head -1 || true)"
[[ -n "$asset" ]] || fail "no /dashboard/assets/*.js reference in index.html (dist mounted? empty dir?)"
code="$(request_code GET "${BASE_URL}${asset}")"
[[ "$code" == "200" ]] || fail "asset ${asset} expected 200, got ${code}"
pass "SPA asset serves (${asset})"

code="$(request_code GET "${BASE_URL}/dashboard/new")"
[[ "$code" == "200" ]] || fail "/dashboard/new expected 200 (SPA try_files fallback), got ${code}"
pass "/dashboard/new → 200 (SPA fallback — V1 post-login target lands)"

# --- /api/v2 ------------------------------------------------------------------------------------
code="$(request_code GET "${BASE_URL}/api/v2/health")"
[[ "$code" == "200" ]] || fail "/api/v2/health expected 200, got ${code} (502 → backend-v2 down; 404 → flip not applied)"
jq -e '.status == "ok"' "${BODY_FILE}" >/dev/null || fail "/api/v2/health body not ok"
pass "/api/v2/health → 200 ok"

code="$(request_code GET "${BASE_URL}/api/v2/framing")"
[[ "$code" == "200" ]] || fail "/api/v2/framing expected 200, got ${code}"
jq -e '.claim_boundary | length > 0' "${BODY_FILE}" >/dev/null || fail "/api/v2/framing missing claim_boundary"
grep -qi '^cache-control: .*max-age' "${HEADER_FILE}" || fail "/api/v2/framing missing Cache-Control"
pass "/api/v2/framing → 200 + claim_boundary"

code="$(request_code POST "${BASE_URL}/api/v2/chat" '{"message":"smoke"}')"
case "$code" in
  401) pass "unauth /api/v2/chat → 401 (fail-closed)" ;;
  503) fail "unauth /api/v2/chat → 503: auth env MISSING on backend-v2 (SEALAI_V2_AUTH_* not set)" ;;
  502) fail "unauth /api/v2/chat → 502: backend-v2 not running/unreachable" ;;
  *) fail "unauth /api/v2/chat expected 401, got ${code}" ;;
esac

# --- V1 regression (the flip must not touch these) -----------------------------------------------
code="$(request_code GET "${BASE_URL}/")"
[[ "$code" == "200" ]] || fail "V1 / expected 200, got ${code}"
pass "V1 / → 200"

code="$(request_code GET "${BASE_URL}/api/health")"
[[ "$code" == "200" ]] || fail "V1 /api/health expected 200, got ${code}"
pass "V1 /api/health → 200"

code="$(request_code GET "${BASE_URL}/realms/sealAI/.well-known/openid-configuration")"
[[ "$code" == "200" ]] || fail "Keycloak well-known expected 200, got ${code}"
jq -e '.issuer' "${BODY_FILE}" >/dev/null || fail "well-known has no issuer"
pass "Keycloak well-known → 200"

# --- authed leg (claim alignment + domain round-trip) ---------------------------------------------
if [[ -n "${TOKEN:-}" ]]; then
  code="$(request_code GET "${BASE_URL}/api/v2/conversations/current/memory" '' "${TOKEN}")"
  [[ "$code" == "200" ]] || fail "authed memory view expected 200, got ${code} (401 → aud/iss/tenant_id/kid claim mismatch)"
  pass "authed memory view → 200 (token claims align: aud/iss/exp/tenant_id/sid/sub)"

  code="$(request_code POST "${BASE_URL}/api/v2/chat" '{"message":"Welche Werkstoffe kommen für einen RWDR mit Hydrauliköl in Frage?"}' "${TOKEN}")"
  [[ "$code" == "200" ]] || fail "authed chat expected 200, got ${code}"
  jq -e 'has("answer") and has("grounded") and has("citations")' "${BODY_FILE}" >/dev/null \
    || fail "chat response missing answer/grounded/citations"
  pass "authed chat → 200 with answer/grounded/citations"

  code="$(request_code POST "${BASE_URL}/api/v2/briefing" '{"message":"RWDR, Hydrauliköl, 80°C"}' "${TOKEN}")"
  [[ "$code" == "200" ]] || fail "authed briefing expected 200, got ${code}"
  jq -e '.body | contains("Geltungsrahmen")' "${BODY_FILE}" >/dev/null || fail "briefing missing Geltungsrahmen note"
  pass "authed briefing → 200 with Geltungsrahmen"

  code="$(request_code DELETE "${BASE_URL}/api/v2/conversations/current" '' "${TOKEN}")"
  [[ "$code" == "200" ]] || fail "forget-all cleanup expected 200, got ${code}"
  pass "forget-all cleanup → 200"
else
  echo ">> TOKEN not set — authed leg skipped (set TOKEN=<bearer> for the full smoke)"
fi

echo "OK: V2 smoke green (${BASE_URL})"
