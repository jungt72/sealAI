---
name: frontend-v2-dashboard
description: >-
  Work on the sealingAI product dashboard — the Vite/React/TypeScript SPA in
  frontend-v2/ served under /dashboard. Use when a task touches frontend-v2/
  (components, chat UI, case sidebar, OIDC/auth callback, PDF/KaTeX rendering,
  vite config, or its tests). Encodes the single biggest footgun: `npm run build`
  in the VPS checkout IS a production deploy (live dist bind-mount), plus the
  no-V1-imports boundary and projection-of-backend-truth rules.
---

# Product dashboard (`frontend-v2/` — Vite/React SPA under `/dashboard`)

The active product UI for `backend/sealai_v2/`. React 18 + TypeScript, built by
**Vite**, tested with **vitest**. It renders answers (react-markdown + KaTeX) and
exports (jspdf). It is a **projection of backend truth**.

## THE footgun: `npm run build` = production deploy

`frontend-v2/dist` is a **live read-only bind-mount** into nginx
(`docker-compose.deploy.yml:93` → `/usr/share/nginx/v2-client:ro`). So on the VPS
checkout, **`vite build` overwrites what is live** — `npm run build` IS the deploy,
not just a type-check. Never run it casually.

- To **verify without deploying**, run the non-build steps only:
  ```bash
  cd frontend-v2 && npm run check:boundary && npm run typecheck && npm run test
  ```
- `npm run verify` (= `check:boundary && typecheck && test && build`) **ends in a
  build → deploy** — only run it when you intend to ship.
- A deliberate dashboard deploy = `npm run build` on the VPS checkout (the mount
  serves the new `dist/` immediately). Be explicit that you are deploying; this is
  a different mechanism from `ops/release-frontend.sh` (marketing) and
  `ops/release-backend-v2.sh` (backend).

## No-V1 imports (the frontend import boundary)

`npm run build` runs `check:boundary` first (`scripts/check-no-v1-imports.mjs`) —
the dashboard must not import V1 client code. Keep it clean; do not bypass the
check to get a build through.

## Projection of backend truth

Do **not** compute or generate authoritative engineering claims (numbers, norms,
material verdicts, suitability) in the frontend. The backend owns facts with
provenance; the dashboard renders them. No technical claims are generated in
frontend code (AGENTS.md Clean-Code rule).

## OIDC / routing (real incident history)

The SPA is client-side routed with an OIDC callback at `/dashboard/callback`
(nginx `try_files … /dashboard/index.html` SPA fallback). Two real bugs shipped
here — watch for them:

- **The OIDC redirect must preserve the query string** (`?case=…`). A redirect that
  dropped `?case=` silently broke deep-linking into a case. Preserve query params
  across the login round-trip.
- **Case-switch race:** switching the active case mid-load raced the fetch. Guard
  against stale-response application when the active case changes.

## Cutover status (owner-gated)

The nginx `/dashboard` route + `/api/v2` proxy live in `nginx/snippets/
v2_dashboard.conf` and are **not applied to prod until an owner-gated cutover**
(the live file is a `.bak`). Do not flip that route yourself — it is owner-gated,
like any shared-edge nginx change.

## Discipline

1. Verify with `check:boundary + typecheck + test` — **not** `build` — unless you
   mean to deploy.
2. Keep the frontend a renderer; push engineering truth to the backend.
3. Shared-edge nginx / cutover changes need explicit per-action owner go-ahead.
