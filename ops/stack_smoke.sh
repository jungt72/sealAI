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

STACK_SERVICES=(backend keycloak redis)

ERROR_PREFIX="[stack-smoke]"

dump_diagnostics() {
  set +e
  set +o pipefail

  echo
  echo "=== docker compose ps ==="
  docker compose "${COMPOSE_ARGS[@]}" ps

  echo
  echo "=== docker compose logs (backend/keycloak/redis, tail 200) ==="
  docker compose "${COMPOSE_ARGS[@]}" logs --tail 200 backend keycloak redis

  echo
  echo "=== public backend health ==="
  curl -k -i -sS --max-time 10 https://sealai.net/api/agent/health || true

  echo
  echo "=== keycloak oidc metadata ==="
  curl -k -i -sS --max-time 10 https://auth.sealai.net/realms/sealAI/.well-known/openid-configuration || true

  echo
  echo "=== backend internal health ==="
  docker compose "${COMPOSE_ARGS[@]}" exec -T backend sh -lc 'curl -i -sS --max-time 5 http://127.0.0.1:8000/health' || true

  echo
  echo "=== backend internal api health path ==="
  docker compose "${COMPOSE_ARGS[@]}" exec -T backend sh -lc 'curl -i -sS --max-time 5 http://127.0.0.1:8000/api/agent/health' || true

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

check_services() {
  local service
  local running
  local healthy

  running="$(
    docker compose "${COMPOSE_ARGS[@]}" \
      ps --status running --format '{{.Service}}' backend keycloak redis
  )"

  healthy="$(
    docker compose "${COMPOSE_ARGS[@]}" \
      ps --format '{{.Service}} {{.Health}}' backend keycloak redis
  )"

  for service in "${STACK_SERVICES[@]}"; do
    if ! grep -Fxq "$service" <<< "$running"; then
      fail "services not running (missing $service)" "$CATEGORY_SERVICES"
    fi

    if grep -q "^${service} " <<< "$healthy"; then
      if ! grep -Eq "^${service} +(healthy|)$" <<< "$healthy"; then
        fail "service not healthy ($service)" "$CATEGORY_SERVICES"
      fi
    fi
  done
}

check_public_backend_health() {
  local url delim response http_code body

  url="https://sealai.net/api/agent/health"
  delim="__STACK_SMOKE_HTTP_CODE__"

  response="$(curl -k --max-time 10 -sS -w "${delim}%{http_code}" "$url")" || \
    fail "curl blocked/timeouts ($url)" "$CATEGORY_CURL"

  http_code="${response##*$delim}"
  body="${response%$delim*}"

  if [[ "$http_code" != "200" ]]; then
    fail "unexpected http code ($url returned $http_code)" "$CATEGORY_CURL"
  fi

  if [[ "$body" != "ok" ]] && [[ "$body" != *'"status":"ok"'* ]]; then
    fail "unexpected backend health body ($url returned: $body)" "$CATEGORY_CURL"
  fi
}

check_keycloak_oidc() {
  local url delim response http_code body

  url="https://auth.sealai.net/realms/sealAI/.well-known/openid-configuration"
  delim="__STACK_SMOKE_HTTP_CODE__"

  response="$(curl -k --max-time 10 -sS -w "${delim}%{http_code}" "$url")" || \
    fail "curl blocked/timeouts ($url)" "$CATEGORY_CURL"

  http_code="${response##*$delim}"
  body="${response%$delim*}"

  if [[ "$http_code" != "200" ]]; then
    fail "unexpected http code ($url returned $http_code)" "$CATEGORY_CURL"
  fi

  if [[ "$body" != *'"issuer"'* ]]; then
    fail "unexpected keycloak metadata body ($url missing issuer)" "$CATEGORY_CURL"
  fi
}

main() {
  check_services
  check_public_backend_health
  check_keycloak_oidc
  echo "$ERROR_PREFIX success: stack smoke tests passed"
}

main
