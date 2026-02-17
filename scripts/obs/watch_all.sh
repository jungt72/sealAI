#!/bin/bash
set -u

# Resolve script dir
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Ensure we run from repo root so .env is found
cd "$REPO_ROOT" || exit 1

cleanup() {
  echo -e "\nStopping watchers..."
  kill $(jobs -p) 2>/dev/null
  exit 0
}

if [[ "${1:-}" == "--once" ]]; then
  echo "--- Nginx (Once) ---"
  bash "$SCRIPT_DIR/nginx_429_watch.sh" --once
  echo "--- Keycloak (Once) ---"
  bash "$SCRIPT_DIR/keycloak_auth_watch.sh"
  echo "--- Redis (Once) ---"
  bash "$SCRIPT_DIR/redis_token_health.sh" --once
  exit 0
fi

trap cleanup SIGINT SIGTERM

echo "Starting all watchers (Ctrl+C to stop)..."
echo "Logging to stdout..."

# Nginx loop (internal default 10s)
bash "$SCRIPT_DIR/nginx_429_watch.sh" &

# Keycloak loop (manual loop 60s)
(
  while true; do
    bash "$SCRIPT_DIR/keycloak_auth_watch.sh"
    sleep 60
  done
) &

# Redis loop (internal default 30s)
bash "$SCRIPT_DIR/redis_token_health.sh" &

wait
