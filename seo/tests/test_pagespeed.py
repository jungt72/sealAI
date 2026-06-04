from pathlib import Path

from sealai_seo.db import apply_migrations, connect
from sealai_seo.pagespeed import extract_metrics, sample_pagespeed_payload, sync_pagespeed


def test_extract_pagespeed_metrics():
    metrics = extract_metrics(sample_pagespeed_payload(), url="https://sealingai.com/", strategy="mobile")

    assert metrics.performance_score == 0.91
    assert metrics.lcp_ms == 1850
    assert metrics.inp_ms == 120
    assert metrics.cls == 0.02
    assert metrics.fcp_ms == 980
    assert metrics.ttfb_ms == 180


def test_sync_pagespeed_dry_run_persists_metrics(tmp_path):
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")

    result = sync_pagespeed(conn, urls=["https://sealingai.com/"], dry_run=True)

    assert result["status"] == "success"
    assert result["urls_scanned"] == 1
    row = conn.execute("SELECT * FROM pagespeed_url_metrics").fetchone()
    assert row["url"] == "https://sealingai.com/"
    assert row["strategy"] == "mobile"
    assert row["performance_score"] == 0.91
