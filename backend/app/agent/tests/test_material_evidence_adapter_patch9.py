from __future__ import annotations

from app.agent.domain.compatibility_precheck import (
    build_material_medium_compatibility_precheck,
)
from app.agent.domain.material_evidence_adapter import (
    build_material_evidence_card_candidate,
    dry_run_material_evidence_candidates,
    validate_material_evidence_candidate,
)


def _paperless_item(**extra: object) -> dict[str, object]:
    item: dict[str, object] = {
        "source_system": "paperless",
        "source_id": "42",
        "route": "material_datasheet",
        "source_title": "FKM water orientation sheet",
        "source_url": "paperless://documents/42",
        "material": "FKM",
        "medium": "water",
        "temperature_min_c": 0,
        "temperature_max_c": 100,
        "text": "Evidence-backed precheck context for FKM and water.",
    }
    item.update(extra)
    return item


def test_material_datasheet_candidate_validates() -> None:
    result = validate_material_evidence_candidate(_paperless_item())

    assert result.status == "valid"
    assert result.validation_result is not None
    assert result.validation_result.support_allowed is True
    assert result.card_candidate is not None
    assert result.card_candidate["source_type"] == "paperless_material_datasheet"
    assert result.card_candidate["final_approval_claim_allowed"] is False


def test_missing_source_metadata_invalid() -> None:
    result = validate_material_evidence_candidate(
        _paperless_item(source_title="", source_url="", source_hash="", source_id="")
    )

    assert result.status == "invalid"
    assert "source_title" in result.missing_fields
    assert "source_metadata" in result.missing_fields


def test_unsupported_claim_level_rejected_by_validator() -> None:
    result = validate_material_evidence_candidate(_paperless_item(claim_level="L4"))

    assert result.status == "invalid"
    assert result.validation_result is not None
    assert "invalid_claim_level" in result.validation_result.reasons


def test_tags_alone_do_not_create_strong_exact_claim() -> None:
    result = validate_material_evidence_candidate(
        {
            "source_system": "paperless",
            "source_id": "tags-only",
            "route": "technical_knowledge",
            "source_title": "Tag-only record",
            "source_url": "paperless://documents/tags-only",
            "tags": ["FKM", "oil"],
        }
    )

    assert result.status == "downgraded"
    assert result.validation_result is not None
    assert result.validation_result.support_allowed is False
    assert result.card_candidate is not None
    assert result.card_candidate.get("material") in (None, "")
    assert "tags_only_context" in result.limitations


def test_unsafe_approval_wording_downgraded_or_rejected() -> None:
    result = validate_material_evidence_candidate(
        _paperless_item(text="FKM ist freigegeben, approved und suitable.")
    )

    assert result.status == "downgraded"
    assert result.validation_result is not None
    assert result.validation_result.support_allowed is False
    assert any("overclaim_wording" in item for item in result.limitations)


def test_generic_medium_results_in_family_or_ambiguous() -> None:
    result = validate_material_evidence_candidate(
        _paperless_item(
            medium="oil", text="Evidence-backed precheck context for FKM and oil."
        )
    )

    assert result.status == "downgraded"
    assert result.validation_result is not None
    normalized = result.validation_result.normalized_card
    assert normalized is not None
    assert normalized["medium"] is None
    assert normalized["medium_family"] == "oelhaltig"
    assert "exact_medium_specification_missing" in result.limitations


def test_acid_base_without_concentration_limitation() -> None:
    result = validate_material_evidence_candidate(
        _paperless_item(
            material="EPDM",
            medium="Natronlauge",
            text="Evidence-backed precheck context for EPDM and sodium hydroxide.",
        )
    )

    assert result.status == "downgraded"
    assert "missing_concentration" in result.limitations
    assert result.validation_result is not None
    assert result.validation_result.support_allowed is False


def test_paperless_provenance_preserved() -> None:
    result = validate_material_evidence_candidate(
        _paperless_item(source_id="paperless-123")
    )

    assert result.source_reference == "paperless:paperless-123"
    assert result.card_candidate is not None
    assert result.card_candidate["source_reference"] == "paperless:paperless-123"
    assert result.card_candidate["source_id"] == "paperless-123"


def test_dry_run_report_counts_valid_invalid_downgraded() -> None:
    report = dry_run_material_evidence_candidates(
        [
            _paperless_item(source_id="valid"),
            _paperless_item(source_id="downgraded", medium="oil"),
            _paperless_item(
                source_id="", source_title="", source_url="", source_hash=""
            ),
        ]
    )

    assert report.total == 3
    assert report.valid_count == 1
    assert report.downgraded_count == 1
    assert report.invalid_count == 1
    assert report.grouped_missing_fields["source_title"] == 1
    assert report.grouped_limitations["exact_medium_specification_missing"] == 1


def test_adapter_output_can_feed_compatibility_precheck() -> None:
    result = validate_material_evidence_candidate(_paperless_item())
    assert result.card_candidate is not None

    item = build_material_medium_compatibility_precheck(
        {
            "medium": "water",
            "material": "FKM",
            "temperature_c": 60,
            "compatibility_evidence_cards": [result.card_candidate],
        }
    )

    assert item.status == "supported_precheck"
    assert item.evidence_status == "evidence_found"
    assert item.evidence_refs
    assert item.final_approval_claim_allowed is False


def test_invalid_adapter_output_not_consumed_by_precheck() -> None:
    result = validate_material_evidence_candidate(
        _paperless_item(source_id="", source_title="", source_url="", source_hash="")
    )
    assert result.card_candidate is not None

    item = build_material_medium_compatibility_precheck(
        {
            "medium": "water",
            "material": "FKM",
            "temperature_c": 60,
            "compatibility_evidence_cards": [result.card_candidate],
        }
    )

    assert result.status == "invalid"
    assert item.status == "insufficient_evidence"
    assert item.evidence_status == "no_evidence"
    assert item.evidence_refs == []


def test_qdrant_payload_shape_builds_candidate_without_side_effects() -> None:
    candidate = build_material_evidence_card_candidate(
        {
            "text": "Evidence-backed precheck context for FKM and water.",
            "metadata": {
                "source_system": "paperless",
                "source_document_id": "99",
                "document_id": "rag-doc-99",
                "chunk_hash": "sha256:chunk-99",
                "route_key": "material_datasheet",
                "title": "Paperless material sheet",
                "source_url": "paperless://documents/99",
                "material_code": "FKM",
                "tags": ["medium:water"],
                "temp_range": {"min_c": 0, "max_c": 80},
            },
        }
    )

    assert candidate["source_reference"] == "paperless:99"
    assert candidate["material"] == "FKM"
    assert candidate["medium"] == "water"
    assert candidate["temperature_max_c"] == 80
