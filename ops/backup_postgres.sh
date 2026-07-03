#!/bin/bash
# Nightly Postgres backup (ops hardening, 2026-07-03) — full-instance pg_dumpall (all databases +
# roles: sealai_v2, sealai/Keycloak, paperless, and anything else on the shared `postgres` container),
# gzip-compressed, timestamped, rotated. Closes the "no recovery path" gap found in the ops/security
# sweep — this is a LOGICAL backup (SQL dump), not a raw volume copy, so it survives a Postgres major
# version upgrade and is restorable into a fresh instance.
#
# Runs OUTSIDE the container via `docker exec` (no dependency on a client tool on the host) using the
# credentials already required by the stack (POSTGRES_USER/POSTGRES_PASSWORD from .env.prod).
#
# Retention: local disk is NOT off-host — this protects against data corruption / bad migration /
# accidental deletion, NOT against total-disk or total-VPS loss. See ops/RESTORE.md for the caveat
# and an off-host-copy recommendation.
set -euo pipefail

ENV_FILE=${ENV_FILE:-"$HOME/sealai/.env.prod"}
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

POSTGRES_USER=${POSTGRES_USER:-sealai}
POSTGRES_CONTAINER=${POSTGRES_CONTAINER:-postgres}
TARGET_DIR=${TARGET_DIR:-"$HOME/sealai-backups/postgres"}
RETENTION_DAYS=${RETENTION_DAYS:-14}

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  echo "backup_postgres: POSTGRES_PASSWORD not set (checked \$ENV_FILE=$ENV_FILE) — aborting" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
DATE=$(date -u +%Y-%m-%d_%H-%M-%S)
FILE="$TARGET_DIR/postgres-all-${DATE}.sql.gz"
TMP_FILE="${FILE}.partial"

echo "backup_postgres: dumping all databases from container '${POSTGRES_CONTAINER}' -> ${FILE}"
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$POSTGRES_CONTAINER" \
  pg_dumpall -U "$POSTGRES_USER" | gzip -9 > "$TMP_FILE"

# Sanity checks BEFORE the temp file replaces any prior good backup: non-trivial size + valid gzip +
# contains at least one recognisable SQL statement (a truncated/failed dump must never look "done").
SIZE=$(stat -c%s "$TMP_FILE" 2>/dev/null || stat -f%z "$TMP_FILE")
if [[ "$SIZE" -lt 1024 ]]; then
  echo "backup_postgres: dump suspiciously small (${SIZE} bytes) — NOT keeping it" >&2
  rm -f "$TMP_FILE"
  exit 1
fi
if ! gzip -t "$TMP_FILE"; then
  echo "backup_postgres: gzip integrity check failed — NOT keeping it" >&2
  rm -f "$TMP_FILE"
  exit 1
fi
if ! zcat "$TMP_FILE" | grep -q "PostgreSQL database dump"; then
  echo "backup_postgres: dump does not look like a Postgres dump — NOT keeping it" >&2
  rm -f "$TMP_FILE"
  exit 1
fi

mv "$TMP_FILE" "$FILE"
echo "backup_postgres: OK, $(du -h "$FILE" | cut -f1) -> $FILE"

# Rotation: delete backups older than RETENTION_DAYS. Never deletes the file just written.
find "$TARGET_DIR" -name 'postgres-all-*.sql.gz' -mtime "+${RETENTION_DAYS}" -print -delete
