#!/usr/bin/env bash
set -euo pipefail

compose_cmd=""
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  compose_cmd="docker compose"
elif command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
  compose_cmd="docker-compose"
else
  echo "compose not available (docker compose or docker-compose)" >&2
  exit 1
fi

backup_dir="backups"
mkdir -p "$backup_dir"

now_utc="$(date -u +"%Y%m%d_%H%M%S")"

echo "[preflight] compose: $compose_cmd"

if docker ps --format '{{.Names}}' | grep -Fxq "postgres"; then
  pg_env="$(docker exec postgres sh -lc 'echo ${POSTGRES_USER:-postgres}:${POSTGRES_DB:-postgres}')"
  pg_user="${pg_env%%:*}"
  pg_db="${pg_env##*:}"
  if [[ -z "$pg_user" ]]; then
    pg_user="postgres"
  fi
  if [[ -z "$pg_db" ]]; then
    pg_db="postgres"
  fi
  pg_dump_path="$backup_dir/pg_${now_utc}.sql"
  echo "[backup] postgres -> $pg_dump_path"
  docker exec postgres pg_dump -U "$pg_user" "$pg_db" > "$pg_dump_path"
else
  echo "[backup] postgres container not running; skipping pg_dump"
fi

echo "[upgrade] pulling redis and qdrant"
$compose_cmd pull redis qdrant

echo "[upgrade] starting redis and qdrant"
$compose_cmd up -d redis qdrant

echo "[verify] redis ping"
docker exec redis redis-cli ping

echo "[verify] qdrant version"
qdrant_json="$(curl -fsS http://127.0.0.1:6333/ || true)"
if [[ -n "$qdrant_json" ]]; then
  if command -v jq >/dev/null 2>&1; then
    echo "$qdrant_json" | jq -r '.version // .version_string // .versionNumber // empty'
  elif command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception:
    sys.exit(1)
for key in ("version", "version_string", "versionNumber"):
    if data.get(key):
        print(data[key])
        break
PY
  else
    echo "$qdrant_json"
  fi
else
  echo "qdrant health check failed" >&2
  echo "rollback: revert docker-compose.yml tags and run '$compose_cmd up -d redis qdrant'" >&2
  exit 1
fi

echo "[verify] backend health"
if ! curl -fsS http://127.0.0.1:8000/api/v1/langgraph/health >/dev/null; then
  echo "backend health check failed" >&2
  echo "rollback: revert docker-compose.yml tags and run '$compose_cmd up -d redis qdrant'" >&2
  exit 1
fi

echo "[done] redis/qdrant upgrade completed"
