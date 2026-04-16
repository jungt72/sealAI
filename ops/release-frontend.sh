#!/usr/bin/env bash
set -euo pipefail

cd /home/thorsten/sealai/frontend

echo ">> Installing dependencies"
npm ci --prefer-offline

echo ">> Building Next.js standalone"
npm run build

echo ">> Switching PM2 process (zero-downtime swap)"
if pm2 describe sealai-frontend >/dev/null 2>&1; then
  ROLLBACK_POSSIBLE=true
else
  ROLLBACK_POSSIBLE=false
fi

pm2 delete sealai-frontend 2>/dev/null || true
PORT=3000 pm2 start .next/standalone/server.js --name sealai-frontend
pm2 save

echo ">> Flushing old logs"
pm2 flush sealai-frontend

echo ">> Waiting for frontend health"
for i in {1..20}; do
  if curl -fsS http://127.0.0.1:3000 >/dev/null 2>&1; then
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

echo ">> Done"

