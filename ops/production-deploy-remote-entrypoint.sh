#!/bin/bash -p
# Root-installed, lease-holding boundary for the production deployment workflow.
# P0 intentionally has no promotion implementation: even an otherwise valid
# Gate-10 decision reaches the explicit hard denial below. P1 must replace that
# denial with exact artifact verification before any fetch/checkout is added.
set -euo pipefail
umask 077
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

readonly INSTALLED_HELPER=/usr/local/libexec/sealai/production-release-gate-check.sh
readonly INSTALLED_LEASE=/usr/local/libexec/sealai/production-storage-lease.sh

usage() {
  printf '%s\n' \
    'usage: production-deploy-remote-entrypoint.sh --control-sha SHA --source-sha SHA --backend-image REF@sha256:DIGEST' >&2
}

CONTROL_SHA=""
SOURCE_SHA=""
BACKEND_IMAGE=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --control-sha)
      [[ "$#" -ge 2 ]] || { usage; exit 64; }
      CONTROL_SHA="$2"
      shift 2
      ;;
    --source-sha)
      [[ "$#" -ge 2 ]] || { usage; exit 64; }
      SOURCE_SHA="$2"
      shift 2
      ;;
    --backend-image)
      [[ "$#" -ge 2 ]] || { usage; exit 64; }
      BACKEND_IMAGE="$2"
      shift 2
      ;;
    *) usage; exit 64 ;;
  esac
done

[[ "${CONTROL_SHA}" =~ ^[0-9a-f]{40}$ ]] || { usage; exit 64; }
[[ "${SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]] || { usage; exit 64; }
[[ "${BACKEND_IMAGE}" =~ ^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$ ]] || {
  usage
  exit 64
}

for installed in "${INSTALLED_HELPER}" "${INSTALLED_LEASE}"; do
  [[ ! -L "${installed}" ]] || {
    printf '%s\n' \
      '{"component":"sealai-production-remote-entrypoint","allowed":false,"reason":"installed_control_symlink"}' >&2
    exit 78
  }
done
[[ "$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- "${INSTALLED_HELPER}" 2>/dev/null || true)" == \
    'regular file:755:root:root' ]] || {
  printf '%s\n' \
    '{"component":"sealai-production-remote-entrypoint","allowed":false,"reason":"installed_gate_helper_unsafe"}' >&2
  exit 78
}
[[ "$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- "${INSTALLED_LEASE}" 2>/dev/null || true)" == \
    'regular file:644:root:root' ]] || {
  printf '%s\n' \
    '{"component":"sealai-production-remote-entrypoint","allowed":false,"reason":"installed_storage_lease_unsafe"}' >&2
  exit 78
}

# shellcheck source=/dev/null
source "${INSTALLED_LEASE}"
declare -F acquire_production_storage_lease >/dev/null || exit 78

# The global lock remains held by FD 9 for the complete process. Its acquisition
# performs the canonical disk preflight. P0 does not execute any file from the
# live user-writable checkout, run Git, or contact Docker after this point.
acquire_production_storage_lease

# No P0 code path may inspect/update the live checkout or deploy an artifact.
# P1 must add a root-trusted, exact Gate-10 control/artifact verifier before it
# can replace this denial; executing a gate from the user-writable live checkout
# would itself cross the trust boundary before authorization.
printf '%s\n' \
  '{"component":"sealai-production-remote-entrypoint","allowed":false,"reason":"p1_exact_artifact_promotion_not_implemented"}' >&2
exit 78
