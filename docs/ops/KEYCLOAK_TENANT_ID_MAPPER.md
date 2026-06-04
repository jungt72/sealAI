# Keycloak `tenant_id` mapper — proposal & P0-2 unblock runbook

**Status:** PROPOSAL. Infra change in Keycloak, set **manually** by an operator —
never applied autonomously by a coding agent. Until it lands and the claim is
verified live, the `tenant_id` fallbacks in `backend/app/agent/api/deps.py:23`
(`… or "default"`) and `backend/app/api/v1/endpoints/rfq.py:42` (`… or user_id`)
**must stay** — removing them now (P0-2) would lock out every login.

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
