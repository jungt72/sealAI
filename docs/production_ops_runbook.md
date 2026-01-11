# Production Ops Runbook

This runbook covers backups, restore steps, and verification for Redis, Qdrant, and Postgres.

## Redis (AOF + RDB)

Persistence mode:
- `docker-compose.yml` sets Redis to `--appendonly yes` and RDB snapshots via `--save` rules.
- Data volume: `redis-data` mounted at `/data`.

Backup:
- Preferred: copy on-disk files (AOF/RDB) from the volume.
  - `docker compose exec -T redis sh -lc 'ls -lh /data'`
  - `docker compose exec -T redis sh -lc 'cp /data/appendonly.aof /data/appendonly.aof.bak'`
  - `docker compose exec -T redis sh -lc 'cp /data/dump.rdb /data/dump.rdb.bak'`
- Alternative: generate an RDB on demand:
  - `docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" --rdb /data/backup.rdb`

Restore:
- Stop the service: `docker compose stop redis`
- Restore files into the volume (`appendonly.aof` and/or `dump.rdb`).
- Start Redis: `docker compose up -d redis`

TTL hygiene notes:
- Checkpoint TTL is driven by `LANGGRAPH_CHECKPOINT_TTL`.
- If legacy keys exist without TTL, use the TTL proof script below to identify and remediate.

## Qdrant

Persistence mode:
- Data volume: `qdrant_storage` mounted at `/qdrant/storage`.

Backup:
- If snapshot API is enabled:
  - `curl -sS -X POST http://localhost:6333/collections/<collection>/snapshots`
  - `curl -sS http://localhost:6333/collections/<collection>/snapshots`
- Filesystem fallback: copy the `qdrant_storage` volume on the host.

Restore:
- Stop Qdrant: `docker compose stop qdrant`
- Restore the snapshot or volume contents.
- Start Qdrant: `docker compose up -d qdrant`

## Postgres

Persistence mode:
- Data volume: `pgdata` mounted at `/var/lib/postgresql/data`.

Backup:
- `docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > pg_dump.sql`

Restore:
- `cat pg_dump.sql | docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"`

## Verification checklist (post-restore)

- Redis keyspace present: `docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" DBSIZE`
- Qdrant collections present: `curl -sS http://localhost:6333/collections`
- Backend health OK: `curl -fsS http://localhost:8000/api/v1/langgraph/health`
- SSE endpoints respond (if enabled): `curl -fsS http://localhost:8000/api/v1/langgraph/health`
