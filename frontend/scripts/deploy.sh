#!/bin/bash
set -e

ROOT_ENV_FILE="../.env.prod"

if [ ! -f "$ROOT_ENV_FILE" ]; then
  echo "Missing production env file: $ROOT_ENV_FILE" >&2
  exit 1
fi

set -a
. "$ROOT_ENV_FILE"
set +a

: "${AUTH_URL:?Missing AUTH_URL in $ROOT_ENV_FILE}"
: "${AUTH_SECRET:?Missing AUTH_SECRET in $ROOT_ENV_FILE}"
: "${NEXTAUTH_URL:?Missing NEXTAUTH_URL in $ROOT_ENV_FILE}"
: "${NEXTAUTH_SECRET:?Missing NEXTAUTH_SECRET in $ROOT_ENV_FILE}"
: "${KEYCLOAK_CLIENT_ID:?Missing KEYCLOAK_CLIENT_ID in $ROOT_ENV_FILE}"
: "${KEYCLOAK_CLIENT_SECRET:?Missing KEYCLOAK_CLIENT_SECRET in $ROOT_ENV_FILE}"
: "${KEYCLOAK_ISSUER:?Missing KEYCLOAK_ISSUER in $ROOT_ENV_FILE}"
: "${NEXT_PUBLIC_API_BASE:?Missing NEXT_PUBLIC_API_BASE in $ROOT_ENV_FILE}"

echo "→ Building Next.js..."
npm run build

echo "→ Copying static assets to standalone..."
cp -r .next/static .next/standalone/.next/static
cp -r public .next/standalone/public

echo "→ Restarting PM2 with new deployment ID..."
NEXT_DEPLOYMENT_ID=$(date +%s) pm2 restart ecosystem.config.js --only sealai-frontend --update-env

echo "✓ Deploy complete"
