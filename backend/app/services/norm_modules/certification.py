from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class CertificationEvidence:
    standard: str
    source_reference: str | None = None
    issuer: str | None = None
    valid: bool | None = None
    declaration_present: bool = False
    traceability_present: bool = False
    migration_test_available: bool = False
    negative: bool = False


@dataclass(frozen=True, slots=True)
class ComplianceEvidenceSummary:
    matching_records: tuple[CertificationEvidence, ...]
    has_positive_evidence: bool
    has_negative_evidence: bool
    has_traceability: bool
    has_migration_test: bool
    has_manufacturer_declaration: bool

    @property
    def has_minimal_food_contact_evidence(self) -> bool:
        return (
            self.has_positive_evidence
            and self.has_traceability
            and self.has_manufacturer_declaration
        )


def normalize_certification_records(context: Mapping[str, Any]) -> tuple[CertificationEvidence, ...]:
    raw_records = context.get("certification_records")
    if raw_records is None:
        raw_records = context.get("compliance_evidence")

    if raw_records is None:
        records: list[Any] = []
    elif isinstance(raw_records, Mapping):
        records = [raw_records]
    elif isinstance(raw_records, str):
        records = [{"standard": raw_records, "valid": True}]
    elif isinstance(raw_records, Iterable):
        records = list(raw_records)
    else:
        records = []

    normalized: list[CertificationEvidence] = []
    for record in records:
        if isinstance(record, CertificationEvidence):
            normalized.append(record)
            continue
        if isinstance(record, str):
            normalized.append(CertificationEvidence(standard=record, valid=True))
            continue
        if not isinstance(record, Mapping):
            continue

        standard = str(
            record.get("standard")
            or record.get("norm")
            or record.get("certification")
            or record.get("code")
            or ""
        ).strip()
        if not standard:
            continue

        normalized.append(
            CertificationEvidence(
                standard=standard,
                source_reference=_optional_str(record.get("source_reference") or record.get("source_ref")),
                issuer=_optional_str(record.get("issuer")),
                valid=_optional_bool(record.get("valid")),
                declaration_present=bool(
                    record.get("declaration_present")
                    or record.get("manufacturer_declaration_present")
                ),
                traceability_present=bool(record.get("traceability_present")),
                migration_test_available=bool(
                    record.get("migration_test_available")
                    or record.get("migration_test_present")
                ),
                negative=bool(record.get("negative") or record.get("explicitly_not_certified")),
            )
        )

    return tuple(normalized)


def summarize_certification_evidence(
    context: Mapping[str, Any],
    accepted_standards: Iterable[str],
) -> ComplianceEvidenceSummary:
    accepted_tokens = {_normalize_token(value) for value in accepted_standards}
    records = normalize_certification_records(context)
    matching = tuple(
        record
        for record in records
        if any(token in _normalize_token(record.standard) for token in accepted_tokens)
    )

    declaration_present = bool(context.get("manufacturer_declaration_present")) or any(
        record.declaration_present for record in matching
    )
    traceability_present = bool(context.get("traceability_present")) or any(
        record.traceability_present for record in matching
    )
    migration_test_available = bool(context.get("migration_test_available")) or any(
        record.migration_test_available for record in matching
    )
    negative = bool(context.get("food_contact_certification_negative")) or bool(
        context.get("explicitly_not_food_contact_certified")
    ) or any(record.negative or record.valid is False for record in matching)
    positive = any(record.valid is not False and not record.negative for record in matching)

    return ComplianceEvidenceSummary(
        matching_records=matching,
        has_positive_evidence=positive,
        has_negative_evidence=negative,
        has_traceability=traceability_present,
        has_migration_test=migration_test_available,
        has_manufacturer_declaration=declaration_present,
    )


def context_text_indicates_food_contact(context: Mapping[str, Any]) -> bool:
    if context.get("food_contact_required") is True:
        return True
    values = (
        context.get("application_domain"),
        context.get("application_category"),
        context.get("medium_name"),
        context.get("medium_class"),
        context.get("industry"),
    )
    text = " ".join(str(value).lower() for value in values if value is not None)
    return any(
        token in text
        for token in (
            "food",
            "lebensmittel",
            "beverage",
            "dairy",
            "milk",
            "chocolate",
            "pharma",
            "food_contact",
        )
    )


def region_matches(context: Mapping[str, Any], accepted_regions: set[str]) -> bool:
    values = (
        context.get("food_contact_region"),
        context.get("jurisdiction"),
        context.get("market_region"),
    )
    for value in values:
        normalized = str(value or "").strip().lower()
        if not normalized or normalized in {"none", "no", "false"}:
            continue
        if normalized in accepted_regions or normalized == "both":
            return True
    return False


def _normalize_token(value: str) -> str:
    return (
        str(value or "")
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("/", "")
        .replace(".", "")
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "valid"}:
            return True
        if lowered in {"false", "no", "0", "invalid"}:
            return False
    return bool(value)
