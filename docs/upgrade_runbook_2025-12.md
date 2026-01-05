# Infra Upgrade Runbook (2025-12)

## Goal
Upgrade Redis Stack and Qdrant safely with backup-first workflow.

- Redis Stack: `redis/redis-stack-server:7.4.0-v8`
- Qdrant: `qdrant/qdrant:v1.16.0`
- Keycloak: not changed (TODO)
- Strapi: not changed (TODO, not in main compose)

## Preflight Checks
- `docker-compose version`
- `docker ps`
- Disk space: `df -h`
- Git state: `git rev-parse --short HEAD` and `git status --short`

## Backups (No Deletes)
### Postgres
Store a timestamped dump in `./backups/`.

```bash
mkdir -p backups
# USER/DB resolved from container env
# docker exec postgres pg_dump -U <USER> <DB> > backups/pg_YYYYmmdd_HHMMSS.sql
```

### Qdrant
Prefer a volume snapshot by your infrastructure provider. Optional local tar backup:

```bash
mkdir -p backups
# Replace volume name if needed
# docker run --rm -v sealai_qdrant_storage:/data -v "$PWD/backups:/backup" \
#   alpine tar -czf /backup/qdrant_YYYYmmdd_HHMMSS.tgz -C /data .
```

### Redis
Ensure RDB/AOF is captured and volume is preserved.

```bash
# Optional: force a snapshot
# docker exec redis redis-cli SAVE
# Snapshot the volume via provider or optional tar backup similar to Qdrant
```

## Upgrade Steps
```bash
docker-compose pull redis qdrant
docker-compose up -d redis qdrant
```

## Verification
```bash
# Redis
docker exec redis redis-cli ping

# Qdrant version
curl -fsS http://127.0.0.1:6333/

# Backend health
curl -fsS http://127.0.0.1:8000/api/v1/langgraph/health

# Container health
docker ps
```

## Rollback
- Revert the image tags in `docker-compose.yml` or `git checkout -- docker-compose.yml`
- Reapply:

```bash
docker-compose up -d redis qdrant
```

## Notes
- Keycloak upgrade is documented below; follow the dedicated section and verify auth flows.
- Strapi is not part of the main compose stack. TODO: plan a separate upgrade if/when `docker-compose.biz.yml` is used in production.

## Keycloak Upgrade 25 -> 26.4.7
Reference:
- Release notes and migration changes: https://www.keycloak.org/docs/latest/release_notes/index.html
- Upgrading guide: https://www.keycloak.org/docs/latest/upgrading/index.html
- Downloads: https://www.keycloak.org/downloads

Key points:
- Review migration changes and any breaking defaults before rollout.
- Expect session/cache changes; validate login flows after upgrade.
- Monitor logs for liquibase or migration warnings.

Steps:
1) Backup Postgres (see Backups section above).
2) Build Keycloak image:
   - Update `keycloak/Dockerfile` to `quay.io/keycloak/keycloak:26.4.7`.
   - `docker-compose build keycloak`
3) Deploy:
   - `docker-compose up -d keycloak`
4) Verify:
   - `docker exec keycloak /opt/keycloak/bin/kc.sh --version`
   - `curl -fsS http://127.0.0.1:9000/health/ready`
   - `curl -fsS https://auth.sealai.net/realms/sealAI/.well-known/openid-configuration | head`
   - `curl -fsS http://127.0.0.1:8000/api/v1/langgraph/health`
5) Rollback (if needed):
   - Revert `keycloak/Dockerfile` to 25.0.4.
   - `docker-compose build keycloak`
   - `docker-compose up -d keycloak`
