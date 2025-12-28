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
echo "OK: no v1 backend imports found"

matches=$(rg -n '/api/v1/langgraph/' frontend/src || true)
if [ -z "$matches" ]; then
  echo "OK: v2-only frontend checks passed"
  exit 0
fi

allowed_re='^(frontend/src/app/api/langgraph/|frontend/src/lib/langgraphApi\.ts)'
illegal=$(printf "%s\n" "$matches" | grep -Ev "$allowed_re" || true)
if [ -n "$illegal" ]; then
  echo "FAIL: forbidden /api/v1/langgraph/ usage in client code" >&2
  printf "%s\n" "$illegal" >&2
  exit 1
fi

echo "OK: v2-only frontend checks passed"
