# SEO Baseline — sealingAI Marketing Site

Status: 2026-07-10. Scope: `frontend/` (the public marketing site — see root
`AGENTS.md`, "`frontend/`: marketing site only"). This is the C0 baseline
audit deliverable, compiled from a live audit + same-session fixes rather
than a from-zero crawl; findings below are evidenced (route checked, HTTP
status observed, file read), not assumed.

## Stack

- Next.js 16 App Router, TypeScript, Tailwind v4.
- Rendering: static/SSG for all public marketing pages (`○`/`●` in the build
  output) — not a client-rendered app shell. Only `/api/*` and `/login` are
  dynamic (`ƒ`).
- Content: flat Markdown + frontmatter in `content/{wissen,werkstoffe,medien}/*.md`,
  read via `src/lib/content/loader.ts`.
- Deploy: `ops/release-frontend.sh` — builds a Docker image, health-gates,
  reloads nginx, runs a live smoke test, auto-rolls-back on health failure.

## Gate 0 status (legal + private-data + infra readiness)

| Item | Status |
|---|---|
| `/datenschutz`, `/nutzungsbedingungen`, `/auftragsverarbeitung` reachable | ✅ 200, but text is an attorney-review draft with `[Platzhalter]` fields (company address, DPO contact, hosting location) — not legally final |
| `/impressum` | ❌ 404 — requires Handelsregister/Geschäftsführer/USt-ID/Anschrift not present anywhere in this repo. Not built (data-blocked, not an oversight) |
| `/kontakt` (linked 4× from header/footer/drawer as `PARTNER_HREF`) | ❌ 404 — no monitored contact email or form backend exists in this repo/config either |
| Private routes protected | ✅ `/dashboard`, `/goal`, `/rag` disallowed in robots.txt AND auth-gated at the app/nginx level — robots.txt is not the only protection |
| Production/staging separated | ✅ no staging leakage observed in this audit |
| Search Console verification | ❓ not confirmed either way from outside — no verification meta tag found in the served homepage HTML, but GSC can also be domain-verified via DNS, which isn't visible from here |
| Analytics decision made | ✅ Rybbit (self-hosted, privacy-first) + GA4/GTM with `consent_default=denied`; `trackProductEvent`/`trackSeoEvent` abstraction already exists in code |
| Route inventory | ✅ this document + `routes.csv` |

## What's already solid (don't rebuild)

- Canonicals: self-referencing on every page checked.
- Metadata: `createMetadata()` in `src/lib/seo/metadata.ts` is the single
  source for title/description/canonical/OG/Twitter/robots across the site.
- Structured data: `Organization`, `WebSite`, `WebApplication` on the
  homepage; `Article`/`TechArticle` + `BreadcrumbList` on every content
  article. No fabricated `FAQPage`, `SearchAction`, or `Review`/`aggregateRating`
  anywhere — correctly absent, not correctly present.
- Internal linking: `MdxProse.tsx` carries a hand-curated `RELATED_LINKS` map
  (~3 contextual links per article) plus breadcrumbs on every article.
- Sitemap/robots: single `next-sitemap.config.js` drives both; real
  per-article `lastmod` from frontmatter (not "now" on every deploy); AI-bot
  policies split training vs. search/answer crawlers.

## Confirmed gaps (see `implementation-backlog.md` for priority)

1. **The public diagnostic tool has no indexable URL.** `HeroPrecheckCard`
   (deterministic, no LLM, real physics calc) is fully built and tested
   (`precheck.spec.ts`) but was living only as a homepage widget; the
   marketing rebuild (PR #191/#212) commented it out entirely
   (`PrecheckDemoSection` unused). `/anfrage/dichtung-auslegen-lassen`
   already has the right SEO framing (title, H1, required-fields content)
   for exactly this tool, but its own CTA skips straight to the login-gated
   dashboard instead of running the free tool. This is the single biggest
   gap relative to the product's own stated differentiation (structured
   public diagnosis before a gated full analysis).
2. **Content data model has no evidence/review metadata.** Frontmatter is
   `title/description/category/datePublished/dateModified/author` only — no
   `evidence_level`, `source_references`, or `review_status`. Existing
   articles' factual claims were not authored or fact-checked by any agent
   session with visibility into this; adding those fields now must not
   retroactively invent values for the 25 existing articles.
3. **No Methodik/Quellen (editorial standards) page.** No author-credibility
   page either — and none should be fabricated (see below).
4. **No named individual author/reviewer.** All content is attributed to the
   organization ("sealingAI"). Current E-E-A-T guidance favors a named,
   credentialed individual — but inventing one is a straightforward
   integrity violation, not a shortcut. Flagged, not worked around.

## Explicitly not done, and why

- **Person schema / named author.** Would require a real person with real
  credentials to attribute content to. Not invented.
- **`aggregateRating` on the tool's `SoftwareApplication` schema.** No real
  ratings exist. Several generic SEO guides suggest adding one anyway
  ("boosts CTR") — that is exactly the fabricated-trust-signal pattern
  Google's own spam policy and this repo's Leitbild both prohibit.
- **`/impressum`, `/kontakt` content.** Real business/contact data required,
  not present in this repo.
