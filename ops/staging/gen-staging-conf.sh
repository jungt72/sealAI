#!/usr/bin/env bash
# ops/staging/gen-staging-conf.sh — generate the staging nginx conf (gitignored output).
#
# The staging conf is a BYTE-COPY of the prod nginx/default.conf with the V2 include applied by
# ops/v2-flip.sh — the same switch the prod flip uses, so staging rehearses the real mechanism —
# plus a snippets copy with the ONE documented staging-only CSP delta: the SPA origin on staging
# is https://sealingai.com:8443 while Keycloak stays on https://sealingai.com, so the OIDC token
# POST (connect-src) and a future prompt=none iframe (frame-src) are cross-origin ON STAGING ONLY.
# Prod keeps the stricter 'self'-only snippet untouched.
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

OUT=ops/staging/conf
rm -rf "$OUT"
mkdir -p "$OUT/snippets"

cp nginx/default.conf "$OUT/default.conf"
cp nginx/snippets/sealai_proxy_headers.conf "$OUT/snippets/"
[[ -f nginx/snippets/keycloak_proxy.conf ]] && cp nginx/snippets/keycloak_proxy.conf "$OUT/snippets/"
cp nginx/snippets/v2_dashboard.conf "$OUT/snippets/v2_dashboard.conf"

# THE staging-only CSP delta (see header). Fails loudly if the prod snippet wording changed.
sed -i \
  -e "s|connect-src 'self';|connect-src 'self' https://sealingai.com;|" \
  -e "s|frame-src 'self';|frame-src 'self' https://sealingai.com;|" \
  "$OUT/snippets/v2_dashboard.conf"
grep -q "connect-src 'self' https://sealingai.com;" "$OUT/snippets/v2_dashboard.conf" \
  || { echo "!! CSP delta did not apply — prod snippet wording changed?" >&2; exit 1; }

# Apply the include with the real flip switch (file-only; nginx -t happens in the container).
./ops/v2-flip.sh --apply --file "$OUT/default.conf" --no-reload

echo ">> staging conf generated at $OUT (include applied + CSP delta)"
