from __future__ import annotations

import inspect

from app.services.norm_modules.certification import (
    CertificationEvidence,
    context_text_indicates_food_contact,
    normalize_certification_records,
    region_matches,
    summarize_certification_evidence,
)


def test_normalize_certification_records_accepts_dict_record() -> None:
    records = normalize_certification_records(
        {
            "certification_records": {
                "standard": "EU 10/2011",
                "source_reference": "cert-1",
                "valid": True,
                "manufacturer_declaration_present": True,
                "traceability_present": True,
                "migration_test_available": True,
            }
        }
    )
    assert records == (
        CertificationEvidence(
            standard="EU 10/2011",
            source_reference="cert-1",
            valid=True,
            declaration_present=True,
            traceability_present=True,
            migration_test_available=True,
        ),
    )


def test_normalize_certification_records_accepts_string_record() -> None:
    records = normalize_certification_records({"certification_records": ["FDA 21 CFR 177.1550"]})
    assert records[0].standard == "FDA 21 CFR 177.1550"
    assert records[0].valid is True


def test_normalize_certification_records_ignores_invalid_entries() -> None:
    records = normalize_certification_records({"certification_records": [None, 123, {"issuer": "x"}]})
    assert records == ()


def test_summarize_certification_evidence_positive_complete() -> None:
    summary = summarize_certification_evidence(
        {
            "certification_records": [
                {
                    "standard": "EU 1935/2004",
                    "valid": True,
                    "declaration_present": True,
                    "traceability_present": True,
                    "migration_test_available": True,
                }
            ]
        },
        ["EU 1935/2004"],
    )
    assert summary.has_minimal_food_contact_evidence is True
    assert summary.has_migration_test is True


def test_summarize_certification_evidence_detects_negative_context_flag() -> None:
    summary = summarize_certification_evidence(
        {
            "food_contact_certification_negative": True,
            "certification_records": [{"standard": "EU 10/2011", "valid": True}],
        },
        ["EU 10/2011"],
    )
    assert summary.has_negative_evidence is True


def test_summarize_certification_evidence_matches_normalized_standard_tokens() -> None:
    summary = summarize_certification_evidence(
        {"certification_records": [{"standard": "FDA_21_CFR_177_1550", "valid": True}]},
        ["FDA 21 CFR 177.1550"],
    )
    assert len(summary.matching_records) == 1
    assert summary.has_positive_evidence is True


def test_context_text_indicates_food_contact_from_domain_and_medium() -> None:
    assert context_text_indicates_food_contact({"application_domain": "food processing"}) is True
    assert context_text_indicates_food_contact({"medium_name": "milk"}) is True
    assert context_text_indicates_food_contact({"application_category": "chemical"}) is False


def test_region_matches_handles_both_and_none() -> None:
    assert region_matches({"food_contact_region": "both"}, {"eu"}) is True
    assert region_matches({"market_region": "USA"}, {"usa"}) is True
    assert region_matches({"food_contact_region": "none"}, {"eu"}) is False


def test_shared_helpers_do_not_import_forbidden_runtime_layers() -> None:
    import app.services.norm_modules.certification as certification

    source = inspect.getsource(certification)
    assert "app.agent" not in source
    assert "langgraph" not in source.lower()
    assert "fastapi" not in source.lower()
