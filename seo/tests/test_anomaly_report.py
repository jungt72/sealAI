from datetime import date, timedelta
from pathlib import Path

from sealai_seo.db import apply_migrations, connect, upsert_page
from sealai_seo.reports.anomaly import generate


def test_anomaly_report_emits_drop(tmp_path):
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    site = "sc-domain:sealai.net"
    target = date(2026, 5, 1)
    for i in range(1, 29):
        d = target - timedelta(days=i)
        upsert_page(conn, {"data_date": d.isoformat(), "site_url": site, "search_type": "web", "country": "ALL", "device": "ALL", "page": "https://sealai.net/", "clicks": 20, "impressions": 400, "ctr": 0.05, "position": 6, "data_state": "final", "ingested_at_utc": "now", "source": "gsc_api"})
    upsert_page(conn, {"data_date": target.isoformat(), "site_url": site, "search_type": "web", "country": "ALL", "device": "ALL", "page": "https://sealai.net/", "clicks": 3, "impressions": 100, "ctr": 0.03, "position": 10, "data_state": "final", "ingested_at_utc": "now", "source": "gsc_api"})
    path = generate(conn, site_url=site, report_dir=tmp_path, target_date=target)
    assert "click_drop" in path.read_text()
