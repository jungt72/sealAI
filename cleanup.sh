#!/usr/bin/env bash
# Dry-run cleanup helper for SealAI backend artifacts.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$ROOT_DIR}"

if [ ! -d "$TARGET_DIR" ]; then
  echo "Target dir '$TARGET_DIR' not found." >&2
  exit 1
fi

echo "[Dry-Run] Scanning for Python build artifacts under: $TARGET_DIR"
echo "--- __pycache__ directories ---"
find "$TARGET_DIR" -type d -name '__pycache__' -print | sed 's/^/would remove: /'

echo "--- *.pyc files ---"
find "$TARGET_DIR" -type f -name '*.pyc' -print | sed 's/^/would remove: /'

echo "--- *.bak files ---"
find "$TARGET_DIR" -type f -name '*.bak' -print | sed 's/^/would remove: /'

echo
echo "[Info] Legacy/duplicate code earmarked for later pruning (manual confirmation required):"
POTENTIAL_PATHS=(
  "services/langgraph"
  "services/rag"
  "services/langgraph/prompting_backup.py"
  "services/langgraph/prompting_backup_final.py"
  "services/langgraph/prompts/recommend.jinja2.bak"
  "services/chat/ws_streaming.py.bak"
  "ws_stream_test.py"
)

for path in "${POTENTIAL_PATHS[@]}"; do
  if [ -e "$TARGET_DIR/$path" ]; then
    echo "would archive/remove: $path"
  fi
done

echo
echo "[Dry-Run complete] No files were removed."
