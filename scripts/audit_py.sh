#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports backend/analysis
export PYTHONPATH="backend${PYTHONPATH:+:$PYTHONPATH}"
python3 -m pip install --break-system-packages -q ruff==0.14.1 vulture deptry pytest
ruff check backend > backend/analysis/ruff_backend.txt || true
vulture backend --min-confidence 80 > backend/analysis/vulture_backend.txt || true
deptry backend > backend/analysis/deptry_backend.txt || true
pytest --collect-only -q > backend/analysis/pytest_collect_backend.log || true
echo "Python audit done → backend/analysis/*"
