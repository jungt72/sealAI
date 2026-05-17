#!/usr/bin/env bash
set -euo pipefail

cd /home/thorsten/sealai/frontend

REPO_ROOT="/home/thorsten/sealai"
NODE_BIN="${NODE_BIN:-/usr/bin/node}"
NPM_BIN="${NPM_BIN:-/usr/bin/npm}"
export PATH="$(dirname "${NODE_BIN}"):${PATH}"

echo ">> Preparing production build environment"
awk -F= '
  BEGIN {
    wanted["NEXT_PUBLIC_SITE_URL"] = 1
    wanted["NEXT_PUBLIC_ANALYTICS_ENABLED"] = 1
    wanted["NEXT_PUBLIC_GTM_ID"] = 1
    wanted["NEXT_PUBLIC_GA_MEASUREMENT_ID"] = 1
    wanted["NEXT_PUBLIC_GOOGLE_CONSENT_DEFAULT"] = 1
    wanted["SITE_URL"] = 1
    wanted["NEXT_PUBLIC_API_BASE"] = 1
    wanted["NEXTAUTH_URL"] = 1
    wanted["AUTH_URL"] = 1
    wanted["AUTH_TRUST_HOST"] = 1
    wanted["KEYCLOAK_ISSUER"] = 1
    wanted["SEALAI_BACKEND_ORIGIN"] = 1
    wanted["FRONTEND_BIND_HOST"] = 1
  }
  /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
  {
    key = $1
    sub(/^[[:space:]]+/, "", key)
    sub(/[[:space:]]+$/, "", key)
    if (wanted[key]) print
  }
' "${REPO_ROOT}/.env.prod" > .env.production.local

if grep -q 'sealai\.net' .env.production.local; then
  echo "!! Refusing to build frontend with legacy sealai.net values in .env.production.local"
  exit 1
fi

echo ">> Using Node runtime"
"${NODE_BIN}" -v
"${NPM_BIN}" -v

echo ">> Installing dependencies"
"${NPM_BIN}" ci --prefer-offline

echo ">> Building Next.js standalone"
"${NPM_BIN}" run build

echo ">> Switching PM2 process (zero-downtime swap)"
if pm2 describe sealai-frontend >/dev/null 2>&1; then
  ROLLBACK_POSSIBLE=true
else
  ROLLBACK_POSSIBLE=false
fi

pm2 delete sealai-frontend 2>/dev/null || true
NEXT_DEPLOYMENT_ID="${NEXT_DEPLOYMENT_ID:-$(date +%Y%m%d%H%M%S)}" \
  pm2 start ecosystem.config.js --only sealai-frontend --update-env
pm2 save

echo ">> Flushing old logs"
pm2 flush sealai-frontend

echo ">> Waiting for frontend health"
FRONTEND_HEALTH_HOST="${FRONTEND_BIND_HOST:-$(awk -F= '
  $1 == "FRONTEND_BIND_HOST" {
    value = $2
    sub(/^[[:space:]]+/, "", value)
    sub(/[[:space:]]+$/, "", value)
    print value
  }
' "${REPO_ROOT}/.env.prod" | tail -n 1)}"
FRONTEND_HEALTH_HOST="${FRONTEND_HEALTH_HOST:-172.17.0.1}"
for i in {1..20}; do
  if curl -fsS "http://${FRONTEND_HEALTH_HOST}:3000" >/dev/null 2>&1; then
    echo ">> Frontend healthy"
    break
  fi
  if [[ $i -eq 20 ]]; then
    echo "!! Frontend nicht erreichbar nach 20 Versuchen"
    pm2 logs sealai-frontend --lines 50 --nostream
    exit 1
  fi
  echo ">> Frontend not ready yet (${i}/20)"
  sleep 2
done

echo ">> PM2 status"
pm2 list

if [[ "${SKIP_LIVE_SMOKE:-0}" != "1" ]]; then
  echo ">> Running live pilot readiness smoke"
  BASE_URL="${BASE_URL:-https://sealingai.com}" "${REPO_ROOT}/ops/smoke-live-pilot-readiness.sh"
else
  echo ">> Live pilot readiness smoke skipped by SKIP_LIVE_SMOKE=1"
fi

echo ">> Done"
