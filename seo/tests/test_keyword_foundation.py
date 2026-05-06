from pathlib import Path

from sealai_seo import db
from sealai_seo.keyword_foundation import extract_search_volume_items, keyword_foundation_rows, upsert_keyword_metrics, upsert_seed_keywords


def test_extract_search_volume_items() -> None:
    payload = {
        "tasks": [
            {
                "result": [
                    {"keyword": "fkm dichtung", "search_volume": 1000},
                    {"not_keyword": "skip"},
                ]
            }
        ]
    }

    assert extract_search_volume_items(payload) == [{"keyword": "fkm dichtung", "search_volume": 1000}]


def test_keyword_foundation_rows_scores_seed_and_metrics(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "seo.db")
    db.apply_migrations(conn, Path(__file__).parents[1] / "migrations")
    upsert_seed_keywords(
        conn,
        [
            {
                "keyword": "fkm dichtung",
                "cluster": "Materials",
                "intent": "Material orientation",
                "page_type": "Material page",
                "v8_positioning": "material suitability requires manufacturer review",
                "rfq_relevance": "high",
                "priority": "100",
            }
        ],
    )
    upsert_keyword_metrics(
        conn,
        items=[
            {
                "keyword": "fkm dichtung",
                "search_volume": 1000,
                "cpc": 1.5,
                "competition": 0.2,
                "competition_index": 20,
                "monthly_searches": [],
            }
        ],
        location_code=2276,
        language_code="de",
        run_id="run",
        task_id="task",
    )

    rows = keyword_foundation_rows(conn, location_code=2276, language_code="de")

    assert rows[0]["keyword"] == "fkm dichtung"
    assert rows[0]["search_volume"] == 1000
    assert rows[0]["opportunity_score"] > 100
