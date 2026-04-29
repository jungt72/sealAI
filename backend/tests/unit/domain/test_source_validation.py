from __future__ import annotations

import json

import pytest

from app.domain.source_validation import (
    SourceType,
    ValidationStatus,
    is_authoritative_validation_status,
    is_unvalidated_source,
    normalize_source_type,
    normalize_validation_status,
    source_type_from_field_status,
    source_validation_metadata,
    validation_status_from_field_status,
)


def test_source_type_contains_stable_v083_values() -> None:
    expected = {
        "rag_verified",
        "partner_verified",
        "manufacturer_documented",
        "uploaded_evidence",
        "user_stated",
        "deterministic_calculation",
        "llm_research_fallback",
        "inferred",
        "system_derived",
        "unknown",
    }

    assert {member.value for member in SourceType} == expected


def test_validation_status_contains_stable_v083_values() -> None:
    expected = {
        "validated",
        "documented",
        "self_declared",
        "user_stated",
        "candidate",
        "unvalidated",
        "conflicting",
        "rejected",
        "calculated",
        "unknown",
    }

    assert {member.value for member in ValidationStatus} == expected


def test_source_and_validation_status_serialize_as_strings() -> None:
    payload = {
        "source_type": SourceType.user_stated,
        "validation_status": ValidationStatus.candidate,
    }

    assert isinstance(SourceType.user_stated, str)
    assert isinstance(ValidationStatus.candidate, str)
    assert json.loads(json.dumps(payload)) == {
        "source_type": "user_stated",
        "validation_status": "candidate",
    }


def test_unknown_strings_normalize_to_unknown() -> None:
    assert normalize_source_type("surprising_vendor_note") is SourceType.unknown
    assert (
        normalize_validation_status("surprising_validation")
        is ValidationStatus.unknown
    )


@pytest.mark.parametrize(
    "status, provenance, expected_source, expected_validation",
    [
        (
            "user_stated",
            "user_stated",
            SourceType.user_stated,
            ValidationStatus.user_stated,
        ),
        (
            "documented",
            "documented",
            SourceType.uploaded_evidence,
            ValidationStatus.documented,
        ),
        ("inferred", "inferred", SourceType.inferred, ValidationStatus.candidate),
        (
            "calculated",
            "calculated",
            SourceType.deterministic_calculation,
            ValidationStatus.calculated,
        ),
        (
            "confirmed",
            "calculated",
            SourceType.deterministic_calculation,
            ValidationStatus.calculated,
        ),
        (
            "conflict",
            "user_stated",
            SourceType.user_stated,
            ValidationStatus.conflicting,
        ),
        ("missing", "missing", SourceType.unknown, ValidationStatus.unknown),
    ],
)
def test_field_statuses_map_to_conservative_source_and_validation(
    status: str,
    provenance: str,
    expected_source: SourceType,
    expected_validation: ValidationStatus,
) -> None:
    metadata = source_validation_metadata(status=status, provenance=provenance)

    assert metadata.source_type is expected_source
    assert metadata.validation_status is expected_validation


def test_documented_maps_to_documented_not_validated() -> None:
    metadata = source_validation_metadata(
        status="documented",
        provenance="upload:datasheet-1",
    )

    assert metadata.source_type is SourceType.uploaded_evidence
    assert metadata.validation_status is ValidationStatus.documented
    assert metadata.validation_status is not ValidationStatus.validated


def test_llm_research_fallback_is_unvalidated_and_not_authoritative() -> None:
    metadata = source_validation_metadata(
        source_type="llm_research_fallback",
        validation_status="validated",
    )

    assert metadata.source_type is SourceType.llm_research_fallback
    assert metadata.validation_status is ValidationStatus.unvalidated
    assert metadata.authoritative is False
    assert is_unvalidated_source(metadata.source_type, metadata.validation_status)
    assert "UnvalidatedSourcePreserved" in metadata.event_names


def test_uploaded_evidence_candidate_is_not_authoritative() -> None:
    metadata = source_validation_metadata(
        source_type="uploaded_evidence",
        validation_status="candidate",
    )

    assert metadata.source_type is SourceType.uploaded_evidence
    assert metadata.validation_status is ValidationStatus.candidate
    assert metadata.authoritative is False
    assert "CandidateSourcePreserved" in metadata.event_names


def test_conflicting_validation_is_preserved() -> None:
    metadata = source_validation_metadata(status="confirmed", conflict=True)

    assert metadata.validation_status is ValidationStatus.conflicting
    assert metadata.authoritative is False
    assert "ConflictValidationPreserved" in metadata.event_names


def test_rag_verified_can_be_validated_or_documented_by_contract() -> None:
    validated = source_validation_metadata(
        source_type="rag_verified",
        validation_status="validated",
    )
    documented = source_validation_metadata(
        source_type="rag_verified",
        validation_status="documented",
    )

    assert validated.source_type is SourceType.rag_verified
    assert validated.validation_status is ValidationStatus.validated
    assert validated.authoritative is True
    assert documented.source_type is SourceType.rag_verified
    assert documented.validation_status is ValidationStatus.documented
    assert documented.authoritative is False


def test_self_declared_is_not_authoritative_unless_explicitly_allowed() -> None:
    assert is_authoritative_validation_status("self_declared") is False
    assert (
        is_authoritative_validation_status(
            "self_declared",
            allow_self_declared=True,
        )
        is True
    )


def test_low_level_mapping_helpers_are_deterministic() -> None:
    assert (
        source_type_from_field_status("candidate", provenance="user")
        is SourceType.user_stated
    )
    assert (
        validation_status_from_field_status("rejected")
        is ValidationStatus.rejected
    )
