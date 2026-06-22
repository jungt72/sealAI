# frontend-v2 — the clean V2 client (M7)

A minimal SPA (Vite + React + TS) for **sealingai.com/dashboard**, projecting **only** over `/api/v2`.
It reuses the sealingAI **design language** (DESIGN.md + the `@theme` tokens, seal-blue `#002A5B`,
Google Sans) but is **dependency-independent of the V1 app** (`frontend/`) — the clean-cutover
guarantee, enforced structurally.

## Boundaries & guardrails
- **Imports nothing from V1 (`frontend/`)** — enforced by `scripts/check-no-v1-imports.mjs` (the
  frontend keystone; `npm run check:boundary`, wired into `npm run verify`). The build fails on a V1 import.
- **Talks ONLY to `/api/v2` (+ same-origin Keycloak)** — `src/api/client.ts`; no V1 backend, no domain
  logic in the client (all truth is computed server-side).
- **Auth:** OIDC Authorization-Code + **PKCE**, **public** client `sealai-v2`; access token **in memory
  only** (never web storage); silent renewal via the Keycloak SSO session preferred. The client never
  asserts tenant/session — it only sends the Bearer (M6c derives identity server-side, no-header-trust).
- **Safety-framing is ubiquitous** (`src/framing.ts` single source): the Orientierung≠Freigabe
  claim-boundary, `vorläufig`/candidate labels, remembered-facts-are-unverified, and citations showing
  the **primary source** (Parker / ISO 3601-2) — on every domain-content surface (chat, history, briefing).

## Develop / build / verify
```bash
cd frontend-v2
npm ci                      # prod/CI: own deps  (this session reuses ../frontend/node_modules via a symlink)
npm run verify              # check:boundary + typecheck + test + build  (all green)
npm run dev                 # local dev server
```
Env (public, not secrets): `VITE_OIDC_ISSUER`, `VITE_OIDC_CLIENT_ID=sealai-v2`, `VITE_OIDC_REDIRECT_URI`.

## OWNER PREREQUISITE — Keycloak (realm `sealAI`), before the live smoke
1. **Public client `sealai-v2`** — Access Type *public* (no secret); Standard Flow on; **PKCE S256
   required**; Valid redirect URIs `https://sealingai.com/dashboard/*`; Web origins `https://sealingai.com`.
2. **Audience mapper** → tokens carry `aud` = the value backend-v2 validates (set `SEALAI_V2_AUTH_AUDIENCE`).
3. **`tenant_id` claim mapper** → the user's tenant into the `tenant_id` claim (`sid`/`sub` are standard).
   Without these the M6c validator fails closed (correct).

## Serving / cutover (owner-gated, NOT applied to prod by M7)
Build → `dist/`; mount at nginx `/usr/share/nginx/v2-client`; `include snippets/v2_dashboard.conf;`
in the `sealingai.com` server block (serves `/dashboard` + strict CSP, enables `/api/v2 →
backend-v2:8001`); bring `backend-v2` online (`v2` profile) with `auth_*` config. Verify with `nginx
-t` + a local/staging bring-up — **the production cutover is a separate owner-gated deploy.**
