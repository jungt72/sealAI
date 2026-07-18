#!/bin/bash -p
# Nightly backup orchestrator. Child scripts fail independently and log JSON events.
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset PYTHONPATH PYTHONHOME

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SAFETY_HELPER="${DIR}/backup_safety.py"
readonly SAFE_HOME=/home/thorsten
readonly CHILD_TIMEOUT_SECONDS=14400
readonly LOG_FILE=/home/thorsten/sealai-backups/backup.log
RETENTION_DAYS=${RETENTION_DAYS:-14}
BACKUP_MIN_LOCAL_COPIES=${BACKUP_MIN_LOCAL_COPIES:-2}
BACKUP_MIN_FREE_BYTES=${BACKUP_MIN_FREE_BYTES:-3221225472}
BACKUP_SAFETY_STATE_DIR=${BACKUP_SAFETY_STATE_DIR:-"${SAFE_HOME}/.local/state/sealai-backup"}
POSTGRES_BACKUP_ESTIMATED_BYTES=${POSTGRES_BACKUP_ESTIMATED_BYTES:-1073741824}
QDRANT_BACKUP_ESTIMATED_BYTES=${QDRANT_BACKUP_ESTIMATED_BYTES:-1073741824}
POSTGRES_CONTAINER=${POSTGRES_CONTAINER:-postgres}
BACKEND_CONTAINER=${BACKEND_CONTAINER:-backend-v2}
QDRANT_CONTAINER=${QDRANT_CONTAINER:-qdrant}
QDRANT_INTERNAL_URL=${QDRANT_INTERNAL_URL:-http://qdrant:6333}
QDRANT_REMOTE_DELETE_POLICY=${QDRANT_REMOTE_DELETE_POLICY:-verified-local}
QDRANT_OFFSITE_RECEIPT=${QDRANT_OFFSITE_RECEIPT:-}
LOG_DIRECTORY_FD=${SEALAI_BACKUP_LOG_DIR_FD:-}
LOG_FD=${SEALAI_BACKUP_LOG_FD:-}
RUN_LOCK_FD=${SEALAI_BACKUP_RUN_LOCK_FD:-}

safe_helper() {
  /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${SAFETY_HELPER}" "$@"
}

fatal_event() {
  if ! safe_helper event --component backup_run \
    --event backup_run --status error --reason "$1" >&2; then
    printf '%s\n' \
      '{"component":"backup_run","event":"backup_run","reason":"event_failure","status":"error"}' \
      >&2
  fi
}

cleanup() {
  if [[ -n "${RUN_LOCK_FD}" ]]; then
    flock -u "${RUN_LOCK_FD}" || true
    exec {RUN_LOCK_FD}>&-
    RUN_LOCK_FD=""
  fi
  if [[ -n "${LOG_FD}" ]]; then
    exec {LOG_FD}>&-
    LOG_FD=""
  fi
  if [[ -n "${LOG_DIRECTORY_FD}" ]]; then
    exec {LOG_DIRECTORY_FD}>&-
    LOG_DIRECTORY_FD=""
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

if [[ -z "${LOG_DIRECTORY_FD}" || -z "${LOG_FD}" || -z "${RUN_LOCK_FD}" ]]; then
  exec /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${SAFETY_HELPER}" run-with-orchestrator-lock \
    --setting "RETENTION_DAYS=${RETENTION_DAYS}" \
    --setting "BACKUP_MIN_LOCAL_COPIES=${BACKUP_MIN_LOCAL_COPIES}" \
    --setting "BACKUP_MIN_FREE_BYTES=${BACKUP_MIN_FREE_BYTES}" \
    --setting "BACKUP_SAFETY_STATE_DIR=${BACKUP_SAFETY_STATE_DIR}" \
    --setting "POSTGRES_BACKUP_ESTIMATED_BYTES=${POSTGRES_BACKUP_ESTIMATED_BYTES}" \
    --setting "QDRANT_BACKUP_ESTIMATED_BYTES=${QDRANT_BACKUP_ESTIMATED_BYTES}" \
    --setting "POSTGRES_CONTAINER=${POSTGRES_CONTAINER}" \
    --setting "BACKEND_CONTAINER=${BACKEND_CONTAINER}" \
    --setting "QDRANT_CONTAINER=${QDRANT_CONTAINER}" \
    --setting "QDRANT_INTERNAL_URL=${QDRANT_INTERNAL_URL}" \
    --setting "QDRANT_REMOTE_DELETE_POLICY=${QDRANT_REMOTE_DELETE_POLICY}" \
    --setting "QDRANT_OFFSITE_RECEIPT=${QDRANT_OFFSITE_RECEIPT}"
fi
if ! safe_helper validate-orchestrator \
  --directory-fd "${LOG_DIRECTORY_FD}" --log-fd "${LOG_FD}" \
  --lock-fd "${RUN_LOCK_FD}" >&2; then
  fatal_event orchestrator_binding_changed
  exit 1
fi

event() {
  safe_helper event --component backup_run "$@" >&"${LOG_FD}" 2>&1
}

event --event backup_run --status ok --reason run_started
PG_OK=1
QD_OK=1

if /usr/bin/timeout --signal=TERM --kill-after=60s "${CHILD_TIMEOUT_SECONDS}s" \
  "${DIR}/backup_postgres.sh" >&"${LOG_FD}" 2>&1; then PG_OK=0; fi
if /usr/bin/timeout --signal=TERM --kill-after=60s "${CHILD_TIMEOUT_SECONDS}s" \
  "${DIR}/backup_qdrant.sh" >&"${LOG_FD}" 2>&1; then QD_OK=0; fi

if [[ "${PG_OK}" -eq 0 && "${QD_OK}" -eq 0 ]]; then
  event --event backup_run --status ok --reason run_completed \
    --metric postgres_ok=true --metric qdrant_ok=true
  exit 0
fi
event --event backup_run --status error --reason child_backup_failed \
  --metric "postgres_ok=$([[ ${PG_OK} -eq 0 ]] && echo true || echo false)" \
  --metric "qdrant_ok=$([[ ${QD_OK} -eq 0 ]] && echo true || echo false)"
exit 1
