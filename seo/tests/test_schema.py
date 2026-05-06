import sqlite3
from pathlib import Path

from sealai_seo.db import apply_migrations, connect


def test_schema_applies(tmp_path):
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"schema_migrations", "gsc_sync_runs", "gsc_daily_page", "gsc_daily_page_query"} <= tables
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_gsc_page_query_query" in indexes
