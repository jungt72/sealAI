from pathlib import Path

from sealai_seo.db import apply_migrations, connect
from sealai_seo.url_inspection import inspect_urls


class FakeInspectionClient:
    def __init__(self):
        self.calls = []

    def inspect_url(self, *, inspection_url: str, site_url: str, language_code: str = "de-DE"):
        self.calls.append((inspection_url, site_url, language_code))
        return {
            "inspectionResult": {
                "indexStatusResult": {
                    "verdict": "PASS",
                    "coverageState": "Submitted and indexed",
                    "indexingState": "INDEXING_ALLOWED",
                    "pageFetchState": "SUCCESSFUL",
                    "robotsTxtState": "ALLOWED",
                    "googleCanonical": inspection_url,
                    "userCanonical": inspection_url,
                    "lastCrawlTime": "2026-05-18T06:00:00Z",
                    "sitemap": ["https://sealingai.com/sitemap.xml"],
                }
            }
        }


def test_url_inspection_persists_gsc_verdict(tmp_path):
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    client = FakeInspectionClient()

    result = inspect_urls(
        conn,
        client=client,
        site_url="sc-domain:sealingai.com",
        urls=["https://sealingai.com/"],
    )

    assert result["status"] == "success"
    assert result["urls_inspected"] == 1
    row = conn.execute("SELECT * FROM gsc_url_inspection").fetchone()
    assert row["inspection_url"] == "https://sealingai.com/"
    assert row["verdict"] == "PASS"
    assert row["coverage_state"] == "Submitted and indexed"
    assert client.calls == [("https://sealingai.com/", "sc-domain:sealingai.com", "de-DE")]
