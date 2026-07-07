@AGENTS.md

# CLAUDE.md — sealingAI frontend (marketing site)

Claude Code operating rules for `/home/thorsten/sealai/frontend` — the **Next.js 16
marketing site** (`sealingai.com`). This is the public website, **not** the product
dashboard (that is `frontend-v2`, a separate Vite app served under `/dashboard`).
Read `AGENTS.md` (this directory) and the repo-root `AGENTS.md` for backend/product
context. Design tokens: `DESIGN.md` + `src/app/globals.css` (`@theme`).

## Claude Code specific rules

Always explore and plan before large multi-file edits. Verify with the project
commands. For this project, do not use an LLM in the public homepage hero
precheck. Preserve sealingAI technical neutrality. Do not introduce heavy
dependencies without a clear reason.

1. **Project goal.** sealingAI is a technical platform for sealing technology that
   turns incomplete input into a usable technical case — not a toy AI, not a seal
   catalog, not a manufacturer advertising portal.
2. **Marketing rule.** No exaggerated AI language. No final technical promises. No
   "AI finds the best seal", no "perfect solution".
3. **Technical safety rule.** The homepage hero precheck uses **no LLM** and gives
   **no** final recommendation (no material, no manufacturer, no RFQ, no approval).
   Its only computation is deterministic (`src/lib/hero-precheck/`).
4. **Neutrality rule.** No manufacturer can buy technical suitability. Technical
   assessment and commercial partnership stay clearly separated.
5. **SEO rule.** New pages/sections must be semantic, indexable, performant and
   aligned with real DACH search intent. No doorway/thin/hidden-content pages.
6. **Component rule.** Server/static by default; `"use client"` only where
   interactivity is required (the precheck card, the website guide, the layer tabs).
7. **Test rule.** New logic must be tested (vitest `*.spec.ts` / `*.test.tsx`,
   or `node:test` via `test:node`).
8. **Content rule.** Do not copy manufacturer data, tables, PDFs, foreign website
   text, third-party fonts, or third-party design (incl. Legora).
9. **Build rule.** After changes run, from this directory: `npm run lint`,
   `npx tsc --noEmit`, `npm run test:run` (and `npm run test:node`), and
   `npm run build`. `npm run build` here is a type-check/build — the marketing
   deploy is `ops/release-frontend.sh`, so building does not ship.
10. **Design rule.** Premium, quiet, technical B2B look. Navy `#002A5B` = trust;
    off-white `#FAFAF9` background; terracotta `#D97757` as the intentional CTA
    accent only. No generic AI visuals, no colorful SaaS clutter, no heavy shadows.
11. **Performance rule.** No heavy animation libraries, large videos, or unnecessary
    bundles without explicit justification. Prefer CSS over JS animation; respect
    `prefers-reduced-motion`.

## Verify (from `frontend/`)

```bash
npm run lint
npx tsc --noEmit
npm run test:run      # vitest (component + logic)
npm run test:node     # node:test units
npm run build         # next build (type-check; NOT a deploy)
```
