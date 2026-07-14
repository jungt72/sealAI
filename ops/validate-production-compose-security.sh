#!/bin/bash -p
# Render and validate the production Compose contract without contacting the daemon.
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"
ENV_FILE="${1:-${REPO_ROOT}/.env.prod}"

[[ "${ENV_FILE}" == "${REPO_ROOT}/.env.prod" \
  && -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] || {
  echo "production compose security: canonical owner-controlled env file is unavailable" >&2
  exit 3
}
REPO_OWNER_UID="$(/usr/bin/stat -c '%u' -- "${REPO_ROOT}")"
[[ "$(/usr/bin/stat -c '%a:%h:%u' -- "${ENV_FILE}")" == "600:1:${REPO_OWNER_UID}" ]] || {
  echo "production compose security: env file metadata is unsafe" >&2
  exit 3
}

docker compose \
  --env-file "${ENV_FILE}" \
  -f "${REPO_ROOT}/docker-compose.yml" \
  -f "${REPO_ROOT}/docker-compose.deploy.yml" \
  --profile v2 \
  --profile frontend-container \
  --profile observability \
  config --format json \
  | /usr/bin/python3 -I "${SCRIPT_DIR}/compose_security_guard.py" \
      --policy "${SCRIPT_DIR}/network_topology_policy.json"
