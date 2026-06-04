"""Dry-run adapter from Paperless/RAG metadata to material evidence cards.

The functions in this module are pure: they accept exported dictionaries from
RAG/Paperless-like sources and return candidate cards plus validation results.
They do not read or write Paperless, Qdrant, or the application database.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from app.agent.domain.material_evidence_cards import (
    MaterialEvidenceCardValidationResult,
    validate_material_evidence_card,
)


AdapterStatus = Literal["valid", "invalid", "downgraded", "skipped"]


@dataclass(frozen=True)
class AdapterResult:
    status: AdapterStatus
    card_candidate: dict[str, Any] | None
    validation_result: MaterialEvidenceCardValidationResult | None
    missing_fields: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    source_reference: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "card_candidate": self.card_candidate,
            "validation": _validation_to_dict(self.validation_result),
            "missing_fields": list(self.missing_fields),
            "limitations": list(self.limitations),
            "source_reference": self.source_reference,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DryRunReport:
    total: int
    valid_count: int
    invalid_count: int
    downgraded_count: int
    skipped_count: int
    results: list[AdapterResult]
    grouped_missing_fields: dict[str, int] = field(default_factory=dict)
    grouped_limitations: dict[str, int] = field(default_factory=dict)
    safety_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "downgraded_count": self.downgraded_count,
            "skipped_count": self.skipped_count,
            "grouped_missing_fields": dict(self.grouped_missing_fields),
            "grouped_limitations": dict(self.grouped_limitations),
            "safety_warnings": list(self.safety_warnings),
            "results": [result.to_dict() for result in self.results],
        }


_MATERIAL_PATTERN = re.compile(
    r"\b(FKM|FPM|VITON|NBR|HNBR|EPDM|PTFE|FVMQ|VMQ|PEEK|UHMW[- ]?PE|PE[- ]?UHMW)\b",
    re.IGNORECASE,
)
_MEDIUM_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(water|wasser)\b", re.IGNORECASE), "water"),
    (
        re.compile(
            r"\b(HLP|HVLP|HEES|HETG|HEPG|HFDU|HFAE|HFC)(?:\s*[-/]?\s*\d{1,3})?\b",
            re.IGNORECASE,
        ),
        "HLP",
    ),
    (
        re.compile(
            r"\b(oil|oel|mineraloel|hydraulic oil|hydraulikoel)\b", re.IGNORECASE
        ),
        "oil",
    ),
    (
        re.compile(r"\b(natronlauge|naoh|sodium hydroxide)\b", re.IGNORECASE),
        "Natronlauge",
    ),
    (
        re.compile(r"\b(salzsaeure|hcl|hydrochloric acid)\b", re.IGNORECASE),
        "Salzsaeure",
    ),
    (re.compile(r"\b(reiniger|cleaner|cleaning agent)\b", re.IGNORECASE), "cleaner"),
)
_GENERIC_MEDIUM_KEYS = {"oil", "oel", "reiniger", "cleaner", "chemical", "chemikalie"}
_AGGRESSIVE_MEDIUM_KEYS = {
    "natronlauge",
    "naoh",
    "sodium hydroxide",
    "salzsaeure",
    "hcl",
    "hydrochloric acid",
    "reiniger",
    "cleaner",
}
_COMPLIANCE_TERMS = (
    "fda",
    "atex",
    "food",
    "trinkwasser",
    "pharma",
    "drinking water",
)
_CERTIFICATE_KEYS = (
    "certificate_id",
    "source_url",
    "doi",
    "manufacturer",
    "source_hash",
)
_SOURCE_ANCHOR_KEYS = ("source_url", "doi", "manufacturer", "source_hash")
_VALID_CLAIM_LEVELS = {"L1", "L2", "L3"}


def build_material_evidence_card_candidate(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Build a conservative Patch-8 card candidate from Paperless/RAG-like data."""

    metadata = _mapping(raw.get("metadata"))
    additional = _mapping(raw.get("additional_metadata")) or _mapping(
        metadata.get("additional_metadata")
    )
    tags = _tags(raw, metadata)
    route = _first_text(
        raw, metadata, keys=("route", "route_key", "metadata.route_key")
    )
    source_system = (
        _first_text(raw, metadata, keys=("source_system", "metadata.source_system"))
        or "rag"
    )
    source_id = _first_text(
        raw,
        metadata,
        keys=(
            "source_id",
            "source_document_id",
            "document_id",
            "evidence_ref",
            "chunk_id",
            "metadata.source_document_id",
            "metadata.document_id",
            "metadata.doc_id",
            "metadata.chunk_id",
        ),
    )
    source_reference = _source_reference(
        source_system=source_system, source_id=source_id
    )
    source_title = _first_text(
        raw,
        metadata,
        keys=(
            "source_title",
            "title",
            "filename",
            "metadata.title",
            "metadata.filename",
        ),
    )
    source_url = _first_text(
        raw,
        metadata,
        keys=("source_url", "url", "uri", "metadata.source_url", "source"),
    )
    source_hash = (
        _first_text(
            raw,
            metadata,
            keys=(
                "source_hash",
                "sha256",
                "chunk_hash",
                "metadata.chunk_hash",
                "metadata.source_version",
            ),
        )
        or source_reference
    )

    text = _first_text(
        raw,
        metadata,
        keys=(
            "statement_short",
            "excerpt_short",
            "excerpt",
            "chunk_text",
            "text",
            "content",
            "metadata.text",
        ),
    )
    material = _first_text(
        raw,
        metadata,
        additional,
        keys=(
            "material",
            "compound",
            "material_code",
            "metadata.material_code",
            "entity",
            "metadata.entity",
        ),
    ) or _extract_tag_value(tags, {"material", "compound", "material_code", "entity"})
    medium = _first_text(
        raw, metadata, additional, keys=("medium", "medium_name", "fluid")
    )
    medium = medium or _extract_tag_value(tags, {"medium", "medium_name", "fluid"})

    material_from_tags_only = not material and bool(
        _extract_known_material(_tag_text(tags))
    )
    medium_from_tags_only = not medium and bool(_extract_known_medium(_tag_text(tags)))
    if not material:
        material = _extract_known_material(_tag_text(tags)) or _extract_known_material(
            text
        )
    if not medium:
        medium = _extract_known_medium(_tag_text(tags)) or _extract_known_medium(text)

    material_family = _first_text(
        raw, metadata, additional, keys=("material_family", "metadata.material_family")
    )
    medium_family = _first_text(
        raw, metadata, additional, keys=("medium_family", "fluid_family")
    )
    limitations = _list_text(raw.get("limitations"))
    limitations.extend(_list_text(metadata.get("limitations")))

    if material and (
        material_from_tags_only
        or not _first_text(
            raw,
            metadata,
            additional,
            keys=(
                "material",
                "compound",
                "material_code",
                "metadata.material_code",
                "entity",
                "metadata.entity",
            ),
        )
    ):
        limitations.append("material_inferred_from_tags_or_text")
    if medium and (
        medium_from_tags_only
        or not _first_text(
            raw, metadata, additional, keys=("medium", "medium_name", "fluid")
        )
    ):
        limitations.append("medium_inferred_from_tags_or_text")

    medium_key = _normalized_key(medium)
    if medium_key in _GENERIC_MEDIUM_KEYS:
        limitations.append("exact_medium_specification_missing")
        medium_family = medium_family or medium
    if medium_key in _AGGRESSIVE_MEDIUM_KEYS and not _first_text(
        raw, metadata, additional, keys=("concentration", "concentration_percent")
    ):
        limitations.append("missing_concentration")

    text_for_claim = " ".join([text, _tag_text(tags), source_title])
    compliance_terms = _compliance_terms(text_for_claim)
    if compliance_terms:
        limitations.append("compliance_certificate_required")

    tags_only_context = bool(tags) and not text
    if tags_only_context:
        limitations.append("tags_only_context")
        material_family = material_family or material
        medium_family = medium_family or medium
        material = None
        medium = None

    claim_level = _claim_level(
        raw,
        route=route,
        exact=bool(material and medium and text),
        tags_only=tags_only_context,
    )
    claim_type = _claim_type(
        raw,
        route=route,
        text=text_for_claim,
        compliance_terms=compliance_terms,
        tags_only=tags_only_context,
    )

    statement = _statement_short(
        text,
        fallback=(
            "Paperless/RAG metadata-only context; exact compatibility evidence not established."
            if tags_only_context
            else "Paperless/RAG dry-run candidate; source evidence requires review."
        ),
    )
    source_type = _source_type(raw, route=route, source_system=source_system)
    candidate = {
        "schema_version": "material_evidence_card.v1",
        "card_id": _card_id(
            source_system=source_system,
            source_id=source_id,
            material=material or material_family,
            medium=medium or medium_family,
        ),
        "material": material,
        "material_family": material_family,
        "medium": medium,
        "medium_family": medium_family,
        "temperature_min_c": _first_number(
            raw,
            metadata,
            additional,
            keys=("temperature_min_c", "temp_min_c", "metadata.temp_range.min_c"),
        ),
        "temperature_max_c": _first_number(
            raw,
            metadata,
            additional,
            keys=("temperature_max_c", "temp_max_c", "metadata.temp_range.max_c"),
        ),
        "concentration": _first_text(
            raw, metadata, additional, keys=("concentration", "concentration_percent")
        ),
        "ph_min": _first_number(raw, metadata, additional, keys=("ph_min",)),
        "ph_max": _first_number(raw, metadata, additional, keys=("ph_max",)),
        "claim_level": claim_level,
        "claim_type": claim_type,
        "compatibility_status": "caution_zone"
        if tags_only_context
        or claim_type in {"caution", "limitation", "manufacturer_datasheet_reference"}
        else "supported_precheck",
        "statement_short": statement,
        "source_title": source_title,
        "source_type": source_type,
        "source_url": source_url,
        "doi": _first_text(raw, metadata, additional, keys=("doi",)),
        "manufacturer": _first_text(raw, metadata, additional, keys=("manufacturer",)),
        "evidence_date": _first_text(
            raw,
            metadata,
            additional,
            keys=("evidence_date", "source_modified_at", "metadata.source_modified_at"),
        ),
        "limitations": _dedupe(limitations),
        "final_approval_claim_allowed": False,
        "compliance_claim_allowed": _compliance_allowed(raw, claim_type=claim_type),
        "created_by_pipeline": "paperless_rag_material_evidence_adapter_dry_run",
        "source_hash": source_hash,
        "excerpt_short": _statement_short(text, fallback=statement),
        "confidence": raw.get("confidence"),
        "source_reference": source_reference,
        "source_system": source_system,
        "source_id": source_id,
        "route": route,
        "tags": tags,
    }
    return {key: value for key, value in candidate.items() if value not in (None, "")}


def validate_material_evidence_candidate(raw: Mapping[str, Any]) -> AdapterResult:
    """Build and validate one dry-run card candidate."""

    if not isinstance(raw, Mapping):
        return AdapterResult(
            status="skipped",
            card_candidate=None,
            validation_result=None,
            missing_fields=["item"],
            reason="item_not_mapping",
        )

    candidate = build_material_evidence_card_candidate(raw)
    source_reference = _text(candidate.get("source_reference")) or None
    missing_fields = _candidate_missing_fields(candidate)
    if (
        not candidate.get("material")
        and not candidate.get("material_family")
        and not candidate.get("medium")
        and not candidate.get("medium_family")
    ):
        return AdapterResult(
            status="skipped",
            card_candidate=candidate,
            validation_result=None,
            missing_fields=_dedupe([*missing_fields, "material_or_medium"]),
            limitations=_list_text(candidate.get("limitations")),
            source_reference=source_reference,
            reason="no_material_or_medium_signal",
        )

    validation = validate_material_evidence_card(candidate)
    status = _adapter_status(validation)
    missing_fields = _dedupe(
        [*missing_fields, *_missing_fields_from_validation(validation)]
    )
    limitations = _dedupe(
        [
            *_list_text(candidate.get("limitations")),
            *validation.limitations,
            *validation.blocked_claims,
        ]
    )
    reason = _reason(
        status=status,
        validation=validation,
        missing_fields=missing_fields,
        limitations=limitations,
    )
    return AdapterResult(
        status=status,
        card_candidate=candidate,
        validation_result=validation,
        missing_fields=missing_fields,
        limitations=limitations,
        source_reference=source_reference,
        reason=reason,
    )


def dry_run_material_evidence_candidates(
    items: list[Mapping[str, Any]],
) -> DryRunReport:
    """Validate a batch of Paperless/RAG-like items without side effects."""

    results = [validate_material_evidence_candidate(item) for item in items]
    status_counts = Counter(result.status for result in results)
    missing_counts: Counter[str] = Counter()
    limitation_counts: Counter[str] = Counter()
    safety_warnings: list[str] = []
    for result in results:
        missing_counts.update(result.missing_fields)
        limitation_counts.update(result.limitations)
        if any(
            "overclaim_wording" in value or "blocked_claim" in value
            for value in result.limitations
        ):
            safety_warnings.append(
                result.source_reference or result.reason or "unsafe_candidate"
            )
    return DryRunReport(
        total=len(items),
        valid_count=status_counts["valid"],
        invalid_count=status_counts["invalid"],
        downgraded_count=status_counts["downgraded"],
        skipped_count=status_counts["skipped"],
        results=results,
        grouped_missing_fields=dict(sorted(missing_counts.items())),
        grouped_limitations=dict(sorted(limitation_counts.items())),
        safety_warnings=_dedupe(safety_warnings),
    )


def _adapter_status(validation: MaterialEvidenceCardValidationResult) -> AdapterStatus:
    if not validation.valid:
        if validation.status == "downgraded":
            return "downgraded"
        return "invalid"
    if validation.support_allowed and validation.status == "valid":
        return "valid"
    return "downgraded"


def _candidate_missing_fields(candidate: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    if not _text(candidate.get("source_title")):
        missing.append("source_title")
    if not any(_text(candidate.get(key)) for key in _SOURCE_ANCHOR_KEYS):
        missing.append("source_anchor")
    if not _text(candidate.get("material")) and not _text(
        candidate.get("material_family")
    ):
        missing.append("material")
    if not _text(candidate.get("medium")) and not _text(candidate.get("medium_family")):
        missing.append("medium")
    if not _text(candidate.get("statement_short")):
        missing.append("statement_short")
    return missing


def _missing_fields_from_validation(
    validation: MaterialEvidenceCardValidationResult,
) -> list[str]:
    mapping = {
        "missing_card_id": "card_id",
        "unsupported_schema_version": "schema_version",
        "invalid_claim_level": "claim_level",
        "invalid_claim_type": "claim_type",
        "missing_source_type": "source_type",
        "missing_source_metadata": "source_metadata",
        "missing_limitations": "limitations",
        "missing_material_or_family": "material",
        "missing_medium_or_family": "medium",
        "missing_statement_short": "statement_short",
    }
    return [mapping[reason] for reason in validation.reasons if reason in mapping]


def _reason(
    *,
    status: AdapterStatus,
    validation: MaterialEvidenceCardValidationResult,
    missing_fields: list[str],
    limitations: list[str],
) -> str:
    if status == "valid":
        return "candidate_passed_precheck_validation"
    if validation.status == "downgraded":
        return "candidate_downgraded_by_safety_gate"
    if missing_fields:
        return "missing:" + ",".join(missing_fields)
    if limitations:
        return "limited:" + ",".join(limitations[:3])
    return validation.status


def _validation_to_dict(
    validation: MaterialEvidenceCardValidationResult | None,
) -> dict[str, Any] | None:
    if validation is None:
        return None
    return {
        "card_id": validation.card_id,
        "valid": validation.valid,
        "status": validation.status,
        "reasons": list(validation.reasons),
        "limitations": list(validation.limitations),
        "blocked_claims": list(validation.blocked_claims),
        "support_allowed": validation.support_allowed,
        "compliance_claim_allowed": validation.compliance_claim_allowed,
        "normalized_card": validation.normalized_card,
    }


def _source_type(raw: Mapping[str, Any], *, route: str, source_system: str) -> str:
    explicit = _text(raw.get("source_type"))
    if explicit:
        return explicit
    route_key = route.casefold()
    if route_key == "material_datasheet":
        return (
            "paperless_material_datasheet"
            if source_system.casefold() == "paperless"
            else "material_datasheet"
        )
    if route_key == "technical_knowledge":
        return (
            "paperless_technical_knowledge"
            if source_system.casefold() == "paperless"
            else "technical_knowledge"
        )
    if source_system.casefold() == "paperless":
        return "paperless_rag_evidence"
    return "rag_evidence"


def _claim_level(
    raw: Mapping[str, Any], *, route: str, exact: bool, tags_only: bool
) -> str:
    explicit = _text(raw.get("claim_level")).upper()
    if explicit:
        return explicit
    if tags_only:
        return "L1"
    if route.casefold() == "material_datasheet" and exact:
        return "L2"
    if route.casefold() == "technical_knowledge" and exact:
        return "L2"
    return "L1"


def _claim_type(
    raw: Mapping[str, Any],
    *,
    route: str,
    text: str,
    compliance_terms: list[str],
    tags_only: bool,
) -> str:
    explicit = _text(raw.get("claim_type")).casefold()
    if explicit:
        return explicit
    normalized = _normalized_text(text)
    if compliance_terms:
        has_certificate = _compliance_allowed(raw, claim_type="compliance_certificate")
        return "compliance_certificate" if has_certificate else "limitation"
    if tags_only:
        return "limitation"
    if any(
        marker in normalized
        for marker in ("warn", "limit", "caution", "review", "pruef", "avoid")
    ):
        return "caution"
    if route.casefold() == "material_datasheet":
        return "compatibility_precheck"
    return "compatibility_observation"


def _compliance_allowed(raw: Mapping[str, Any], *, claim_type: str) -> bool:
    if claim_type != "compliance_certificate" or not bool(
        raw.get("compliance_claim_allowed")
    ):
        return False
    return any(_text(raw.get(key)) for key in _CERTIFICATE_KEYS)


def _statement_short(text: str, *, fallback: str) -> str:
    value = re.sub(r"\s+", " ", _text(text)).strip()
    if not value:
        return fallback
    sentence_match = re.match(r"(.{1,240}?)(?:[.!?](?:\s|$)|$)", value)
    statement = (
        sentence_match.group(1).strip() if sentence_match else value[:240].strip()
    )
    return statement[:240].strip() or fallback


def _extract_known_material(value: str) -> str:
    match = _MATERIAL_PATTERN.search(_normalized_text(value).upper())
    if not match:
        return ""
    material = match.group(1).upper().replace(" ", "-")
    if material in {"FPM", "VITON"}:
        return material.title() if material == "VITON" else material
    if material in {"UHMWPE", "UHMW-PE", "PE-UHMW"}:
        return "UHMW-PE"
    return material


def _extract_known_medium(value: str) -> str:
    normalized = _normalized_text(value)
    for pattern, label in _MEDIUM_PATTERNS:
        if pattern.search(normalized):
            return label
    return ""


def _extract_tag_value(tags: list[str], keys: set[str]) -> str:
    for tag in tags:
        if ":" not in tag:
            continue
        key, value = tag.split(":", 1)
        if _normalized_key(key) in keys:
            return _text(value)
    return ""


def _compliance_terms(value: str) -> list[str]:
    normalized = _normalized_text(value)
    return [term for term in _COMPLIANCE_TERMS if term in normalized]


def _card_id(
    *, source_system: str, source_id: str, material: str | None, medium: str | None
) -> str:
    parts = [
        source_system or "rag",
        source_id or "unknown-source",
        material or "unknown-material",
        medium or "unknown-medium",
    ]
    slug = "-".join(_slug(part) for part in parts if _slug(part))
    return f"material-evidence-{slug}"[:120]


def _source_reference(*, source_system: str, source_id: str) -> str:
    if source_system and source_id:
        return f"{source_system}:{source_id}"
    return source_id or source_system or ""


def _tags(*items: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for item in items:
        values.extend(_list_text(item.get("tags")))
        values.extend(_list_text(item.get("metadata.tags")))
    return _dedupe(values)


def _tag_text(tags: list[str]) -> str:
    return " ".join(tags)


def _first_text(*items: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        for item in items:
            value = _nested_value(item, key)
            text = _text(value)
            if text:
                return text
    return ""


def _first_number(*items: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        for item in items:
            value = _nested_value(item, key)
            number = _number(value)
            if number is not None:
                return number
    return None


def _nested_value(item: Mapping[str, Any], key: str) -> Any:
    if key in item:
        return item.get(key)
    current: Any = item
    for part in key.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value).replace(",", ".")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _list_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_text(value)] if _text(value) else []
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalized_key(value)).strip("-")


def _normalized_key(value: Any) -> str:
    text = _normalized_text(_text(value))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalized_text(value: Any) -> str:
    text = _text(value).casefold()
    replacements = {
        "\u00e4": "ae",
        "\u00f6": "oe",
        "\u00fc": "ue",
        "\u00df": "ss",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"\s+", " ", text.replace("-", " ")).strip()


__all__ = [
    "AdapterResult",
    "AdapterStatus",
    "DryRunReport",
    "build_material_evidence_card_candidate",
    "dry_run_material_evidence_candidates",
    "validate_material_evidence_candidate",
]
