#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ops/lib/verified-tls.sh
source "${SCRIPT_DIR}/lib/verified-tls.sh"

DOMAIN="${DOMAIN:-sealingai.com}"
WWW_DOMAIN="${WWW_DOMAIN:-www.${DOMAIN}}"
EXPECTED_A="${EXPECTED_A:-49.13.233.145}"
WORK_DIR=""
HEADER_FILE=""
trap 'if [[ -n "${WORK_DIR}" ]]; then rm -rf -- "${WORK_DIR}"; fi' EXIT

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

pass() {
  printf 'PASS: %s\n' "$1"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing dependency: $1"
}

need_cmd curl
need_cmd dig
need_cmd openssl
need_cmd mktemp
need_cmd timeout
sealai_configure_tls_client || exit $?
sealai_validate_hostname "$DOMAIN" DOMAIN || exit $?
sealai_validate_hostname "$WWW_DOMAIN" WWW_DOMAIN || exit $?
if [[ ! "$EXPECTED_A" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
  fail "EXPECTED_A is not an IPv4 address"
fi
WORK_DIR="$(mktemp -d /tmp/sealai-domain-readiness.XXXXXX)"
HEADER_FILE="${WORK_DIR}/headers.txt"

assert_dns_points_to_expected_a() {
  local host="$1"
  local records
  records="$(dig +short "$host" A \
    | awk '/^[0-9]{1,3}(\.[0-9]{1,3}){3}$/ { print }' \
    | sort -u)"
  if [[ "$records" != "$EXPECTED_A" ]]; then
    printf '%s\n' "$records" >&2
    if [[ "$host" == "$WWW_DOMAIN" ]]; then
      printf 'Set DNS: CNAME www -> %s, or A www -> %s\n' "$DOMAIN" "$EXPECTED_A" >&2
    fi
    fail "${host} A record does not point to ${EXPECTED_A}"
  fi
  pass "${host} A record points to ${EXPECTED_A}"
}

assert_https_reachable() {
  local host="$1"
  local code
  code="$(curl "${SEALAI_CURL_TLS_ARGS[@]}" -sS --max-time 15 \
    -D "$HEADER_FILE" -o /dev/null -w '%{http_code}' -- "https://${host}/")"
  case "$code" in
    200|301|302|307|308) ;;
    *) fail "https://${host}/ returns ${code}" ;;
  esac
  sealai_assert_security_headers "$HEADER_FILE" false \
    || fail "https://${host}/ is missing required security headers"
  pass "https://${host}/ returns ${code} with verified TLS and security headers"
}

assert_dashboard_headers() {
  local host="$1"
  local code
  code="$(curl "${SEALAI_CURL_TLS_ARGS[@]}" -sS --max-time 15 \
    -D "$HEADER_FILE" -o /dev/null -w '%{http_code}' -- "https://${host}/dashboard/")"
  [[ "$code" == "200" ]] || fail "https://${host}/dashboard/ returns ${code}, expected 200"
  sealai_assert_security_headers "$HEADER_FILE" true \
    || fail "https://${host}/dashboard/ is missing required dashboard security headers"
  pass "https://${host}/dashboard/ returns 200 with HSTS, CSP, XCTO, referrer, and permissions policy"
}

assert_cert_san() {
  local host="$1"
  local cert
  cert="$(timeout 15 openssl s_client "${SEALAI_OPENSSL_CA_ARGS[@]}" \
    -connect "${host}:443" -servername "$host" \
    -min_protocol TLSv1.2 -verify_return_error -verify_hostname "$host" \
    </dev/null 2>/dev/null \
    | openssl x509 -noout -ext subjectAltName 2>/dev/null)" \
    || fail "certificate chain or hostname verification failed for ${host}"
  if ! tr ',' '\n' <<<"$cert" \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
    | grep -Fqx -- "DNS:${host}"; then
    printf '%s\n' "$cert" >&2
    printf 'Run after DNS is correct: ./ops/issue-sealingai-cert.sh\n' >&2
    fail "certificate SAN does not include ${host}"
  fi
  pass "certificate SAN includes ${host}"
}

printf 'sealingAI domain readiness (%s, %s)\n' "$DOMAIN" "$WWW_DOMAIN"

assert_dns_points_to_expected_a "$DOMAIN"
assert_dns_points_to_expected_a "$WWW_DOMAIN"
assert_https_reachable "$DOMAIN"
assert_https_reachable "$WWW_DOMAIN"
assert_dashboard_headers "$DOMAIN"
assert_cert_san "$DOMAIN"
assert_cert_san "$WWW_DOMAIN"

printf 'OK: domain readiness passed\n'
