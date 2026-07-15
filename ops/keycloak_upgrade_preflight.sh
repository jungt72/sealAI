#!/bin/bash -p
set -euo pipefail
umask 077
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=production-release-gate-check.sh
source "${SCRIPT_DIR}/production-release-gate-check.sh"
production_release_gate_check "${SCRIPT_DIR}/production_release_gate.py" pull
# shellcheck source=production-storage-lease.sh
source /usr/local/libexec/sealai/production-storage-lease.sh
acquire_production_storage_lease

echo "BLOCKED_EXTERNAL: Keycloak promotion lacks an independently verified publisher/attestation chain" >&2
echo "The isolated upgrade preflight remains disabled until that external trust proof exists." >&2
exit 2

# Starts a candidate Keycloak image against a restored copy of production data.
# The live database and live Keycloak container are never touched.

IMAGE_REF="${1:-}"
[[ "$IMAGE_REF" == *@sha256:* ]] || {
  echo "usage: $0 IMAGE_TAG@sha256:DIGEST" >&2
  exit 2
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.prod}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-sealai}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-sealai}"
POSTGRES_DB="${POSTGRES_DB:-sealai}"
NETWORK="${KEYCLOAK_DOCKER_NETWORK:-${COMPOSE_PROJECT_NAME}_default}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TEST_DB="sealai_kc_preflight_$(date -u +%Y%m%d%H%M%S)"
TEST_CONTAINER="keycloak-preflight-${STAMP,,}"
PROOF_DIR="${KEYCLOAK_PROOF_DIR:-$HOME/sealai-review/keycloak}"
DUMP_FILE="$PROOF_DIR/${POSTGRES_DB}-${STAMP}.dump"

[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE" >&2; exit 1; }
if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  POSTGRES_PASSWORD="$(/usr/bin/python3 -I - "$ENV_FILE" <<'PY'
import sys
from pathlib import Path

values = {}
for raw in Path(sys.argv[1]).read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    values[key] = value

print(values.get("POSTGRES_PASSWORD", ""), end="")
PY
)"
fi
[[ -n "${POSTGRES_PASSWORD:-}" ]] || { echo "POSTGRES_PASSWORD is required" >&2; exit 1; }

cleanup() {
  docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true
  docker exec "$POSTGRES_CONTAINER" dropdb -U "$POSTGRES_USER" --if-exists "$TEST_DB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p "$PROOF_DIR"
chmod 700 "$PROOF_DIR"

echo ">> Pulling and identifying candidate"
docker pull "$IMAGE_REF" >/dev/null
docker run --rm "$IMAGE_REF" --version

echo ">> Creating verified production-data snapshot: $DUMP_FILE"
docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc >"$DUMP_FILE.partial"
[[ "$(wc -c <"$DUMP_FILE.partial")" -gt 1024 ]] || { echo "dump is unexpectedly small" >&2; exit 1; }
docker exec -i "$POSTGRES_CONTAINER" pg_restore -l <"$DUMP_FILE.partial" >/dev/null
mv "$DUMP_FILE.partial" "$DUMP_FILE"
chmod 600 "$DUMP_FILE"

echo ">> Restoring isolated database copy: $TEST_DB"
docker exec "$POSTGRES_CONTAINER" createdb -U "$POSTGRES_USER" "$TEST_DB"
docker exec -i "$POSTGRES_CONTAINER" pg_restore -U "$POSTGRES_USER" -d "$TEST_DB" --no-owner --no-privileges <"$DUMP_FILE"

before_count="$(docker exec "$POSTGRES_CONTAINER" psql -X -U "$POSTGRES_USER" -d "$TEST_DB" -Atc 'select count(*) from databasechangelog')"

echo ">> Starting candidate against the isolated database"
docker run -d --name "$TEST_CONTAINER" --network "$NETWORK" \
  -e KC_DB=postgres \
  -e "KC_DB_URL=jdbc:postgresql://postgres:5432/$TEST_DB" \
  -e "KC_DB_USERNAME=$POSTGRES_USER" \
  -e "KCRAW_DB_PASSWORD=$POSTGRES_PASSWORD" \
  -e KC_CACHE=local \
  -e KC_HTTP_ENABLED=true \
  -e KC_HOSTNAME_STRICT=false \
  -e KC_HEALTH_ENABLED=true \
  -e KC_METRICS_ENABLED=true \
  "$IMAGE_REF" start --optimized >/dev/null

for _ in $(seq 1 90); do
  if docker exec "$TEST_CONTAINER" /bin/bash -ec \
    'exec 3<>/dev/tcp/127.0.0.1/9000; printf "HEAD /health/ready HTTP/1.0\r\n\r\n" >&3; IFS= read -r status <&3; [[ "$status" == *" 200 "* ]]' \
    >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec "$TEST_CONTAINER" /bin/bash -ec \
  'exec 3<>/dev/tcp/127.0.0.1/9000; printf "HEAD /health/ready HTTP/1.0\r\n\r\n" >&3; IFS= read -r status <&3; [[ "$status" == *" 200 "* ]]'

after_count="$(docker exec "$POSTGRES_CONTAINER" psql -X -U "$POSTGRES_USER" -d "$TEST_DB" -Atc 'select count(*) from databasechangelog')"
docker logs "$TEST_CONTAINER" 2>&1 | grep -Eqi 'ERROR|FATAL' && {
  docker logs --tail 200 "$TEST_CONTAINER" >&2
  echo "candidate emitted ERROR/FATAL during preflight" >&2
  exit 1
}

printf 'Keycloak upgrade preflight OK: changelog=%s->%s backup=%s\n' \
  "$before_count" "$after_count" "$DUMP_FILE"
