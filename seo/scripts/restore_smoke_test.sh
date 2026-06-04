#!/usr/bin/env bash
set -euo pipefail
cd /home/thorsten/sealai
PYTHONPATH=seo/src python -m sealai_seo.cli restore-smoke-test --backup-dir /home/thorsten/var/seo/backups --tmp-dir /home/thorsten/var/seo/restore-smoke "$@"
