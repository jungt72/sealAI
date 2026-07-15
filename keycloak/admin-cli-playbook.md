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

The recovery wrapper reads `KEYCLOAK_SECURITY_PROFILE` from `.env.prod` and
calls `ops/keycloak_ensure_roles.sh`. The accepted profiles are:

- `test`: no forced OTP for the privileged test owner, no email verification,
  and no password-reset link while SMTP is absent;
- `production`: enforced OTP enrollment for the privileged owner, verified email
  and password reset;
  reconciliation fails closed until Keycloak SMTP is configured.

Both profiles apply:

- realm security, session, brute-force, password and event policies;
- only the non-governance `user_basic` and `user_pro` product roles;
- owner-specific realm-local `realm-management/realm-admin`;
- E-mail-as-username registration, optional name fields and German default locale;
- `user_basic` as a default role for self-service accounts;
- Keycloak's standard ordered browser flow: password authentication first,
  credential-conditioned OTP second; the OTP subflow is disabled entirely in
  `test` and enabled conditionally in `production`;
- revocation of every pre-existing owner session before recovery access is removed;
- exact redirect/origin and PKCE policies for `nextauth` and `sealai-v2`;
- deletion of the short-lived recovery user.

Application governance roles and groups are a separate GATE-06 boundary. They
are defined exactly by `security/keycloak-governance-v1.json` and inspected by
`ops/keycloak_governance_reconcile.py`. The governance reconciler never changes
user memberships and is read-only unless both `--apply` and the expected
manifest SHA-256 are supplied. It blocks apply when any subject belongs to an
incompatible group combination or still holds the forbidden legacy `admin`
realm role. Receipts contain counts and contract hashes only.

The temporary test exception must be explicit in production's environment:

```dotenv
KEYCLOAK_SECURITY_PROFILE=test
```

Before launch, configure SMTP, change the value to `production`, run the
recovery wrapper, and complete the newly required OTP enrollment.

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

## Governance-role census and reconciliation

The commands in this section require a separately approved **GATE-06**. A dry
run reads role/group state but mutates nothing:

```bash
python3 ops/keycloak_governance_reconcile.py
```

Review the sanitized receipt and resolve every incompatible membership and
legacy direct `admin` assignment through the human-owned identity roster. The
reconciler deliberately cannot guess or rewrite user memberships. Once the
approved manifest hash and sanitized census are bound to the release record,
the future apply command is:

```bash
MANIFEST_SHA256='<approved canonical manifest SHA-256>'
python3 ops/keycloak_governance_reconcile.py \
  --apply \
  --expected-manifest-sha256 "$MANIFEST_SHA256"
```

Run the default dry-run again afterwards. `planned_operations`,
`incompatible_subjects`, and `forbidden_direct_assignments` must all be zero.
This does not activate any backend feature or deploy any container; those
remain GATE-07 and GATE-08 decisions.

## Verification

```bash
docker inspect --format '{{.State.Health.Status}}' keycloak
docker exec keycloak /opt/keycloak/bin/kc.sh --version
curl -fsS https://sealingai.com/realms/sealAI/.well-known/openid-configuration >/dev/null
curl -fsS https://sealingai.com/realms/sealAI/protocol/openid-connect/certs >/dev/null
```

Run all database backups and version upgrades through
`docs/keycloak-upgrade.md`.
