#!/usr/bin/env bash
set -euo pipefail

PYTEST_ARGS="${PYTEST_ARGS:-}"

run_unit() {
  python3 -m pytest -q backend/app/services/rag/tests/test_rag_orchestrator_fastembed.py ${PYTEST_ARGS}
  python3 -m pytest -q backend/app/services/rag/tests/test_single_collection.py ${PYTEST_ARGS}
  python3 -m pytest -q backend/tests/test_rag_ingest_metadata.py ${PYTEST_ARGS}
}

run_api() {
  docker compose exec backend python -m pytest -q -p no:cacheprovider ${PYTEST_ARGS} /app/backend/app/api/v1/tests/test_rag_tenant_scoping.py
}

case "${1:-}" in
  unit)
    run_unit
    ;;
  api)
    run_api
    ;;
  all)
    run_unit
    run_api
    ;;
  *)
    echo "Usage: $0 {unit|api|all}"
    exit 2
    ;;
esac
