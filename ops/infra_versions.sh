#!/usr/bin/env bash
set -euo pipefail

OUT="docs/infra_versions.md"
mkdir -p "$(dirname "$OUT")"

now_utc="$(date -u +"%Y-%m-%d %H:%M:%S UTC")"
hostname_val="$(hostname)"

missing_tools=()

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

add_missing() {
  missing_tools+=("$1")
}

run_capture() {
  local output
  if output="$("$@" 2>&1)"; then
    printf '%s' "$output"
    return 0
  fi
  printf '%s' "$output"
  return 1
}

docker_available=0
docker_usable=0
docker_access_error=""
if command_exists docker; then
  docker_available=1
else
  add_missing "docker"
fi

docker_compose_available=0
if ((docker_available)) && docker compose version >/dev/null 2>&1; then
  docker_compose_available=1
fi

compose_ps_output="docker compose not available"
if ((docker_compose_available)); then
  if compose_ps_output=$(run_capture docker compose ps); then
    :
  else
    compose_ps_output="docker compose ps failed: ${compose_ps_output}"
  fi
fi

docker_ps_output="docker not available"
if ((docker_available)); then
  if docker_ps_output=$(run_capture docker ps); then
    docker_usable=1
  else
    docker_access_error="$docker_ps_output"
    docker_ps_output="docker ps failed: ${docker_ps_output}"
  fi
fi

images_output="docker not available"
if ((docker_usable)); then
  if images_output=$(run_capture docker images); then
    :
  else
    images_output="docker images failed: ${images_output}"
  fi
fi

container_running() {
  local name="$1"
  docker ps --format '{{.Names}}' | grep -Fx "$name" >/dev/null 2>&1
}

container_exists() {
  local name="$1"
  docker ps -a --format '{{.Names}}' | grep -Fx "$name" >/dev/null 2>&1
}

container_image() {
  local name="$1"
  local output
  output=$(run_capture docker ps -a --filter "name=^${name}$" --format '{{.Image}}' || true)
  printf '%s' "$output" | head -n1
}

container_ports() {
  local name="$1"
  local output
  output=$(run_capture docker ps --filter "name=^${name}$" --format '{{.Ports}}' || true)
  printf '%s' "$output" | head -n1
}

parse_psql_version() {
  awk '
    /PostgreSQL/ {
      if (index($0, "|")) {
        split($0, parts, "|")
        gsub(/^[ \t]+|[ \t]+$/, "", parts[2])
        print parts[2]
      } else {
        gsub(/^[ \t]+|[ \t]+$/, "", $0)
        print $0
      }
      exit
    }
  '
}

parse_redis_version() {
  awk 'match($0, /v=([0-9.]+)/, a) {print a[1]; exit}'
}

parse_qdrant_version_from_json() {
  if command_exists jq; then
    jq -r '.version // .version_string // .versionNumber // empty'
    return
  fi
  if command_exists python3; then
    python3 - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for key in ("version", "version_string", "versionNumber"):
    if key in data and data[key]:
        print(data[key])
        sys.exit(0)
PY
    return
  fi
  if command_exists python; then
    python - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for key in ("version", "version_string", "versionNumber"):
    if key in data and data[key]:
        print(data[key])
        sys.exit(0)
PY
    return
  fi
  return 1
}

strapi_service_defined="unknown"
if ((docker_compose_available)); then
  if services_output=$(run_capture docker compose config --services); then
    if echo "$services_output" | grep -Fxq "strapi"; then
      strapi_service_defined="yes"
    else
      strapi_service_defined="no"
    fi
  else
    strapi_service_defined="error: ${services_output}"
  fi
fi

postgres_version=""
postgres_cmd=""
postgres_note=""
if ((docker_usable)) && container_running "postgres"; then
  postgres_cmd="docker exec -it postgres psql -U postgres -c \"SELECT version();\""
  if out=$(run_capture docker exec -it postgres psql -U postgres -c "SELECT version();"); then
    postgres_version=$(printf '%s\n' "$out" | parse_psql_version)
  else
    postgres_note="first attempt failed: ${out}"
  fi
  if [[ -z "$postgres_version" ]]; then
    pg_user="$(run_capture docker exec postgres printenv POSTGRES_USER || true)"
    pg_db="$(run_capture docker exec postgres printenv POSTGRES_DB || true)"
    pg_user="${pg_user:-postgres}"
    pg_db="${pg_db:-postgres}"
    postgres_cmd="docker exec postgres psql -U ${pg_user} -d ${pg_db} -c \"SELECT version();\""
    if out=$(run_capture docker exec postgres psql -U "$pg_user" -d "$pg_db" -c "SELECT version();"); then
      postgres_version=$(printf '%s\n' "$out" | parse_psql_version)
    else
      postgres_note="fallback failed: ${out}"
    fi
  fi
elif ((docker_usable)) && container_exists "postgres"; then
  postgres_note="container exists but not running"
else
  if ((docker_available)) && ((docker_usable == 0)); then
    postgres_note="docker not accessible: ${docker_access_error}"
  else
    postgres_note="container not found"
  fi
fi

qdrant_version=""
qdrant_cmd=""
qdrant_note=""
if ((docker_usable)) && container_running "qdrant"; then
  qdrant_cmd="docker exec qdrant qdrant --version"
  if out=$(run_capture docker exec qdrant qdrant --version); then
    qdrant_version="$out"
  else
    qdrant_note="first attempt failed: ${out}"
  fi
elif ((docker_usable)) && container_exists "qdrant"; then
  qdrant_note="container exists but not running"
else
  if ((docker_available)) && ((docker_usable == 0)); then
    qdrant_note="docker not accessible: ${docker_access_error}"
  else
    qdrant_note="container not found"
  fi
fi

if [[ -z "$qdrant_version" ]]; then
  if command_exists curl; then
    qdrant_cmd="curl http://127.0.0.1:6333/"
    if out=$(run_capture curl -sS http://127.0.0.1:6333/); then
      if ! command_exists jq && ! command_exists python3 && ! command_exists python; then
        qdrant_note="no JSON parser available for qdrant response"
        add_missing "jq/python3/python"
      elif parsed=$(printf '%s' "$out" | parse_qdrant_version_from_json); then
        qdrant_version="$parsed"
      else
        qdrant_note="failed to parse version from JSON"
      fi
    else
      qdrant_note="curl failed: ${out}"
    fi
  else
    qdrant_note="curl not available for fallback"
    add_missing "curl"
  fi
fi

redis_version=""
redis_cmd=""
redis_note=""
if ((docker_usable)) && container_running "redis"; then
  redis_cmd="docker exec redis redis-server --version"
  if out=$(run_capture docker exec redis redis-server --version); then
    redis_version=$(printf '%s\n' "$out" | parse_redis_version)
  else
    redis_note="first attempt failed: ${out}"
  fi
  if [[ -z "$redis_version" ]]; then
    redis_cmd="docker exec redis redis-cli INFO server | grep redis_version"
    if out=$(run_capture docker exec redis redis-cli INFO server); then
      redis_version=$(printf '%s\n' "$out" | grep -m1 redis_version | awk -F: '{print $2}')
    else
      redis_note="fallback failed: ${out}"
    fi
  fi
elif ((docker_usable)) && container_exists "redis"; then
  redis_note="container exists but not running"
else
  if ((docker_available)) && ((docker_usable == 0)); then
    redis_note="docker not accessible: ${docker_access_error}"
  else
    redis_note="container not found"
  fi
fi

keycloak_version=""
keycloak_cmd=""
keycloak_note=""
if ((docker_usable)) && container_running "keycloak"; then
  keycloak_cmd="docker exec keycloak /opt/keycloak/bin/kc.sh --version"
  if out=$(run_capture docker exec keycloak /opt/keycloak/bin/kc.sh --version); then
    keycloak_version="$out"
  else
    keycloak_note="command failed: ${out}"
  fi
elif ((docker_usable)) && container_exists "keycloak"; then
  keycloak_note="container exists but not running"
else
  if ((docker_available)) && ((docker_usable == 0)); then
    keycloak_note="docker not accessible: ${docker_access_error}"
  else
    keycloak_note="container not found"
  fi
fi

strapi_version=""
strapi_cmd=""
strapi_note=""
if ((docker_usable)) && container_running "strapi"; then
  strapi_cmd="docker exec strapi node -p \"require('@strapi/strapi/package.json').version\""
  if out=$(run_capture docker exec strapi node -p "require('@strapi/strapi/package.json').version"); then
    strapi_version="$out"
  else
    strapi_note="command failed: ${out}"
  fi
elif ((docker_usable)) && container_exists "strapi"; then
  strapi_note="container exists but not running"
else
  strapi_pkg_path=""
  if [[ -f "strapi/package.json" ]]; then
    strapi_pkg_path="strapi/package.json"
  elif [[ -f "strapi-backend/package.json" ]]; then
    strapi_pkg_path="strapi-backend/package.json"
  fi

  if [[ -n "$strapi_pkg_path" ]]; then
    if command_exists python3; then
      strapi_cmd="python3 -c 'import json; ...' (${strapi_pkg_path})"
      strapi_version=$(python3 - <<PY
import json
from pathlib import Path
pkg = json.loads(Path("${strapi_pkg_path}").read_text())
for section in ("dependencies", "devDependencies", "peerDependencies"):
    deps = pkg.get(section) or {}
    for key in ("@strapi/strapi", "strapi"):
        if key in deps:
            print(deps[key])
            raise SystemExit(0)
raise SystemExit(1)
PY
) || strapi_note="failed to read version from ${strapi_pkg_path}"
    elif command_exists python; then
      strapi_cmd="python -c 'import json; ...' (${strapi_pkg_path})"
      strapi_version=$(python - <<PY
import json
from pathlib import Path
pkg = json.loads(Path("${strapi_pkg_path}").read_text())
for section in ("dependencies", "devDependencies", "peerDependencies"):
    deps = pkg.get(section) or {}
    for key in ("@strapi/strapi", "strapi"):
        if key in deps:
            print(deps[key])
            raise SystemExit(0)
raise SystemExit(1)
PY
) || strapi_note="failed to read version from ${strapi_pkg_path}"
    elif command_exists jq; then
      strapi_cmd="jq (${strapi_pkg_path})"
      strapi_version=$(jq -r '.dependencies["@strapi/strapi"] // .dependencies.strapi // .devDependencies["@strapi/strapi"] // .devDependencies.strapi // .peerDependencies["@strapi/strapi"] // .peerDependencies.strapi // empty' "${strapi_pkg_path}")
      if [[ -z "$strapi_version" ]]; then
        strapi_note="failed to read version from ${strapi_pkg_path}"
      fi
    else
      strapi_note="no parser available for ${strapi_pkg_path}"
      add_missing "python3/python/jq"
    fi
  else
    if ((docker_available)) && ((docker_usable == 0)); then
      strapi_note="docker not accessible: ${docker_access_error}"
    else
      strapi_note="not in stack (no container, no ./strapi or ./strapi-backend)"
    fi
  fi
fi

postgres_image=""
postgres_ports=""
qdrant_image=""
qdrant_ports=""
redis_image=""
redis_ports=""
keycloak_image=""
keycloak_ports=""
strapi_image=""
strapi_ports=""

if ((docker_usable)); then
  postgres_image=$(container_image "postgres")
  postgres_ports=$(container_ports "postgres")
  qdrant_image=$(container_image "qdrant")
  qdrant_ports=$(container_ports "qdrant")
  redis_image=$(container_image "redis")
  redis_ports=$(container_ports "redis")
  keycloak_image=$(container_image "keycloak")
  keycloak_ports=$(container_ports "keycloak")
  strapi_image=$(container_image "strapi")
  strapi_ports=$(container_ports "strapi")
fi

{
  echo "# Infra Versions"
  echo
  echo "Generated: ${now_utc}"
  echo "Host: ${hostname_val}"
  echo
  echo "## Container inventory"
  echo "### docker compose ps"
  echo '```'
  echo "$compose_ps_output"
  echo '```'
  echo "### docker ps"
  echo '```'
  echo "$docker_ps_output"
  echo '```'
  echo "### docker images"
  echo '```'
  echo "$images_output"
  echo '```'
  echo
  echo "## Services"
  echo "### Postgres"
  echo "- Container: postgres"
  echo "- Image: ${postgres_image:-not found}"
  echo "- Ports: ${postgres_ports:-not running}"
  echo "- Running version: ${postgres_version:-unknown}"
  echo "- Command/Query: ${postgres_cmd:-not executed}"
  if [[ -n "$postgres_note" ]]; then
    echo "- Notes: ${postgres_note}"
  fi
  echo
  echo "### Qdrant"
  echo "- Container: qdrant"
  echo "- Image: ${qdrant_image:-not found}"
  echo "- Ports: ${qdrant_ports:-not running}"
  echo "- Running version: ${qdrant_version:-unknown}"
  echo "- Command/Query: ${qdrant_cmd:-not executed}"
  if [[ -n "$qdrant_note" ]]; then
    echo "- Notes: ${qdrant_note}"
  fi
  echo
  echo "### Redis"
  echo "- Container: redis"
  echo "- Image: ${redis_image:-not found}"
  echo "- Ports: ${redis_ports:-not running}"
  echo "- Running version: ${redis_version:-unknown}"
  echo "- Command/Query: ${redis_cmd:-not executed}"
  if [[ -n "$redis_note" ]]; then
    echo "- Notes: ${redis_note}"
  fi
  echo
  echo "### Keycloak"
  echo "- Container: keycloak"
  echo "- Image: ${keycloak_image:-not found}"
  echo "- Ports: ${keycloak_ports:-not running}"
  echo "- Running version: ${keycloak_version:-unknown}"
  echo "- Command/Query: ${keycloak_cmd:-not executed}"
  if [[ -n "$keycloak_note" ]]; then
    echo "- Notes: ${keycloak_note}"
  fi
  echo "- Image tag (from docker ps): ${keycloak_image:-unknown}"
  echo
  echo "### Strapi"
  echo "- Container: strapi"
  echo "- Image: ${strapi_image:-not found}"
  echo "- Ports: ${strapi_ports:-not running}"
  echo "- Running version: ${strapi_version:-unknown}"
  echo "- Command/Query: ${strapi_cmd:-not executed}"
  echo "- Service defined in compose: ${strapi_service_defined}"
  if [[ -n "$strapi_note" ]]; then
    echo "- Notes: ${strapi_note}"
  fi
  if ((${#missing_tools[@]})); then
    echo
    echo "## Missing tools"
    printf '%s\n' "${missing_tools[@]}"
  fi
} > "$OUT"

printf 'Infra versions written to %s\n' "$OUT"

printf '\nSummary (running versions):\n'
printf 'Postgres: %s\n' "${postgres_version:-unknown}"
printf 'Qdrant: %s\n' "${qdrant_version:-unknown}"
printf 'Redis: %s\n' "${redis_version:-unknown}"
printf 'Keycloak: %s\n' "${keycloak_version:-unknown}"
printf 'Strapi: %s\n' "${strapi_version:-unknown}"
