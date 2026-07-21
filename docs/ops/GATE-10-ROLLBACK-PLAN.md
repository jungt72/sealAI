# GATE-10 rollback plan

This is the canonical rollback plan hashed by `rollback_plan_sha256` in the GATE-10
release manifest (`ops/production-release-manifest.json`). The gate independently
recomputes the SHA-256 of this file's committed content — see
`ops/production_release_gate.py::_rollback_plan_sha256` — and rejects a manifest whose
claimed value does not match. Editing this file without updating the manifest will
correctly fail the gate; that is the point.

This document does not invent a new rollback mechanism. It consolidates the rollback
paths that already exist, scattered across `ops/release-backend-v2.sh`,
`ops/release-frontend.sh`, and individual `docs/ops/GOVERNANCE_LOG.md` entries, into one
place an owner can read before approving a release.

## backend-v2

Every `ops/release-backend-v2.sh` run preserves the currently-running image **before**
touching anything:

1. The running `backend-v2` image is identity-verified (`python -m
   sealai_v2.config.build_identity verify`) and tagged as a rollback hold
   (`sealai-backend-v2:rollback-hold-<revision>-<timestamp>`).
2. Once the new candidate is prepared, that hold is promoted to a rollback rung:
   `sealai-backend-v2:rollback-pre-<run-label>-<timestamp>`.
3. If any post-deploy smoke check goes RED (health, `/health`, public
   `/api/v2/health`, outbox worker health), the script halts **before** writing the
   deploy ledger and prints the exact rollback command:

   ```
   BACKEND_V2_IMAGE=<rollback-rung-tag> docker compose --env-file .env.prod \
     -f docker-compose.yml -f docker-compose.deploy.yml --profile v2 \
     up -d --no-build --no-deps --force-recreate backend-v2 backend-v2-worker
   ```

4. If a database migration ran, the pre-migration backup path is included in the same
   halt message (`MIGRATION_BACKUP`, written under the repo's backup directory before
   any schema change).

No manual image rebuild is ever needed for a backend-v2 rollback — the rollback rung is
an already-built, already-verified image sitting in the local Docker image store.

## frontend (V1, `frontend/`)

`ops/release-frontend.sh` snapshots `.env.prod` to `.env.prod.rollback-<timestamp>`
before recreating the `frontend` container. If the post-deploy health probe
(`/api/health`) does not go green within 30 attempts, the script **automatically**
restores that snapshot and force-recreates the container — no manual step needed for the
common case. The rollback snapshot file path is echoed at deploy time
(`>> Rollback snapshot: ...`); keep it if a rollback is needed after the script has
already exited (e.g. a regression noticed after the smoke window).

## Database (Postgres)

Both scripts route schema changes through Alembic migrations with a pre-migration
`pg_dump` captured first (see `MIGRATION_BACKUP` in the backend flow;
`backups/pre-migration/` holds the dump files). Rolling back a migration means restoring
the matching dump — there is currently no automated `alembic downgrade` path wired into
either release script, so a data-affecting rollback is a manual DBA action: stop the
affected service, restore the dump, restart. This gap is explicitly noted here rather
than glossed over.

## What this plan does **not** cover yet

- **frontend-v2 (the dashboard SPA):** no publisher exists yet
  (`dashboard_artifact_sha256` remains open in the release manifest), so there is no
  live dashboard rollback path to document — nothing has shipped to roll back from.
- **Keycloak / infrastructure containers:** out of scope for this plan; they are not
  part of the GATE-10-gated release surface.

## Owner-facing summary

If a release goes wrong: backend rolls back with one printed command against an
already-built image; frontend (V1) rolls back automatically on a failed health check;
database changes roll back via a DBA restoring the pre-migration dump. None of this is
new — it is what already happens today. This document exists so the rollback path is
written down once, in one place, and bound to the release manifest by hash instead of
living only in script comments and past incident logs.
