#!/bin/bash -p
# The only sanctioned compose build/up entrypoint for the VPS staging stack.
set -euo pipefail

readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
readonly SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
readonly STORAGE_LEASE=/usr/local/libexec/sealai/production-storage-lease.sh

[[ $# -eq 0 ]] || {
  printf '%s\n' 'usage: ops/staging/up-staging-v2.sh' >&2
  exit 64
}

# The active production freeze intentionally denies this operation on the VPS.
# No storage lease, Docker build, or compose up is attempted after a denial.
# shellcheck source=../production-release-gate-check.sh
source "${REPO_ROOT}/ops/production-release-gate-check.sh"
production_release_gate_check \
  "${REPO_ROOT}/ops/production_release_gate.py" build

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

cd "${REPO_ROOT}"
exec /usr/bin/docker compose \
  --env-file .env.prod \
  -f ops/staging/docker-compose.staging.yml \
  --profile v2 \
  up -d --build
