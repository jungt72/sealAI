#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

usage() {
  cat <<'EOF'
Usage: check-env-drift.sh MODE
  MODE must be "dev" or "prod". The script validates required keys in .env.MODE,
  rejects placeholder values in production, validates pinned production image
  references, and in dev mode checks that NEXTAUTH_SECRET in the root .env (if
  present) still matches .env.dev.
EOF
}

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 2
fi

MODE=$1
if [[ "$MODE" != "dev" && "$MODE" != "prod" ]]; then
  usage >&2
  exit 2
fi

ENV_FILE="$REPO_ROOT/.env"
SOURCE_FILE="$REPO_ROOT/.env.$MODE"

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "fatal: expected $SOURCE_FILE to exist (mode: $MODE)" >&2
  exit 1
fi

extract_key() {
  local file=$1
  local key=$2
  /usr/bin/python3 -I - "$file" "$key" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
needle = sys.argv[2]
value_out = None
with path.open() as fh:
    for raw in fh:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != needle:
            continue
        value_out = value.strip()
        if (value_out.startswith('"') and value_out.endswith('"')) or (value_out.startswith("'") and value_out.endswith("'")):
            value_out = value_out[1:-1]
        print(value_out, end="")
        break

if value_out is None:
    raise SystemExit(1)
PY
}

validate_required_keys() {
  local file=$1
  shift
  local key value

  for key in "$@"; do
    if ! value="$(extract_key "$file" "$key")"; then
      echo "fatal: $key not set in $file" >&2
      exit 1
    fi
    if [[ -z "$value" ]]; then
      echo "fatal: $key is empty in $file" >&2
      exit 1
    fi
    if [[ "$MODE" == "prod" && ( "$value" == *"REPLACE"* || "$value" == *"CHANGE_ME"* || "$value" == *"<SET"* || "$value" == "SET_IN_SECRET_STORE" ) ]]; then
      echo "fatal: $key in $file still uses a placeholder value" >&2
      exit 1
    fi
  done
}

validate_image_ref() {
  local file=$1
  local key=$2
  local repository=$3
  local value

  if ! value="$(extract_key "$file" "$key")"; then
    echo "fatal: $key not set in $file" >&2
    exit 1
  fi
  if ! /usr/bin/python3 -I - "$value" "$repository" <<'PY'
import re
import sys

value, repository = sys.argv[1:]
pattern = re.escape(repository) + r":[A-Za-z0-9][A-Za-z0-9._-]{0,127}@sha256:[0-9a-f]{64}"
raise SystemExit(0 if re.fullmatch(pattern, value) else 1)
PY
  then
    echo "fatal: $key in $file must use exact repository ${repository} and tag@sha256 digest" >&2
    exit 1
  fi
}

validate_scoped_credential() {
  local file=$1
  local key=$2
  local value

  if ! value="$(extract_key "$file" "$key")"; then
    echo "fatal: $key not set in $file" >&2
    exit 1
  fi
  if [[ ! "$value" =~ ^[A-Za-z0-9._~-]{32,256}$ ]]; then
    echo "fatal: $key must use the scoped base64url-safe credential contract" >&2
    exit 1
  fi
}

validate_database_identifier() {
  local file=$1
  local key=$2
  local value

  if ! value="$(extract_key "$file" "$key")"; then
    echo "fatal: $key not set in $file" >&2
    exit 1
  fi
  if [[ ! "$value" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
    echo "fatal: $key must be a bounded lowercase database identifier" >&2
    exit 1
  fi
}

validate_distinct_values() {
  local file=$1
  local first_key=$2
  local second_key=$3
  local first_value second_value

  if ! first_value="$(extract_key "$file" "$first_key")" ||
     ! second_value="$(extract_key "$file" "$second_key")"; then
    echo "fatal: cannot compare required scoped credentials" >&2
    exit 1
  fi
  if [[ "$first_value" == "$second_value" ]]; then
    echo "fatal: $first_key and $second_key in $file must use distinct scoped credentials" >&2
    exit 1
  fi
}

source_secret=""

required_keys=(
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  KEYCLOAK_CLIENT_SECRET
  NEXTAUTH_SECRET
  OPENAI_API_KEY
)

if [[ "$MODE" == "dev" ]]; then
  required_keys+=(
    KC_BOOTSTRAP_ADMIN_USERNAME
    KC_BOOTSTRAP_ADMIN_PASSWORD
  )
fi

validate_required_keys "$SOURCE_FILE" "${required_keys[@]}"

if [[ "$MODE" == "prod" ]]; then
  validate_image_ref "$SOURCE_FILE" BACKEND_IMAGE ghcr.io/jungt72/sealai-backend
  validate_image_ref "$SOURCE_FILE" BACKEND_V2_IMAGE ghcr.io/jungt72/sealai-backend-v2
  validate_image_ref "$SOURCE_FILE" KEYCLOAK_IMAGE ghcr.io/jungt72/sealai-keycloak
  validate_image_ref "$SOURCE_FILE" FRONTEND_IMAGE ghcr.io/jungt72/sealai-frontend
  validate_image_ref "$SOURCE_FILE" NGINX_IMAGE docker.io/library/nginx
  validate_image_ref "$SOURCE_FILE" POSTGRES_IMAGE docker.io/library/postgres
  validate_image_ref "$SOURCE_FILE" REDIS_IMAGE docker.io/redis/redis-stack-server
  validate_image_ref "$SOURCE_FILE" QDRANT_IMAGE docker.io/qdrant/qdrant
  validate_image_ref "$SOURCE_FILE" GOTENBERG_IMAGE docker.io/gotenberg/gotenberg
  validate_image_ref "$SOURCE_FILE" TIKA_IMAGE docker.io/apache/tika
  validate_image_ref "$SOURCE_FILE" ALERTMANAGER_IMAGE prom/alertmanager
  validate_image_ref "$SOURCE_FILE" BLACKBOX_EXPORTER_IMAGE prom/blackbox-exporter
  validate_image_ref "$SOURCE_FILE" NODE_EXPORTER_IMAGE prom/node-exporter
  validate_image_ref "$SOURCE_FILE" CADVISOR_IMAGE gcr.io/cadvisor/cadvisor
  validate_image_ref "$SOURCE_FILE" POSTGRES_EXPORTER_IMAGE quay.io/prometheuscommunity/postgres-exporter
  validate_image_ref "$SOURCE_FILE" REDIS_EXPORTER_IMAGE oliver006/redis_exporter

  production_secret_keys=(
    QDRANT_API_KEY
    QDRANT_READ_ONLY_API_KEY
    KC_DB_NAME
    KC_DB_USERNAME
    KC_DB_PASSWORD
    SEALAI_V2_DB_USER
    SEALAI_V2_DB_PASSWORD
    GRAFANA_ADMIN_PASSWORD
    MISTRAL_API_KEY
    POSTGRES_EXPORTER_DSN
    REDIS_EXPORTER_PASSWORD
    ALERTMANAGER_WEBHOOK_URL
    ALERTMANAGER_WATCHDOG_URL
  )
  production_runtime_keys=(
    STRAPI_POSTGRES_NETWORK_NAME
    POSTGRES_MEMORY_LIMIT POSTGRES_CPU_LIMIT POSTGRES_PIDS_LIMIT
    REDIS_MEMORY_LIMIT REDIS_CPU_LIMIT REDIS_PIDS_LIMIT
    QDRANT_MEMORY_LIMIT QDRANT_CPU_LIMIT QDRANT_PIDS_LIMIT
    GOTENBERG_MEMORY_LIMIT GOTENBERG_CPU_LIMIT GOTENBERG_PIDS_LIMIT
    TIKA_MEMORY_LIMIT TIKA_CPU_LIMIT TIKA_PIDS_LIMIT
    PROMETHEUS_MEMORY_LIMIT PROMETHEUS_CPU_LIMIT PROMETHEUS_PIDS_LIMIT
    GRAFANA_MEMORY_LIMIT GRAFANA_CPU_LIMIT GRAFANA_PIDS_LIMIT
    ALERTMANAGER_MEMORY_LIMIT ALERTMANAGER_CPU_LIMIT ALERTMANAGER_PIDS_LIMIT
    BLACKBOX_EXPORTER_MEMORY_LIMIT BLACKBOX_EXPORTER_CPU_LIMIT BLACKBOX_EXPORTER_PIDS_LIMIT
    NODE_EXPORTER_MEMORY_LIMIT NODE_EXPORTER_CPU_LIMIT NODE_EXPORTER_PIDS_LIMIT
    CADVISOR_MEMORY_LIMIT CADVISOR_CPU_LIMIT CADVISOR_PIDS_LIMIT
    POSTGRES_EXPORTER_MEMORY_LIMIT POSTGRES_EXPORTER_CPU_LIMIT POSTGRES_EXPORTER_PIDS_LIMIT
    REDIS_EXPORTER_MEMORY_LIMIT REDIS_EXPORTER_CPU_LIMIT REDIS_EXPORTER_PIDS_LIMIT
    FRONTEND_MEMORY_LIMIT FRONTEND_CPU_LIMIT FRONTEND_PIDS_LIMIT
    KEYCLOAK_MEMORY_LIMIT KEYCLOAK_CPU_LIMIT KEYCLOAK_PIDS_LIMIT
    NGINX_MEMORY_LIMIT NGINX_CPU_LIMIT NGINX_PIDS_LIMIT
    BACKEND_V2_MEMORY_LIMIT BACKEND_V2_CPU_LIMIT BACKEND_V2_PIDS_LIMIT
    BACKEND_V2_WORKER_MEMORY_LIMIT BACKEND_V2_WORKER_CPU_LIMIT BACKEND_V2_WORKER_PIDS_LIMIT
    NODE_EXPORTER_TEXTFILE_DIR
  )
  validate_required_keys "$SOURCE_FILE" "${production_secret_keys[@]}"
  validate_required_keys "$SOURCE_FILE" "${production_runtime_keys[@]}"
  for credential_key in \
    QDRANT_API_KEY \
    QDRANT_READ_ONLY_API_KEY \
    KC_DB_PASSWORD \
    SEALAI_V2_DB_PASSWORD \
    GRAFANA_ADMIN_PASSWORD \
    REDIS_EXPORTER_PASSWORD; do
    validate_scoped_credential "$SOURCE_FILE" "$credential_key"
  done
  for identifier_key in KC_DB_NAME KC_DB_USERNAME SEALAI_V2_DB_USER; do
    validate_database_identifier "$SOURCE_FILE" "$identifier_key"
  done
  validate_distinct_values "$SOURCE_FILE" QDRANT_API_KEY QDRANT_READ_ONLY_API_KEY

  images_dir="$(mktemp -d "${TMPDIR:-/tmp}/sealai-compose-images.XXXXXX")"
  trap 'rm -rf "${images_dir}"' EXIT
  env \
    -u BACKEND_IMAGE \
    -u BACKEND_V2_IMAGE \
    -u FRONTEND_IMAGE \
    -u KEYCLOAK_IMAGE \
    -u NGINX_IMAGE \
    -u POSTGRES_IMAGE \
    -u REDIS_IMAGE \
    -u QDRANT_IMAGE \
    -u GOTENBERG_IMAGE \
    -u TIKA_IMAGE \
    -u ALERTMANAGER_IMAGE \
    -u BLACKBOX_EXPORTER_IMAGE \
    -u NODE_EXPORTER_IMAGE \
    -u CADVISOR_IMAGE \
    -u POSTGRES_EXPORTER_IMAGE \
    -u REDIS_EXPORTER_IMAGE \
    docker compose \
      --env-file "$SOURCE_FILE" \
      -f "$REPO_ROOT/docker-compose.yml" \
      -f "$REPO_ROOT/docker-compose.deploy.yml" \
      --profile v2 \
      --profile frontend-container \
      --profile observability \
      config --images > "${images_dir}/images.txt"
  /usr/bin/python3 -I "$REPO_ROOT/ops/supply_chain_gate.py" \
    verify-materialized-images \
    --manifest docker-compose.yml \
    --manifest docker-compose.deploy.yml \
    --images-file "${images_dir}/images.txt"
  exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
  # No global .env to drift in dev mode.
  exit 0
fi

env_secret=""
if ! env_secret="$(extract_key "$ENV_FILE" NEXTAUTH_SECRET)"; then
  echo "fatal: NEXTAUTH_SECRET not set in $ENV_FILE" >&2
  exit 1
fi

if ! source_secret="$(extract_key "$SOURCE_FILE" NEXTAUTH_SECRET)"; then
  echo "fatal: NEXTAUTH_SECRET not set in $SOURCE_FILE" >&2
  exit 1
fi

if [[ "$env_secret" != "$source_secret" ]]; then
  echo "fatal: NEXTAUTH_SECRET in $ENV_FILE differs from $SOURCE_FILE (mode: $MODE)" >&2
  echo "       Remove or resync $ENV_FILE to match $SOURCE_FILE before starting the stack." >&2
  exit 1
fi

exit 0
