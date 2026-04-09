#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.prod}"
KEYCLOAK_CONTAINER="${KEYCLOAK_CONTAINER:-keycloak}"
KEYCLOAK_SERVER="${KEYCLOAK_SERVER:-http://localhost:8080}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

REALM="${KEYCLOAK_REALM:-}"
if [[ -z "$REALM" && -n "${KEYCLOAK_ISSUER:-}" ]]; then
  REALM="${KEYCLOAK_ISSUER##*/}"
fi
REALM="${REALM:-sealAI}"

ADMIN_USER="${KEYCLOAK_ADMIN_USER:-${KEYCLOAK_ADMIN:-admin}}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-}"
ADMIN_FALLBACK_USERS="${KEYCLOAK_ADMIN_FALLBACK_USERS:-superadmin}"

if [[ -z "$ADMIN_PASSWORD" ]]; then
  echo "KEYCLOAK_ADMIN_PASSWORD missing; export it or provide ENV_FILE with credentials." >&2
  exit 1
fi

kc() {
  docker exec "$KEYCLOAK_CONTAINER" /bin/sh -lc "$1"
}

kcadm() {
  local escaped=()
  local arg
  for arg in "$@"; do
    escaped+=("$(printf '%q' "$arg")")
  done
  kc "/opt/keycloak/bin/kcadm.sh ${escaped[*]}"
}

try_login() {
  local username="$1"
  if [[ -z "$username" ]]; then
    return 1
  fi
  if kcadm config credentials \
    --server "$KEYCLOAK_SERVER" \
    --realm master \
    --user "$username" \
    --password "$ADMIN_PASSWORD" >/dev/null 2>&1; then
    echo "$username"
    return 0
  fi
  return 1
}

echo "Logging into Keycloak container '$KEYCLOAK_CONTAINER' on realm 'master'..."
ACTIVE_ADMIN_USER=""
if ACTIVE_ADMIN_USER="$(try_login "$ADMIN_USER")"; then
  :
else
  IFS=',' read -r -a fallback_users <<<"$ADMIN_FALLBACK_USERS"
  for candidate in "${fallback_users[@]}"; do
    candidate="$(printf '%s' "$candidate" | xargs)"
    [[ -n "$candidate" && "$candidate" != "$ADMIN_USER" ]] || continue
    if ACTIVE_ADMIN_USER="$(try_login "$candidate")"; then
      echo "Configured admin user '$ADMIN_USER' failed; using fallback master admin '$ACTIVE_ADMIN_USER'." >&2
      break
    fi
  done
fi

if [[ -z "$ACTIVE_ADMIN_USER" ]]; then
  echo "Unable to authenticate to Keycloak master realm at $KEYCLOAK_SERVER." >&2
  echo "Tried KEYCLOAK_ADMIN_USER/KEYCLOAK_ADMIN='$ADMIN_USER' plus fallbacks: ${ADMIN_FALLBACK_USERS:-<none>}." >&2
  echo "This usually means the running Keycloak DB has persisted admin users that differ from $ENV_FILE." >&2
  exit 1
fi

declare -a roles=(
  "user_basic"
  "user_pro"
  "manufacturer"
  "admin"
)

for role in "${roles[@]}"; do
  if ! kcadm get "roles/$role" -r "$REALM" >/dev/null 2>&1; then
    echo "Creating role: $role"
    kcadm create roles -r "$REALM" -s "name=$role" >/dev/null
  fi
done

echo "Verified roles in realm '$REALM':"
for role in "${roles[@]}"; do
  kcadm get "roles/$role" -r "$REALM" --fields name
done
