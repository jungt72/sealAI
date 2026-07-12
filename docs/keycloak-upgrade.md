# Keycloak 26.7.0: Upgrade, Recovery and Rollback

Target server version: **26.7.0**. The image is built from the digest-pinned
official amd64 manifest and published by `.github/workflows/keycloak.yml` with
OCI provenance and an SBOM.

Primary references:

- https://www.keycloak.org/2026/07/keycloak-2670-released
- https://www.keycloak.org/server/configuration-production
- https://www.keycloak.org/server/reverseproxy
- https://www.keycloak.org/server/bootstrap-admin-recovery
- https://www.keycloak.org/server/containers

## Security model

- Runtime containers receive only the Keycloak DB credential. Bootstrap or
  recovery admin credentials are never stored in `.env.prod`.
- `mail@thorsten-jung.de` is the permanent owner. The account receives the
  `sealAI` realm-local `realm-management/realm-admin` role through
  `/platform-admins`, plus the sealingAI product and governance roles.
- The owner is deliberately **not** a permanent master-realm superadmin. That
  would grant unnecessary cross-realm authority.
- Password replacement and TOTP enrollment are required before Keycloak issues
  a fresh privileged session.
- Recovery uses a random temporary service admin while every Keycloak node is
  stopped. The client is deleted in the same reconciliation run.
- User and admin events are retained for seven days. Admin event
  representations stay disabled to avoid persisting secrets in audit payloads.

## Preflight against a production-data copy

Run this before changing the live container. It creates a fresh custom-format
dump, restores it into a temporary database, starts the candidate against that
copy, verifies readiness and migrations, then removes the test database and
container.

```bash
cd /home/thorsten/sealai
./ops/keycloak_upgrade_preflight.sh \
  ghcr.io/jungt72/sealai-keycloak:<commit>@sha256:<digest>
```

The verified backup remains mode `0600` under
`$HOME/sealai-review/keycloak/`. Never clear Liquibase checksums or edit
Keycloak tables by hand.

## Production upgrade

1. Confirm the preflight proof and current full Postgres backup.
2. Update only `KEYCLOAK_IMAGE` in `.env.prod` to the immutable
   `tag@sha256:digest` reference.
3. Pull and recreate Keycloak without recreating Postgres:

```bash
COMPOSE="docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml"
$COMPOSE pull keycloak
$COMPOSE up -d --no-deps --force-recreate keycloak
$COMPOSE up -d --no-deps nginx
docker inspect --format '{{.State.Health.Status}}' keycloak
docker exec keycloak /opt/keycloak/bin/kc.sh --version
```

4. Verify the public discovery document, JWKS and login redirect before admin
   recovery.

## One-shot owner recovery

Use this once after the new Compose model is active:

```bash
cd /home/thorsten/sealai
./ops/keycloak_recover_admin.sh --apply
```

The script performs a fresh full backup, stops Keycloak, uses the official
`bootstrap-admin service` command, reconciles the realm, assigns the owner, and
deletes the temporary recovery client. It never prints the generated secret.

At the next login, the owner must replace the password and enroll TOTP. The
realm admin console is:

```text
https://sealingai.com/admin/sealAI/console/
```

After successful enrollment, verify that no temporary warning appears and no
client whose ID starts with `sealai-recovery-` remains in the master realm.

## Rollback

If 26.7.0 fails before accepting writes, restore the prior immutable 26.6.1
image reference and recreate only Keycloak. If the upgraded server has changed
the schema, do not run an older server against the upgraded database. Stop the
stack and restore the preflight/full Postgres backup first.

## Known boundary

The Admin Console currently shares `sealingai.com` because no separately
managed admin hostname or VPN ingress exists. Authentication, TOTP, exact
realm-local authorization and event logging protect it, but moving `/admin/`
to a private/VPN-only admin ingress remains the preferred later hardening step.
