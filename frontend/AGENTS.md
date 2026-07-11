# Frontend AGENTS.md

## Scope

This file applies to `/home/thorsten/sealai/frontend`.

The frontend is a standalone Next.js 16 App Router project. Treat this directory as the authoritative UI workspace for local frontend package installs, builds, and lockfile updates.

## Working Rules

- Run frontend package commands from `/home/thorsten/sealai/frontend`.
- This app is the **public marketing site only** — the dashboard/chat/RFQ/RAG product UI lives in `frontend-v2` (Vite), served under `/dashboard` via nginx, not from this app. For product work, read the repository root `AGENTS.md` first.
- Keep changes minimal and aligned with the existing App Router structure.
- Do not move domain logic from the backend into the frontend.
- Prefer typed interfaces in `src/lib` and lightweight UI composition in `src/components`.
- Preserve the current auth integration in `src/auth.ts` and `src/app/api/auth/[...nextauth]`.

## Structure

- `src/app/(marketing)`
  The public site: homepage, `/wissen`, `/werkstoffe`, `/medien`, `/anfrage`, legal pages. This is what SEO work in this repo means in practice.
- `src/app/api`
  Frontend-side route handlers such as auth and health endpoints.
- `src/app/(app)/dashboard`
  Dead — contains no real `page.tsx` (only a stray `._page.tsx`). The actual dashboard is `frontend-v2`, not this app. Do not build product UI here.
- `src/components/marketing`
  Marketing site sections and components.
- `src/components/content`
  Markdown/article rendering (`MdxProse`) shared by `/wissen`, `/werkstoffe`, `/medien`.
- `src/lib/content`
  Content loader — reads `content/{wissen,werkstoffe,medien}/*.md` frontmatter + body.
- `src/lib/seo`
  Metadata (`createMetadata`), JSON-LD (`jsonLd.ts`), OG image generation (`ogImage.tsx`). Central and required — see SEO rules below.
- `src/hooks`
  Client hooks for streaming, workspace state, and UI coordination.
- `src/lib`
  Typed client utilities and API-facing helpers.
- `src/auth.ts`
  Central NextAuth/Auth.js configuration.
- `src/proxy.ts`
  Request gating for protected routes using the Next.js 16 proxy convention.

## SEO / public marketing site rules

The marketing site's job is to help someone with a real industrial sealing
problem, not to capture keyword variations. See `docs/seo/` for the baseline
audit and backlog this section is derived from.

- **Never invent technical facts.** Material limits, compatibility ratings,
  norms, formulas, or citations must come from reviewed content — the
  Leitbild's "no domain fact invented" rule (root `AGENTS.md`) applies to this
  app exactly as much as to the backend. A frontend PR is not exempt because
  it's "just marketing."
- **Never fabricate trust signals.** No invented author names/credentials, no
  fake `aggregateRating`/`Review` schema, no self-referencing or placeholder
  `sameAs` links, no FAQPage schema for content that isn't visibly rendered as
  FAQ on the page. If a real named reviewer or external profile doesn't exist
  yet, leave the field out — don't fill it with something plausible-looking.
- **Structured data must match visible content.** Test JSON-LD against what a
  user actually sees before adding a new schema type.
- **Indexability is deliberate, not accidental.** A new content page needs a
  unique title/H1/description, a self-referencing canonical, and real unique
  value before it's linked from anywhere crawlable or added to
  `next-sitemap.config.js`'s output. Private/individualized routes
  (`/dashboard`, `/goal`, `/rag` equivalents, any future per-user result page)
  must never appear in the sitemap or be indexable, regardless of robots.txt —
  robots.txt is not a security boundary, actual auth-gating is.
- **Prefer SSR/SSG.** Public pages should render their primary content,
  title, canonical, and internal links into the initial HTML. Don't make a
  public page client-only for content that matters to search or AI crawlers.
- **`next-sitemap.config.js` is the actual served `robots.txt`/sitemap
  source** (it writes a static `public/robots.txt` at build time, which Next
  serves ahead of the `src/app/robots.ts` route). Keep `robots.ts` in sync
  anyway — if the postbuild step is ever removed, it becomes live again, and a
  stale fallback fails silently.
- **AI crawlers:** training crawlers (GPTBot, ClaudeBot, Google-Extended,
  Bytespider, CCBot, meta-externalagent, Applebot-Extended) are disallowed;
  live AI-search/answer crawlers (OAI-SearchBot, ChatGPT-User,
  Claude-SearchBot, Claude-User, PerplexityBot) are allowed. These are
  separate bots per vendor — allowing one does not allow the other. Revisit
  the training-bot stance only as an explicit, documented decision, not a
  silent edit.
- **Analytics payloads stay categorical.** Never send free-text case inputs,
  drawings, personal data, or anything from `TEASER_STORAGE_KEY`/precheck
  form fields verbatim to `trackProductEvent`/`trackSeoEvent` — only
  technical/categorical state (which step, which coarse status, counts).
- **Core Web Vitals:** the LCP element on any page (typically a hero
  image/heading) must not be animated in via `opacity` — that delays or
  disqualifies its measured paint time. Use `next/image` with `priority` for
  any above-the-fold hero image, never a CSS `background-image` for the same
  role.

## Build And Verification

- Install dependencies with `npm ci`.
- Start local development with `npm run dev`.
- Verify production readiness with `npm run build`.
- When changing dependencies, keep `package-lock.json` in sync.

## Notes For Agents

- The repository root also contains a separate `package.json`; it is not the authoritative frontend app workspace.
- `next.config.js` pins both `turbopack.root` and `outputFileTracingRoot` because this repo has multiple lockfiles.
