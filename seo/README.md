# SealAI SEO Pipeline

Phase 1 is a deterministic Google Search Console data foundation. It mirrors GSC Search Analytics signals into SQLite and emits Markdown reports.

Included:

- GSC page and page/query sync
- SQLite storage with idempotent upserts
- Daily anomaly report
- Weekly quick-win keyword report
- Runtime scripts, backups, tests

Not included in Phase 1: LangGraph, MCP, Claude/LLM jobs, GA4, PageSpeed, DataForSEO, crawling, backlinks, competitor analysis, or automated content generation.

DataForSEO is configured as an optional external signal connector. Keep it gated behind explicit runs because most keyword, SERP, and backlink endpoints can consume account balance.

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
PYTHONPATH=seo/src python -m sealai_seo.cli report-keyword-foundation
PYTHONPATH=seo/src python -m sealai_seo.cli report-content-roadmap
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
```

Run `dataforseo-budget-check` before any paid DataForSEO workflow. It blocks when the planned cost exceeds the per-run limit or the current account balance.

Run 0 uses `seo/data/run0_keywords.csv` and the DataForSEO Google Ads Search Volume live endpoint for a small German-language seed validation. Plan `$0.10` for the initial seed-volume run; use SERP APIs only after the top keyword set is known.

Tests:

```bash
make -C seo test
```
