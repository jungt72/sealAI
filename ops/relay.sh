#!/usr/bin/env bash
# Compatibility entry point for the fail-closed local agent relay.
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)"
PYTHON_BIN="${SEALAI_RELAY_PYTHON:-$REPO_ROOT/.venv/bin/python}"

case "$PYTHON_BIN" in
  /*) ;;
  *)
    printf '%s\n' 'BLOCKED_EXTERNAL: SEALAI_RELAY_PYTHON must be an absolute path' >&2
    exit 3
    ;;
esac

if [[ ! -x "$PYTHON_BIN" ]]; then
  printf 'BLOCKED_EXTERNAL: relay Python is unavailable: %s\n' "$PYTHON_BIN" >&2
  exit 3
fi

if ! "$PYTHON_BIN" -I -c 'import importlib.util, jsonschema, yaml; assert importlib.util.find_spec("pytest"); assert importlib.util.find_spec("ruff")' >/dev/null 2>&1; then
  printf '%s\n' 'BLOCKED_EXTERNAL: relay Python lacks PyYAML, jsonschema, pytest, or Ruff' >&2
  exit 3
fi

exec "$PYTHON_BIN" -I "$SCRIPT_DIR/agent_relay.py" "$@"
