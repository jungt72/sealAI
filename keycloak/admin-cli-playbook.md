# Keycloak Admin CLI Playbook

This repository treats Keycloak configuration as an idempotent reconciliation,
not a collection of copy-pasted admin commands.

## Production

Do not keep a master-realm username, password, client ID or client secret in
`.env.prod`. Lost-admin recovery uses an official temporary admin user while
all Keycloak nodes are stopped:

```bash
./ops/keycloak_recover_admin.sh --apply
```

The recovery wrapper calls `ops/keycloak_ensure_roles.sh`, which applies:

- realm security, session, brute-force, password and event policies;
- product roles and reviewer roles;
- `/platform-admins` and `/governance-reviewers` product-role group mappings;
- owner-specific realm-local `realm-management/realm-admin`;
- `UPDATE_PASSWORD` and `CONFIGURE_TOTP` for the privileged owner;
- revocation of every pre-existing owner session before recovery access is removed;
- exact redirect/origin and PKCE policies for `nextauth` and `sealai-v2`;
- deletion of the short-lived recovery user.

## Manual authenticated reconciliation

For an already authenticated realm administrator, pass credentials only in the
current process. Do not add them to an env file or shell history.

Service account:

```bash
read -rsp 'Temporary admin client secret: ' KEYCLOAK_ADMIN_CLIENT_SECRET
export KEYCLOAK_ADMIN_CLIENT_SECRET
KEYCLOAK_ADMIN_CLIENT_ID='<temporary-client>' \
KEYCLOAK_TARGET_EMAIL='mail@thorsten-jung.de' \
  ./ops/keycloak_ensure_roles.sh
unset KEYCLOAK_ADMIN_CLIENT_SECRET
```

Interactive admin user:

```bash
read -rsp 'Admin password: ' KEYCLOAK_ADMIN_PASSWORD
export KEYCLOAK_ADMIN_PASSWORD
KEYCLOAK_ADMIN_USER='<admin-user>' \
KEYCLOAK_AUTH_REALM='sealAI' \
  ./ops/keycloak_ensure_roles.sh
unset KEYCLOAK_ADMIN_PASSWORD
```

The script uses a unique `/tmp` kcadm configuration file inside the container
and deletes it on every exit path.

## Verification

```bash
docker inspect --format '{{.State.Health.Status}}' keycloak
docker exec keycloak /opt/keycloak/bin/kc.sh --version
curl -fsS https://sealingai.com/realms/sealAI/.well-known/openid-configuration >/dev/null
curl -fsS https://sealingai.com/realms/sealAI/protocol/openid-connect/certs >/dev/null
```

Run all database backups and version upgrades through
`docs/keycloak-upgrade.md`.
