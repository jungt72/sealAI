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
  local value

  if ! value="$(extract_key "$file" "$key")"; then
    echo "fatal: $key not set in $file" >&2
    exit 1
  fi
  if [[ "$value" == *":latest"* ]]; then
    echo "fatal: $key in $file must not use a floating :latest reference" >&2
    exit 1
  fi
  if [[ ! "$value" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]]; then
    echo "fatal: $key in $file must be pinned as an exact name@sha256 digest" >&2
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
  production_secret_keys=(
    QDRANT_API_KEY
    KC_DB_NAME
    KC_DB_USERNAME
    KC_DB_PASSWORD
    SEALAI_V2_DB_USER
    SEALAI_V2_DB_PASSWORD
    GRAFANA_ADMIN_PASSWORD
    MISTRAL_API_KEY
  )
  production_image_keys=(
    BACKEND_IMAGE
    BACKEND_V2_IMAGE
    KEYCLOAK_IMAGE
    FRONTEND_IMAGE
    NGINX_IMAGE
    POSTGRES_IMAGE
    REDIS_IMAGE
    QDRANT_IMAGE
    GOTENBERG_IMAGE
    TIKA_IMAGE
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
    FRONTEND_MEMORY_LIMIT FRONTEND_CPU_LIMIT FRONTEND_PIDS_LIMIT
    KEYCLOAK_MEMORY_LIMIT KEYCLOAK_CPU_LIMIT KEYCLOAK_PIDS_LIMIT
    NGINX_MEMORY_LIMIT NGINX_CPU_LIMIT NGINX_PIDS_LIMIT
    BACKEND_V2_MEMORY_LIMIT BACKEND_V2_CPU_LIMIT BACKEND_V2_PIDS_LIMIT
    BACKEND_V2_WORKER_MEMORY_LIMIT BACKEND_V2_WORKER_CPU_LIMIT BACKEND_V2_WORKER_PIDS_LIMIT
  )
  for image_key in "${production_image_keys[@]}"; do
    validate_image_ref "$SOURCE_FILE" "$image_key"
  done
  validate_required_keys "$SOURCE_FILE" "${production_secret_keys[@]}"
  validate_required_keys "$SOURCE_FILE" "${production_runtime_keys[@]}"
  for credential_key in QDRANT_API_KEY KC_DB_PASSWORD SEALAI_V2_DB_PASSWORD GRAFANA_ADMIN_PASSWORD; do
    validate_scoped_credential "$SOURCE_FILE" "$credential_key"
  done
  for identifier_key in KC_DB_NAME KC_DB_USERNAME SEALAI_V2_DB_USER; do
    validate_database_identifier "$SOURCE_FILE" "$identifier_key"
  done
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
