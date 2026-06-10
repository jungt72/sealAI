#!/usr/bin/env bash
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
# path. All edits here are in-place (`cat > file`), never mv/sed -i, or the container would keep
# reading the old content and the flip would silently not happen.
set -euo pipefail

MODE=""
FILE="nginx/default.conf"
CONTAINER="${NGINX_CONTAINER:-nginx}"
RELOAD=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) MODE=apply ;;
    --revert) MODE=revert ;;
    --file) FILE="$2"; shift ;;
    --container) CONTAINER="$2"; shift ;;
    --no-reload) RELOAD=0 ;;
    *) echo "usage: $0 --apply|--revert [--file PATH] [--container NAME] [--no-reload]" >&2; exit 2 ;;
  esac
  shift
done
[[ -n "$MODE" ]] || { echo "usage: $0 --apply|--revert [--file PATH] [--container NAME] [--no-reload]" >&2; exit 2; }
[[ -f "$FILE" ]] || { echo "!! no such file: $FILE" >&2; exit 2; }

ANCHOR='    server_name sealingai.com;'
INCLUDE_LINE='    include snippets/v2_dashboard.conf;  # V2-CUTOVER (ops/v2-flip.sh)'
INCLUDE_RE='^[[:space:]]*include snippets/v2_dashboard\.conf;'

TMP="$(mktemp "${TMPDIR:-/tmp}/v2-flip.XXXXXX")"
BACKUP="$(mktemp "${TMPDIR:-/tmp}/v2-flip-backup.XXXXXX")"
trap 'rm -f "$TMP" "$BACKUP"' EXIT
cp "$FILE" "$BACKUP"

changed=0
if [[ "$MODE" == apply ]]; then
  if grep -qE "$INCLUDE_RE" "$FILE"; then
    echo ">> already applied — file unchanged"
  else
    anchor_count="$(grep -cxF "$ANCHOR" "$FILE" || true)"
    [[ "$anchor_count" == "1" ]] || { echo "!! flip anchor not unique in $FILE (count=$anchor_count) — refusing" >&2; exit 1; }
    awk -v a="$ANCHOR" -v ins="$INCLUDE_LINE" '{ print; if ($0 == a) print ins }' "$FILE" > "$TMP"
    cat "$TMP" > "$FILE"   # in-place: preserve the bind-mounted inode
    changed=1
    echo ">> include line inserted into $FILE"
  fi
else
  if ! grep -qE "$INCLUDE_RE" "$FILE"; then
    echo ">> already reverted — file unchanged"
  else
    grep -vE "$INCLUDE_RE" "$FILE" > "$TMP"
    cat "$TMP" > "$FILE"   # in-place: preserve the bind-mounted inode
    changed=1
    echo ">> include line removed from $FILE"
  fi
fi

if [[ "$RELOAD" == 1 ]]; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "!! container '$CONTAINER' not running — cannot validate/reload (use --no-reload for file-only edits)" >&2
    [[ "$changed" == 1 ]] && cat "$BACKUP" > "$FILE" && echo "!! file restored" >&2
    exit 1
  fi
  if ! docker exec "$CONTAINER" nginx -t; then
    echo "!! nginx -t FAILED — restoring $FILE, NOT reloading" >&2
    cat "$BACKUP" > "$FILE"
    exit 1
  fi
  docker exec "$CONTAINER" nginx -s reload
  echo ">> nginx reloaded ($CONTAINER) — $MODE is live"
else
  echo ">> --no-reload: file edited only; validate + reload separately"
fi
