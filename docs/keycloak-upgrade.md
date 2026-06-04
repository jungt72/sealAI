# Keycloak Upgrade (26.5.7)

Target Keycloak server version: **26.5.7** (track https://www.keycloak.org/downloads for updates).

Recommended safe procedure:
1) Stop and diagnose before changing data:
   - `docker logs --tail 200 keycloak`
   - `docker exec postgres psql -U sealai -d sealai -c "select orderexecuted, id, filename from databasechangelog order by orderexecuted desc limit 20;"`
2) Back up the production database before any state-altering start:
   - `mkdir -p backups`
   - `ts=$(date -u +%Y%m%dT%H%M%SZ)`
   - `docker exec postgres pg_dump -U sealai -d sealai -Fc -f /tmp/sealai_keycloak_${ts}.dump`
   - `docker cp postgres:/tmp/sealai_keycloak_${ts}.dump ./backups/`
3) Rebuild the custom image on `quay.io/keycloak/keycloak:26.5.7`:
   - `docker build -f keycloak/Dockerfile -t sealai-keycloak:26.5.7-local keycloak`
4) Validate the rebuilt image before repinning:
   - `docker run --rm sealai-keycloak:26.5.7-local --version`
5) Start only Keycloak against the existing database:
   - `KEYCLOAK_IMAGE=sealai-keycloak:26.5.7-local docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml up -d keycloak`
6) Verify startup and schema handling:
   - `docker logs --tail 200 keycloak`
   - `docker exec postgres psql -U sealai -d sealai -c "select count(*) from databasechangelog;"`
   - `curl -fsS http://127.0.0.1:9000/health/ready`
7) Only after validation, update `.env.prod` to the new immutable image ref and re-run `./ops/up-prod.sh`

Notes:
- Health and metrics remain enabled via build flags; endpoints stay at their usual paths.
- Hostname/HTTPS settings remain in `keycloak/keycloak.conf` (e.g., `hostname=auth.sealai.net`, `hostname-strict=true`).
- No DB credentials/names changed; the Postgres data is left untouched.
- If the database already contains 26.x changelog rows, do not pin back to 25.x. Restore a matching 26.5.7 image instead of clearing checksums blindly.
- Do not clear Liquibase checksums unless a matching-version start still fails after the backup and the failing changeset is confirmed to be covered by Keycloak's own `validCheckSum` handling.
- `backup_keycloak.sh` reads admin credentials and realm from your `.env.dev` (or environment) and fails fast if they are missing; it exports the specified realm (clients, secrets, users) to `$HOME/sealai/keycloak-realm-backup/`.
- Tests: `pytest tests/keycloak/test_backup_keycloak.py` provides a fast sanity check of the backup script’s env validation and export path construction.
