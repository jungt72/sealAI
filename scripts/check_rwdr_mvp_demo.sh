#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

echo "== RWDR golden cases =="
PYTHONPATH=backend "$PYTHON_BIN" -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py

echo "== RWDR/RFQ backend focused suite =="
PYTHONPATH=backend "$PYTHON_BIN" -m pytest -q \
  backend/tests/unit/services/test_rwdr_mvp_brief.py \
  backend/tests/unit/services/test_rfq_preview_service.py \
  backend/app/api/tests/test_rfq_endpoint.py \
  backend/app/api/tests/test_rwdr_golden_cases.py

echo "== RWDR frontend focused suite =="
npm --prefix frontend run test:run -- \
  src/components/dashboard/RfqPane.test.tsx \
  src/components/dashboard/ManufacturerFitPanel.test.tsx \
  src/lib/unsafeProductCopy.spec.ts

echo "== Frontend broad suite =="
npm --prefix frontend run test:run

echo "== Static diff hygiene =="
git diff --check

echo "== Forbidden-language scan =="
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs || true

echo "RWDR guided-demo gates completed. Review forbidden-language hits for RWDR customer-facing D-class issues."
