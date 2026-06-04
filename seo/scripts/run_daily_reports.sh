#!/usr/bin/env bash
set -euo pipefail
cd /home/thorsten/sealai
PYTHONPATH=seo/src python -m sealai_seo.cli init-db
PYTHONPATH=seo/src python -m sealai_seo.cli report-daily "$@"
PYTHONPATH=seo/src python -m sealai_seo.cli report-indexability
