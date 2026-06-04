from __future__ import annotations

from app.agent.rag.paperless_tags import (
    PAPERLESS_PILOT_TAGS,
    augment_paperless_tags_for_rag,
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
    assert parsed["rag_enabled"] is True


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

    assert readiness["rag_enabled"] is False
    assert readiness["ingest_ready"] is False
    assert readiness["pilot_ready"] is False
    assert readiness["missing_pilot_fields"] == ["sts_type", "lang", "source"]


def test_evaluate_paperless_tag_readiness_requires_explicit_rag_flag() -> None:
    without_flag = evaluate_paperless_tag_readiness(
        [
            "doc_type:datasheet",
            "sts_mat:STS-MAT-SIC-A1",
            "sts_type:STS-TYPE-GS-CART",
            "lang:de",
            "source:hersteller-name",
        ]
    )
    with_flag = evaluate_paperless_tag_readiness(
        [
            "sealai:rag",
            "doc_type:datasheet",
            "sts_mat:STS-MAT-SIC-A1",
            "sts_type:STS-TYPE-GS-CART",
            "lang:de",
            "source:hersteller-name",
        ]
    )

    assert without_flag["ingest_ready"] is False
    assert without_flag["pilot_ready"] is False
    assert with_flag["ingest_ready"] is True
    assert with_flag["pilot_ready"] is True


def test_augment_paperless_tags_infers_nbr_deep_research_metadata() -> None:
    tags = augment_paperless_tags_for_rag(
        ["sealai:rag"],
        title="NBR Deep Research",
        filename="deep-research-report.md",
    )

    assert "sealai:rag" in tags
    assert "doc_type:technical_knowledge" in tags
    assert "route:technical_knowledge" in tags
    assert "sts_mat:STS-MAT-NBR-A1" in tags

    readiness = evaluate_paperless_tag_readiness(tags)
    assert readiness["ingest_ready"] is True
    assert readiness["pilot_ready"] is False


def test_augment_paperless_tags_keeps_rag_flag_mandatory() -> None:
    tags = augment_paperless_tags_for_rag(
        [],
        title="NBR Deep Research",
        filename="deep-research-report.md",
    )

    assert tags == []
    assert evaluate_paperless_tag_readiness(tags)["ingest_ready"] is False


def test_augment_paperless_tags_does_not_confuse_hnbr_with_nbr() -> None:
    tags = augment_paperless_tags_for_rag(
        ["rag:enabled"],
        title="HNBR Datenblatt",
        filename="hnbr-datasheet.pdf",
    )

    assert "sts_mat:STS-MAT-HNBR-A1" in tags
    assert "sts_mat:STS-MAT-NBR-A1" not in tags
    assert "doc_type:datasheet" in tags
    assert "route:material_datasheet" in tags
