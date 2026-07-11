# SEO Implementation Backlog

Priority follows the source concept's own gate model (P0 = no external
dependency, P1 = judgment call but technically self-contained, P2 = needs
real business data from the owner, P3 = defer until an earlier cluster
proves organic signal). Status reflects what's actually shipped as of this
document's commit, not what's planned.

## P0 — done this session

- [x] Sitemap `lastmod`: real per-article dates instead of `new Date()` on
      every entry.
- [x] Cache-Control regression fixed again (`must-revalidate`).
- [x] Per-article OG images (`opengraph-image.tsx` via `next/og`).
- [x] `dateModified` in Article/TechArticle schema + visible "Stand: …" date
      on every article.
- [x] `og:locale`, `robots["max-image-preview"]`.
- [x] AI-crawler-specific robots.txt policies (training vs. search/answer
      bots split).
- [x] SEO rules encoded in `frontend/AGENTS.md` (was previously zero SEO
      governance in either `AGENTS.md`).
- [x] Stale `frontend/AGENTS.md` structure section fixed (described a
      `dashboard`/`rag` app-router structure that hasn't existed since the
      V1 retirement).
- [x] This `docs/seo/` baseline.

## P1 — done this session

- [x] Free precheck tool (`HeroPrecheckCard` via `PrecheckDemoSection`)
      surfaced on `/anfrage/dichtung-auslegen-lassen` instead of living
      unused in the codebase. Existing page copy/CTA updated so "Fall jetzt
      klären" leads to the actual tool, not straight past it to login.
- [x] `SoftwareApplication` schema added for that tool (real fields only —
      no fabricated rating).
- [x] Content data model: added optional `evidence_level` / `sources` /
      `review_status` frontmatter fields + types, with a documented default
      of `review_status: legacy` for the 25 existing articles (an honest
      statement of process state, not an invented accuracy claim) rather
      than back-filling fake evidence levels.
- [x] `/methodik` page — describes the real, verifiable mechanics (Kernel
      vs. LLM, confirmed/estimated/missing states, human-in-the-loop,
      deterministic precheck) already documented in this repo's own Leitbild.

## P1 — flagged, not done (needs your call, not a technical blocker)

- [x] **Named author/reviewer** — done 2026-07-11: owner authorized
      "Thorsten Jung"; all 25 articles carry the author, Article/TechArticle
      schema emits a Person entity, articles show a visible byline, and
      /methodik#redaktionelle-verantwortung names editorial responsibility
      (which is also the EU AI Act Art. 50(4) exemption condition, ahead of
      the 2026-08-02 start date).
- [ ] **`/probleme/` URL reframing.** The concept suggests problem-first URLs
      (`/probleme/wellendichtring-undicht/`) instead of the current
      `/wissen/wellendichtring-undicht`. The content already covers this
      cluster closely — a URL migration is a real (if reversible) SEO risk
      to whatever ranking signal the current URLs have already accumulated.
      Recommend deciding this only after Search Console shows actual
      impressions/rankings on the current URLs, not before.

## P2 — blocked on real data, not technical work

- [ ] **www.sealingai.com has no DNS record** (found 2026-07-11): any
      www backlink/type-in fails before the app's www→apex redirect can
      run. Needs an A/CNAME record at the registrar plus cert/server_name
      in nginx.

- [ ] `/impressum` — Handelsregister, Geschäftsführer, USt-ID, Anschrift.
- [ ] `/kontakt` — a real, monitored contact email or form backend.
- [ ] Attorney sign-off on `/datenschutz`, `/nutzungsbedingungen`,
      `/auftragsverarbeitung` (currently drafts with `[Platzhalter]` fields —
      see `docs/legal-onboarding.md`).

## P3 — explicitly deferred, not forgotten

- `/schadensbilder/`, `/anwendungen/` as dedicated taxonomy hubs.
- English (`/en/`) version.
- Glossary (correctly low priority per the source concept itself).
- Programmatic SEO / large-scale page generation.
- A second/third calculator beyond the circumferential-speed one already
  embedded in the precheck tool.
