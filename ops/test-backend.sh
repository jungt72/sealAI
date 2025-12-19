#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR/backend"

echo "[tests] unit+integration (pure app)"
pytest -q

if [[ "${RUN_INTEGRATION:-0}" == "1" ]]; then
  echo "[tests] compose wiring (RUN_INTEGRATION=1)"
  pytest -q tests/integration/test_compose_wiring.py
else
  echo "[tests] compose wiring skipped (set RUN_INTEGRATION=1)"
fi

