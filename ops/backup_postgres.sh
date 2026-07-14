#!/bin/bash -p
# Verified full-instance Postgres backup with target-aware capacity and retention gates.
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset PYTHONPATH PYTHONHOME

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SAFETY_HELPER="${SCRIPT_DIR}/backup_safety.py"
readonly SAFE_HOME=/home/thorsten
readonly COMMAND_TIMEOUT_SECONDS=3600

POSTGRES_CONTAINER=${POSTGRES_CONTAINER:-postgres}
TARGET_DIR=${TARGET_DIR:-"${SAFE_HOME}/sealai-backups/postgres"}
RETENTION_DAYS=${RETENTION_DAYS:-14}
BACKUP_MIN_LOCAL_COPIES=${BACKUP_MIN_LOCAL_COPIES:-2}
BACKUP_MIN_FREE_BYTES=${BACKUP_MIN_FREE_BYTES:-3221225472}
BACKUP_ESTIMATED_BYTES=${POSTGRES_BACKUP_ESTIMATED_BYTES:-${BACKUP_ESTIMATED_BYTES:-1073741824}}
BACKUP_SAFETY_STATE_DIR=${BACKUP_SAFETY_STATE_DIR:-"${SAFE_HOME}/.local/state/sealai-backup"}
readonly PRODUCTION_STORAGE_LEASE_LIB=/usr/local/libexec/sealai/production-storage-lease.sh

TMP_FILE=""
LIFECYCLE_LOCK_FD=${SEALAI_BACKUP_LIFECYCLE_FD:-}
TARGET_DIRECTORY_FD=${SEALAI_BACKUP_TARGET_FD:-}
BACKUP_COMPLETE=0

safe_helper() {
  /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${SAFETY_HELPER}" "$@"
}

event() {
  safe_helper event --component backup_postgres "$@" >&2
}

release_lifecycle_lock() {
  if [[ -n "${LIFECYCLE_LOCK_FD}" ]]; then
    flock -u "${LIFECYCLE_LOCK_FD}" || true
    exec {LIFECYCLE_LOCK_FD}>&-
    LIFECYCLE_LOCK_FD=""
  fi
  if [[ -n "${TARGET_DIRECTORY_FD}" ]]; then
    exec {TARGET_DIRECTORY_FD}>&-
    TARGET_DIRECTORY_FD=""
  fi
}

publish_no_clobber() {
  if ! ln -- "${TMP_FILE}" "${FILE}"; then
    event --event local_verification --status blocked --reason final_name_collision
    return 1
  fi
  if ! rm -f -- "${TMP_FILE}"; then
    rm -f -- "${FILE}" || true
    event --event local_verification --status blocked --reason partial_cleanup_failed
    return 1
  fi
  TMP_FILE=""
}

cleanup() {
  local rc=$?
  if [[ -n "${TMP_FILE}" ]]; then
    rm -f -- "${TMP_FILE}"
  fi
  release_lifecycle_lock
  if [[ "${rc}" -ne 0 && "${BACKUP_COMPLETE}" -eq 0 ]]; then
    event --event backup --status error --reason backup_failed || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

load_production_env() {
  local -a values=()
  mapfile -d '' -t values < <(safe_helper read-production-env --profile postgres)
  if [[ ${#values[@]} -ne 4 \
    || "${values[0]}" != POSTGRES_USER \
    || "${values[2]}" != POSTGRES_PASSWORD ]]; then
    return 1
  fi
  POSTGRES_USER=${values[1]}
  POSTGRES_PASSWORD=${values[3]}
  unset values
}

if ! load_production_env || [[ -z "${POSTGRES_PASSWORD}" ]]; then
  event --event configuration --status blocked --reason credential_missing
  exit 1
fi
if [[ ! "${POSTGRES_USER}" =~ ^[A-Za-z_][A-Za-z0-9_.-]{0,62}$ ]]; then
  event --event configuration --status blocked --reason postgres_user_invalid
  exit 1
fi

# The lease performs the root-mediated canonical Docker-filesystem preflight
# and stays held until this shell exits.
if [[ ! -r "${PRODUCTION_STORAGE_LEASE_LIB}" || -L "${PRODUCTION_STORAGE_LEASE_LIB}" ]]; then
  event --event storage_lease --status blocked --reason lease_library_unavailable
  exit 1
fi
# shellcheck source=production-storage-lease.sh
source "${PRODUCTION_STORAGE_LEASE_LIB}"
if ! declare -F acquire_production_storage_lease >/dev/null \
  || ! acquire_production_storage_lease >&2; then
  event --event storage_lease --status blocked --reason lease_acquisition_failed
  exit 1
fi

# This must run before mkdir, mktemp, or pg_dump writes anything into TARGET_DIR.
safe_helper preflight \
  --component backup_postgres \
  --target-dir "${TARGET_DIR}" \
  --estimated-write-bytes "${BACKUP_ESTIMATED_BYTES}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2

if [[ -z "${LIFECYCLE_LOCK_FD}" || -z "${TARGET_DIRECTORY_FD}" ]]; then
  exec /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${SAFETY_HELPER}" run-with-lifecycle \
    --writer postgres --target-dir "${TARGET_DIR}" \
    --setting "RETENTION_DAYS=${RETENTION_DAYS}" \
    --setting "BACKUP_MIN_LOCAL_COPIES=${BACKUP_MIN_LOCAL_COPIES}" \
    --setting "BACKUP_MIN_FREE_BYTES=${BACKUP_MIN_FREE_BYTES}" \
    --setting "BACKUP_ESTIMATED_BYTES=${BACKUP_ESTIMATED_BYTES}" \
    --setting "BACKUP_SAFETY_STATE_DIR=${BACKUP_SAFETY_STATE_DIR}" \
    --setting "POSTGRES_CONTAINER=${POSTGRES_CONTAINER}"
fi
if ! safe_helper validate-lifecycle --target-dir "${TARGET_DIR}" \
  --target-fd "${TARGET_DIRECTORY_FD}" --lock-fd "${LIFECYCLE_LOCK_FD}" >&2; then
  event --event lifecycle_lock --status blocked --reason lifecycle_binding_changed
  exit 1
fi
safe_helper preflight-bound \
  --component backup_postgres \
  --target-dir "${TARGET_DIR}" \
  --target-fd "${TARGET_DIRECTORY_FD}" \
  --lock-fd "${LIFECYCLE_LOCK_FD}" \
  --estimated-write-bytes "${BACKUP_ESTIMATED_BYTES}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2
readonly BOUND_TARGET_DIR="/proc/self/fd/${TARGET_DIRECTORY_FD}"
DATE=$(date -u +%Y-%m-%d_%H-%M-%S)
TMP_FILE=$(mktemp "${BOUND_TARGET_DIR}/.postgres-all-${DATE}.partial.XXXXXX")
TOKEN=${TMP_FILE##*.}
FILE="${BOUND_TARGET_DIR}/postgres-all-${DATE}-${TOKEN}.sql.gz"
chmod 600 "${TMP_FILE}"

event --event backup --status ok --reason backup_started
PGPASSWORD=${POSTGRES_PASSWORD}
export PGPASSWORD
/usr/bin/timeout --signal=TERM --kill-after=30s "${COMMAND_TIMEOUT_SECONDS}s" \
  docker exec -e PGPASSWORD "${POSTGRES_CONTAINER}" \
  pg_dumpall -U "${POSTGRES_USER}" | gzip -9 > "${TMP_FILE}"
unset PGPASSWORD

SIZE=$(stat -c%s "${TMP_FILE}" 2>/dev/null || stat -f%z "${TMP_FILE}")
if [[ "${SIZE}" -lt 1024 ]]; then
  event --event local_verification --status blocked --reason backup_too_small
  exit 1
fi
if ! gzip -t "${TMP_FILE}"; then
  event --event local_verification --status blocked --reason gzip_invalid
  exit 1
fi
# grep must consume the complete stream; grep -q can make zcat fail under pipefail.
if ! zcat "${TMP_FILE}" | grep -c "PostgreSQL database dump" >/dev/null; then
  event --event local_verification --status blocked --reason dump_format_invalid
  exit 1
fi

publish_no_clobber
chmod 600 "${FILE}"
safe_helper write-checksum \
  --component backup_postgres --backup "${FILE}" >&2
safe_helper verify-local \
  --component backup_postgres --backup "${FILE}" >&2
release_lifecycle_lock

# The helper deletes only old, checksum-valid copies with a matching verified
# offsite receipt, and always preserves BACKUP_MIN_LOCAL_COPIES good local files.
safe_helper prune \
  --component backup_postgres \
  --target-dir "${TARGET_DIR}" \
  --pattern 'postgres-all-*.sql.gz' \
  --retention-days "${RETENTION_DAYS}" \
  --minimum-local-copies "${BACKUP_MIN_LOCAL_COPIES}" >&2

BACKUP_COMPLETE=1
event --event backup --status ok --reason backup_completed --metric "bytes=${SIZE}"
