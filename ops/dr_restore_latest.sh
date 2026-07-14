#!/bin/bash -p
# Resolve the newest tagged immutable DR set, then delegate to the exact drill runner.
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset PYTHONPATH PYTHONHOME CDPATH ENV BASH_ENV
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG
unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_ENV_FILES

readonly RESTIC_BIN=/usr/bin/restic
readonly REPOSITORY_FILE=/etc/sealai/dr/restic-repository
readonly PASSWORD_FILE=/etc/sealai/dr/restic-password
readonly SAFE_HOME=/var/lib/sealai-dr/empty-home
readonly CACHE_DIR=/var/cache/sealai-dr/restic
readonly DRILL_RUNNER=/usr/local/libexec/sealai/dr_restore_drill.sh

fail() {
  printf '{"component":"dr_restore_latest","event":"restore_selection","reason":"%s","status":"error"}\n' \
    "$1" >&2
  exit 1
}

private_root_file() {
  local metadata
  [[ -f "$1" && ! -L "$1" ]] || fail private_file_missing
  metadata=$(stat -c '%u:%a:%h' -- "$1") || fail private_file_unsafe
  [[ "${metadata}" == "0:600:1" || "${metadata}" == "0:400:1" ]] \
    || fail private_file_unsafe
}

root_executable() {
  local metadata
  [[ -f "$1" && ! -L "$1" ]] || fail runtime_unavailable
  metadata=$(stat -c '%u:%a:%h' -- "$1") || fail runtime_unavailable
  [[ "${metadata}" == "0:755:1" ]] || fail runtime_unavailable
}

[[ $# -eq 0 && "$(id -u)" == 0 ]] || fail invalid_invocation
[[ -x "${RESTIC_BIN}" && ! -L "${RESTIC_BIN}" ]] || fail runtime_unavailable
root_executable "${DRILL_RUNNER}"
private_root_file "${REPOSITORY_FILE}"
private_root_file "${PASSWORD_FILE}"
[[ -d "${SAFE_HOME}" && ! -L "${SAFE_HOME}" \
  && -d "${CACHE_DIR}" && ! -L "${CACHE_DIR}" \
  && -d /var/lib/sealai-dr/drills && ! -L /var/lib/sealai-dr/drills ]] \
  || fail runtime_directory_missing
SNAPSHOTS=$(mktemp /var/lib/sealai-dr/drills/.snapshots.XXXXXX)
trap 'rm -f -- "${SNAPSHOTS}"' EXIT
chmod 600 "${SNAPSHOTS}"
/usr/bin/timeout --signal=TERM --kill-after=60s 1800s \
  /usr/bin/env -i HOME="${SAFE_HOME}" PATH="${PATH}" LANG=C LC_ALL=C \
    RESTIC_CACHE_DIR="${CACHE_DIR}" \
    "${RESTIC_BIN}" --repository-file "${REPOSITORY_FILE}" \
    --password-file "${PASSWORD_FILE}" snapshots --json --latest 1 \
    --host sealingai-production --tag sealai-dr >"${SNAPSHOTS}" 2>/dev/null \
  || fail snapshot_query_failed
readarray -t IDS < <(/usr/bin/python3 -I -c '
import json, re, sys
items = json.load(sys.stdin)
if not isinstance(items, list) or len(items) != 1:
    raise SystemExit(2)
item = items[0]
snapshot = item.get("id")
tags = item.get("tags")
if not isinstance(snapshot, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot):
    raise SystemExit(2)
set_tags = [tag for tag in tags if isinstance(tag, str) and re.fullmatch(r"set-[0-9a-f]{64}", tag)] if isinstance(tags, list) else []
if len(set_tags) != 1:
    raise SystemExit(2)
print(set_tags[0][4:])
print(snapshot)
' <"${SNAPSHOTS}") || fail snapshot_selection_invalid
[[ ${#IDS[@]} -eq 2 ]] || fail snapshot_selection_invalid
rm -f -- "${SNAPSHOTS}"
trap - EXIT
exec "${DRILL_RUNNER}" "${IDS[0]}" "${IDS[1]}"
