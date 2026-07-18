---
name: frontend-marketing
description: >-
  Work on the sealingAI marketing website — the Next.js app in frontend/ (NOT the
  product dashboard). Use when a task touches frontend/ (marketing pages, SEO,
  NextAuth/BFF proxy-auth, the landing/lifecycle UI, or its tests), or asks to
  deploy the marketing site. Encodes the release-frontend.sh deploy path, the
  frontend/DESIGN.md design SoT, and the two-auth-systems distinction.
---

# Marketing website (`frontend/` — Next.js)

`frontend/` is the **marketing site only** — the public sealingai.com pages. It is
**not** the product UI (that is `frontend-v2/`, the dashboard — see the
`frontend-v2-dashboard` skill). Next.js 16 (App Router), NextAuth 5 beta,
framer-motion, vitest.

## Design source of truth

`frontend/DESIGN.md` is the design SoT for marketing UI work — read it for any
visual/layout change. Rebrand + chat-scroll rework are already live on `main`.

## Deploy path

Marketing ships **only** via the sanctioned script — health-gated, with a rollback
anchor read from the running daemon:

```bash
./ops/release-frontend.sh
```

Build mechanism: a Next.js **standalone** build (`next build` + a `postbuild` that
assembles `.next/standalone`), deployed as a container image. This is a **different
mechanism** from the dashboard (`frontend-v2` deploys via its `dist/` bind-mount,
where `npm run build` IS the deploy). Be explicit about which frontend you mean.

## Tests

```bash
cd frontend && npm run test:all     # node (tsx) + vitest
cd frontend && npm run test:run     # vitest CI mode only
cd frontend && npm run lint         # eslint
```

Note: the release script's pre-deploy gate tolerates one known pre-existing red
(the `workspaceMapping` vitest fail) — nothing *new* may break. Two stale smoke
checks in the release path still need cleanup; don't add a third.

## Two auth systems — do not conflate

The marketing site uses **NextAuth** (`next-auth` beta) + a BFF proxy-auth layer
(`src/lib/bff/`, `src/proxy-auth.ts`). The **product** uses **V2 OIDC** (Keycloak,
the dashboard `/dashboard/callback`). They are separate systems — a change to one
is not a change to the other. Respect Keycloak user/tenant scoping; do not expose
or invent secrets.

## Projection, not authority

Marketing pages must not generate authoritative engineering claims. Keep the
public copy within the scoped safety language (screening / orientation / review
required) — never "geeignet"/"freigegeben"/final release (AGENTS.md § Safety
Boundaries).

## Discipline

1. Deploy only via `ops/release-frontend.sh`; read the rollback anchor from the
   running daemon, never memory.
2. Read `frontend/DESIGN.md` before UI changes.
3. Keep marketing (`frontend/`) and dashboard (`frontend-v2/`) mentally separate —
   different framework, different deploy, different auth.
