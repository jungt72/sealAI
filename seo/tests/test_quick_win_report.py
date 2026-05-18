from datetime import date, timedelta
from pathlib import Path

from sealai_seo.db import apply_migrations, connect, upsert_page_query
from sealai_seo.reports.quick_wins import generate
from sealai_seo.text_sanitizer import QUERY_TAINT


def test_quick_win_report_sorts_candidates(tmp_path):
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    site = "sc-domain:sealingai.com"
    end = date(2026, 5, 1)
    for query, impressions, position in [("Dichtungstechnik", 500, 7), ("PTFE-RWDR", 150, 15)]:
        upsert_page_query(conn, {"data_date": end.isoformat(), "site_url": site, "search_type": "web", "country": "ALL", "device": "ALL", "page": "https://sealingai.com/wissen/gleitringdichtung-grundlagen", "query": query, "query_sanitized": query, "query_taint": QUERY_TAINT, "clicks": 1, "impressions": impressions, "ctr": 1 / impressions, "position": position, "data_state": "final", "ingested_at_utc": "now", "source": "gsc_api"})
    path = generate(conn, site_url=site, report_dir=tmp_path, period_end=end)
    text = path.read_text()
    assert "Dichtungstechnik" in text
    assert text.index("Dichtungstechnik") < text.index("PTFE\\-RWDR")
