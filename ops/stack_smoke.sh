#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

COMPOSE_ARGS=(
  --project-directory "$REPO_ROOT"
  -f "$REPO_ROOT/docker-compose.yml"
  -f "$REPO_ROOT/docker-compose.deploy.yml"
)

CATEGORY_SERVICES=11
CATEGORY_LISTENERS=22
CATEGORY_CURL=33

STACK_SERVICES=(backend frontend)
LISTENER_PORTS=(3000 8000)

ERROR_PREFIX="[stack-smoke]"

dump_diagnostics() {
  set +e
  set +o pipefail
  echo
  echo "=== docker compose ps ==="
  docker compose "${COMPOSE_ARGS[@]}" ps
  echo
  echo "=== docker compose logs (backend/frontend, tail 200) ==="
  docker compose "${COMPOSE_ARGS[@]}" logs --tail 200 backend frontend
  echo
  echo "=== ufw status verbose ==="
  ufw status verbose || true
  echo
  echo "=== iptables DOCKER-USER (first 40 lines) ==="
  iptables -L DOCKER-USER -n --line-numbers | sed -n '1,40p' || true
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
ensure_command ss
ensure_command curl
ensure_command ufw
ensure_command iptables

check_services() {
  local service
  local running
  running=$(
    docker compose "${COMPOSE_ARGS[@]}" \
      ps --status running --format '{{.Service}}' backend frontend
  )

  for service in "${STACK_SERVICES[@]}"; do
    if ! grep -Fxq "$service" <<< "$running"; then
      fail "services not running (missing $service)" "$CATEGORY_SERVICES"
    fi
  done
}

check_listeners() {
  local port
  local listener
  listener=$(ss -lntp)

  for port in "${LISTENER_PORTS[@]}"; do
    if ! grep -q ":${port}[[:space:]]" <<< "$listener" && ! grep -q ":${port}$" <<< "$listener"; then
      fail "listeners missing for :${port}" "$CATEGORY_LISTENERS"
    fi
  done
}

check_health() {
  local url expected
  local delim="__STACK_SMOKE_HTTP_CODE__"
  local response
  local http_code
  local body

  url="http://127.0.0.1:3000/api/health"
  expected="ok"
  response=$(curl --max-time 5 -sS -w "${delim}%{http_code}" "$url") || \
    fail "curl blocked/timeouts ($url)" "$CATEGORY_CURL"
  http_code="${response##*$delim}"
  body="${response%$delim*}"
  if [[ "$http_code" != "200" ]]; then
    fail "curl blocked/timeouts ($url returned $http_code)" "$CATEGORY_CURL"
  fi
  if ! grep -qi "$expected" <<< "$body"; then
    fail "curl blocked/timeouts (unexpected response from $url)" "$CATEGORY_CURL"
  fi

  url="http://127.0.0.1:8000/api/v1/langgraph/health"
  response=$(curl --max-time 5 -sS -w "${delim}%{http_code}" "$url") || \
    fail "curl blocked/timeouts ($url)" "$CATEGORY_CURL"
  http_code="${response##*$delim}"
  if [[ "$http_code" != "200" ]]; then
    fail "curl blocked/timeouts ($url returned $http_code)" "$CATEGORY_CURL"
  fi
}

main() {
  check_services
  check_listeners
  check_health
  echo "$ERROR_PREFIX success: stack smoke tests passed"
}

main
