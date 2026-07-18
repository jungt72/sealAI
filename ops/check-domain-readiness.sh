#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

DOMAIN="${DOMAIN:-sealingai.com}"
WWW_DOMAIN="${WWW_DOMAIN:-www.${DOMAIN}}"
EXPECTED_A="${EXPECTED_A:-49.13.233.145}"

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

assert_dns_points_to_expected_a() {
  local host="$1"
  local records
  records="$(dig +short "$host" A | sed '/^$/d' | sort -u)"
  if ! grep -qx "$EXPECTED_A" <<<"$records"; then
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
  code="$(curl -k -sS --max-time 15 -o /dev/null -w '%{http_code}' "https://${host}/")"
  case "$code" in
    200|301|302|307|308) pass "https://${host}/ returns ${code}" ;;
    *) fail "https://${host}/ returns ${code}" ;;
  esac
}

assert_cert_san() {
  local host="$1"
  local cert
  cert="$(openssl s_client -connect "${DOMAIN}:443" -servername "$host" </dev/null 2>/dev/null \
    | openssl x509 -noout -ext subjectAltName 2>/dev/null)"
  if ! grep -q "DNS:${host}" <<<"$cert"; then
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
assert_cert_san "$DOMAIN"
assert_cert_san "$WWW_DOMAIN"

printf 'OK: domain readiness passed\n'
