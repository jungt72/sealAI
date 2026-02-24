#!/usr/bin/env bash
set -euo pipefail

# SealAI Backend Venv Setup
# Standardizes isolation for host/CI tests

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$BACKEND_DIR/.venv"

echo "Setting up backend venv at $VENV_PATH..."

if [[ ! -d "$VENV_PATH" ]]; then
  python3 -m venv "$VENV_PATH"
  echo "Venv created."
else
  echo "Venv already exists."
fi

echo "Installing/Updating dependencies..."
"$VENV_PATH/bin/python" -m pip install --upgrade pip
# Removed -c constraints.txt because the lockfile on VPS is stale compared to requirements.txt
"$VENV_PATH/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt"

if [[ -f "$BACKEND_DIR/requirements-dev.txt" ]]; then
    "$VENV_PATH/bin/python" -m pip install -r "$BACKEND_DIR/requirements-dev.txt" || echo "requirements-dev.txt failed, ignoring..."
fi

echo "Venv setup complete!"
