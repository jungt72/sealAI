# SealAI SEO Pipeline

Phase 1 is a deterministic Google SEO control foundation. It mirrors GSC Search Analytics signals into SQLite, enriches the keyword foundation with DataForSEO, records PageSpeed/Core-Web-Vitals lab checks, crawls sitemap URLs for indexability and internal-link signals, and emits Markdown reports.

Included:

- GSC page and page/query sync
- SQLite storage with idempotent upserts
- Daily anomaly report
- Weekly quick-win keyword report
- Sitemap indexability crawler and internal link graph
- GSC URL Inspection persistence for selected URLs
- DataForSEO keyword-volume foundation with explicit budget guard
- DataForSEO SERP snapshots with explicit budget guard
- PageSpeed Insights / Lighthouse lab checks for key landing pages
- Runtime scripts, backups, tests

Not included in Phase 1: LangGraph, MCP, Claude/LLM jobs, backlinks, Merchant Center, Looker Studio provisioning, Google Business Profile management, or automated content generation.

DataForSEO is configured as an optional external signal connector. Keep it gated behind explicit runs because most keyword, SERP, and backlink endpoints can consume account balance.

GA4/GTM is handled in the Next.js frontend through environment-gated client tags. The app emits `page_view`, `material_page_viewed`, `medium_page_viewed`, `case_started`, `rfq_started`, and `rfq_preview_generated` without sending chat text or entered parameters.

GSC Search Analytics API data is treated as a strong SEO performance signal, not a complete raw export of all search data. If longtail completeness becomes critical, evaluate Search Console Bulk Data Export to BigQuery.

## Quick Start

```bash
cd /home/thorsten/sealai
PYTHONPATH=seo/src python -m sealai_seo.cli init-db
PYTHONPATH=seo/src python -m sealai_seo.cli sync-gsc --dry-run
PYTHONPATH=seo/src python -m sealai_seo.cli report-weekly
PYTHONPATH=seo/src python -m sealai_seo.cli dataforseo-user-data
PYTHONPATH=seo/src python -m sealai_seo.cli dataforseo-budget-check --planned-cost 0.25
PYTHONPATH=seo/src python -m sealai_seo.cli seed-keywords
PYTHONPATH=seo/src python -m sealai_seo.cli dataforseo-keyword-volume --dry-run --planned-cost 0.10
PYTHONPATH=seo/src python -m sealai_seo.cli dataforseo-serp-snapshot --dry-run --planned-cost 0.20
PYTHONPATH=seo/src python -m sealai_seo.cli report-keyword-foundation
PYTHONPATH=seo/src python -m sealai_seo.cli report-content-roadmap
PYTHONPATH=seo/src python -m sealai_seo.cli crawl-indexability
PYTHONPATH=seo/src python -m sealai_seo.cli report-indexability
PYTHONPATH=seo/src python -m sealai_seo.cli sync-url-inspection --sitemap-url https://sealingai.com/sitemap.xml --limit 10 --dry-run
PYTHONPATH=seo/src python -m sealai_seo.cli sync-pagespeed --dry-run
```

Runtime paths:

- DB: `/var/seo/data/seo.db`
- Reports: `/var/seo/reports`
- Logs: `/var/seo/logs`
- Backups: `/var/seo/backups`
- Secrets: `/etc/seo/secrets`

Optional DataForSEO secret fallback:

- `/home/thorsten/.sealai/dataforseo.env`

Expected keys:

```bash
DATAFORSEO_LOGIN=...
DATAFORSEO_PASSWORD=...
DATAFORSEO_BASE_URL=https://api.dataforseo.com/v3
DATAFORSEO_MAX_RUN_COST_USD=0.25
PAGESPEED_API_KEY=
PAGESPEED_URLS=https://sealingai.com/,https://sealingai.com/wissen/wellendichtring,https://sealingai.com/werkstoffe/fkm,https://sealingai.com/werkstoffe/ptfe,https://sealingai.com/anfrage/dichtung-auslegen-lassen
```

Run `dataforseo-budget-check` before any paid DataForSEO workflow. It blocks when the planned cost exceeds the per-run limit or the current account balance.

Run 0 uses `seo/data/run0_keywords.csv` and the DataForSEO Google Ads Search Volume live endpoint for a small German-language seed validation. Plan `$0.10` for the initial seed-volume run. SERP snapshots are available through `dataforseo-serp-snapshot` and must stay explicit and budget-gated.

Tests:

```bash
make -C seo test
```
