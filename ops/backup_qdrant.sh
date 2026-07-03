#!/bin/bash
# Nightly Qdrant backup (ops hardening, 2026-07-03) — server-side snapshot of the sealai_v2_fachkarten
# collection (the live knowledge base), extracted to the host, then the remote snapshot is deleted so
# Qdrant's own storage (already at meaningful capacity) never accumulates. Companion to
# ops/backup_postgres.sh — closes the "no recovery path" gap for the OTHER half of the knowledge/state
# (Postgres holds case-state/leads/auth; Qdrant holds the retrievable Fachkarten index).
#
# No HTTP client exists inside the `qdrant` container itself, and its port is docker-network-internal
# only (not published to the host) — so the snapshot API is called via `backend-v2` (already on the
# same network, already talks to Qdrant in prod) with `docker exec`, and the resulting file is pulled
# out via `docker cp` from the qdrant container's own snapshot directory (avoids re-downloading the
# ~200MB collection over HTTP a second time).
set -euo pipefail

ENV_FILE=${ENV_FILE:-"$HOME/sealai/.env.prod"}
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

COLLECTION=${SEALAI_V2_QDRANT_COLLECTION:-sealai_v2_fachkarten}
BACKEND_CONTAINER=${BACKEND_CONTAINER:-backend-v2}
QDRANT_CONTAINER=${QDRANT_CONTAINER:-qdrant}
QDRANT_INTERNAL_URL=${QDRANT_INTERNAL_URL:-http://qdrant:6333}
TARGET_DIR=${TARGET_DIR:-"$HOME/sealai-backups/qdrant"}
RETENTION_DAYS=${RETENTION_DAYS:-14}

mkdir -p "$TARGET_DIR"
DATE=$(date -u +%Y-%m-%d_%H-%M-%S)

echo "backup_qdrant: creating a server-side snapshot of '${COLLECTION}'"
RESPONSE=$(docker exec "$BACKEND_CONTAINER" curl -sS -X POST \
  "${QDRANT_INTERNAL_URL}/collections/${COLLECTION}/snapshots")

# RESPONSE is piped via stdin (not interpolated into source) — the JSON may contain quote characters
# that would otherwise break out of an embedded Python string literal.
SNAPSHOT_NAME=$(printf '%s' "$RESPONSE" | docker exec -i "$BACKEND_CONTAINER" python3 -c "
import json, sys
print(json.load(sys.stdin)['result']['name'])
")

if [[ -z "$SNAPSHOT_NAME" || "$SNAPSHOT_NAME" == "None" ]]; then
  echo "backup_qdrant: snapshot creation failed — response was: ${RESPONSE}" >&2
  exit 1
fi

FILE="$TARGET_DIR/${COLLECTION}-${DATE}.snapshot"
echo "backup_qdrant: extracting ${SNAPSHOT_NAME} -> ${FILE}"
docker cp "${QDRANT_CONTAINER}:/qdrant/snapshots/${COLLECTION}/${SNAPSHOT_NAME}" "$FILE"

# Sanity check BEFORE deleting the remote copy — never lose the only copy on a truncated docker cp.
SIZE=$(stat -c%s "$FILE" 2>/dev/null || stat -f%z "$FILE")
if [[ "$SIZE" -lt 1024 ]]; then
  echo "backup_qdrant: extracted file suspiciously small (${SIZE} bytes) — NOT deleting the remote snapshot, aborting" >&2
  rm -f "$FILE"
  exit 1
fi
echo "backup_qdrant: OK, $(du -h "$FILE" | cut -f1) -> $FILE"

# Clean up the remote snapshot — Qdrant's own volume must not accumulate one file per night forever.
docker exec "$BACKEND_CONTAINER" curl -sS -X DELETE \
  "${QDRANT_INTERNAL_URL}/collections/${COLLECTION}/snapshots/${SNAPSHOT_NAME}" >/dev/null
echo "backup_qdrant: remote snapshot cleaned up"

# Rotation: delete local backups older than RETENTION_DAYS. Never deletes the file just written.
find "$TARGET_DIR" -name "${COLLECTION}-*.snapshot" -mtime "+${RETENTION_DAYS}" -print -delete
