import sqlite3
from pathlib import Path

from sealai_seo.db import apply_migrations, connect


def test_schema_applies(tmp_path):
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "schema_migrations",
        "gsc_sync_runs",
        "gsc_daily_page",
        "gsc_daily_page_query",
        "pagespeed_sync_runs",
        "pagespeed_url_metrics",
        "keyword_seed",
        "keyword_metrics",
        "dataforseo_runs",
        "seo_crawl_runs",
        "seo_url_checks",
        "seo_internal_links",
        "gsc_url_inspection_runs",
        "gsc_url_inspection",
        "dataforseo_serp_runs",
        "dataforseo_serp_results",
    } <= tables
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_gsc_page_query_query" in indexes
    assert "idx_pagespeed_metrics_url" in indexes
    assert "idx_seo_url_checks_url" in indexes
    assert "idx_gsc_url_inspection_url" in indexes
    assert "idx_dataforseo_serp_target" in indexes
