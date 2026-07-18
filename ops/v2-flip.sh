#!/bin/bash -p
# ops/v2-flip.sh — THE V2 cutover switch and its one-step rollback (cutover runbook Phase 3/4).
#
# Inserts/removes the single `include snippets/v2_dashboard.conf;` line after the unique
# `server_name sealingai.com;` anchor, validates with `nginx -t` BEFORE any reload, and restores
# the file if validation fails — so the system is never left between states.
#
#   ops/v2-flip.sh --apply                                   # prod flip
#   ops/v2-flip.sh --revert                                  # prod rollback (one step, any time)
#   ops/v2-flip.sh --apply --file ops/staging/conf/default.conf --container nginx-staging
#   ops/v2-flip.sh --apply --no-reload                       # file edit only (no container ops)
#
# IMPORTANT: the prod default.conf is a SINGLE-FILE bind mount — docker tracks the inode, not the
# path. All edits here are fsynced in-place through an inode-checked descriptor,
# never mv/sed -i, or the container would keep reading the old content and the
# flip would silently not happen.
set -euo pipefail
umask 077
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
readonly DOCKER_BIN=/usr/bin/docker

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
# shellcheck source=production-release-gate-check.sh
source "${SCRIPT_DIR}/production-release-gate-check.sh"
MODE=""
FILE="nginx/default.conf"
CONTAINER="${NGINX_CONTAINER:-nginx}"
RELOAD=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) MODE=apply ;;
    --revert) MODE=revert ;;
    --file)
      [[ $# -ge 2 && -n "$2" ]] || { echo "!! --file requires a path" >&2; exit 2; }
      FILE="$2"
      shift
      ;;
    --container)
      [[ $# -ge 2 && -n "$2" ]] || { echo "!! --container requires a name" >&2; exit 2; }
      CONTAINER="$2"
      shift
      ;;
    --no-reload) RELOAD=0 ;;
    *) echo "usage: $0 --apply|--revert [--file PATH] [--container NAME] [--no-reload]" >&2; exit 2 ;;
  esac
  shift
done
[[ -n "$MODE" ]] || { echo "usage: $0 --apply|--revert [--file PATH] [--container NAME] [--no-reload]" >&2; exit 2; }

PRODUCTION_FILE="${REPO_ROOT}/nginx/default.conf"
STAGING_FILE="${REPO_ROOT}/ops/staging/conf/default.conf"

# Open both paths without following a final symlink and classify the target by
# canonical path plus inode. Only the exact production and staging tuples are
# supported. In particular, hardlink/bind aliases and arbitrary container
# names cannot turn this switch into an ungated nginx editor/reloader.
FILE_INFO="$(/usr/bin/python3 -I - "$FILE" "$PRODUCTION_FILE" <<'PY'
import json
import os
import stat
import sys


def inspect(path_value: str) -> tuple[str, int, int]:
    absolute = os.path.abspath(path_value)
    canonical = os.path.realpath(absolute)
    if absolute != canonical:
        raise SystemExit("v2-flip: symlinked target paths are forbidden")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise SystemExit("v2-flip: target is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SystemExit("v2-flip: target is not a regular file")
        return canonical, metadata.st_dev, metadata.st_ino
    finally:
        os.close(descriptor)


target = inspect(sys.argv[1])
production = inspect(sys.argv[2])
print(json.dumps({"target": target, "production": production}, separators=(",", ":")))
PY
)" || exit 2
IFS=$'\t' read -r CANONICAL_FILE TARGET_DEVICE TARGET_INODE PRODUCTION_CANONICAL PRODUCTION_DEVICE PRODUCTION_INODE < <(
  /usr/bin/python3 -I - "${FILE_INFO}" <<'PY'
import json
import sys

value = json.loads(sys.argv[1])
print(*value["target"], *value["production"], sep="\t")
PY
)

TARGET_KIND=""
if [[ "${PRODUCTION_CANONICAL}" == "${PRODUCTION_FILE}" \
      && "${CANONICAL_FILE}" == "${PRODUCTION_FILE}" \
      && "${TARGET_DEVICE}:${TARGET_INODE}" == "${PRODUCTION_DEVICE}:${PRODUCTION_INODE}" \
      && "${CONTAINER}" == nginx ]]; then
  TARGET_KIND=production
elif [[ "${CANONICAL_FILE}" == "${STAGING_FILE}" \
        && "${TARGET_DEVICE}:${TARGET_INODE}" != "${PRODUCTION_DEVICE}:${PRODUCTION_INODE}" \
        && "${CONTAINER}" == nginx-staging ]]; then
  TARGET_KIND=staging
else
  echo "!! unsupported file/container tuple; only exact production or staging targets are allowed" >&2
  exit 2
fi

if [[ "${TARGET_KIND}" == production ]]; then
  production_release_gate_check \
    "${SCRIPT_DIR}/production_release_gate.py" dashboard-publish
fi
FILE="${CANONICAL_FILE}"

ANCHOR='    server_name sealingai.com;'
INCLUDE_LINE='    include snippets/v2_dashboard.conf;  # V2-CUTOVER (ops/v2-flip.sh)'
INCLUDE_RE='^[[:space:]]*include snippets/v2_dashboard\.conf;'

TMP="$(mktemp "${TMPDIR:-/tmp}/v2-flip.XXXXXX")"
BACKUP="$(mktemp "${TMPDIR:-/tmp}/v2-flip-backup.XXXXXX")"
trap 'rm -f "$TMP" "$BACKUP"' EXIT
cp "$FILE" "$BACKUP"

write_in_place() {
  local source="$1"
  /usr/bin/python3 -I - "$FILE" "$TARGET_DEVICE" "$TARGET_INODE" "$source" <<'PY'
import os
import stat
import sys

target, expected_device, expected_inode, source = sys.argv[1:]
data = open(source, "rb").read()
flags = os.O_WRONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(target, flags)
try:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_dev != int(expected_device)
        or metadata.st_ino != int(expected_inode)
    ):
        raise SystemExit("v2-flip: target identity changed before write")
    os.ftruncate(descriptor, 0)
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        view = view[written:]
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
}

changed=0
if [[ "$MODE" == apply ]]; then
  if grep -qE "$INCLUDE_RE" "$FILE"; then
    echo ">> already applied — file unchanged"
  else
    anchor_count="$(grep -cxF "$ANCHOR" "$FILE" || true)"
    [[ "$anchor_count" == "1" ]] || { echo "!! flip anchor not unique in $FILE (count=$anchor_count) — refusing" >&2; exit 1; }
    awk -v a="$ANCHOR" -v ins="$INCLUDE_LINE" '{ print; if ($0 == a) print ins }' "$FILE" > "$TMP"
    write_in_place "$TMP"   # preserve the bind-mounted inode
    changed=1
    echo ">> include line inserted into $FILE"
  fi
else
  if ! grep -qE "$INCLUDE_RE" "$FILE"; then
    echo ">> already reverted — file unchanged"
  else
    grep -vE "$INCLUDE_RE" "$FILE" > "$TMP"
    write_in_place "$TMP"   # preserve the bind-mounted inode
    changed=1
    echo ">> include line removed from $FILE"
  fi
fi

if [[ "$RELOAD" == 1 ]]; then
  if ! "${DOCKER_BIN}" ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "!! container '$CONTAINER' not running — cannot validate/reload (use --no-reload for file-only edits)" >&2
    [[ "$changed" == 1 ]] && write_in_place "$BACKUP" && echo "!! file restored" >&2
    exit 1
  fi
  if ! "${DOCKER_BIN}" exec "$CONTAINER" nginx -t; then
    echo "!! nginx -t FAILED — restoring $FILE, NOT reloading" >&2
    write_in_place "$BACKUP"
    exit 1
  fi
  if ! "${DOCKER_BIN}" exec "$CONTAINER" nginx -s reload; then
    echo "!! nginx reload FAILED — restoring $FILE" >&2
    if [[ "$changed" == 1 ]]; then
      write_in_place "$BACKUP"
      # The first reload has an indeterminate live result. Revalidate the
      # restored bytes and attempt one rollback reload; the on-disk bind mount
      # remains restored even if the daemon cannot be reached again.
      if ! "${DOCKER_BIN}" exec "$CONTAINER" nginx -t \
        || ! "${DOCKER_BIN}" exec "$CONTAINER" nginx -s reload; then
        echo "!! rollback reload FAILED — file restored; live nginx state is indeterminate" >&2
      fi
    fi
    exit 1
  fi
  echo ">> nginx reloaded ($CONTAINER) — $MODE is live"
else
  echo ">> --no-reload: file edited only; validate + reload separately"
fi
