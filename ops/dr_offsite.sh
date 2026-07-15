#!/bin/bash -p
# Provider-neutral encrypted offsite transport using a fixed restic trust boundary.
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset PYTHONPATH PYTHONHOME CDPATH ENV BASH_ENV

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DR_HELPER="${SCRIPT_DIR}/dr_recovery.py"
readonly RESTIC_BIN=/usr/bin/restic
readonly REPOSITORY_FILE=/etc/sealai/dr/restic-repository
readonly PASSWORD_FILE=/etc/sealai/dr/restic-password
readonly GATE08_RECEIPT=/run/sealai-gates/gate-08-dr.json
readonly STORAGE_LEASE_LIB=/usr/local/libexec/sealai/production-storage-lease.sh
readonly SAFE_HOME=/var/lib/sealai-dr/empty-home
readonly CACHE_DIR=/var/cache/sealai-dr/restic
readonly RETENTION_POLICY="${SCRIPT_DIR}/dr/restic-retention-policy.json"
readonly COMMAND_TIMEOUT_SECONDS=21600

event() {
  printf '{"component":"dr_offsite","event":"%s","reason":"%s","status":"%s"}\n' \
    "$1" "$3" "$2" >&2
}

fail() {
  event offsite error "$1"
  exit 1
}

check_root() {
  local root=$1 set_id
  [[ "${root}" == /var/lib/sealai-dr/sets/* \
    && "${root}" != */ \
    && "${root}" != *//* \
    && "${root}" != *'/../'* \
    && "${root}" != *'/./'* ]] || fail invalid_set_root
  /usr/bin/python3 -I "${DR_HELPER}" verify-manifest --root "${root}" >/dev/null \
    || fail manifest_invalid
  set_id=$(/usr/bin/python3 -I "${DR_HELPER}" show-set-id --root "${root}") \
    || fail set_id_unavailable
  [[ "${root##*/}" == "${set_id}" ]] || fail set_directory_mismatch
  printf '%s\n' "${set_id}"
}

check_private_root_file() {
  local path=$1 metadata
  [[ -f "${path}" && ! -L "${path}" ]] || fail private_config_missing
  metadata=$(stat -c '%u:%a:%h' -- "${path}") || fail private_config_unsafe
  [[ "${metadata}" == "0:600:1" ]] || fail private_config_unsafe
}

check_root_executable() {
  local metadata
  [[ -f "$1" && ! -L "$1" ]] || fail installed_artifact_unsafe
  metadata=$(stat -c '%u:%a:%h' -- "$1") || fail installed_artifact_unsafe
  [[ "${metadata}" == "0:755:1" ]] || fail installed_artifact_unsafe
}

check_runtime() {
  [[ "$(id -u)" == 0 ]] || fail root_required
  [[ -x "${RESTIC_BIN}" && ! -L "${RESTIC_BIN}" ]] || fail restic_unavailable
  check_root_executable "${DR_HELPER}"
  check_private_root_file "${REPOSITORY_FILE}"
  check_private_root_file "${PASSWORD_FILE}"
  [[ -d "${SAFE_HOME}" && ! -L "${SAFE_HOME}" ]] || fail safe_home_unavailable
  [[ -d "${CACHE_DIR}" && ! -L "${CACHE_DIR}" ]] || fail cache_unavailable
}

restic() {
  /usr/bin/timeout --signal=TERM --kill-after=60s "${COMMAND_TIMEOUT_SECONDS}s" \
    /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
      RESTIC_CACHE_DIR="${CACHE_DIR}" \
      "${RESTIC_BIN}" --repository-file "${REPOSITORY_FILE}" \
      --password-file "${PASSWORD_FILE}" "$@"
}

acquire_storage_lease() {
  [[ -r "${STORAGE_LEASE_LIB}" && ! -L "${STORAGE_LEASE_LIB}" ]] \
    || fail storage_lease_unavailable
  # shellcheck source=production-storage-lease.sh
  source "${STORAGE_LEASE_LIB}"
  declare -F acquire_production_storage_lease >/dev/null \
    || fail storage_lease_unavailable
  acquire_production_storage_lease >/dev/null 2>&1 \
    || fail storage_lease_blocked
}

backup_set() {
  local root=$1 set_id summary snapshot_hash
  set_id=$(check_root "${root}")
  /usr/bin/python3 -I "${DR_HELPER}" verify-gate-08 \
    --root "${root}" --receipt "${GATE08_RECEIPT}" \
    --action dr_offsite_backup >/dev/null || fail gate_08_missing
  acquire_storage_lease
  summary=$(mktemp /var/lib/sealai-dr/.restic-summary.XXXXXX)
  trap 'rm -f -- "${summary:-}"' RETURN
  chmod 600 "${summary}"
  event offsite ok backup_started
  if ! restic backup --json --one-file-system --host sealingai-production \
    --tag sealai-dr --tag "set-${set_id}" -- "${root}" >"${summary}" 2>/dev/null; then
    fail backup_failed
  fi
  snapshot_hash=$(/usr/bin/python3 -I -c '
import hashlib, json, re, sys
snapshot = None
for line in sys.stdin:
    item = json.loads(line)
    if item.get("message_type") == "summary":
        snapshot = item.get("snapshot_id")
if not isinstance(snapshot, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot):
    raise SystemExit(2)
print(hashlib.sha256(snapshot.encode("ascii")).hexdigest())
' <"${summary}") || fail restic_summary_invalid
  /usr/bin/python3 -I "${DR_HELPER}" verify-manifest --root "${root}" >/dev/null \
    || fail source_changed_during_backup
  rm -f -- "${summary}"
  trap - RETURN
  event offsite ok backup_uploaded_unverified
  printf '%s\n' "${snapshot_hash}"
}

retention_plan() {
  # The policy is intentionally rendered only as a restic dry run. Applying
  # forget/prune requires a separate exact GATE-08 receipt and two fresh,
  # validated full-restore receipts; this script has no ungated delete path.
  [[ -f "${RETENTION_POLICY}" && ! -L "${RETENTION_POLICY}" ]] \
    || fail retention_policy_missing
  restic forget --dry-run --json --host sealingai-production --tag sealai-dr \
    --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --keep-yearly 7
}

usage() {
  printf 'usage: %s preflight | backup /var/lib/sealai-dr/sets/<set-id> | check | retention-plan\n' \
    "$0" >&2
  exit 64
}

[[ $# -ge 1 ]] || usage
command=$1
shift
check_runtime
case "${command}" in
  preflight)
    [[ $# -eq 0 ]] || usage
    restic snapshots --json --host sealingai-production --tag sealai-dr >/dev/null
    event offsite ok preflight_completed
    ;;
  backup)
    [[ $# -eq 1 ]] || usage
    backup_set "$1"
    ;;
  check)
    [[ $# -eq 0 ]] || usage
    restic check --read-data
    event offsite ok read_data_verified
    ;;
  retention-plan)
    [[ $# -eq 0 ]] || usage
    retention_plan
    ;;
  *) usage ;;
esac
