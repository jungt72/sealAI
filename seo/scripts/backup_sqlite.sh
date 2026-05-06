#!/usr/bin/env bash
set -euo pipefail
cd /home/thorsten/sealai
PYTHONPATH=seo/src python -m sealai_seo.cli backup --backup-dir /home/thorsten/var/seo/backups "$@"
