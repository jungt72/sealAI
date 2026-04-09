from __future__ import annotations

from app.agent.rag.paperless_tags import (
    PAPERLESS_PILOT_TAGS,
    evaluate_paperless_tag_readiness,
    parse_paperless_tags,
)


def test_parse_paperless_tags_extracts_w26_target_metadata() -> None:
    parsed = parse_paperless_tags(PAPERLESS_PILOT_TAGS)

    assert parsed["doc_type"] == "datasheet"
    assert parsed["language"] == "de"
    assert parsed["source"] == "hersteller-name"
    assert parsed["sts_mat_codes"] == ["STS-MAT-SIC-A1"]
    assert parsed["sts_type_codes"] == ["STS-TYPE-GS-CART"]


def test_evaluate_paperless_tag_readiness_marks_pilot_ready() -> None:
    readiness = evaluate_paperless_tag_readiness(PAPERLESS_PILOT_TAGS)

    assert readiness["ingest_ready"] is True
    assert readiness["pilot_ready"] is True
    assert readiness["missing_pilot_fields"] == []


def test_evaluate_paperless_tag_readiness_reports_missing_pilot_fields() -> None:
    readiness = evaluate_paperless_tag_readiness(
        [
            "doc_type:datasheet",
            "sts_mat:STS-MAT-SIC-A1",
        ]
    )

    assert readiness["ingest_ready"] is True
    assert readiness["pilot_ready"] is False
    assert readiness["missing_pilot_fields"] == ["sts_type", "lang", "source"]
