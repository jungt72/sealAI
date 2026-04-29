"""Stable v0.8.3 SourceType / ValidationStatus primitives.

This module is deterministic and side-effect free. It derives projection
metadata only; it does not change persistence authority or confirm case truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class SourceType(str, Enum):
    rag_verified = "rag_verified"
    partner_verified = "partner_verified"
    manufacturer_documented = "manufacturer_documented"
    uploaded_evidence = "uploaded_evidence"
    user_stated = "user_stated"
    deterministic_calculation = "deterministic_calculation"
    llm_research_fallback = "llm_research_fallback"
    inferred = "inferred"
    system_derived = "system_derived"
    unknown = "unknown"


class ValidationStatus(str, Enum):
    validated = "validated"
    documented = "documented"
    self_declared = "self_declared"
    user_stated = "user_stated"
    candidate = "candidate"
    unvalidated = "unvalidated"
    conflicting = "conflicting"
    rejected = "rejected"
    calculated = "calculated"
    unknown = "unknown"


@dataclass(frozen=True, slots=True)
class SourceValidationMetadata:
    """Code-level projection facts for S-SOURCE-VALIDATION-001."""

    source_type: SourceType
    validation_status: ValidationStatus
    source_type_derived: bool = True
    validation_status_derived: bool = True
    authoritative: bool = False
    not_for_release_decisions: bool = True

    @property
    def event_names(self) -> tuple[str, ...]:
        events = [
            "SourceValidationStatusAssigned",
            "SourceTypeDerived",
            "ValidationStatusDerived",
        ]
        if is_unvalidated_source(self.source_type, self.validation_status):
            events.append("UnvalidatedSourcePreserved")
        if self.validation_status is ValidationStatus.candidate:
            events.append("CandidateSourcePreserved")
        if self.validation_status is ValidationStatus.conflicting:
            events.append("ConflictValidationPreserved")
        return tuple(events)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type.value,
            "validation_status": self.validation_status.value,
            "authoritative": self.authoritative,
            "not_for_release_decisions": self.not_for_release_decisions,
            "event_names": self.event_names,
        }


_SOURCE_ALIASES: dict[str, SourceType] = {
    "rag": SourceType.rag_verified,
    "rag_hit": SourceType.rag_verified,
    "rag_verified": SourceType.rag_verified,
    "curated_knowledge": SourceType.rag_verified,
    "factcard": SourceType.rag_verified,
    "fact_card": SourceType.rag_verified,
    "partner": SourceType.partner_verified,
    "partner_verified": SourceType.partner_verified,
    "manufacturer": SourceType.manufacturer_documented,
    "manufacturer_documented": SourceType.manufacturer_documented,
    "manufacturer_doc": SourceType.manufacturer_documented,
    "document": SourceType.uploaded_evidence,
    "documented": SourceType.uploaded_evidence,
    "evidence": SourceType.uploaded_evidence,
    "upload": SourceType.uploaded_evidence,
    "uploaded": SourceType.uploaded_evidence,
    "uploaded_evidence": SourceType.uploaded_evidence,
    "user": SourceType.user_stated,
    "user_override": SourceType.user_stated,
    "user_stated": SourceType.user_stated,
    "calculated": SourceType.deterministic_calculation,
    "calculation": SourceType.deterministic_calculation,
    "deterministic": SourceType.deterministic_calculation,
    "deterministic_calculation": SourceType.deterministic_calculation,
    "llm_research_fallback": SourceType.llm_research_fallback,
    "llm_fallback": SourceType.llm_research_fallback,
    "fallback": SourceType.llm_research_fallback,
    "inferred": SourceType.inferred,
    "pattern_derived": SourceType.inferred,
    "system": SourceType.system_derived,
    "system_derived": SourceType.system_derived,
    "deterministic_text_inference": SourceType.system_derived,
    "unknown": SourceType.unknown,
}

_VALIDATION_ALIASES: dict[str, ValidationStatus] = {
    "validated": ValidationStatus.validated,
    "confirmed": ValidationStatus.validated,
    "documented": ValidationStatus.documented,
    "self_declared": ValidationStatus.self_declared,
    "self-declared": ValidationStatus.self_declared,
    "user_stated": ValidationStatus.user_stated,
    "user_confirmed": ValidationStatus.user_stated,
    "candidate": ValidationStatus.candidate,
    "needs_confirmation": ValidationStatus.candidate,
    "requires_confirmation": ValidationStatus.candidate,
    "inferred": ValidationStatus.candidate,
    "unvalidated": ValidationStatus.unvalidated,
    "not_validated": ValidationStatus.unvalidated,
    "llm_research_fallback": ValidationStatus.unvalidated,
    "conflict": ValidationStatus.conflicting,
    "conflicting": ValidationStatus.conflicting,
    "rejected": ValidationStatus.rejected,
    "invalid": ValidationStatus.rejected,
    "calculated": ValidationStatus.calculated,
    "missing": ValidationStatus.unknown,
    "unknown": ValidationStatus.unknown,
    "unspecified": ValidationStatus.unknown,
}


def normalize_source_type(value: str | SourceType | None) -> SourceType:
    if isinstance(value, SourceType):
        return value
    normalized = _normalize_token(value)
    if not normalized:
        return SourceType.unknown
    if normalized.startswith("upload:") or normalized.startswith("document:"):
        return SourceType.uploaded_evidence
    if normalized.startswith("rag:") or normalized.startswith("source::"):
        return SourceType.rag_verified
    return _SOURCE_ALIASES.get(normalized, SourceType.unknown)


def normalize_validation_status(
    value: str | ValidationStatus | None,
) -> ValidationStatus:
    if isinstance(value, ValidationStatus):
        return value
    normalized = _normalize_token(value)
    if not normalized:
        return ValidationStatus.unknown
    return _VALIDATION_ALIASES.get(normalized, ValidationStatus.unknown)


def source_type_from_field_status(
    status: Any,
    provenance: Any = None,
    origin: Any = None,
) -> SourceType:
    for candidate in (_extract_mapping_value(provenance), origin, provenance):
        source_type = normalize_source_type(_string_or_none(candidate))
        if source_type is not SourceType.unknown:
            return source_type

    status_token = _normalize_token(status)
    if status_token in {"calculated", "derived"}:
        return SourceType.deterministic_calculation
    if status_token in {"inferred", "candidate"}:
        return SourceType.inferred
    if status_token in {"user_stated", "user_confirmed"}:
        return SourceType.user_stated
    if status_token == "documented":
        return SourceType.uploaded_evidence
    return SourceType.unknown


def validation_status_from_field_status(
    status: Any,
    *,
    conflict: bool = False,
    rejected: bool = False,
) -> ValidationStatus:
    if rejected:
        return ValidationStatus.rejected
    if conflict:
        return ValidationStatus.conflicting

    validation_status = normalize_validation_status(_string_or_none(status))
    if validation_status is not ValidationStatus.unknown:
        return validation_status

    status_token = _normalize_token(status)
    if status_token in {"open", "stale"}:
        return ValidationStatus.candidate
    return ValidationStatus.unknown


def is_authoritative_validation_status(
    status: str | ValidationStatus | None,
    *,
    include_documented: bool = False,
    allow_self_declared: bool = False,
) -> bool:
    normalized = normalize_validation_status(status)
    if normalized in {ValidationStatus.validated, ValidationStatus.calculated}:
        return True
    if include_documented and normalized is ValidationStatus.documented:
        return True
    if allow_self_declared and normalized is ValidationStatus.self_declared:
        return True
    return False


def is_unvalidated_source(
    source_type: str | SourceType | None,
    validation_status: str | ValidationStatus | None,
) -> bool:
    return normalize_source_type(source_type) is SourceType.llm_research_fallback or (
        normalize_validation_status(validation_status) is ValidationStatus.unvalidated
    )


def source_validation_metadata(
    *,
    status: Any = None,
    provenance: Any = None,
    origin: Any = None,
    source_type: str | SourceType | None = None,
    validation_status: str | ValidationStatus | None = None,
    conflict: bool = False,
    rejected: bool = False,
) -> SourceValidationMetadata:
    normalized_source = normalize_source_type(source_type)
    if normalized_source is SourceType.unknown:
        normalized_source = source_type_from_field_status(
            status, provenance=provenance, origin=origin
        )

    normalized_validation = normalize_validation_status(validation_status)
    if normalized_validation is ValidationStatus.unknown:
        normalized_validation = validation_status_from_field_status(
            status,
            conflict=conflict,
            rejected=rejected,
        )

    normalized_source, normalized_validation = _apply_source_validation_guards(
        normalized_source,
        normalized_validation,
    )
    authoritative = is_authoritative_validation_status(normalized_validation)
    return SourceValidationMetadata(
        source_type=normalized_source,
        validation_status=normalized_validation,
        authoritative=authoritative,
        not_for_release_decisions=not authoritative,
    )


def _apply_source_validation_guards(
    source_type: SourceType,
    validation_status: ValidationStatus,
) -> tuple[SourceType, ValidationStatus]:
    if source_type is SourceType.llm_research_fallback:
        return source_type, ValidationStatus.unvalidated
    if source_type is SourceType.uploaded_evidence and (
        validation_status is ValidationStatus.validated
    ):
        return source_type, ValidationStatus.documented
    if source_type is SourceType.partner_verified and (
        validation_status is ValidationStatus.validated
    ):
        return source_type, ValidationStatus.documented
    if source_type is SourceType.deterministic_calculation and validation_status in {
        ValidationStatus.validated,
        ValidationStatus.documented,
        ValidationStatus.unknown,
    }:
        return source_type, ValidationStatus.calculated
    return source_type, validation_status


def _extract_mapping_value(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return None
    for key in ("source_type", "source", "origin", "source_kind", "provenance"):
        candidate = value.get(key)
        if candidate not in (None, ""):
            return candidate
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _normalize_token(value: Any) -> str:
    text = _string_or_none(value)
    if not text:
        return ""
    return (
        text.strip()
        .casefold()
        .replace("-", "_")
        .replace(" ", "_")
        .replace(".", "_")
    )
