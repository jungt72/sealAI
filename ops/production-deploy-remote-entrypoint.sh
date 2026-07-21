#!/bin/bash -p
# Root-installed, lease-holding boundary for the production deployment workflow.
# Independently re-verifies the exact Gate-10 control commit, its release
# decision, and its backend image digest (never trusting the SSH payload's own
# claims) before terminating in an explicit not-yet-implemented denial. P1
# still has no actual promotion implementation -- no docker pull, no compose
# up -- that remains a deliberately separate, later, higher-stakes change.
set -euo pipefail
umask 077
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

readonly INSTALLED_HELPER=/usr/local/libexec/sealai/production-release-gate-check.sh
readonly INSTALLED_LEASE=/usr/local/libexec/sealai/production-storage-lease.sh
readonly LIVE_VERIFIER=/home/thorsten/sealai/ops/verify_gate10_control_commit.py
readonly VERIFIER_SHA256=5cfa4e8cc6d71f369492a8c6e8fdd6259f8ce5587979327bc4a93605e3cbb6b0

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
# performs the canonical disk preflight.
acquire_production_storage_lease

# The verifier's own logic must independently re-clone the exact control commit,
# which only the live checkout's git remote can supply -- so it necessarily lives
# there, not under /usr/local/libexec. It is never executed directly from that
# user-writable location: staged as non-executable data, hash-checked against the
# value fixed in this already-installed, already hash-bound entrypoint, and only
# the verified root-owned copy is ever run -- the exact trusted-loader pattern
# documented for Gate-08 in docs/ops/production-release-freeze.md, applied here.
[[ -f "${LIVE_VERIFIER}" && ! -L "${LIVE_VERIFIER}" ]] || {
  printf '%s\n' \
    '{"component":"sealai-production-remote-entrypoint","allowed":false,"reason":"verifier_source_unavailable"}' >&2
  exit 78
}
VERIFIER_STAGE="$(/usr/bin/mktemp -d /run/sealai-gate10-verifier.XXXXXX)"
/usr/bin/chown root:root "${VERIFIER_STAGE}"
/usr/bin/chmod 0700 "${VERIFIER_STAGE}"
cleanup_verifier_stage() {
  [[ "${VERIFIER_STAGE}" == /run/sealai-gate10-verifier.* ]] || return
  /usr/bin/rm -r -- "${VERIFIER_STAGE}" 2>/dev/null || true
}
trap cleanup_verifier_stage EXIT

readonly STAGED_VERIFIER="${VERIFIER_STAGE}/verify-gate10-control-commit.data"
/usr/bin/cp -- "${LIVE_VERIFIER}" "${STAGED_VERIFIER}"
/usr/bin/chown root:root "${STAGED_VERIFIER}"
/usr/bin/chmod 0600 "${STAGED_VERIFIER}"
ACTUAL_VERIFIER_SHA256="$(/usr/bin/sha256sum -- "${STAGED_VERIFIER}" | /usr/bin/awk '{print $1}')"
[[ "${ACTUAL_VERIFIER_SHA256}" == "${VERIFIER_SHA256}" ]] || {
  printf '%s\n' \
    '{"component":"sealai-production-remote-entrypoint","allowed":false,"reason":"verifier_hash_mismatch"}' >&2
  exit 78
}

if VERIFY_OUTPUT="$(
  /usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${STAGED_VERIFIER}" \
    --control-sha "${CONTROL_SHA}" --source-sha "${SOURCE_SHA}" --backend-image "${BACKEND_IMAGE}" \
    2>&1
)"; then
  printf '%s\n' "${VERIFY_OUTPUT}"
else
  VERIFIER_STATUS=$?
  printf '%s\n' "${VERIFY_OUTPUT}" >&2
  exit "${VERIFIER_STATUS}"
fi

# Verification succeeded: the control commit, its Gate-10 decision, and its
# backend image digest are all independently proven genuine on this host, not
# merely asserted by the SSH payload. P0 still has no promotion implementation
# -- no docker pull, no compose up exists yet. That remains a deliberately
# separate, later, higher-stakes change.
printf '%s\n' \
  '{"component":"sealai-production-remote-entrypoint","allowed":false,"reason":"p1_exact_artifact_promotion_not_implemented"}' >&2
exit 78
