#!/usr/bin/env bash
set -euo pipefail
cd /home/thorsten/sealai
PYTHONPATH=seo/src python -m sealai_seo.cli init-db
PYTHONPATH=seo/src python -m sealai_seo.cli dataforseo-budget-check --planned-cost 0.10
PYTHONPATH=seo/src python -m sealai_seo.cli seed-keywords
PYTHONPATH=seo/src python -m sealai_seo.cli dataforseo-keyword-volume --planned-cost 0.10 --max-run-cost 0.10
PYTHONPATH=seo/src python -m sealai_seo.cli report-keyword-foundation
PYTHONPATH=seo/src python -m sealai_seo.cli report-content-roadmap
