# Disaster recovery — Postgres + Qdrant

Backups run nightly (03:00 UTC, `thorsten`'s crontab) via `ops/backup_run.sh`, which calls
`ops/backup_postgres.sh` + `ops/backup_qdrant.sh`. Files land in `~/sealai-backups/{postgres,qdrant}/`,
retained 14 days. A one-line summary per run is appended to `~/sealai-backups/backup.log`.

**Known limitation — read this first**: these backups live on the SAME host/disk as the data they
protect. They cover data corruption, a bad migration, or an accidental `DELETE`/`DROP` — they do
**not** cover total-disk failure or total-VPS loss. There is currently no off-host copy (no S3/object
storage or second host configured). If/when off-host storage is available, add a step to
`backup_run.sh` that copies the two newest files to it after a successful local run.

## Restore Postgres (full instance)

`pg_dumpall` output is a plain SQL script — restoring it re-creates roles + all databases. This is
DESTRUCTIVE to whatever currently exists with the same names, so:

1. **Never restore directly onto the live `postgres` container without confirming with the owner
   first** — this is exactly the kind of destructive action that needs explicit sign-off, not
   something to run unilaterally even in an emergency, unless the owner has explicitly authorized it
   in the moment.
2. To restore:
   ```bash
   gunzip -c ~/sealai-backups/postgres/postgres-all-<TIMESTAMP>.sql.gz | \
     docker exec -i postgres psql -U sealai -d postgres
   ```
   (`pg_dumpall` output includes `CREATE DATABASE`/`\connect` statements for every database in the
   dump, so a single `psql` invocation against the `postgres` maintenance database restores
   everything.)
3. Verify: `docker exec postgres psql -U sealai -d sealai_v2 -c '\dt'` should list the expected tables.

### Restoring a single database only

If only `sealai_v2` needs restoring (e.g. a bad migration), it is safer to extract just that
database's statements rather than replay the whole-instance dump — `pg_dumpall` doesn't cleanly
split by database, so prefer a fresh `pg_dump -U sealai -d sealai_v2` taken BEFORE the incident if one
exists, or restore into a scratch database first (see verification procedure below) and manually
`pg_dump`/`pg_restore` just the needed tables across.

## Restore Qdrant (a single collection)

The collection name in the backup filename IS the collection to restore into — it changes over time
as the schema evolves (e.g. `sealai_v2_fachkarten` was migrated to `sealai_v2_fachkarten_hybrid` on
2026-07-03; check the current value with
`docker exec backend-v2 env | grep SEALAI_V2_QDRANT_COLLECTION`). Substitute `<COLLECTION>` below with
whatever the backup file itself is named after, not necessarily either example name above.

1. Copy the snapshot file into the qdrant container's snapshot directory:
   ```bash
   docker cp ~/sealai-backups/qdrant/<COLLECTION>-<TIMESTAMP>.snapshot \
     qdrant:/qdrant/snapshots/<COLLECTION>/restore.snapshot
   ```
2. Recover the collection from it (this REPLACES the collection if it already exists — confirm with
   the owner before running against the live collection):
   ```bash
   docker exec backend-v2 curl -sS -X PUT \
     'http://qdrant:6333/collections/<COLLECTION>/snapshots/recover' \
     -H 'Content-Type: application/json' \
     -d '{"location": "file:///qdrant/snapshots/<COLLECTION>/restore.snapshot"}'
   ```
3. Verify: `docker exec backend-v2 curl -sS http://qdrant:6333/collections/<COLLECTION>` shows
   the expected `points_count`.

## Verifying a backup is actually restorable (safe, non-destructive)

**Do NOT replay a `pg_dumpall` dump against the live shared `postgres` container to "test" it** — the
dump's `\connect sealai_v2` / `\connect sealai` statements target the REAL database names, so running
it against the live instance (even into a differently-named database first) will recreate/overwrite
the real databases, not a throwaway copy. The dump is whole-INSTANCE, not per-database.

The only safe way to verify a `pg_dumpall` dump end-to-end is to restore it into a completely
SEPARATE, throwaway Postgres instance — never the shared one:

```bash
docker run --rm -d --name pg-restore-test -e POSTGRES_PASSWORD=verify postgres:15
sleep 5  # wait for it to accept connections
gunzip -c ~/sealai-backups/postgres/postgres-all-<TIMESTAMP>.sql.gz | \
  docker exec -i pg-restore-test psql -U postgres -v ON_ERROR_STOP=1 -q
docker exec pg-restore-test psql -U postgres -d sealai_v2 -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
docker stop pg-restore-test  # --rm cleans up the container + its volume automatically
```

**Correction (2026-07-04)**: this file previously claimed this procedure had already been run once
(2026-07-03) to prove the mechanism works. That was inaccurate — `backup_postgres.sh`'s own content
sanity check had a pipefail/SIGPIPE false-negative bug (fixed 2026-07-04) that silently discarded
every dump it ever produced, so there was no kept backup to restore-verify against until the fix
landed. The procedure above is safe and recommended to run periodically — it never touches the live
`postgres` container — but treat it as NOT YET independently verified end-to-end until someone
actually runs it against a real nightly backup file.
