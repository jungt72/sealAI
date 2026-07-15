#!/bin/bash
# Shared fail-closed TLS client contract for operational verification scripts.
# This file is sourced; callers keep control of their own error formatting.

SEALAI_CURL_TLS_ARGS=(--proto '=https' --tlsv1.2)
SEALAI_OPENSSL_CA_ARGS=()

sealai_validate_hostname() {
  local hostname="$1"
  local label="${2:-hostname}"
  local dns_label
  local -a dns_labels

  if ((${#hostname} > 253)) \
    || [[ ! "$hostname" =~ ^[A-Za-z0-9.-]+$ ]] \
    || [[ "$hostname" == .* ]] \
    || [[ "$hostname" == *. ]] \
    || [[ "$hostname" == *..* ]]; then
    printf 'TLS configuration error: %s is not a valid DNS hostname\n' "$label" >&2
    return 2
  fi
  IFS='.' read -r -a dns_labels <<<"$hostname"
  for dns_label in "${dns_labels[@]}"; do
    if ((${#dns_label} < 1 || ${#dns_label} > 63)) \
      || [[ ! "$dns_label" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]]; then
      printf 'TLS configuration error: %s is not a valid DNS hostname\n' "$label" >&2
      return 2
    fi
  done
}

sealai_validate_https_url() {
  local value="$1"
  local label="${2:-URL}"
  local remainder authority hostname port

  if [[ "$value" != https://* ]] \
    || [[ "$value" == *[[:space:]]* ]] \
    || [[ "$value" == *\?* ]] \
    || [[ "$value" == *\#* ]]; then
    printf 'TLS configuration error: %s must be an HTTPS URL without whitespace, query, or fragment\n' "$label" >&2
    return 2
  fi

  remainder="${value#https://}"
  authority="${remainder%%/*}"
  if [[ -z "$authority" ]] || [[ "$authority" == *@* ]]; then
    printf 'TLS configuration error: %s must have a non-userinfo authority\n' "$label" >&2
    return 2
  fi
  if [[ ! "$authority" =~ ^[A-Za-z0-9.-]+(:[0-9]{1,5})?$ ]]; then
    printf 'TLS configuration error: %s has an invalid authority\n' "$label" >&2
    return 2
  fi

  hostname="${authority%%:*}"
  sealai_validate_hostname "$hostname" "${label} hostname" || return
  if [[ "$authority" == *:* ]]; then
    port="${authority##*:}"
    if ((10#$port < 1 || 10#$port > 65535)); then
      printf 'TLS configuration error: %s has an invalid port\n' "$label" >&2
      return 2
    fi
  fi
}

sealai_validate_https_origin() {
  local value="$1"
  local label="${2:-BASE_URL}"
  local remainder

  sealai_validate_https_url "$value" "$label" || return
  remainder="${value#https://}"
  if [[ "$remainder" == */* ]]; then
    printf 'TLS configuration error: %s must be an origin without a path\n' "$label" >&2
    return 2
  fi
}

sealai_validate_loopback_http_origin() {
  local value="$1"
  local label="${2:-BACKEND_BASE_URL}"
  local authority port

  if [[ "$value" != http://localhost* && "$value" != http://127.0.0.1* ]]; then
    printf 'TLS configuration error: %s may use HTTP only for an explicit loopback origin\n' "$label" >&2
    return 2
  fi
  authority="${value#http://}"
  if [[ "$authority" == */* ]] \
    || [[ "$authority" == *[[:space:]@?#]* ]] \
    || [[ ! "$authority" =~ ^(localhost|127\.0\.0\.1)(:[0-9]{1,5})?$ ]]; then
    printf 'TLS configuration error: %s is not a valid loopback origin\n' "$label" >&2
    return 2
  fi
  if [[ "$authority" == *:* ]]; then
    port="${authority##*:}"
    if ((10#$port < 1 || 10#$port > 65535)); then
      printf 'TLS configuration error: %s has an invalid port\n' "$label" >&2
      return 2
    fi
  fi
}

sealai_configure_tls_client() {
  local ca_file="${TLS_CA_FILE:-}"

  SEALAI_CURL_TLS_ARGS=(--proto '=https' --tlsv1.2)
  SEALAI_OPENSSL_CA_ARGS=()
  if [[ -z "$ca_file" ]]; then
    return 0
  fi
  if [[ "$ca_file" != /* ]] \
    || [[ ! -f "$ca_file" ]] \
    || [[ -L "$ca_file" ]] \
    || [[ ! -r "$ca_file" ]]; then
    printf 'TLS configuration error: TLS_CA_FILE must be an absolute, readable, regular, non-symlink file\n' >&2
    return 2
  fi
  SEALAI_CURL_TLS_ARGS+=(--cacert "$ca_file")
  SEALAI_OPENSSL_CA_ARGS+=(-CAfile "$ca_file")
}

sealai_assert_security_headers() {
  local header_file="$1"
  local require_csp="${2:-false}"

  if [[ ! -f "$header_file" ]]; then
    printf 'TLS verification error: response header file is missing\n' >&2
    return 1
  fi
  if ! LC_ALL=C grep -Eqi '^strict-transport-security:[[:space:]]*max-age=[1-9][0-9]*' "$header_file"; then
    printf 'TLS verification error: HSTS is missing or has a zero max-age\n' >&2
    return 1
  fi
  if ! LC_ALL=C grep -Eqi '^x-content-type-options:[[:space:]]*nosniff[[:space:]]*$' "$header_file"; then
    printf 'TLS verification error: X-Content-Type-Options nosniff is missing\n' >&2
    return 1
  fi
  if ! LC_ALL=C grep -Eqi '^referrer-policy:[[:space:]]*(no-referrer|strict-origin-when-cross-origin)[[:space:]]*$' "$header_file"; then
    printf 'TLS verification error: the approved Referrer-Policy is missing\n' >&2
    return 1
  fi
  if ! LC_ALL=C grep -Eqi '^permissions-policy:[[:space:]]*geolocation=\(\),[[:space:]]*microphone=\(\),[[:space:]]*camera=\(\)[[:space:]]*$' "$header_file"; then
    printf 'TLS verification error: the required Permissions-Policy is missing\n' >&2
    return 1
  fi
  if [[ "$require_csp" == "true" ]] \
    && ! LC_ALL=C grep -Eqi "^content-security-policy:.*default-src[[:space:]]+'self'" "$header_file"; then
    printf 'TLS verification error: the dashboard CSP is missing its approved default source\n' >&2
    return 1
  fi
}
