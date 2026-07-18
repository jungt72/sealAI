# Credential Rotation and Revocation Runbook

Use this runbook for the credential artifacts confirmed by the 2026-07-14
production audit and for future scanner findings. It is an operator procedure;
this repository change does not rotate, revoke, deploy, or restart anything.

## Confirmed affected classes

- repository TLS private-key artifact (`certs/tls.key`)
- repository Keycloak private-key artifact (`keycloak/certs/key.pem`)
- ACME account private JWK under `nginx/certbot/accounts/`
- authenticated live diagnostic capture under `docs/debug_internal_error/live/`
- any credentials copied into host env/rollback/backup files that were readable
  by unintended local accounts

The current tree removes the confirmed repository artifacts plus co-located raw
diagnostic and ACME account metadata. Old credential values remain compromised
until authoritative rotation/revocation is complete, and the Git objects remain
in history until a separately approved rewrite.

## Gate 0 — authorize and contain

1. Name the incident/change owner, credential administrator, reviewer, affected
   environment, and maintenance window.
2. Freeze production promotion from a tree or runtime using an affected
   credential.
3. Do not display, hash, compare, copy, or paste old/new values in terminals,
   tickets, chat, CI, or audit evidence.
4. Identify consumers from configuration *names and mounts only*. Do not use
   broad environment dumps or recursive file-content commands.
5. Prepare a service rollback that retains the replacement credential. Never
   plan to roll back to the exposed value.

## Gate 1 — rotate by authoritative system

### Bearer/JWT and API credentials

Issue a new least-privilege credential in the owning provider, inject it through
the approved runtime secret path, validate the named consumer, then revoke the
old token/client secret. Invalidate refresh tokens and sessions when the owning
system supports it. A JWT captured in diagnostics is treated as usable until its
expiry or explicit session/client revocation is confirmed.

### ACME account JWK

Create or select an approved ACME account key outside Git, update the Certbot
account store with service-only ownership, prove renewal against the intended
account, then deactivate the exposed account/key if the CA workflow supports
it. Confirm renewal continuity before retiring the old account.

### TLS/private key material

Determine through a private operator-side check whether any served certificate
or trust relationship uses the exposed key. If it might, generate a new key,
reissue the certificate, deploy through the sanctioned edge-change procedure,
verify certificate metadata and service health, then revoke the superseded
certificate where supported. Do not log key comparisons or fingerprints.

### Keycloak key material

Establish whether the artifact ever backed TLS, realm signing, or another
Keycloak provider. Rotate through Keycloak's supported key/provider mechanism,
retain an overlap window only when token validation requires it, validate login
and token verification, and then disable/remove the old provider/key. A file
deletion alone does not rotate realm signing keys.

### Database, cache, and application env credentials

Create per-service replacements rather than reusing a shared bootstrap
credential. Update one consumer at a time where possible, validate it, revoke
the prior login/password, and review connection pools/workers for stale
sessions. Treat every credential stored in an unintended-readable copy as
exposed.

## Gate 2 — value-free verification

Record only:

- credential class and logical identifier
- authoritative system and named consumers
- replacement active: yes/no
- old credential revoked/disabled: yes/no
- service health/authentication result
- operator, reviewer, timestamp, and change/incident ID

Verify logs contain no value, authorization header, connection string, or raw
exception context. Re-run the repository scanner and relevant service health
checks. Provider-side rejection of the old credential may be tested only with a
safe, purpose-built method that does not put it in shell history or logs.

## Gate 3 — cleanup and closure

1. Remove old runtime files, rollback copies, diagnostic captures, CI artifacts,
   and backup copies under an approved retention decision.
2. Apply the file-permission runbook and correct the producer scripts/umask so
   insecure modes do not recur.
3. Obtain explicit approval before shared Git history is rewritten.
4. Notify clone/fork owners and invalidate caches/artifacts after a rewrite.
5. Close the incident only when rotation/revocation, runtime validation,
   repository gates, permissions, and distribution cleanup are independently
   reviewed.

If any consumer cannot be identified or the old credential cannot be revoked,
keep the incident and release freeze open and escalate to the owner.
