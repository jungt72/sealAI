"""Stable v0.8.3 ArtifactType registry.

This module is a side-effect-free backend domain registry. It recognizes the
v0.8.3 artifact taxonomy and conservative legacy aliases without creating new
artifact workflows, persistence rules, or UI behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.case_type import CaseType


class ArtifactType(str, Enum):
    rfq_preview = "rfq_preview"
    manufacturer_fit_matrix = "manufacturer_fit_matrix"
    technical_inquiry_summary = "technical_inquiry_summary"
    compatibility_matrix = "compatibility_matrix"
    complaint_intake = "complaint_intake"
    failure_analysis_intake = "failure_analysis_intake"
    replacement_sheet = "replacement_sheet"
    legacy_part_intake = "legacy_part_intake"
    drawing_review = "drawing_review"
    quote_comparison = "quote_comparison"
    compliance_checklist = "compliance_checklist"
    material_substitution_brief = "material_substitution_brief"
    emergency_triage = "emergency_triage"
    customer_reply_draft = "customer_reply_draft"
    internal_engineering_note = "internal_engineering_note"
    unknown = "unknown"


class ArtifactImplementedStatus(str, Enum):
    implemented = "implemented"
    recognized_not_implemented = "recognized_not_implemented"
    unknown = "unknown"


@dataclass(frozen=True, slots=True)
class ArtifactTypeMetadata:
    artifact_type: ArtifactType
    label: str
    implemented_status: ArtifactImplementedStatus
    consent_required_default: bool
    exportable_default: bool
    supported_case_types: tuple[CaseType, ...]
    allowed_in_v083: bool

    @property
    def generated_or_available(self) -> bool:
        return self.implemented_status is ArtifactImplementedStatus.implemented


@dataclass(frozen=True, slots=True)
class ArtifactTypeRegistryView:
    """Code-level projection facts for S-ARTIFACT-TYPE-001."""

    artifact_type: ArtifactType
    metadata: ArtifactTypeMetadata
    artifact_type_registered: bool
    artifact_type_recognized: bool
    artifact_type_rejected: bool
    artifact_type_mapped_from_legacy_artifact: bool
    source_value: str | None

    @property
    def event_name(self) -> str:
        if self.artifact_type_rejected:
            return "ArtifactTypeRejected"
        if self.artifact_type_mapped_from_legacy_artifact:
            return "ArtifactTypeMappedFromLegacyArtifact"
        if self.artifact_type_recognized:
            return "ArtifactTypeRecognized"
        return "ArtifactTypeRegistered"

    @property
    def event_names(self) -> tuple[str, ...]:
        events: list[str] = []
        if self.artifact_type_registered:
            events.append("ArtifactTypeRegistered")
        if self.artifact_type_recognized:
            events.append("ArtifactTypeRecognized")
        if self.artifact_type_mapped_from_legacy_artifact:
            events.append("ArtifactTypeMappedFromLegacyArtifact")
        if self.artifact_type_rejected:
            events.append("ArtifactTypeRejected")
        return tuple(events)


_REGISTRY: dict[ArtifactType, ArtifactTypeMetadata] = {
    ArtifactType.rfq_preview: ArtifactTypeMetadata(
        artifact_type=ArtifactType.rfq_preview,
        label="RFQ Preview",
        implemented_status=ArtifactImplementedStatus.implemented,
        consent_required_default=True,
        exportable_default=True,
        supported_case_types=(CaseType.new_rfq,),
        allowed_in_v083=True,
    ),
    ArtifactType.manufacturer_fit_matrix: ArtifactTypeMetadata(
        artifact_type=ArtifactType.manufacturer_fit_matrix,
        label="Manufacturer Fit Matrix",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.manufacturer_matching,),
        allowed_in_v083=True,
    ),
    ArtifactType.technical_inquiry_summary: ArtifactTypeMetadata(
        artifact_type=ArtifactType.technical_inquiry_summary,
        label="Technical Inquiry Summary",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(
            CaseType.new_rfq,
            CaseType.compatibility_inquiry,
            CaseType.manufacturer_support_intake,
        ),
        allowed_in_v083=True,
    ),
    ArtifactType.compatibility_matrix: ArtifactTypeMetadata(
        artifact_type=ArtifactType.compatibility_matrix,
        label="Compatibility Matrix",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.compatibility_inquiry,),
        allowed_in_v083=True,
    ),
    ArtifactType.complaint_intake: ArtifactTypeMetadata(
        artifact_type=ArtifactType.complaint_intake,
        label="Complaint Intake",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.complaint_case,),
        allowed_in_v083=True,
    ),
    ArtifactType.failure_analysis_intake: ArtifactTypeMetadata(
        artifact_type=ArtifactType.failure_analysis_intake,
        label="Failure Analysis Intake",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.failure_analysis,),
        allowed_in_v083=True,
    ),
    ArtifactType.replacement_sheet: ArtifactTypeMetadata(
        artifact_type=ArtifactType.replacement_sheet,
        label="Replacement Sheet",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.replacement_reorder,),
        allowed_in_v083=True,
    ),
    ArtifactType.legacy_part_intake: ArtifactTypeMetadata(
        artifact_type=ArtifactType.legacy_part_intake,
        label="Legacy Part Intake",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.unknown_legacy_part,),
        allowed_in_v083=True,
    ),
    ArtifactType.drawing_review: ArtifactTypeMetadata(
        artifact_type=ArtifactType.drawing_review,
        label="Drawing Review",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.drawing_review,),
        allowed_in_v083=True,
    ),
    ArtifactType.quote_comparison: ArtifactTypeMetadata(
        artifact_type=ArtifactType.quote_comparison,
        label="Quote Comparison",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.quote_comparison,),
        allowed_in_v083=True,
    ),
    ArtifactType.compliance_checklist: ArtifactTypeMetadata(
        artifact_type=ArtifactType.compliance_checklist,
        label="Compliance Checklist",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.compliance_certificate_request,),
        allowed_in_v083=True,
    ),
    ArtifactType.material_substitution_brief: ArtifactTypeMetadata(
        artifact_type=ArtifactType.material_substitution_brief,
        label="Material Substitution Brief",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.material_substitution,),
        allowed_in_v083=True,
    ),
    ArtifactType.emergency_triage: ArtifactTypeMetadata(
        artifact_type=ArtifactType.emergency_triage,
        label="Emergency Triage",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(CaseType.emergency_mro,),
        allowed_in_v083=True,
    ),
    ArtifactType.customer_reply_draft: ArtifactTypeMetadata(
        artifact_type=ArtifactType.customer_reply_draft,
        label="Customer Reply Draft",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=True,
        exportable_default=False,
        supported_case_types=(
            CaseType.compatibility_inquiry,
            CaseType.complaint_case,
            CaseType.failure_analysis,
            CaseType.manufacturer_support_intake,
        ),
        allowed_in_v083=True,
    ),
    ArtifactType.internal_engineering_note: ArtifactTypeMetadata(
        artifact_type=ArtifactType.internal_engineering_note,
        label="Internal Engineering Note",
        implemented_status=ArtifactImplementedStatus.recognized_not_implemented,
        consent_required_default=False,
        exportable_default=False,
        supported_case_types=(
            CaseType.new_rfq,
            CaseType.compatibility_inquiry,
            CaseType.complaint_case,
            CaseType.failure_analysis,
            CaseType.manufacturer_support_intake,
        ),
        allowed_in_v083=True,
    ),
    ArtifactType.unknown: ArtifactTypeMetadata(
        artifact_type=ArtifactType.unknown,
        label="Unknown Artifact",
        implemented_status=ArtifactImplementedStatus.unknown,
        consent_required_default=False,
        exportable_default=False,
        supported_case_types=(),
        allowed_in_v083=False,
    ),
}

_LEGACY_ARTIFACT_TYPE_MAP: dict[str, ArtifactType] = {
    "rfq_preview": ArtifactType.rfq_preview,
    "manufacturer_inquiry": ArtifactType.technical_inquiry_summary,
    "technical_summary": ArtifactType.technical_inquiry_summary,
}


def normalize_artifact_type(value: ArtifactType | str | None) -> ArtifactType:
    if isinstance(value, ArtifactType):
        return value
    normalized = _normalize(value)
    if not normalized:
        return ArtifactType.unknown
    if normalized in _LEGACY_ARTIFACT_TYPE_MAP:
        return _LEGACY_ARTIFACT_TYPE_MAP[normalized]
    try:
        return ArtifactType(normalized)
    except ValueError:
        return ArtifactType.unknown


def is_known_artifact_type(value: ArtifactType | str | None) -> bool:
    return normalize_artifact_type(value) is not ArtifactType.unknown


def artifact_type_metadata(
    value: ArtifactType | str | None,
) -> ArtifactTypeMetadata:
    return _REGISTRY[normalize_artifact_type(value)]


def is_artifact_type_implemented(value: ArtifactType | str | None) -> bool:
    return (
        artifact_type_metadata(value).implemented_status
        is ArtifactImplementedStatus.implemented
    )


def artifact_registry_view(value: ArtifactType | str | None) -> ArtifactTypeRegistryView:
    artifact_type = normalize_artifact_type(value)
    source_value = None if value is None else str(getattr(value, "value", value))
    source_key = _normalize(value)
    mapped_from_legacy = (
        bool(source_key)
        and source_key in _LEGACY_ARTIFACT_TYPE_MAP
        and source_key != artifact_type.value
    )
    rejected = artifact_type is ArtifactType.unknown and source_key not in {
        "",
        ArtifactType.unknown.value,
    }
    return ArtifactTypeRegistryView(
        artifact_type=artifact_type,
        metadata=artifact_type_metadata(artifact_type),
        artifact_type_registered=artifact_type is not ArtifactType.unknown,
        artifact_type_recognized=artifact_type is not ArtifactType.unknown,
        artifact_type_rejected=rejected,
        artifact_type_mapped_from_legacy_artifact=mapped_from_legacy,
        source_value=source_value,
    )


def all_artifact_type_metadata() -> tuple[ArtifactTypeMetadata, ...]:
    return tuple(_REGISTRY[artifact_type] for artifact_type in ArtifactType)


def _normalize(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().casefold()
