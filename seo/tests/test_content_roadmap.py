from pathlib import Path

from sealai_seo import db
from sealai_seo.content_roadmap import roadmap_rows
from sealai_seo.keyword_foundation import upsert_keyword_metrics, upsert_seed_keywords


def test_content_roadmap_includes_existing_and_new_routes(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "seo.db")
    db.apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    upsert_seed_keywords(
        conn,
        [
            {
                "keyword": "wellendichtring",
                "cluster": "Radial shaft seals",
                "intent": "Identify component",
                "page_type": "Knowledge page",
                "v8_positioning": "technical orientation not final design approval",
                "rfq_relevance": "high",
                "priority": "96",
            }
        ],
    )
    upsert_keyword_metrics(
        conn,
        items=[{"keyword": "wellendichtring", "search_volume": 5400, "cpc": 1.37, "competition_index": 91}],
        location_code=2276,
        language_code="de",
        run_id="run",
        task_id="task",
    )

    rows = roadmap_rows(conn, location_code=2276, language_code="de")

    assert rows[0]["path"] == "/wissen/wellendichtring"
    assert any(row["route_status"] == "new_route_required" for row in rows)
    assert any("Hersteller" in row["meta_description"] or "Hersteller" in row["h1"] for row in rows)
