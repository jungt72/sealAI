#!/usr/bin/env bash
# Create a verified, database-local pre-migration backup for sealai_v2.
set -euo pipefail

ENV_FILE=${ENV_FILE:-"$(git rev-parse --show-toplevel)/.env.prod"}
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

POSTGRES_USER=${POSTGRES_USER:-sealai}
POSTGRES_CONTAINER=${POSTGRES_CONTAINER:-postgres}
DATABASE_NAME=${SEALAI_V2_DATABASE_NAME:-sealai_v2}
TARGET_DIR=${TARGET_DIR:-"$HOME/sealai-backups/pre-migration"}
RETENTION_DAYS=${RETENTION_DAYS:-30}

[[ -n "${POSTGRES_PASSWORD:-}" ]] || {
  echo "backup_v2_database: POSTGRES_PASSWORD is required" >&2
  exit 1
}

mkdir -p "${TARGET_DIR}"
chmod 700 "${TARGET_DIR}"
stamp=$(date -u +%Y-%m-%d_%H-%M-%S)
file="${TARGET_DIR}/${DATABASE_NAME}-pre-migration-${stamp}.dump"
partial="${file}.partial"

echo "backup_v2_database: creating ${file}" >&2
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${POSTGRES_CONTAINER}" \
  pg_dump --format=custom --no-owner --no-acl \
  --username="${POSTGRES_USER}" --dbname="${DATABASE_NAME}" > "${partial}"
chmod 600 "${partial}"

size=$(wc -c < "${partial}" | tr -d ' ')
if [[ "${size}" -lt 1024 ]]; then
  rm -f "${partial}"
  echo "backup_v2_database: dump is suspiciously small (${size} bytes)" >&2
  exit 1
fi

docker exec -i "${POSTGRES_CONTAINER}" pg_restore --list < "${partial}" >/dev/null
mv "${partial}" "${file}"
sha256sum "${file}" > "${file}.sha256"
chmod 600 "${file}.sha256"

find "${TARGET_DIR}" -name "${DATABASE_NAME}-pre-migration-*.dump" \
  -mtime "+${RETENTION_DAYS}" -print -delete >&2
find "${TARGET_DIR}" -name "${DATABASE_NAME}-pre-migration-*.dump.sha256" \
  -mtime "+${RETENTION_DAYS}" -print -delete >&2

printf '%s\n' "${file}"
