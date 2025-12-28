#!/usr/bin/env bash
set -euo pipefail

if ! command -v rg >/dev/null 2>&1; then
  echo "FAIL: ripgrep (rg) not found" >&2
  exit 1
fi

if rg -n 'app\.langgraph\.compile' backend/app --glob '!backend/app/archive/**' >/tmp/rg_langgraph_compile.txt; then
  echo "FAIL: found legacy app.langgraph.compile usage (non-archive)" >&2
  cat /tmp/rg_langgraph_compile.txt >&2
  exit 1
fi

allowed_re='^frontend/src/(app/api/langgraph/|lib/langgraphApi\.ts)'
if rg -n '/api/v1/langgraph/' frontend/src >/tmp/rg_langgraph_paths.txt; then
  if ! awk -v re="$allowed_re" 'BEGIN{bad=0} {if ($1 !~ re) {bad=1; print}} END{exit bad}' /tmp/rg_langgraph_paths.txt; then
    echo "OK: v2-only checks passed"
    exit 0
  fi
  echo "FAIL: forbidden /api/v1/langgraph/ usage in client code" >&2
  cat /tmp/rg_langgraph_paths.txt >&2
  exit 1
fi

echo "OK: v2-only checks passed"
