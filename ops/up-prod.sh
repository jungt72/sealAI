#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck source=production-release-gate-check.sh
source "${SCRIPT_DIR}/production-release-gate-check.sh"
production_release_gate_check \
  "${SCRIPT_DIR}/production_release_gate.py" recovery-start-existing

echo ">> Validating .env.prod and pinned production image refs"
/bin/bash -p "$SCRIPT_DIR/check-env-drift.sh" prod

cd "$REPO_ROOT"

# During the release freeze this path is intentionally limited to starting
# containers which already exist. `compose start` cannot build, pull, create,
# recreate, remove or migrate an artifact.
COMPOSE=(docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml --profile v2 --profile frontend-container)
SERVICES=(postgres redis qdrant gotenberg tika keycloak nginx frontend backend-v2 backend-v2-worker)

missing=()
for service in "${SERVICES[@]}"; do
  [[ -n "$("${COMPOSE[@]}" ps -aq "$service")" ]] || missing+=("$service")
done
if (( ${#missing[@]} > 0 )); then
  printf 'up-prod: recovery requires existing containers; missing:' >&2
  printf ' %s' "${missing[@]}" >&2
  printf '\n' >&2
  exit 1
fi

echo ">> Starting existing production containers (no pull/build/create/recreate)"
"${COMPOSE[@]}" start "${SERVICES[@]}"
