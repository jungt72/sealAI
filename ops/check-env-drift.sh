#!/usr/bin/env bash
set -euo pipefail

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
  python3 - "$file" "$key" <<'PY'
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
    if [[ "$MODE" == "prod" && ( "$value" == "SET_IN_SECRET_STORE" || "$value" == "<REPLACE_ME>" ) ]]; then
      echo "fatal: $key in $file still uses a placeholder value ($value)" >&2
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
    echo "fatal: $key in $file must not use a floating :latest reference ($value)" >&2
    exit 1
  fi
  if [[ "$value" != *@sha256:* ]]; then
    echo "fatal: $key in $file must be pinned as tag@digest or digest-only ($value)" >&2
    exit 1
  fi
  if [[ "$value" == *"<REPLACE_ME>"* || "$value" == *"SET_IN_SECRET_STORE"* ]]; then
    echo "fatal: $key in $file still uses a placeholder value ($value)" >&2
    exit 1
  fi
}

source_secret=""

required_keys=(
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  KEYCLOAK_ADMIN_PASSWORD
  KEYCLOAK_CLIENT_SECRET
  NEXTAUTH_SECRET
  OPENAI_API_KEY
)

validate_required_keys "$SOURCE_FILE" "${required_keys[@]}"

if [[ "$MODE" == "prod" ]]; then
  validate_image_ref "$SOURCE_FILE" BACKEND_IMAGE
  validate_image_ref "$SOURCE_FILE" KEYCLOAK_IMAGE
  validate_image_ref "$SOURCE_FILE" FRONTEND_IMAGE
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
