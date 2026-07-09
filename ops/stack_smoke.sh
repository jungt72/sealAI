#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

COMPOSE_ARGS=(
  --env-file "$REPO_ROOT/.env.prod"
  --project-directory "$REPO_ROOT"
  -f "$REPO_ROOT/docker-compose.yml"
  -f "$REPO_ROOT/docker-compose.deploy.yml"
)

CATEGORY_SERVICES=11
CATEGORY_CURL=33

STACK_SERVICES=(backend-v2 keycloak redis)

ERROR_PREFIX="[stack-smoke]"
SERVICE_ATTEMPTS="${STACK_SMOKE_SERVICE_ATTEMPTS:-45}"
SERVICE_SLEEP_SECONDS="${STACK_SMOKE_SERVICE_SLEEP_SECONDS:-2}"
HTTP_ATTEMPTS="${STACK_SMOKE_HTTP_ATTEMPTS:-45}"
HTTP_SLEEP_SECONDS="${STACK_SMOKE_HTTP_SLEEP_SECONDS:-2}"
KEYCLOAK_OIDC_URL="${KEYCLOAK_OIDC_URL:-https://sealingai.com/realms/sealAI/.well-known/openid-configuration}"

dump_diagnostics() {
  set +e
  set +o pipefail

  echo
  echo "=== docker compose ps ==="
  docker compose "${COMPOSE_ARGS[@]}" ps

  echo
  echo "=== docker compose logs (backend-v2/keycloak/redis, tail 200) ==="
  docker compose "${COMPOSE_ARGS[@]}" --profile v2 logs --tail 200 backend-v2 keycloak redis

  echo
  echo "=== public backend health ==="
  curl -k -i -sS --max-time 10 https://sealingai.com/api/v2/health || true

  echo
  echo "=== keycloak oidc metadata ==="
  curl -k -i -sS --max-time 10 "$KEYCLOAK_OIDC_URL" || true

  echo
  echo "=== backend-v2 internal health ==="
  docker compose "${COMPOSE_ARGS[@]}" --profile v2 exec -T backend-v2 sh -lc 'curl -i -sS --max-time 5 http://127.0.0.1:8001/health' || true

  if command -v ufw >/dev/null 2>&1; then
    echo
    echo "=== ufw status verbose ==="
    ufw status verbose || true
  fi

  if command -v iptables >/dev/null 2>&1; then
    echo
    echo "=== iptables DOCKER-USER (first 40 lines) ==="
    iptables -L DOCKER-USER -n --line-numbers | sed -n '1,40p' || true
  fi

  echo
  set -o pipefail
  set -euo pipefail
}

fail() {
  local message=$1
  local code=$2
  echo "$ERROR_PREFIX failure: $message" >&2
  dump_diagnostics
  exit "$code"
}

ensure_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$ERROR_PREFIX fatal: missing dependency $1" >&2
    exit 1
  fi
}

ensure_command docker
ensure_command curl

services_ready() {
  local service
  local running
  local healthy

  running="$(
      docker compose "${COMPOSE_ARGS[@]}" --profile v2 \
      ps --status running --format '{{.Service}}' backend-v2 keycloak redis
  )"

  healthy="$(
    docker compose "${COMPOSE_ARGS[@]}" --profile v2 \
      ps --format '{{.Service}} {{.Health}}' backend-v2 keycloak redis
  )"

  for service in "${STACK_SERVICES[@]}"; do
    if ! grep -Fxq "$service" <<< "$running"; then
      return 1
    fi

    if grep -q "^${service} " <<< "$healthy"; then
      if ! grep -Eq "^${service} +(healthy|)$" <<< "$healthy"; then
        return 1
      fi
    fi
  done

  return 0
}

check_services() {
  local attempt

  for ((attempt = 1; attempt <= SERVICE_ATTEMPTS; attempt++)); do
    if services_ready; then
      return 0
    fi

    if [[ "$attempt" -lt "$SERVICE_ATTEMPTS" ]]; then
      echo "$ERROR_PREFIX waiting for services (${attempt}/${SERVICE_ATTEMPTS})"
      sleep "$SERVICE_SLEEP_SECONDS"
    fi
  done

  fail "services not running or not healthy after wait" "$CATEGORY_SERVICES"
}

http_get_with_retries() {
  local url delim response http_code body
  local expected_body_fragment=$2
  local description=$3
  local attempt

  url=$1
  delim="__STACK_SMOKE_HTTP_CODE__"

  for ((attempt = 1; attempt <= HTTP_ATTEMPTS; attempt++)); do
    response="$(curl -k --max-time 10 -sS -w "${delim}%{http_code}" "$url")" || response=""

    if [[ -n "$response" && "$response" == *"$delim"* ]]; then
      http_code="${response##*$delim}"
      body="${response%$delim*}"

      if [[ "$http_code" == "200" && "$body" == *"$expected_body_fragment"* ]]; then
        return 0
      fi
    fi

    if [[ "$attempt" -lt "$HTTP_ATTEMPTS" ]]; then
      echo "$ERROR_PREFIX waiting for $description (${attempt}/${HTTP_ATTEMPTS})"
      sleep "$HTTP_SLEEP_SECONDS"
    fi
  done

  fail "unexpected or unavailable $description ($url)" "$CATEGORY_CURL"
}

check_public_backend_health() {
  http_get_with_retries \
    "https://sealingai.com/api/v2/health" \
    '"status":"ok"' \
    "public backend health"
}

check_keycloak_oidc() {
  http_get_with_retries \
    "$KEYCLOAK_OIDC_URL" \
    '"issuer"' \
    "keycloak oidc metadata"
}

main() {
  check_services
  check_public_backend_health
  check_keycloak_oidc
  echo "$ERROR_PREFIX success: stack smoke tests passed"
}

main
