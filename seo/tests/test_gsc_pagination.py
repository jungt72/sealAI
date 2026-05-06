from datetime import date

from sealai_seo.config import MAX_ROWS_PER_REQUEST
from sealai_seo.db import apply_migrations, connect
from sealai_seo.gsc_client import MockGscClient
from sealai_seo.sync_gsc import sync


def rows(n):
    return [{"keys": [f"https://example.com/{i}"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 9} for i in range(n)]


def test_pagination_uses_start_row(tmp_path):
    conn = connect(tmp_path / "seo.db")
    from pathlib import Path
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    client = MockGscClient({
        ("2026-05-01", ("page",), 0): rows(MAX_ROWS_PER_REQUEST),
        ("2026-05-01", ("page",), MAX_ROWS_PER_REQUEST): rows(2),
        ("2026-05-01", ("page",), MAX_ROWS_PER_REQUEST * 2): [],
        ("2026-05-01", ("page", "query"), 0): [],
    })
    sync(conn, client=client, site_url="sc-domain:sealai.net", date_from=date(2026, 5, 1), date_to=date(2026, 5, 1), log_dir=tmp_path)
    assert ("2026-05-01", ("page",), MAX_ROWS_PER_REQUEST) in client.calls
    assert ("2026-05-01", ("page",), MAX_ROWS_PER_REQUEST * 2) in client.calls
