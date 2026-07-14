#!/bin/bash -p
# Full-download restore rehearsal for a dedicated, non-production recovery runner.
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset PYTHONPATH PYTHONHOME CDPATH ENV BASH_ENV
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG
unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_ENV_FILES
unset DR_POSTGRES_IMAGE DR_QDRANT_IMAGE DR_VERIFIER_IMAGE
unset DR_POSTGRES_PASSWORD DR_QDRANT_API_KEY DR_SET_ROOT DR_QDRANT_HELPER

readonly DR_HELPER=/usr/local/libexec/sealai/dr_recovery.py
readonly QDRANT_HELPER=/usr/local/libexec/sealai/dr_qdrant_drill.py
readonly COMPOSE_FILE=/usr/local/share/sealai/dr/restore-compose.yml
readonly RESTIC_BIN=/usr/bin/restic
readonly DOCKER_BIN=/usr/bin/docker
readonly REPOSITORY_FILE=/etc/sealai/dr/restic-repository
readonly PASSWORD_FILE=/etc/sealai/dr/restic-password
readonly KEY_ID_FILE=/etc/sealai/dr/restic-key-id.sha256
readonly IMAGE_ENV_FILE=/etc/sealai/dr/restore-images.env
readonly RUNNER_SENTINEL=/etc/sealai/dr/isolated-recovery-runner
readonly GATE08_RECEIPT=/run/sealai-gates/gate-08-dr.json
readonly SAFE_HOME=/var/lib/sealai-dr/empty-home
readonly CACHE_DIR=/var/cache/sealai-dr/restic
readonly DRILL_PARENT=/var/lib/sealai-dr/drills
readonly RECEIPT_PARENT=/var/lib/sealai-dr/receipts
readonly COMMAND_TIMEOUT_SECONDS=21600
readonly HEX_RE='^[0-9a-f]{64}$'

event() {
  printf '{"component":"dr_restore_drill","event":"restore_drill","reason":"%s","status":"%s"}\n' \
    "$2" "$1" >&2
}

fail() {
  event error "$1"
  exit 1
}

private_root_file() {
  local metadata
  [[ -f "$1" && ! -L "$1" ]] || fail private_file_missing
  metadata=$(stat -c '%u:%a:%h' -- "$1") || fail private_file_unsafe
  [[ "${metadata}" == "0:600:1" || "${metadata}" == "0:400:1" ]] \
    || fail private_file_unsafe
}

root_artifact() {
  local metadata expected_mode=$2
  [[ -f "$1" && ! -L "$1" ]] || fail installed_artifact_missing
  metadata=$(stat -c '%u:%a:%h' -- "$1") || fail installed_artifact_unsafe
  [[ "${metadata}" == "0:${expected_mode}:1" ]] || fail installed_artifact_unsafe
}

restic() {
  /usr/bin/timeout --signal=TERM --kill-after=60s "${COMMAND_TIMEOUT_SECONDS}s" \
    /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
      RESTIC_CACHE_DIR="${CACHE_DIR}" \
      "${RESTIC_BIN}" --repository-file "${REPOSITORY_FILE}" \
      --password-file "${PASSWORD_FILE}" "$@"
}

compose() {
  docker_local compose --project-name "${PROJECT}" \
    --env-file "${IMAGE_ENV_FILE}" --env-file "${EPHEMERAL_ENV}" \
    -f "${COMPOSE_FILE}" "$@"
}

docker_local() {
  "${DOCKER_BIN}" --host=unix:///var/run/docker.sock "$@"
}

cleanup() {
  local rc=$?
  if [[ -n "${PROJECT:-}" && -n "${EPHEMERAL_ENV:-}" && -f "${EPHEMERAL_ENV}" ]]; then
    compose down --volumes --remove-orphans --timeout 30 >/dev/null 2>&1 || true
  fi
  [[ -z "${EPHEMERAL_ENV:-}" ]] || rm -f -- "${EPHEMERAL_ENV}"
  [[ -z "${RESTIC_LOG:-}" ]] || rm -f -- "${RESTIC_LOG}"
  [[ -z "${CONFIG_JSON:-}" ]] || rm -f -- "${CONFIG_JSON}"
  if [[ "${rc}" -ne 0 ]]; then
    event error drill_failed || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

[[ $# -eq 2 ]] || fail invalid_arguments
SET_ID=$1
SNAPSHOT_ID=$2
[[ "${SET_ID}" =~ ${HEX_RE} && "${SNAPSHOT_ID}" =~ ${HEX_RE} ]] \
  || fail invalid_identifier
[[ "$(id -u)" == 0 ]] || fail root_required

for file in "${RUNNER_SENTINEL}" "${REPOSITORY_FILE}" "${PASSWORD_FILE}" \
  "${KEY_ID_FILE}" "${IMAGE_ENV_FILE}"; do
  private_root_file "${file}"
done
[[ "$(<"${RUNNER_SENTINEL}")" == SEALAI_DEDICATED_RECOVERY_RUNNER_V1 ]] \
  || fail runner_sentinel_invalid
[[ ! -e /home/thorsten/sealai/.env.prod \
  && ! -e /etc/sealai/disk-guard.json \
  && ! -e /run/lock/sealai-storage-mutation.lock ]] || fail production_marker_present
root_artifact "${DR_HELPER}" 755
root_artifact "${QDRANT_HELPER}" 755
root_artifact "${COMPOSE_FILE}" 644
[[ -x "${RESTIC_BIN}" && ! -L "${RESTIC_BIN}" ]] || fail restic_unavailable
[[ -x "${DOCKER_BIN}" && ! -L "${DOCKER_BIN}" ]] || fail docker_unavailable
[[ -S /var/run/docker.sock && ! -L /var/run/docker.sock ]] || fail docker_socket_unsafe
[[ -d "${SAFE_HOME}" && ! -L "${SAFE_HOME}" \
  && -d "${CACHE_DIR}" && ! -L "${CACHE_DIR}" \
  && -d "${DRILL_PARENT}" && ! -L "${DRILL_PARENT}" \
  && -d "${RECEIPT_PARENT}" && ! -L "${RECEIPT_PARENT}" ]] \
  || fail runtime_directory_missing
/usr/bin/python3 -I "${DR_HELPER}" validate-restore-images \
  --file "${IMAGE_ENV_FILE}" >/dev/null || fail restore_images_invalid

if docker_local ps --format '{{.Names}}' \
  | grep -Eq '^(postgres|qdrant|redis|backend-v2|backend-v2-worker|nginx|keycloak)$'; then
  fail production_container_present
fi
if docker_local network ls --format '{{.Name}}' | grep -Eq '^sealai(_default)?$'; then
  fail production_network_present
fi

STARTED_AT=$(date +%s)
RUN_TOKEN=$(/usr/bin/python3 -I -c 'import secrets; print(secrets.token_hex(8))')
PROJECT="sealaidr${SET_ID:0:8}${RUN_TOKEN:0:8}"
RESTORE_DIR="${DRILL_PARENT}/${SET_ID}-${RUN_TOKEN}"
RESTORED_SET="${RESTORE_DIR}/var/lib/sealai-dr/sets/${SET_ID}"
RECEIPT_DIR="${RECEIPT_PARENT}/${SET_ID}"
mkdir --mode=0700 -- "${RESTORE_DIR}" "${RECEIPT_DIR}"

RESTIC_LOG=$(mktemp "${DRILL_PARENT}/.restic-check.XXXXXX")
chmod 600 "${RESTIC_LOG}"
event ok full_download_check_started
restic check --read-data >"${RESTIC_LOG}" 2>&1 || fail restic_read_data_failed
restic restore "${SNAPSHOT_ID}" --target "${RESTORE_DIR}" \
  --include "/var/lib/sealai-dr/sets/${SET_ID}" >>"${RESTIC_LOG}" 2>&1 \
  || fail restic_restore_failed
/usr/bin/python3 -I "${DR_HELPER}" verify-manifest --root "${RESTORED_SET}" >/dev/null \
  || fail restored_manifest_invalid
[[ "$(/usr/bin/python3 -I "${DR_HELPER}" show-set-id --root "${RESTORED_SET}")" == "${SET_ID}" ]] \
  || fail restored_set_mismatch
/usr/bin/python3 -I "${DR_HELPER}" verify-gate-08 \
  --root "${RESTORED_SET}" --receipt "${GATE08_RECEIPT}" \
  --action dr_restore_drill >/dev/null || fail gate_08_missing

POSTGRES_PASSWORD=$(/usr/bin/python3 -I -c 'import secrets; print(secrets.token_urlsafe(48))')
QDRANT_API_KEY=$(/usr/bin/python3 -I -c 'import secrets; print(secrets.token_urlsafe(48))')
EPHEMERAL_ENV=$(mktemp "${DRILL_PARENT}/.restore-env.XXXXXX")
chmod 600 "${EPHEMERAL_ENV}"
printf 'DR_POSTGRES_PASSWORD=%s\nDR_QDRANT_API_KEY=%s\nDR_SET_ROOT=%s\nDR_QDRANT_HELPER=%s\n' \
  "${POSTGRES_PASSWORD}" "${QDRANT_API_KEY}" "${RESTORED_SET}" "${QDRANT_HELPER}" \
  >"${EPHEMERAL_ENV}"
unset POSTGRES_PASSWORD QDRANT_API_KEY

event ok isolated_services_starting
compose config --quiet >/dev/null || fail compose_contract_invalid
compose up -d --wait postgres qdrant verifier >/dev/null || fail isolated_services_failed
PG_BACKUP=$(/usr/bin/python3 -I "${DR_HELPER}" show-postgres-backup \
  --root "${RESTORED_SET}") || fail postgres_backup_ambiguous
gzip -cd -- "${PG_BACKUP}" \
  | compose exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q \
  >/dev/null || fail postgres_restore_failed
TABLE_COUNT=$(compose exec -T postgres psql -U postgres -d sealai_v2 -Atqc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" \
  | tr -d '[:space:]') || fail postgres_verification_failed
[[ "${TABLE_COUNT}" =~ ^[1-9][0-9]*$ ]] || fail postgres_schema_empty
compose exec -T postgres pg_amcheck --all --install-missing >/dev/null \
  || fail postgres_amcheck_failed

compose exec -T verifier python -I /opt/dr/qdrant_drill.py \
  --plan /recovery/recovery/qdrant-rebuild.json >/dev/null \
  || fail qdrant_restore_failed
/usr/bin/python3 -I "${DR_HELPER}" verify-manifest --root "${RESTORED_SET}" >/dev/null \
  || fail restore_set_changed

CONFIG_JSON=$(mktemp "${DRILL_PARENT}/.restic-config.XXXXXX")
chmod 600 "${CONFIG_JSON}"
restic cat config >"${CONFIG_JSON}" 2>/dev/null || fail repository_config_unavailable
REPOSITORY_ID=$(/usr/bin/python3 -I -c '
import json, re, sys
value = json.load(sys.stdin).get("id")
if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
    raise SystemExit(2)
print(value)
' <"${CONFIG_JSON}") || fail repository_id_invalid
KEY_ID_SHA=$(tr -d '\n' <"${KEY_ID_FILE}")
[[ "${KEY_ID_SHA}" =~ ${HEX_RE} ]] || fail key_id_invalid
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OFFSITE_RECEIPT="${RECEIPT_DIR}/offsite-${STAMP}.json"
DRILL_RECEIPT="${RECEIPT_DIR}/restore-${STAMP}.json"
/usr/bin/python3 -I "${DR_HELPER}" write-offsite-receipt \
  --root "${RESTORED_SET}" --output "${OFFSITE_RECEIPT}" \
  --repository-id "${REPOSITORY_ID}" --snapshot-id "${SNAPSHOT_ID}" \
  --encryption-key-id-sha256 "${KEY_ID_SHA}" >/dev/null || fail offsite_receipt_failed
ELAPSED=$(( $(date +%s) - STARTED_AT ))
[[ "${ELAPSED}" -gt 0 ]] || ELAPSED=1
/usr/bin/python3 -I "${DR_HELPER}" write-drill-receipt \
  --root "${RESTORED_SET}" --output "${DRILL_RECEIPT}" \
  --elapsed-seconds "${ELAPSED}" >/dev/null || fail restore_receipt_failed
/usr/bin/python3 -I "${DR_HELPER}" verify-offsite-receipt \
  --root "${RESTORED_SET}" --receipt "${OFFSITE_RECEIPT}" >/dev/null \
  || fail offsite_receipt_invalid
/usr/bin/python3 -I "${DR_HELPER}" verify-drill-receipt \
  --root "${RESTORED_SET}" --receipt "${DRILL_RECEIPT}" >/dev/null \
  || fail restore_receipt_invalid

event ok restore_drill_completed
printf '%s\n%s\n' "${OFFSITE_RECEIPT}" "${DRILL_RECEIPT}"
