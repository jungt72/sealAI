from datetime import date
from pathlib import Path

from sealai_seo.db import apply_migrations, connect
from sealai_seo.sync_gsc import ingest_rows


def test_idempotent_page_upsert(tmp_path):
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    base = [{"keys": ["https://sealingai.com/"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 8}]
    ingest_rows(conn, site_url="sc-domain:sealingai.com", search_type="web", data_date_value=date(2026, 5, 1), dimensions=["page"], rows=base)
    updated = [{"keys": ["https://sealingai.com/"], "clicks": 3, "impressions": 30, "ctr": 0.1, "position": 7}]
    ingest_rows(conn, site_url="sc-domain:sealingai.com", search_type="web", data_date_value=date(2026, 5, 1), dimensions=["page"], rows=updated)
    assert conn.execute("SELECT COUNT(*) FROM gsc_daily_page").fetchone()[0] == 1
    assert conn.execute("SELECT clicks FROM gsc_daily_page").fetchone()[0] == 3
