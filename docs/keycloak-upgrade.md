# Keycloak Upgrade (26.4.5)

Target Keycloak server version: **26.4.5** (track https://www.keycloak.org/downloads for updates).

Recommended safe procedure:
1) Export the realm (clients, secrets, users):
   - `ENV_FILE=.env.dev ./backup_keycloak.sh`
2) Optional DB safety net (Keycloak schema):
   - `docker exec postgres pg_dump -U sealai -d sealai -f /tmp/keycloak.sql`
   - `docker cp postgres:/tmp/keycloak.sql ./keycloak-realm-backup/`
3) Rebuild and start Keycloak with the new base image:
   - `docker compose up -d --build keycloak`
4) Verify the running version:
- `docker exec keycloak /opt/keycloak/bin/kc.sh version`
5) Validate functionality:
   - Log into the Keycloak admin UI and confirm realms, clients, secrets, and tokens still work.

Notes:
- Health and metrics remain enabled via build flags; endpoints stay at their usual paths.
- Hostname/HTTPS settings remain in `keycloak/keycloak.conf` (e.g., `hostname=auth.sealai.net`, `hostname-strict=true`).
- No DB credentials/names changed; the Postgres data is left untouched.
- `backup_keycloak.sh` reads admin credentials and realm from your `.env.dev` (or environment) and fails fast if they are missing; it exports the specified realm (clients, secrets, users) to `$HOME/sealai/keycloak-realm-backup/`.
- Tests: `pytest tests/keycloak/test_backup_keycloak.py` provides a fast sanity check of the backup script’s env validation and export path construction.
