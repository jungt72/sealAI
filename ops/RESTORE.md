# Disaster recovery — Postgres + Qdrant

Backups run nightly (03:00 UTC, `thorsten`'s crontab) via `ops/backup_run.sh`, which calls
`ops/backup_postgres.sh` + `ops/backup_qdrant.sh`. Files land in `~/sealai-backups/{postgres,qdrant}/`.
`RETENTION_DAYS=14` makes an old file eligible for review, but it is deleted only with a matching,
verified offsite receipt and only while the configured minimum number of good local copies remains.
Structured JSON events are appended to `~/sealai-backups/backup.log`. See
`docs/runbooks/backup-storage-safety.md` for the capacity, checksum, receipt, and retention contract.

**Known limitation — read this first**: unless a validated offsite receipt exists, these backups
remain host-local. They cover data corruption, a bad migration, or an accidental `DELETE`/`DROP`,
but they do **not** cover total-disk failure or total-VPS loss. Do not create a receipt merely because
an upload command returned success: the complete encrypted object must be downloaded over verified
TLS, bound to its versioned object/key identifiers, authenticated/decrypted with the retained key,
and the resulting plaintext SHA-256 must match the local backup. Offsite transport, private
least-privilege IAM, encryption/KMS, and key lifecycle remain `BLOCKED_EXTERNAL` until that workflow
and an isolated restore-key test are approved.

Every restore must first validate the adjacent `.sha256` sidecar. A missing or failed sidecar blocks
the documented restore path; do not treat filename, age, or file size as integrity evidence.

## Restore Postgres (full instance)

`pg_dumpall` output is a plain SQL script — restoring it re-creates roles + all databases. This is
DESTRUCTIVE to whatever currently exists with the same names, so:

1. **Never restore directly onto the live `postgres` container without confirming with the owner
   first** — this is exactly the kind of destructive action that needs explicit sign-off, not
   something to run unilaterally even in an emergency, unless the owner has explicitly authorized it
   in the moment.
2. To restore:
   ```bash
   cd ~/sealai-backups/postgres
   BACKUP='postgres-all-<TIMESTAMP>-<RANDOM>.sql.gz'
   sha256sum -c "${BACKUP}.sha256"
   gzip -t "${BACKUP}"
   gunzip -c "${BACKUP}" | \
     docker exec -i postgres psql -v ON_ERROR_STOP=1 -U sealai -d postgres
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

### Restoring the automatic pre-migration V2 backup

Every sanctioned backend-v2 release writes a verified custom-format dump to
`~/sealai-backups/pre-migration/` before Alembic runs. Its adjacent `.sha256`
file must validate before use. Restoring is destructive and therefore requires
an explicit incident decision and a stopped API/worker:

```bash
cd ~/sealai-backups/pre-migration
BACKUP='sealai_v2-pre-migration-<TIMESTAMP>-<RANDOM>.dump'
sha256sum -c "${BACKUP}.sha256"
docker compose --env-file /home/thorsten/sealai/.env.prod \
  -f /home/thorsten/sealai/docker-compose.yml \
  -f /home/thorsten/sealai/docker-compose.deploy.yml \
  --profile v2 stop backend-v2 backend-v2-worker
docker exec postgres dropdb -U sealai --if-exists sealai_v2
docker exec postgres createdb -U sealai sealai_v2
docker exec -i postgres pg_restore -U sealai -d sealai_v2 \
  --no-owner --no-acl --exit-on-error < "${BACKUP}"
```

Before restarting production, run the candidate image's schema check and then
the sanctioned release script; never use a direct `compose up` as a substitute.

## Restore Qdrant (a single collection)

The collection name in the backup filename IS the collection to restore into — it changes over time
as the schema evolves (e.g. `sealai_v2_fachkarten` was migrated to `sealai_v2_fachkarten_hybrid` on
2026-07-03; check the current value with
`docker exec backend-v2 env | grep SEALAI_V2_QDRANT_COLLECTION`). Substitute `<COLLECTION>` below with
whatever the backup file itself is named after, not necessarily either example name above.

1. Copy the snapshot file into the qdrant container's snapshot directory:
   ```bash
   cd ~/sealai-backups/qdrant
   SNAPSHOT='<COLLECTION>-<TIMESTAMP>-<RANDOM>.snapshot'
   sha256sum -c "${SNAPSHOT}.sha256"
   SNAPSHOT_SHA=$(cut -d ' ' -f1 "${SNAPSHOT}.sha256")
   docker cp "${SNAPSHOT}" \
     qdrant:/qdrant/snapshots/<COLLECTION>/restore.snapshot
   ```
2. Recover the collection from it (this REPLACES the collection if it already exists — confirm with
   the owner before running against the live collection):
   ```bash
   RESTORE_RESPONSE=$(docker exec backend-v2 curl \
     --connect-timeout 30 --max-time 1800 -fsS -X PUT \
     "http://qdrant:6333/collections/<COLLECTION>/snapshots/recover?wait=true" \
     -H 'Content-Type: application/json' \
     -d "{\"location\":\"file:///qdrant/snapshots/<COLLECTION>/restore.snapshot\",\"checksum\":\"${SNAPSHOT_SHA}\"}")
   printf '%s' "${RESTORE_RESPONSE}" | docker exec -i backend-v2 python3 -c '
   import json, sys
   response = json.load(sys.stdin)
   if response.get("status") != "ok" or response.get("result") is not True:
       raise SystemExit(2)
   '
   unset RESTORE_RESPONSE
   ```
   A curl exit code of zero is not sufficient: the JSON check must also confirm `status=ok` and
   `result=true`. No other recover query parameter is authorized by this runbook; the verified
   checksum belongs in the JSON body next to `location`.
3. Verify: `docker exec backend-v2 curl --connect-timeout 30 --max-time 60 -fsS
   http://qdrant:6333/collections/<COLLECTION>` shows the expected `points_count`.

## Verifying a backup is actually restorable (safe, non-destructive)

**Do NOT replay a `pg_dumpall` dump against the live shared `postgres` container to "test" it** — the
dump's `\connect sealai_v2` / `\connect sealai` statements target the REAL database names, so running
it against the live instance (even into a differently-named database first) will recreate/overwrite
the real databases, not a throwaway copy. The dump is whole-INSTANCE, not per-database.

The only safe way to verify a `pg_dumpall` dump end-to-end is to restore it into a completely
SEPARATE, throwaway Postgres instance — never the shared one:

```bash
cd ~/sealai-backups/postgres
BACKUP='postgres-all-<TIMESTAMP>-<RANDOM>.sql.gz'
sha256sum -c "${BACKUP}.sha256"
docker run --rm -d --name pg-restore-test -e POSTGRES_PASSWORD=verify postgres:15
sleep 5  # wait for it to accept connections
gunzip -c "${BACKUP}" | \
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
