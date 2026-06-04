# Keycloak `tenant_id` mapper — applied + P0-2 unblock runbook

**Status:** APPLIED LIVE (2026-06-04). The mapper and the user-profile attribute
were set **manually by an operator** in the running `keycloak` container under
explicit authorization — not autonomously by a coding agent. The `tenant_id`
claim is now verified live (see the audit trail at the end of this file).

This **unblocks** P0-2 but does **not** perform it. Until the P0-2 code change
lands *and* the existing-row data migration is handled, the `tenant_id` fallbacks
in `backend/app/agent/api/deps.py:23` (`… or "default"`) and
`backend/app/api/v1/endpoints/rfq.py:42` (`… or user_id`) **must stay** — removing
them now would lock out the 353 `default` / 42 `user_id` legacy cases and any
login whose token predates the mapper.

## Why this is needed

Diagnosis (2026-06-03): Keycloak issues **no `tenant_id` claim** today — there is
no mapper in `keycloak/`, `AUTH_TENANT_ID_CLAIM` is unset, and the live token
carries no tenant. So `_resolve_tenant_id` (`backend/app/services/auth/dependencies.py`)
returns `None` and callers fall back to `"default"` / `user_id`. Distribution in
`cases`: 353 `default` / 42 `tenant_id==user_id` / 0 real org claims. P0-1
(LTM tenant scoping) is in place as defense-in-depth; P0-2 (fallback removal) is
the part that depends on this mapper.

## The mapper

Add a protocol mapper to the SealAI client (or a shared client scope) in the
realm:

- **Type:** `oidc-usermodel-attribute-mapper` (User Attribute mapper)
- **Config:** `user.attribute = tenant_id`, `claim.name = tenant_id`,
  `jsonType.label = String`, `access.token.claim = true`, `id.token.claim = true`
- **Prereq:** every user (or org) must carry a `tenant_id` user attribute.

Group/Organization-based alternative: if tenants map to Keycloak groups/orgs,
use a hardcoded-claim-per-group or a script mapper instead of a user attribute.

Then set `AUTH_TENANT_ID_CLAIM=tenant_id` in the backend environment (it already
defaults to `tenant_id`, but make it explicit and pass it through the active
Compose service env per the V10 runtime rule).

## Verify before changing any code

1. Obtain a fresh access token for a test user (real login or token endpoint).
2. Decode it and confirm a non-empty, correct `tenant_id` claim is present.
3. Only with the claim verified live do the next two steps proceed.

## Data migration (own step, before/with the fallback removal)

Existing rows do not get a real tenant retroactively: 353 `cases` on
`tenant_id="default"` + 42 on `user_id`. When real tenants arrive, NEW cases get
the real tenant but OLD ones stay on `default`/`user_id` and would become
invisible once the fallback is gone. Plan a one-off remap (out of scope for P0-1;
flagged here so it is not forgotten).

## P0-2 repo patch (only AFTER the claim is verified live)

- Remove the `or "default"` fallback at `backend/app/agent/api/deps.py:23`.
- Remove the `or user.user_id` fallback at `backend/app/api/v1/endpoints/rfq.py:42`.
- Effect: a request without a `tenant_id` claim now 401s instead of silently
  collapsing to a shared tenant. Land with cross-tenant read/delete tests green.

## Hard lines

No autonomous Keycloak/infra change. `.env*` files are off-limits. The fallback
removal is contingent on the verified claim — if the claim is absent, STOP and
keep the fallback (do not guess).

---

## Execution / audit trail (2026-06-04)

Applied live in the running `keycloak` container (KC 26) under explicit operator
authorization, via a temporary recovery admin (`bootstrap-admin`). All steps were
**additive**; no secrets, tokens, or `.env*` files were read, printed, or
committed. Realm `sealAI`, client `nextauth`
(uuid `c9267ac2-a7dc-4a62-ba11-25d932a8f8a2`).

**Backup taken first** → `~/keycloak-backups/20260604T074629Z/`:
`client-nextauth.json`, `client-nextauth-protocolmappers.json` (was `[]` — the
client had zero mappers), `user-profile.json`, and a full
`sealAI-realm-export.json` (58.9 KB). These are the rollback anchors.

**1. User Profile — `tenant_id` declared admin-only.** Added (idempotently) to
the declarative user profile, leaving the four existing attributes
(username/email/firstName/lastName) and the `user-metadata` group untouched
(diff-verified clean):

```json
{ "name": "tenant_id", "displayName": "Tenant ID", "multivalued": false,
  "permissions": { "view": ["admin"], "edit": ["admin"] } }
```

`view`/`edit` = `["admin"]` only → admin-managed, not user-visible/editable.

**2. Attribute backfill — `tenant_id="sealai"` on all 6 human users** of `sealAI`
(no `service-account-*` users exist in the realm; all 6 enabled). Verified 6/6
via full GET:

| username | uuid |
|---|---|
| codex-live | 1617f8ff-b5ac-43dd-a33c-6227d1b69a15 |
| codexscrollmay15 | 1b79c20d-771b-48cf-825e-90168d5b46df |
| fraoel | 16e67159-fd2e-425e-9c35-249cd4c78c37 |
| jungt | 7748ba15-bef4-43b4-b95a-cf80fcc476d8 |
| wazwfqwgqavdntfcg | 305fd896-288e-4574-a394-d0ff426bb44b |
| xbttckojhxxfwlguxiitdj | 2f816137-fb94-4af0-9243-8f1d490daaf4 |

(Note: this `jungt` is the **sealAI-realm** account — distinct from the
half-created **master-realm** `jungt` in cleanup item (b) below.)

**3. Protocol mapper created on `nextauth`** (additive; client had no prior
mappers) — `oidc-usermodel-attribute-mapper`, id `9fa67adc-dc29-43fc-8bfc-85dcfdd3ef64`:

```
user.attribute=tenant_id  claim.name=tenant_id  jsonType.label=String
access.token.claim=true  id.token.claim=true  userinfo.token.claim=true
introspection.token.claim=true  multivalued=false  aggregate.attrs=false
```

**4. Proof** via `clients/<id>/evaluate-scopes/generate-example-access-token`
(`userId=`jungt, `scope=openid`) — `tenant_id` claim excerpt only:

```json
{ "tenant_id": "sealai", "preferred_username": "jungt", "azp": "nextauth" }
```

This is exactly the claim `_resolve_tenant_id`
(`backend/app/services/auth/dependencies.py:76-81`) reads.

### P0-2 is now unblocked — but is a separate change, NOT in this PR
The live-claim precondition from "Verify before changing any code" is met. The
P0-2 code change remains its own task: remove the fallbacks at `deps.py:23` /
`rfq.py:42`, set `AUTH_TENANT_ID_CLAIM=tenant_id` explicitly in the active Compose
service env (V10 runtime rule), and land it **together with** the existing-row
data migration (353 `default` + 42 `user_id`) so legacy cases are not orphaned,
with cross-tenant read/delete tests green.

### Outstanding manual follow-ups (operator — do NOT auto-run; order is binding)
- **(a) Pre-restart blocker — Keycloak build config.** The `bootstrap-admin` runs
  persisted `health-enabled=false` / `metrics-enabled=false` into the container's
  build config. The image (`keycloak/Dockerfile`) builds `true/true` and runs
  `start --optimized`, so a **restart would boot the persisted false/false build**
  → `:9000/health/ready` breaks → unhealthy/restart-loop risk. Before the next
  restart: verify the start command (`--optimized`?) and reset the build config to
  `true/true`. (Container is currently `Up`, so not yet triggered.)
- **(b)** Half-created **master-realm** user `jungt` (row without a valid
  credential from a crashed run) — clarify / delete.
- **(c)** Rotate the **real admin password** (Thorsten) → verify login → **only
  then** delete the recovery admin `test`.
- **(d)** Store the new password at exactly one authoritative location; remove
  stale `.env` copies (Thorsten, manual).
