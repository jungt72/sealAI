# Structured Data Inventory

Source of truth: `frontend/src/lib/seo/jsonLd.ts`. All schemas are generated
from real page data (title/description/dates from content frontmatter, or
hardcoded owner-authored copy) — none are templated from unverified
assumptions.

| Schema type | Where used | Fields sourced from | Notes |
|---|---|---|---|
| `Organization` | homepage | hardcoded name/url/logo/description | `sameAs` intentionally omitted (previously a self-referencing no-op URL) — add real external profile URLs (LinkedIn etc.) once they exist |
| `WebSite` | homepage | hardcoded | `inLanguage: de-DE` |
| `WebApplication` | homepage | hardcoded | describes the whole platform; `offers.price: "0"` for the free precheck + login-gated analysis |
| `Article` | every `/wissen/[slug]` | frontmatter `title/description/datePublished/dateModified/author` | `dateModified` falls back to `datePublished` when never edited since |
| `TechArticle` | every `/werkstoffe/[slug]` and `/medien/[slug]` | frontmatter + hardcoded `category` per route file | same `dateModified` fallback |
| `BreadcrumbList` | every article | hardcoded per-page (Startseite / hub / article title) | |
| `SoftwareApplication` | `/anfrage/dichtung-auslegen-lassen` (added this session) | real: name, applicationCategory, operatingSystem, offers.price=0 | **No `aggregateRating`/`Review`** — none exist; would be a fabricated trust signal, not added |

## Deliberately absent (do not add without a real basis)

- `FAQPage` — no visible FAQ content on the homepage; Google restricts this
  rich result to gov/health sites since 2023 anyway. `generateFAQPageSchema`
  still exists in `jsonLd.ts` for the standalone `WebsiteGuide` component's
  own FAQ list, if that's ever re-enabled with real visible FAQ content.
- `SearchAction` — no working site search exists.
- `Person` — no named individual author/reviewer exists (see baseline.md).
- `Dataset` — no downloadable/queryable dataset is published.
- `Review` / `aggregateRating` anywhere — no real ratings exist.

## Validation

Not run in this session (no network access to Google's Rich Results Test
from this environment). Recommended before the next content push: paste a
built article's rendered JSON-LD into https://validator.schema.org/ and
Google's Rich Results Test.
