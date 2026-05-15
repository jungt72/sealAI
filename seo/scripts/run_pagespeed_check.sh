#!/usr/bin/env bash
set -euo pipefail
cd /home/thorsten/sealai

for env_file in /etc/seo/secrets/seo.env /home/thorsten/.sealai/seo.env; do
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
done

if [[ -z "${PAGESPEED_API_KEY:-}" && "${PAGESPEED_ALLOW_UNAUTH:-0}" != "1" ]]; then
  echo "Skipping PageSpeed run: set PAGESPEED_API_KEY or PAGESPEED_ALLOW_UNAUTH=1."
  exit 0
fi

PYTHONPATH=seo/src python -m sealai_seo.cli init-db
PYTHONPATH=seo/src python -m sealai_seo.cli sync-pagespeed --strategy mobile
