#!/usr/bin/env bash
# Dry-run refactor helper to detach local langgraph package from PyPI module.
set -euo pipefail

MODE="dry-run"
if [ "${1:-}" == "--apply" ]; then
  MODE="apply"
  shift
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$ROOT_DIR}"

if [ ! -d "$TARGET_DIR" ]; then
  echo "Target dir '$TARGET_DIR' not found." >&2
  exit 1
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "rg (ripgrep) is required for pattern counting. Please install it first." >&2
  exit 1
fi

run_cmd() {
  local cmd="$1"
  if [ "$MODE" = "apply" ]; then
    eval "$cmd"
  else
    echo "would run: $cmd"
  fi
}

LANGGRAPH_DIR="$TARGET_DIR/langgraph"
SAI_GRAPH_DIR="$TARGET_DIR/sai_graph"

echo "[Stage 1] Package rename check"
if [ -d "$LANGGRAPH_DIR" ]; then
  run_cmd "mv \"$LANGGRAPH_DIR\" \"$SAI_GRAPH_DIR\""
else
  echo "langgraph directory not present (already renamed?)."
fi

echo
echo "[Stage 2] Import rewrites"
rewrite_pattern() {
  local find_pattern="$1"
  local description="$2"
  local sed_expr="$3"
  while IFS= read -r -d '' file; do
    local hits
    hits=$(rg --no-heading -c "$find_pattern" "$file" 2>/dev/null | cut -d: -f2)
    hits=${hits:-0}
    if [ "$hits" != "0" ]; then
      if [ "$MODE" = "apply" ]; then
        sed -i'.refbak' -e "$sed_expr" "$file"
        echo "rewrote $description in $file ($hits matches)"
      else
        echo "would rewrite $description in $file ($hits matches)"
      fi
    fi
  done < <(find "$TARGET_DIR" -type f \( -name '*.py' -o -name '*.pyi' \) -print0)
}

rewrite_pattern 'from +langgraph' "'from langgraph'→'from sai_graph'" 's/\bfrom langgraph\b/from sai_graph/g'
rewrite_pattern 'import +langgraph' "'import langgraph'→'import sai_graph as langgraph_local'" 's/\bimport langgraph\b/import sai_graph as langgraph_local/g'
rewrite_pattern 'from +app\.langgraph' "'from app.langgraph'→'from app.sai_graph'" 's/from app\.langgraph/from app.sai_graph/g'
rewrite_pattern 'import +app\.langgraph' "'import app.langgraph'→'import app.sai_graph as sai_graph_pkg'" 's/import app\.langgraph/import app.sai_graph as sai_graph_pkg/g'

echo
echo "[Stage 3] Cleanup temporary sed backups (.refbak)"
if [ "$MODE" = "apply" ]; then
  find "$TARGET_DIR" -type f -name '*.refbak' -print -delete
else
  find "$TARGET_DIR" -type f -name '*.refbak' -print | sed 's/^/would remove backup: /'
fi

echo
echo "[Stage 4] Diff overview"
if [ "$MODE" = "apply" ]; then
  (cd "$TARGET_DIR" && git status -sb)
  (cd "$TARGET_DIR" && git diff --stat)
else
  echo "would run: (cd \"$TARGET_DIR\" && git status -sb)"
  echo "would run: (cd \"$TARGET_DIR\" && git diff --stat)"
fi

echo
echo "[Refactor $MODE complete]"
