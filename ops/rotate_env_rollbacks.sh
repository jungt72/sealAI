#!/bin/bash
# Keeps the N most recent .env.prod.rollback-*/.env.prod.bak-* snapshots in the repo root,
# deletes the rest. Idempotent, safe to run repeatedly. Never touches .env.prod itself or
# any .example file (globs are anchored to the rollback/bak naming pattern only).
set -euo pipefail

REPO_ROOT="${1:-/home/thorsten/sealai}"
KEEP="${KEEP:-15}"
DRY_RUN="${DRY_RUN:-0}"

cd "$REPO_ROOT"

shopt -s nullglob
candidates=(.env.prod.rollback-* .env.prod.bak-* .env.prod.bak.* .env.dev.bak.* .env.bak.*)
shopt -u nullglob

if [ "${#candidates[@]}" -le "$KEEP" ]; then
  echo "rotate_env_rollbacks: ${#candidates[@]} files, keep=${KEEP} -- nothing to do"
  exit 0
fi

# Sort by mtime, newest first; keep the first $KEEP, delete the rest.
mapfile -t sorted < <(ls -t "${candidates[@]}")
to_delete=("${sorted[@]:$KEEP}")

echo "rotate_env_rollbacks: ${#sorted[@]} files found, keeping ${KEEP} newest, deleting ${#to_delete[@]}"
for f in "${to_delete[@]}"; do
  if [ "$DRY_RUN" = "1" ]; then
    echo "would delete: $f"
  else
    rm -f -- "$f"
    echo "deleted: $f"
  fi
done
