#!/bin/bash
set -euo pipefail

# Optional: load KEYCLOAK_* defaults from .env.dev so we use real admin creds
ENV_FILE=${ENV_FILE:-.env.dev}
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

DATE=$(date +%Y-%m-%d_%H-%M)
TARGET_DIR=${TARGET_DIR:-"$HOME/sealai/keycloak-realm-backup"}
REALM_NAME=${KEYCLOAK_REALM:-sealAI}
ADMIN_USER=${KEYCLOAK_ADMIN:-}
ADMIN_PASSWORD=${KEYCLOAK_ADMIN_PASSWORD:-}
FILE=$TARGET_DIR/${REALM_NAME}-realm-${DATE}.json

if [[ -z "${REALM_NAME}" ]]; then
  echo "❌ KEYCLOAK_REALM is required (set in $ENV_FILE or env)" >&2
  exit 1
fi

if [[ -z "${ADMIN_USER}" || -z "${ADMIN_PASSWORD}" ]]; then
  echo "❌ KEYCLOAK_ADMIN and KEYCLOAK_ADMIN_PASSWORD are required (set in $ENV_FILE or env)" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"

echo "➡️  Exporting realm '${REALM_NAME}' to ${FILE}"
docker exec keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user "$ADMIN_USER" \
  --password "$ADMIN_PASSWORD" \
  >/dev/null

docker exec keycloak /opt/keycloak/bin/kcadm.sh create partial-export -r "$REALM_NAME" \
  -s exportClients=true \
  -s exportGroupsAndRoles=true \
  -s exportUsers=true > /tmp/"${REALM_NAME}".json

docker cp keycloak:/tmp/"${REALM_NAME}".json "$FILE"

echo "✅ Backup gespeichert: $FILE"
