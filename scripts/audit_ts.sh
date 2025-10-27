#!/usr/bin/env bash
set -euo pipefail
mkdir -p analysis
node scripts/strip_tsconfig_comments.mjs frontend/tsconfig.json > analysis/tsconfig.no-comments.json || true
npx -y depcheck@1.4.7 > analysis/depcheck_frontend.json || true
npx -y knip@5.66.3 --tsConfig frontend/tsconfig.json --reporter=json --no-progress > analysis/knip_frontend.json || true
npx -y ts-prune@0.10.3 -p frontend/tsconfig.json > analysis/ts_prune_frontend.txt || true
echo "TS audit done → analysis/*"
