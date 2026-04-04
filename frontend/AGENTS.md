# Frontend AGENTS.md

## Scope

This file applies to `/home/thorsten/sealai/frontend`.

The frontend is a standalone Next.js 16 App Router project. Treat this directory as the authoritative UI workspace for local frontend package installs, builds, and lockfile updates.

## Working Rules

- Run frontend package commands from `/home/thorsten/sealai/frontend`.
- Keep changes minimal and aligned with the existing App Router structure.
- Do not move domain logic from the backend into the frontend.
- Prefer typed interfaces in `src/lib` and lightweight UI composition in `src/components`.
- Preserve the current auth integration in `src/auth.ts` and `src/app/api/auth/[...nextauth]`.

## Structure

- `src/app`
  App Router entrypoints, layouts, routes, and API handlers.
- `src/app/api`
  Frontend-side route handlers such as auth and health endpoints.
- `src/app/dashboard`
  Main authenticated dashboard experience.
- `src/app/rag`
  RAG document and retrieval UI routes.
- `src/components/dashboard`
  Dashboard-specific UI components.
- `src/components/rag`
  RAG-specific UI components.
- `src/hooks`
  Client hooks for streaming, workspace state, and UI coordination.
- `src/lib`
  Typed client utilities and API-facing helpers.
- `src/auth.ts`
  Central NextAuth/Auth.js configuration.
- `src/proxy.ts`
  Request gating for protected routes using the Next.js 16 proxy convention.

## Build And Verification

- Install dependencies with `npm ci`.
- Start local development with `npm run dev`.
- Verify production readiness with `npm run build`.
- When changing dependencies, keep `package-lock.json` in sync.

## Notes For Agents

- The repository root also contains a separate `package.json`; it is not the authoritative frontend app workspace.
- `next.config.js` pins both `turbopack.root` and `outputFileTracingRoot` because this repo has multiple lockfiles.
