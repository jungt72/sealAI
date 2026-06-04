from pathlib import Path

from sealai_seo.db import apply_migrations, connect
from sealai_seo.serp_snapshot import extract_serp_items, run_serp_snapshot


class FakeSerpClient:
    def user_data(self):
        return {
            "tasks": [
                {
                    "result": [
                        {
                            "login": "mail@example.com",
                            "money": {"balance": 10.0},
                        }
                    ]
                }
            ]
        }

    def serp_google_organic_live_advanced(self, *, keywords, location_code, language_code, depth):
        return {
            "status_code": 20000,
            "status_message": "Ok.",
            "cost": 0.01,
            "tasks": [
                {
                    "data": {"keyword": keywords[0]},
                    "result": [
                        {
                            "items": [
                                {
                                    "type": "organic",
                                    "rank_group": 1,
                                    "rank_absolute": 1,
                                    "domain": "sealingai.com",
                                    "url": "https://sealingai.com/wissen/wellendichtring",
                                    "title": "Wellendichtring",
                                    "description": "Technische Orientierung.",
                                }
                            ]
                        }
                    ],
                }
            ],
        }


def test_extract_serp_items_reads_organic_results():
    payload = FakeSerpClient().serp_google_organic_live_advanced(
        keywords=["wellendichtring"],
        location_code=2276,
        language_code="de",
        depth=10,
    )

    rows = extract_serp_items(payload)

    assert rows[0]["keyword"] == "wellendichtring"
    assert rows[0]["domain"] == "sealingai.com"
    assert rows[0]["rank_absolute"] == 1


def test_serp_snapshot_persists_target_domain_hits(tmp_path):
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")

    result = run_serp_snapshot(
        conn,
        client=FakeSerpClient(),
        keywords=["wellendichtring"],
        location_code=2276,
        language_code="de",
        planned_cost_usd=0.01,
        max_run_cost_usd=0.10,
        target_domains=["sealingai.com"],
        depth=10,
        dry_run=False,
    )

    assert result["target_hits"] == 1
    row = conn.execute("SELECT * FROM dataforseo_serp_results").fetchone()
    assert row["is_target_domain"] == 1
    assert row["url"] == "https://sealingai.com/wissen/wellendichtring"
