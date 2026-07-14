#!/bin/bash -p
# The only sanctioned compose build/up entrypoint for the isolated RC web stack.
set -euo pipefail

readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
readonly SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
readonly STORAGE_LEASE=/usr/local/libexec/sealai/production-storage-lease.sh

[[ $# -eq 0 ]] || {
  printf '%s\n' 'usage: ops/staging/up-staging-v2.sh' >&2
  exit 64
}

# The RC contract is strict literal data with a closed key set. It rejects all
# inherited serving/provider/Docker variables and all missing external fixtures
# before the production release gate, lease, or Docker is reached.
# shellcheck source=rc-contract.sh
source "${REPO_ROOT}/ops/staging/rc-contract.sh"
rc_contract_load "${REPO_ROOT}" staging
rc_contract_assert_nonproduction_checkout "${REPO_ROOT}"
rc_contract_assert_tls_fixtures "${REPO_ROOT}"

cd "${REPO_ROOT}"
readonly TREE_HASH="$(/bin/bash -p ops/tree-hash.sh)"
readonly GATE_CONTROL_GIT_SHA="$(/usr/bin/git rev-parse HEAD)"
readonly SOURCE_PARENT_GIT_SHA="$(/usr/bin/git rev-parse HEAD^)"
[[ "${TREE_HASH}" =~ ^[0-9a-f]{40}$ ]] || {
  printf '%s\n' 'ops/staging/up-staging-v2.sh: invalid served-tree hash' >&2
  exit 78
}
readonly RC_BACKEND_IMAGE="localhost/sealai-rc-backend:staging-${TREE_HASH:0:12}"

# The active production freeze intentionally denies this operation on the VPS.
# No storage lease, Docker build, or compose up is attempted after a denial.
# shellcheck source=../production-release-gate-check.sh
source "${REPO_ROOT}/ops/production-release-gate-check.sh"
production_release_gate_check \
  "${REPO_ROOT}/ops/production_release_gate.py" build
rc_contract_bind_approved_source \
  "${GATE_CONTROL_GIT_SHA}" \
  "${SOURCE_PARENT_GIT_SHA}" \
  "${PRODUCTION_RELEASE_APPROVED_SOURCE_SHA}"
readonly RC_GIT_SHA="${RC_APPROVED_SOURCE_SHA}"
rc_contract_assert_served_tree_binding "${REPO_ROOT}" "${RC_GIT_SHA}"

if [[ -L "${STORAGE_LEASE}" ]] || \
   [[ "$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- "${STORAGE_LEASE}" 2>/dev/null || true)" != \
      'regular file:644:root:root' ]]; then
  printf '%s\n' \
    '{"component":"sealai-staging-build","result":"blocked","reason_code":"installed_storage_lease_unsafe"}' >&2
  exit 78
fi

# shellcheck source=/dev/null
source "${STORAGE_LEASE}"
declare -F acquire_production_storage_lease >/dev/null || {
  printf '%s\n' \
    '{"component":"sealai-staging-build","result":"blocked","reason_code":"installed_storage_lease_invalid"}' >&2
  exit 78
}
acquire_production_storage_lease

# The external, hash-named volumes must already carry the seeder's READY labels.
# This read-only daemon check prevents Compose from ever creating blank data stores.
rc_contract_assert_snapshot_volumes /usr/bin/docker

COMPOSE=(
  /usr/bin/env -i
  HOME=/nonexistent
  PATH=/usr/sbin:/usr/bin:/sbin:/bin
  LANG=C
  LC_ALL=C
  DOCKER_HOST=unix:///var/run/docker.sock
  COMPOSE_DISABLE_ENV_FILE=1
  "RC_BACKEND_IMAGE=${RC_BACKEND_IMAGE}"
  "RC_TREE_HASH=${TREE_HASH}"
  "RC_GIT_SHA=${RC_GIT_SHA}"
  /usr/bin/docker compose
  --env-file "${RC_ENV_FILE}"
  -f ops/staging/docker-compose.staging.yml
  --profile rc-data
  --profile rc-stubs
  --profile rc-web
  --profile v2
)

"${COMPOSE[@]}" build backend-v2-staging
readonly POST_BUILD_TREE_HASH="$(/bin/bash -p ops/tree-hash.sh)"
[[ "${POST_BUILD_TREE_HASH}" == "${TREE_HASH}" ]] || {
  printf '%s\n' 'ops/staging/up-staging-v2.sh: served tree changed during candidate build' >&2
  exit 78
}

readonly IMAGE_ID="$(
  /usr/bin/env -i \
    HOME=/nonexistent \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    DOCKER_HOST=unix:///var/run/docker.sock \
    /usr/bin/docker image inspect --format '{{.Id}}' "${RC_BACKEND_IMAGE}"
)"
[[ "${IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  printf '%s\n' 'ops/staging/up-staging-v2.sh: candidate image has no immutable image ID' >&2
  exit 78
}

UP_COMPOSE=(
  /usr/bin/env -i
  HOME=/nonexistent
  PATH=/usr/sbin:/usr/bin:/sbin:/bin
  LANG=C
  LC_ALL=C
  DOCKER_HOST=unix:///var/run/docker.sock
  COMPOSE_DISABLE_ENV_FILE=1
  "RC_BACKEND_IMAGE=${IMAGE_ID}"
  "RC_TREE_HASH=${TREE_HASH}"
  "RC_GIT_SHA=${RC_GIT_SHA}"
  /usr/bin/docker compose
  --env-file "${RC_ENV_FILE}"
  -f ops/staging/docker-compose.staging.yml
  --profile rc-data
  --profile rc-stubs
  --profile rc-web
  --profile v2
)
exec "${UP_COMPOSE[@]}" up -d --no-build
