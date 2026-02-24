#!/usr/bin/env bash
set -euo pipefail

# SealAI Backend Venv Test Runner
# Use this to run backend tests in the isolated environment on host/CI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$BACKEND_DIR/.venv"

if [[ ! -f "$VENV_PATH/bin/pytest" ]]; then
  echo "Error: Virtual environment not found or pytest not installed at $VENV_PATH."
  echo "Please run: $SCRIPT_DIR/setup_venv.sh"
  exit 1
fi

# Set PYTHONPATH to include the backend directory so 'app' is importable
export PYTHONPATH="$BACKEND_DIR"

echo "Running backend tests using venv..."
"$VENV_PATH/bin/pytest" "$@"
