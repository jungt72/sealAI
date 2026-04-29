from __future__ import annotations

import json

import pytest

from app.domain.artifact_type import (
    ArtifactImplementedStatus,
    ArtifactType,
    all_artifact_type_metadata,
    artifact_registry_view,
    artifact_type_metadata,
    is_artifact_type_implemented,
    is_known_artifact_type,
    normalize_artifact_type,
)
from app.services.rfq_preview_service import RFQ_PREVIEW_ARTIFACT_TYPE


def test_artifact_type_contains_stable_v083_values() -> None:
    expected = {
        "rfq_preview",
        "manufacturer_fit_matrix",
        "technical_inquiry_summary",
        "compatibility_matrix",
        "complaint_intake",
        "failure_analysis_intake",
        "replacement_sheet",
        "legacy_part_intake",
        "drawing_review",
        "quote_comparison",
        "compliance_checklist",
        "material_substitution_brief",
        "emergency_triage",
        "customer_reply_draft",
        "internal_engineering_note",
        "unknown",
    }

    assert {member.value for member in ArtifactType} == expected
    assert {item.artifact_type for item in all_artifact_type_metadata()} == set(ArtifactType)


def test_artifact_type_serializes_as_string() -> None:
    payload = {"artifact_type": ArtifactType.rfq_preview}

    assert isinstance(ArtifactType.rfq_preview, str)
    assert json.loads(json.dumps(payload)) == {"artifact_type": "rfq_preview"}


def test_rfq_preview_is_the_only_implemented_artifact_type() -> None:
    assert artifact_type_metadata(ArtifactType.rfq_preview).implemented_status is (
        ArtifactImplementedStatus.implemented
    )
    assert is_artifact_type_implemented("rfq_preview") is True

    implemented = {
        item.artifact_type
        for item in all_artifact_type_metadata()
        if item.implemented_status is ArtifactImplementedStatus.implemented
    }
    assert implemented == {ArtifactType.rfq_preview}


@pytest.mark.parametrize(
    "artifact_type",
    [
        ArtifactType.manufacturer_fit_matrix,
        ArtifactType.compatibility_matrix,
        ArtifactType.complaint_intake,
        ArtifactType.failure_analysis_intake,
        ArtifactType.customer_reply_draft,
        ArtifactType.internal_engineering_note,
    ],
)
def test_required_future_artifacts_are_recognized_not_implemented(
    artifact_type: ArtifactType,
) -> None:
    metadata = artifact_type_metadata(artifact_type)

    assert metadata.implemented_status is (
        ArtifactImplementedStatus.recognized_not_implemented
    )
    assert metadata.allowed_in_v083 is True
    assert metadata.generated_or_available is False
    assert is_artifact_type_implemented(artifact_type) is False


def test_unknown_string_maps_to_unknown_and_is_rejected_fact() -> None:
    view = artifact_registry_view("dispatch_payload")

    assert normalize_artifact_type("dispatch_payload") is ArtifactType.unknown
    assert is_known_artifact_type("dispatch_payload") is False
    assert view.artifact_type is ArtifactType.unknown
    assert view.artifact_type_rejected is True
    assert view.event_name == "ArtifactTypeRejected"


@pytest.mark.parametrize(
    "legacy_value",
    ["technical_summary", "manufacturer_inquiry"],
)
def test_legacy_summary_artifacts_map_conservatively(
    legacy_value: str,
) -> None:
    view = artifact_registry_view(legacy_value)

    assert normalize_artifact_type(legacy_value) is ArtifactType.technical_inquiry_summary
    assert view.artifact_type_mapped_from_legacy_artifact is True
    assert view.event_name == "ArtifactTypeMappedFromLegacyArtifact"
    assert is_artifact_type_implemented(legacy_value) is False


def test_unknown_artifacts_are_not_exportable_by_default() -> None:
    metadata = artifact_type_metadata("anything_new")

    assert metadata.artifact_type is ArtifactType.unknown
    assert metadata.implemented_status is ArtifactImplementedStatus.unknown
    assert metadata.exportable_default is False
    assert metadata.consent_required_default is False
    assert metadata.generated_or_available is False


@pytest.mark.parametrize(
    "artifact_type",
    [
        ArtifactType.manufacturer_fit_matrix,
        ArtifactType.technical_inquiry_summary,
        ArtifactType.compatibility_matrix,
        ArtifactType.complaint_intake,
        ArtifactType.failure_analysis_intake,
        ArtifactType.replacement_sheet,
        ArtifactType.legacy_part_intake,
        ArtifactType.drawing_review,
        ArtifactType.quote_comparison,
        ArtifactType.compliance_checklist,
        ArtifactType.material_substitution_brief,
        ArtifactType.emergency_triage,
        ArtifactType.customer_reply_draft,
        ArtifactType.internal_engineering_note,
    ],
)
def test_recognized_not_implemented_artifacts_are_not_generated_or_available(
    artifact_type: ArtifactType,
) -> None:
    metadata = artifact_type_metadata(artifact_type)

    assert is_known_artifact_type(artifact_type) is True
    assert metadata.implemented_status is (
        ArtifactImplementedStatus.recognized_not_implemented
    )
    assert metadata.exportable_default is False
    assert metadata.generated_or_available is False


def test_rfq_preview_remains_compatible_with_existing_rfq_service_constant() -> None:
    metadata = artifact_type_metadata(RFQ_PREVIEW_ARTIFACT_TYPE)
    view = artifact_registry_view(RFQ_PREVIEW_ARTIFACT_TYPE)

    assert RFQ_PREVIEW_ARTIFACT_TYPE == "rfq_preview"
    assert metadata.artifact_type is ArtifactType.rfq_preview
    assert metadata.exportable_default is True
    assert metadata.consent_required_default is True
    assert view.artifact_type_recognized is True
    assert view.event_name == "ArtifactTypeRecognized"
    assert view.event_names == (
        "ArtifactTypeRegistered",
        "ArtifactTypeRecognized",
    )


def test_registry_view_exposes_registered_recognized_and_rejected_facts() -> None:
    registered = artifact_registry_view(ArtifactType.compatibility_matrix)
    rejected = artifact_registry_view("not_a_v083_artifact")

    assert registered.event_names == (
        "ArtifactTypeRegistered",
        "ArtifactTypeRecognized",
    )
    assert rejected.event_names == ("ArtifactTypeRejected",)
