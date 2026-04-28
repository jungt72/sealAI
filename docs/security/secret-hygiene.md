# Secret and Env Hygiene

SeaLAI keeps real credentials out of git. Real `.env` files, local overrides,
rollbacks, backups, Keycloak exports with secrets, and operator-only auth files
must remain local to the VPS or the appropriate secret store.

## Repository Policy

- Tracked env files are limited to placeholder examples such as `.env.example`,
  `.env.prod.example`, and service-local `.env.example` files.
- Real files such as `.env`, `.env.dev`, `.env.prod`, `.env.local`, `.env.*`,
  `*.env`, backups, and rollback snapshots are ignored.
- Keycloak realm exports are allowed only when secret fields are placeholders.
  If an export may contain a real client secret, token, password, or private key,
  rotate that credential before using the repository for pilot work.
- Never paste env values, API keys, tokens, passwords, private keys, or Keycloak
  client secrets into tickets, docs, PRs, logs, or agent output.

## Safe Audit Commands

Run these from `/home/thorsten/sealai`:

```bash
git status --short
git ls-files '.env*' 'keycloak/*.json' 'keycloak/import/*.json'
python3 ops/check-secret-hygiene.py
```

`ops/check-secret-hygiene.py` reports only file paths, key names or JSON field
paths, and risk classes. It intentionally suppresses values.

## Rotation Requirement

Rotate the affected credential if any of these are true:

- a real secret was ever committed to git
- a Keycloak realm export contains a non-placeholder `secret`, `password`,
  `token`, `api_key`, `client_secret`, or `private_key` field
- a local `.env` backup, rollback, or auth file was copied outside the VPS
- agent, shell, CI, or application output exposed a secret value

Document rotation by credential name and system only. Do not document the old or
new value.
