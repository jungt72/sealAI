#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

DOMAIN="${DOMAIN:-sealingai.com}"
WWW_DOMAIN="${WWW_DOMAIN:-www.${DOMAIN}}"
EXPECTED_A="${EXPECTED_A:-49.13.233.145}"
WEBROOT="${WEBROOT:-/home/thorsten/sealai/nginx/www}"

cd /home/thorsten/sealai

for host in "$DOMAIN" "$WWW_DOMAIN"; do
  if ! dig +short "$host" A | grep -qx "$EXPECTED_A"; then
    echo "!! ${host} must point to ${EXPECTED_A} before issuing the certificate" >&2
    exit 1
  fi
done

sudo certbot certonly \
  --webroot \
  --webroot-path "$WEBROOT" \
  --cert-name "$DOMAIN" \
  -d "$DOMAIN" \
  -d "$WWW_DOMAIN" \
  --deploy-hook "/usr/bin/docker exec nginx nginx -s reload"

/usr/bin/docker exec nginx nginx -t
/usr/bin/docker exec nginx nginx -s reload

/bin/bash -p ./ops/check-domain-readiness.sh
