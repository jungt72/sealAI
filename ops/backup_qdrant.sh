#!/bin/bash -p
# Verified Qdrant snapshot backup with capacity and remote-delete gates.
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset PYTHONPATH PYTHONHOME

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SAFETY_HELPER="${SCRIPT_DIR}/backup_safety.py"
readonly SAFE_HOME=/home/thorsten
readonly HTTP_TIMEOUT_SECONDS=600
readonly COPY_TIMEOUT_SECONDS=3600

BACKEND_CONTAINER=${BACKEND_CONTAINER:-backend-v2}
QDRANT_CONTAINER=${QDRANT_CONTAINER:-qdrant}
QDRANT_INTERNAL_URL=${QDRANT_INTERNAL_URL:-http://qdrant:6333}
TARGET_DIR=${TARGET_DIR:-"${SAFE_HOME}/sealai-backups/qdrant"}
RETENTION_DAYS=${RETENTION_DAYS:-14}
BACKUP_MIN_LOCAL_COPIES=${BACKUP_MIN_LOCAL_COPIES:-2}
BACKUP_MIN_FREE_BYTES=${BACKUP_MIN_FREE_BYTES:-3221225472}
BACKUP_ESTIMATED_BYTES=${QDRANT_BACKUP_ESTIMATED_BYTES:-${BACKUP_ESTIMATED_BYTES:-1073741824}}
BACKUP_SAFETY_STATE_DIR=${BACKUP_SAFETY_STATE_DIR:-"${SAFE_HOME}/.local/state/sealai-backup"}
QDRANT_REMOTE_DELETE_POLICY=${QDRANT_REMOTE_DELETE_POLICY:-verified-local}
QDRANT_OFFSITE_RECEIPT=${QDRANT_OFFSITE_RECEIPT:-}
readonly DOCKER_DATA_FILESYSTEM=/mnt/sealai-data
readonly PRODUCTION_STORAGE_LEASE_LIB=/usr/local/libexec/sealai/production-storage-lease.sh

TMP_FILE=""
FILE=""
SNAPSHOT_NAME=""
SNAPSHOT_SIZE=""
SNAPSHOT_CHECKSUM=""
LIFECYCLE_LOCK_FD=${SEALAI_BACKUP_LIFECYCLE_FD:-}
TARGET_DIRECTORY_FD=${SEALAI_BACKUP_TARGET_FD:-}
BACKUP_BINDING_FD=""
BACKUP_COMPLETE=0

safe_helper() {
  /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${SAFETY_HELPER}" "$@"
}

event() {
  safe_helper event --component backup_qdrant "$@" >&2
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

release_backup_binding() {
  if [[ -n "${BACKUP_BINDING_FD}" ]]; then
    flock -u "${BACKUP_BINDING_FD}" || true
    exec {BACKUP_BINDING_FD}>&-
    BACKUP_BINDING_FD=""
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

qdrant_api() {
  # The credential is already present in backend-v2's environment. Feed it to
  # curl through stdin so it is never present in docker-exec/curl argv, backup
  # events, or the host environment. The allowlist rejects config-file control
  # characters before curl parses the generated one-line config.
  /usr/bin/timeout --signal=TERM --kill-after=30s "${HTTP_TIMEOUT_SECONDS}s" \
    docker exec "${BACKEND_CONTAINER}" sh -eu -c '
      key=${SEALAI_V2_QDRANT_API_KEY:-}
      case "${key}" in
        ""|*[!A-Za-z0-9._~-]*) exit 64 ;;
      esac
      [ "${#key}" -ge 32 ] && [ "${#key}" -le 256 ] || exit 64
      printf '\''header = "api-key: %s"\n'\'' "${key}" \
        | curl --config - --connect-timeout 30 --max-time 540 -fsS "$@"
    ' sh "$@"
}

cleanup() {
  local rc=$?
  if [[ -n "${TMP_FILE}" ]]; then
    rm -f -- "${TMP_FILE}"
  fi
  release_backup_binding
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
  mapfile -d '' -t values < <(safe_helper read-production-env --profile qdrant)
  if [[ ${#values[@]} -ne 2 || "${values[0]}" != SEALAI_V2_QDRANT_COLLECTION ]]; then
    return 1
  fi
  COLLECTION=${values[1]}
  unset values
}

if ! load_production_env; then
  event --event configuration --status blocked --reason production_env_invalid
  exit 1
fi

if [[ ! "${BACKEND_CONTAINER}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ \
  || ! "${QDRANT_CONTAINER}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ \
  || "${QDRANT_INTERNAL_URL}" != "http://qdrant:6333" ]]; then
  event --event configuration --status blocked --reason qdrant_endpoint_invalid
  exit 1
fi

case "${QDRANT_REMOTE_DELETE_POLICY}" in
  verified-local|verified-offsite) ;;
  *)
    event --event configuration --status blocked --reason invalid_remote_delete_policy
    exit 1
    ;;
esac
if [[ "${COLLECTION}" == "." || "${COLLECTION}" == ".." \
  || ! "${COLLECTION}" =~ ^[A-Za-z0-9._-]+$ ]]; then
  event --event configuration --status blocked --reason invalid_collection
  exit 1
fi

# The lease covers the Docker data mount where the server-side snapshot is
# created; TARGET_DIR is checked separately below.
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

# The canonical guard checks fresh 85/80 state. This second, target-aware check
# also reserves the estimated snapshot bytes on the fixed Docker data mount.
safe_helper preflight \
  --component backup_qdrant_data \
  --target-dir "${DOCKER_DATA_FILESYSTEM}" \
  --estimated-write-bytes "${BACKUP_ESTIMATED_BYTES}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2

# Run this before the API creates a remote snapshot and before docker cp writes locally.
safe_helper preflight \
  --component backup_qdrant \
  --target-dir "${TARGET_DIR}" \
  --estimated-write-bytes "${BACKUP_ESTIMATED_BYTES}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2

if [[ -z "${LIFECYCLE_LOCK_FD}" || -z "${TARGET_DIRECTORY_FD}" ]]; then
  exec /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    /usr/bin/python3 -I "${SAFETY_HELPER}" run-with-lifecycle \
    --writer qdrant --target-dir "${TARGET_DIR}" \
    --setting "RETENTION_DAYS=${RETENTION_DAYS}" \
    --setting "BACKUP_MIN_LOCAL_COPIES=${BACKUP_MIN_LOCAL_COPIES}" \
    --setting "BACKUP_MIN_FREE_BYTES=${BACKUP_MIN_FREE_BYTES}" \
    --setting "BACKUP_ESTIMATED_BYTES=${BACKUP_ESTIMATED_BYTES}" \
    --setting "BACKUP_SAFETY_STATE_DIR=${BACKUP_SAFETY_STATE_DIR}" \
    --setting "BACKEND_CONTAINER=${BACKEND_CONTAINER}" \
    --setting "QDRANT_CONTAINER=${QDRANT_CONTAINER}" \
    --setting "QDRANT_INTERNAL_URL=${QDRANT_INTERNAL_URL}" \
    --setting "QDRANT_REMOTE_DELETE_POLICY=${QDRANT_REMOTE_DELETE_POLICY}" \
    --setting "QDRANT_OFFSITE_RECEIPT=${QDRANT_OFFSITE_RECEIPT}"
fi
if ! safe_helper validate-lifecycle --target-dir "${TARGET_DIR}" \
  --target-fd "${TARGET_DIRECTORY_FD}" --lock-fd "${LIFECYCLE_LOCK_FD}" >&2; then
  event --event lifecycle_lock --status blocked --reason lifecycle_binding_changed
  exit 1
fi
# Recheck the fixed Docker-data filesystem under the still-held global lease,
# then measure the exact opened target filesystem before either POST or mktemp.
safe_helper preflight \
  --component backup_qdrant_data \
  --target-dir "${DOCKER_DATA_FILESYSTEM}" \
  --estimated-write-bytes "${BACKUP_ESTIMATED_BYTES}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2
safe_helper preflight-bound \
  --component backup_qdrant \
  --target-dir "${TARGET_DIR}" \
  --target-fd "${TARGET_DIRECTORY_FD}" \
  --lock-fd "${LIFECYCLE_LOCK_FD}" \
  --estimated-write-bytes "${BACKUP_ESTIMATED_BYTES}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2
readonly BOUND_TARGET_DIR="/proc/self/fd/${TARGET_DIRECTORY_FD}"
DATE=$(date -u +%Y-%m-%d_%H-%M-%S)
TMP_FILE=$(mktemp "${BOUND_TARGET_DIR}/.${COLLECTION}-${DATE}.partial.XXXXXX")
TOKEN=${TMP_FILE##*.}
FILE="${BOUND_TARGET_DIR}/${COLLECTION}-${DATE}-${TOKEN}.snapshot"
chmod 600 "${TMP_FILE}"

event --event backup --status ok --reason snapshot_started
RESPONSE=$(qdrant_api -X POST \
  "${QDRANT_INTERNAL_URL}/collections/${COLLECTION}/snapshots")

# Parse through stdin; the untrusted API response is never interpolated or logged.
SNAPSHOT_METADATA=$(printf '%s' "${RESPONSE}" \
  | /usr/bin/timeout --signal=TERM --kill-after=5s 60s \
    docker exec -i "${BACKEND_CONTAINER}" python3 -c '
import json, sys
payload = json.load(sys.stdin)
result = payload.get("result", {})
if payload.get("status") != "ok" or not isinstance(result, dict):
    raise SystemExit(2)
name = result.get("name")
size = result.get("size")
checksum = result.get("checksum")
if (
    not isinstance(name, str)
    or not isinstance(size, int)
    or isinstance(size, bool)
    or size < 1024
):
    raise SystemExit(2)
if not isinstance(checksum, str):
    raise SystemExit(2)
print(f"{name}\t{size}\t{checksum.lower()}")
')
unset RESPONSE
IFS=$'\t' read -r SNAPSHOT_NAME SNAPSHOT_SIZE SNAPSHOT_CHECKSUM <<<"${SNAPSHOT_METADATA}"
unset SNAPSHOT_METADATA

if [[ -z "${SNAPSHOT_NAME}" || "${SNAPSHOT_NAME}" == "." || "${SNAPSHOT_NAME}" == ".." \
  || ! "${SNAPSHOT_NAME}" =~ ^[A-Za-z0-9._-]+$ ]]; then
  event --event remote_snapshot --status blocked --reason snapshot_name_invalid
  exit 1
fi
if [[ ! "${SNAPSHOT_SIZE}" =~ ^[0-9]+$ ]]; then
  event --event remote_snapshot --status blocked --reason snapshot_size_invalid
  exit 1
fi
if [[ ! "${SNAPSHOT_CHECKSUM}" =~ ^[0-9a-f]{64}$ ]]; then
  event --event remote_snapshot --status blocked --reason snapshot_checksum_invalid
  exit 1
fi

# The API now provides the exact source size. Re-observe TARGET_DIR before the
# copy: on a shared filesystem the completed server snapshot is already part
# of current usage, so this projects the coexisting second copy correctly.
safe_helper preflight-bound \
  --component backup_qdrant \
  --target-dir "${TARGET_DIR}" \
  --target-fd "${TARGET_DIRECTORY_FD}" \
  --lock-fd "${LIFECYCLE_LOCK_FD}" \
  --estimated-write-bytes "${SNAPSHOT_SIZE}" \
  --minimum-reserve-bytes "${BACKUP_MIN_FREE_BYTES}" \
  --state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2

/usr/bin/timeout --signal=TERM --kill-after=30s "${COPY_TIMEOUT_SECONDS}s" docker cp \
  "${QDRANT_CONTAINER}:/qdrant/snapshots/${COLLECTION}/${SNAPSHOT_NAME}" \
  "${TMP_FILE}"
chmod 600 "${TMP_FILE}"
SIZE=$(stat -c%s "${TMP_FILE}" 2>/dev/null || stat -f%z "${TMP_FILE}")
if [[ "${SIZE}" -lt 1024 ]]; then
  event --event local_verification --status blocked --reason backup_too_small
  exit 1
fi
safe_helper verify-expected \
  --component backup_qdrant \
  --backup "${TMP_FILE}" \
  --expected-bytes "${SNAPSHOT_SIZE}" \
  --expected-sha256 "${SNAPSHOT_CHECKSUM}" >&2

publish_no_clobber
chmod 600 "${FILE}"
safe_helper write-checksum \
  --component backup_qdrant --backup "${FILE}" >&2
safe_helper verify-local \
  --component backup_qdrant --backup "${FILE}" >&2

# Hold the exact local inode and both cooperative locks through the delete gate
# and confirmed Qdrant DELETE. The helper re-hashes this inherited descriptor,
# requires path/dev/inode/metadata identity and nlink=1, and compares it with
# the server-provided checksum and size immediately before the API mutation.
if ! exec {BACKUP_BINDING_FD}<"${FILE}"; then
  event --event remote_delete_gate --status blocked --reason binding_open_failed
  exit 1
fi
if ! flock -n "${BACKUP_BINDING_FD}"; then
  event --event remote_delete_gate --status blocked --reason binding_lock_failed
  exit 1
fi

REMOTE_GATE=(
  safe_helper remote-delete-eligible
  --component backup_qdrant
  --backup "${FILE}"
  --policy "${QDRANT_REMOTE_DELETE_POLICY}"
  --backup-fd "${BACKUP_BINDING_FD}"
  --expected-bytes "${SNAPSHOT_SIZE}"
  --expected-sha256 "${SNAPSHOT_CHECKSUM}"
)
if [[ -n "${QDRANT_OFFSITE_RECEIPT}" ]]; then
  REMOTE_GATE+=(--receipt "${QDRANT_OFFSITE_RECEIPT}")
fi

if "${REMOTE_GATE[@]}" >&2; then
  DELETE_RESPONSE=$(qdrant_api -X DELETE \
    "${QDRANT_INTERNAL_URL}/collections/${COLLECTION}/snapshots/${SNAPSHOT_NAME}")
  if ! printf '%s' "${DELETE_RESPONSE}" \
    | /usr/bin/timeout --signal=TERM --kill-after=5s 60s \
      docker exec -i "${BACKEND_CONTAINER}" python3 -c '
import json, sys
payload = json.load(sys.stdin)
if payload.get("status") != "ok" or payload.get("result") is not True:
    raise SystemExit(2)
' >/dev/null; then
    unset DELETE_RESPONSE
    event --event remote_snapshot --status blocked --reason snapshot_delete_unconfirmed
    exit 1
  fi
  unset DELETE_RESPONSE
  event --event remote_snapshot --status ok --reason snapshot_deleted
else
  # The local backup remains valid, but remote cleanup is incomplete and must alert.
  event --event remote_snapshot --status blocked --reason snapshot_retained
  exit 1
fi

release_backup_binding
release_lifecycle_lock

safe_helper prune \
  --component backup_qdrant \
  --target-dir "${TARGET_DIR}" \
  --pattern "${COLLECTION}-*.snapshot" \
  --retention-days "${RETENTION_DAYS}" \
  --minimum-local-copies "${BACKUP_MIN_LOCAL_COPIES}" >&2

BACKUP_COMPLETE=1
event --event backup --status ok --reason backup_completed --metric "bytes=${SIZE}"
