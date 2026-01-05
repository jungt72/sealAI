#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

usage() {
  cat <<'EOF'
Usage: check-env-drift.sh MODE
  MODE must be "dev" or "prod". The script reads NEXTAUTH_SECRET from .env and .env.MODE
  and exits with an error if the secrets differ. This prevents the root .env from drifting
  away from the expected environment file.
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

if [[ ! -f "$ENV_FILE" ]]; then
  # No global .env to drift.
  exit 0
fi

extract_secret() {
  local file=$1
  python3 - "$file" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
secret = None
with path.open() as fh:
    for raw in fh:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "NEXTAUTH_SECRET":
            continue
        secret = value.strip()
        if (secret.startswith('"') and secret.endswith('"')) or (secret.startswith("'") and secret.endswith("'")):
            secret = secret[1:-1]
        print(secret, end="")
        break

if secret is None:
    raise SystemExit(1)
PY
}

env_secret=""
source_secret=""

if ! env_secret="$(extract_secret "$ENV_FILE")"; then
  echo "fatal: NEXTAUTH_SECRET not set in $ENV_FILE" >&2
  exit 1
fi

if ! source_secret="$(extract_secret "$SOURCE_FILE")"; then
  echo "fatal: NEXTAUTH_SECRET not set in $SOURCE_FILE" >&2
  exit 1
fi

if [[ "$env_secret" != "$source_secret" ]]; then
  echo "fatal: NEXTAUTH_SECRET in $ENV_FILE differs from $SOURCE_FILE (mode: $MODE)" >&2
  echo "       Remove or resync $ENV_FILE to match $SOURCE_FILE before starting the stack." >&2
  exit 1
fi

exit 0
