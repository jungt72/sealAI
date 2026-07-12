#!/usr/bin/env bash
set -euo pipefail
umask 077

# One-shot production recovery. It creates a temporary Keycloak admin user
# while all Keycloak nodes are stopped, reconciles the permanent realm admin,
# then deletes the temporary user. No recovery credential is persisted.

[[ "${1:-}" == "--apply" ]] || {
  echo "usage: $0 --apply" >&2
  exit 2
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.prod}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-sealai}"
TARGET_EMAIL="${KEYCLOAK_TARGET_EMAIL:-mail@thorsten-jung.de}"
RECOVERY_USER=''
RECOVERY_PASSWORD=''
KEYCLOAK_WAS_STOPPED=false
RECOVERY_CREATED=false

[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE" >&2; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "openssl is required" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq is required" >&2; exit 1; }
RECOVERY_USER="sealai-recovery-$(date -u +%Y%m%d%H%M%S)-$(openssl rand -hex 4)"
RECOVERY_PASSWORD="$(openssl rand -base64 48 | tr -d '\n')"

COMPOSE=(
  docker compose
  --project-name "$COMPOSE_PROJECT_NAME"
  --env-file "$ENV_FILE"
  -f "$ROOT_DIR/docker-compose.yml"
  -f "$ROOT_DIR/docker-compose.deploy.yml"
)

restore_keycloak_on_failure() {
  if [[ "$KEYCLOAK_WAS_STOPPED" == "true" ]]; then
    "${COMPOSE[@]}" up -d --no-build keycloak >/dev/null 2>&1 || true
  fi
  if [[ "$RECOVERY_CREATED" == "true" ]]; then
    local config="/tmp/sealai-recovery-cleanup-$$.config"
    local authenticated=false
    local user_uuid=''
    for _ in $(seq 1 30); do
      if docker exec \
        --env SEALAI_KCADM_PASSWORD="$RECOVERY_PASSWORD" \
        keycloak /bin/bash -ec \
        'exec /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user "$1" --password "$SEALAI_KCADM_PASSWORD" --config "$2"' \
        -- "$RECOVERY_USER" "$config" >/dev/null 2>&1; then
        authenticated=true
        break
      fi
      sleep 2
    done
    if [[ "$authenticated" == "true" ]]; then
      user_uuid="$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get users -r master \
        -q "username=$RECOVERY_USER" --fields id,username --config "$config" 2>/dev/null \
        | jq -r --arg user "$RECOVERY_USER" '.[] | select(.username == $user) | .id' \
        | head -n1 || true)"
      if [[ -n "$user_uuid" ]]; then
        docker exec keycloak /opt/keycloak/bin/kcadm.sh delete "users/$user_uuid" \
          -r master --config "$config" >/dev/null 2>&1 || \
          echo "WARNING: failed to delete temporary recovery user; remove it immediately" >&2
      fi
    else
      echo "WARNING: could not authenticate cleanup; temporary recovery user may remain" >&2
    fi
    docker exec keycloak rm -f "$config" >/dev/null 2>&1 || true
  fi
  unset RECOVERY_PASSWORD
}
trap restore_keycloak_on_failure EXIT

echo ">> Taking a fresh full Postgres backup before admin recovery"
ENV_FILE="$ENV_FILE" "$ROOT_DIR/ops/backup_postgres.sh"

echo ">> Stopping every Keycloak node"
"${COMPOSE[@]}" stop keycloak
KEYCLOAK_WAS_STOPPED=true

echo ">> Creating an ephemeral recovery admin user"
"${COMPOSE[@]}" run --rm --no-deps \
  -e KC_BOOTSTRAP_ADMIN_USERNAME="$RECOVERY_USER" \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD="$RECOVERY_PASSWORD" \
  keycloak \
  bootstrap-admin user --optimized --no-prompt \
  --username:env=KC_BOOTSTRAP_ADMIN_USERNAME \
  --password:env=KC_BOOTSTRAP_ADMIN_PASSWORD \
  >/dev/null
RECOVERY_CREATED=true

echo ">> Restarting Keycloak and waiting for readiness"
"${COMPOSE[@]}" up -d --no-build keycloak
for _ in $(seq 1 60); do
  if [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}' keycloak 2>/dev/null || true)" == "healthy" ]]; then
    break
  fi
  sleep 2
done
[[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' keycloak)" == "healthy" ]] || {
  docker logs --tail 100 keycloak >&2
  echo "Keycloak did not become healthy" >&2
  exit 1
}

echo ">> Reconciling the permanent realm administrator and deleting recovery access"
KEYCLOAK_ADMIN_USER="$RECOVERY_USER" \
KEYCLOAK_ADMIN_PASSWORD="$RECOVERY_PASSWORD" \
KEYCLOAK_DELETE_ADMIN_USER=true \
KEYCLOAK_TARGET_EMAIL="$TARGET_EMAIL" \
  "$ROOT_DIR/ops/keycloak_ensure_roles.sh"

KEYCLOAK_WAS_STOPPED=false
RECOVERY_CREATED=false
unset RECOVERY_PASSWORD
trap - EXIT
echo ">> Recovery complete; the temporary admin user was deleted"
