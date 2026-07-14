#!/bin/bash -p
# Create a verified, database-local pre-migration backup for sealai_v2.
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
TARGET_DIR=${TARGET_DIR:-"${SAFE_HOME}/sealai-backups/pre-migration"}
RETENTION_DAYS=${RETENTION_DAYS:-30}
BACKUP_MIN_LOCAL_COPIES=${BACKUP_MIN_LOCAL_COPIES:-2}
BACKUP_MIN_FREE_BYTES=${BACKUP_MIN_FREE_BYTES:-3221225472}
BACKUP_ESTIMATED_BYTES=${V2_DATABASE_BACKUP_ESTIMATED_BYTES:-${BACKUP_ESTIMATED_BYTES:-1073741824}}
BACKUP_SAFETY_STATE_DIR=${BACKUP_SAFETY_STATE_DIR:-"${SAFE_HOME}/.local/state/sealai-backup"}
readonly PRODUCTION_STORAGE_LEASE_LIB=/usr/local/libexec/sealai/production-storage-lease.sh

partial=""
LIFECYCLE_LOCK_FD=${SEALAI_BACKUP_LIFECYCLE_FD:-}
TARGET_DIRECTORY_FD=${SEALAI_BACKUP_TARGET_FD:-}
BACKUP_COMPLETE=0

safe_helper() {
  /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${SAFETY_HELPER}" "$@"
}

event() {
  safe_helper event --component backup_v2_database "$@" >&2
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
  if ! ln -- "${partial}" "${file}"; then
    event --event local_verification --status blocked --reason final_name_collision
    return 1
  fi
  if ! rm -f -- "${partial}"; then
    rm -f -- "${file}" || true
    event --event local_verification --status blocked --reason partial_cleanup_failed
    return 1
  fi
  partial=""
}

cleanup() {
  local rc=$?
  if [[ -n "${partial}" ]]; then
    rm -f -- "${partial}"
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
  mapfile -d '' -t values < <(safe_helper read-production-env --profile v2_database)
  if [[ ${#values[@]} -ne 6 \
    || "${values[0]}" != POSTGRES_USER \
    || "${values[2]}" != POSTGRES_PASSWORD \
    || "${values[4]}" != SEALAI_V2_DATABASE_NAME ]]; then
    return 1
  fi
  POSTGRES_USER=${values[1]}
  POSTGRES_PASSWORD=${values[3]}
  DATABASE_NAME=${values[5]}
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
if [[ ! "${DATABASE_NAME}" =~ ^[A-Za-z_][A-Za-z0-9_.-]{0,62}$ ]]; then
  event --event configuration --status blocked --reason database_name_invalid
  exit 1
fi

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

safe_helper preflight \
  --component backup_v2_database \
  --target-dir "${TARGET_DIR}" \
  --estimated-write-bytes "${BACKUP_ESTIMATED_BYTES}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2

if [[ -z "${LIFECYCLE_LOCK_FD}" || -z "${TARGET_DIRECTORY_FD}" ]]; then
  exec /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${SAFETY_HELPER}" run-with-lifecycle \
    --writer v2_database --target-dir "${TARGET_DIR}" \
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
  --component backup_v2_database \
  --target-dir "${TARGET_DIR}" \
  --target-fd "${TARGET_DIRECTORY_FD}" \
  --lock-fd "${LIFECYCLE_LOCK_FD}" \
  --estimated-write-bytes "${BACKUP_ESTIMATED_BYTES}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2
readonly BOUND_TARGET_DIR="/proc/self/fd/${TARGET_DIRECTORY_FD}"
stamp=$(date -u +%Y-%m-%d_%H-%M-%S)
partial=$(mktemp "${BOUND_TARGET_DIR}/.${DATABASE_NAME}-pre-migration-${stamp}.partial.XXXXXX")
token=${partial##*.}
file="${BOUND_TARGET_DIR}/${DATABASE_NAME}-pre-migration-${stamp}-${token}.dump"
canonical_file="${TARGET_DIR}/${DATABASE_NAME}-pre-migration-${stamp}-${token}.dump"
chmod 600 "${partial}"

event --event backup --status ok --reason backup_started
PGPASSWORD=${POSTGRES_PASSWORD}
export PGPASSWORD
/usr/bin/timeout --signal=TERM --kill-after=30s "${COMMAND_TIMEOUT_SECONDS}s" \
  docker exec -e PGPASSWORD "${POSTGRES_CONTAINER}" \
  pg_dump --format=custom --no-owner --no-acl \
  --username="${POSTGRES_USER}" --dbname="${DATABASE_NAME}" > "${partial}"
unset PGPASSWORD

size=$(wc -c < "${partial}" | tr -d ' ')
if [[ "${size}" -lt 1024 ]]; then
  event --event local_verification --status blocked --reason backup_too_small
  exit 1
fi
/usr/bin/timeout --signal=TERM --kill-after=30s "${COMMAND_TIMEOUT_SECONDS}s" \
  docker exec -i "${POSTGRES_CONTAINER}" pg_restore --list \
  < "${partial}" >/dev/null

publish_no_clobber
chmod 600 "${file}"
safe_helper write-checksum \
  --component backup_v2_database --backup "${file}" >&2
safe_helper verify-local \
  --component backup_v2_database --backup "${file}" >&2
release_lifecycle_lock

safe_helper prune \
  --component backup_v2_database \
  --target-dir "${TARGET_DIR}" \
  --pattern "${DATABASE_NAME}-pre-migration-*.dump" \
  --retention-days "${RETENTION_DAYS}" \
  --minimum-local-copies "${BACKUP_MIN_LOCAL_COPIES}" >&2

BACKUP_COMPLETE=1
event --event backup --status ok --reason backup_completed --metric "bytes=${size}"
printf '%s\n' "${canonical_file}"
