from typing import List, Optional, Dict, Any, Tuple
import re
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from app.agent.domain.datasheet_contract import (
    AuditContract,
    DataExtractionMethod,
    DataOriginType,
    DatasheetContractV23,
    DocumentBindingStrength,
    DocumentClass,
    DocumentCollisionStatus,
    DocumentIdentity,
    DocumentMetadata,
    EvidenceStrengthClass,
    HumanReviewStatus,
    TestSpecimenSource,
)
from app.agent.domain.parameters import PhysicalParameter
from app.agent.domain.limits import OperatingLimit


_MATERIAL_PATTERN = re.compile(r"\b(NBR|PTFE|FKM|EPDM|SILIKON)\b", re.I)
_GRADE_PATTERN = re.compile(r"\b(?:grade|compound|typ|type)\s*[:\-]?\s*([a-z0-9._-]+)\b", re.I)
_FILLER_PATTERN = re.compile(r"\b(filled|glass[- ]filled|carbon[- ]filled|bronze[- ]filled)\b", re.I)
_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
_KB_SOURCE_PATH = Path(__file__).resolve().parents[2] / "data" / "kb" / "SEALAI_KB_PTFE_factcards_gates_v1_3.json"
_SOURCE_CATALOG_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_MANUFACTURER_DOCUMENT_TYPES = {
    "manufacturer_datasheet",
    "manufacturer_technical_brochure",
    "manufacturer_brochure",
    "manufacturer_guide",
}


def _read_metadata_str(metadata: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _read_metadata_float(metadata: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            continue
    return None


def _load_source_catalog() -> Dict[str, Dict[str, Any]]:
    global _SOURCE_CATALOG_CACHE
    if _SOURCE_CATALOG_CACHE is not None:
        return _SOURCE_CATALOG_CACHE
    try:
        data = json.loads(_KB_SOURCE_PATH.read_text(encoding="utf-8"))
        catalog = data.get("sources") or {}
        if isinstance(catalog, dict):
            _SOURCE_CATALOG_CACHE = catalog
        else:
            _SOURCE_CATALOG_CACHE = {}
    except Exception:
        _SOURCE_CATALOG_CACHE = {}
    return _SOURCE_CATALOG_CACHE


def _source_entry(card_dict: dict) -> Dict[str, Any]:
    metadata = card_dict.get("metadata") or {}
    source_key = card_dict.get("source") or metadata.get("source")
    catalog_entry = {}
    if source_key:
        catalog_entry = _load_source_catalog().get(str(source_key), {}) or {}

    entry = dict(catalog_entry)
    for key in (
        "source",
        "source_type",
        "source_rank",
        "title",
        "url",
        "edition",
        "revision_date",
        "published_at",
        "edition_year",
        "document_revision",
        "manufacturer_name",
        "product_line",
        "grade_name",
        "material_family",
        "evidence_scope",
        "scope_of_validity",
    ):
        if card_dict.get(key) not in (None, ""):
            entry[key] = card_dict.get(key)
    for meta_key, target_key in (
        ("source", "source"),
        ("source_type", "source_type"),
        ("source_rank", "source_rank"),
        ("title", "title"),
        ("url", "url"),
        ("edition", "edition"),
        ("revision_date", "revision_date"),
        ("published_at", "published_at"),
        ("edition_year", "edition_year"),
        ("document_revision", "document_revision"),
        ("source_version", "document_revision"),
        ("effective_date", "published_at"),
        ("manufacturer_name", "manufacturer_name"),
        ("manufacturer", "manufacturer_name"),
        ("product_line", "product_line"),
        ("grade_name", "grade_name"),
        ("grade", "grade_name"),
        ("material_family", "material_family"),
        ("material", "material_family"),
        ("evidence_scope", "evidence_scope"),
        ("scope_of_validity", "scope_of_validity"),
    ):
        if metadata.get(meta_key) not in (None, "") and entry.get(target_key) in (None, ""):
            entry[target_key] = metadata.get(meta_key)
    return entry


def _document_metadata(card_dict: dict) -> Dict[str, Any]:
    entry = _source_entry(card_dict)
    metadata = card_dict.get("metadata") or {}
    source_rank = entry.get("source_rank", entry.get("rank"))
    try:
        source_rank = int(source_rank) if source_rank is not None else None
    except (TypeError, ValueError):
        source_rank = None

    source_type = entry.get("source_type") or entry.get("type")
    source_ref = card_dict.get("source_ref") or card_dict.get("source")
    scope_of_validity = entry.get("scope_of_validity")
    if isinstance(scope_of_validity, str):
        scope_of_validity = [scope_of_validity]
    evidence_scope = entry.get("evidence_scope")
    if isinstance(evidence_scope, str):
        evidence_scope = [evidence_scope]

    return {
        "source_ref": source_ref,
        "source_type": source_type,
        "source_rank": source_rank,
        "title": entry.get("title"),
        "url": entry.get("url"),
        "revision_date": entry.get("revision_date"),
        "published_at": entry.get("published_at"),
        "edition_year": entry.get("edition_year"),
        "document_revision": entry.get("document_revision"),
        "manufacturer_name": entry.get("manufacturer_name") or _read_metadata_str(metadata, "manufacturer_name", "manufacturer", "brand"),
        "product_line": entry.get("product_line") or _read_metadata_str(metadata, "product_line", "product_series", "trade_name", "entity"),
        "grade_name": entry.get("grade_name") or _read_metadata_str(metadata, "grade_name", "grade", "compound_code", "compound"),
        "material_family": entry.get("material_family") or _read_metadata_str(metadata, "material_family", "material", "family"),
        "evidence_scope": evidence_scope or [],
        "scope_of_validity": scope_of_validity or [],
    }


def _document_metadata_quality(card_dict: dict) -> Dict[str, Any]:
    doc_meta = _document_metadata(card_dict)
    candidate_kind = _candidate_kind(
        _extract_material_family(card_dict),
        _extract_filler_hint(card_dict),
        _extract_grade_name(card_dict),
        _extract_manufacturer_name(card_dict),
    )
    required = ["source_ref", "source_type", "source_rank"]
    if candidate_kind in {"grade", "manufacturer_grade"}:
        required.extend(["material_family", "grade_name"])
    if candidate_kind == "manufacturer_grade":
        required.append("manufacturer_name")
    if doc_meta.get("source_type") == "manufacturer_datasheet" and candidate_kind in {"grade", "manufacturer_grade"}:
        if not any(doc_meta.get(field) not in (None, "", []) for field in ("revision_date", "published_at", "edition_year", "document_revision")):
            required.append("revision_or_publication_metadata")
    missing = [
        field for field in required
        if field == "revision_or_publication_metadata"
        and not any(doc_meta.get(candidate) not in (None, "", []) for candidate in ("revision_date", "published_at", "edition_year", "document_revision"))
    ]
    missing.extend(
        field for field in required
        if field != "revision_or_publication_metadata" and doc_meta.get(field) in (None, "", [])
    )
    return {
        "quality": "complete" if not missing else "incomplete",
        "missing_fields": missing,
    }


def _map_document_class(source_type: Optional[str]) -> DocumentClass:
    mapping = {
        "manufacturer_grade_sheet": DocumentClass.manufacturer_grade_sheet,
        "manufacturer_datasheet": DocumentClass.manufacturer_datasheet,
        "distributor_sheet": DocumentClass.distributor_sheet,
        "certificate": DocumentClass.certificate,
        "standard_specification": DocumentClass.standard_specification,
        "standard_test_method": DocumentClass.standard_test_method,
    }
    return mapping.get(str(source_type or "").strip().lower(), DocumentClass.unknown)


def _map_data_origin_type(source_type: Optional[str]) -> DataOriginType:
    mapping = {
        "manufacturer_grade_sheet": DataOriginType.manufacturer_grade_sheet,
        "manufacturer_datasheet": DataOriginType.manufacturer_declared,
        "distributor_sheet": DataOriginType.distributor_sheet,
        "certificate": DataOriginType.certificate,
        "standard_specification": DataOriginType.standard_document,
        "standard_test_method": DataOriginType.standard_document,
    }
    return mapping.get(str(source_type or "").strip().lower(), DataOriginType.unknown)


def _read_data_origin_type(card_dict: dict, document_metadata: Dict[str, Any]) -> DataOriginType:
    metadata = card_dict.get("metadata") or {}
    explicit = str(metadata.get("data_origin_type") or card_dict.get("data_origin_type") or "").strip().lower()
    if explicit:
        try:
            return DataOriginType(explicit)
        except ValueError:
            pass
    return _map_data_origin_type(document_metadata.get("source_type"))


def _derive_document_binding_strength(card_dict: dict, document_metadata: Dict[str, Any]) -> DocumentBindingStrength:
    metadata = card_dict.get("metadata") or {}
    if any(metadata.get(key) not in (None, "") for key in ("revision_date", "published_at", "document_revision", "edition_year")):
        return DocumentBindingStrength.direct_document
    if card_dict.get("source") and document_metadata.get("source_ref"):
        return DocumentBindingStrength.source_registry_bound
    if (card_dict.get("evidence_id") or card_dict.get("id")) and document_metadata.get("source_ref"):
        return DocumentBindingStrength.fact_card_bound
    return DocumentBindingStrength.weak_reference


def _derive_data_extraction_method(card_dict: dict, identity_quality: Dict[str, Dict[str, Any]]) -> DataExtractionMethod:
    metadata = card_dict.get("metadata") or {}
    source = str(metadata.get("extraction_method") or metadata.get("data_extraction_method") or "").strip().lower()
    if source == "llm":
        return DataExtractionMethod.llm_extracted
    if source in {"manual", "manual_structured"}:
        return DataExtractionMethod.manual_structured
    if source in {"parser", "deterministic_parser"}:
        return DataExtractionMethod.deterministic_parser

    quality_sources = {str(details.get("source") or "") for details in identity_quality.values()}
    if "metadata" in quality_sources:
        return DataExtractionMethod.manual_structured
    if "metadata_conflict_text" in quality_sources:
        return DataExtractionMethod.mixed
    if "text" in quality_sources:
        return DataExtractionMethod.regex_structured
    return DataExtractionMethod.deterministic_parser


def _derive_evidence_strength_class(
    authority: Dict[str, Any],
    temporal: Dict[str, Any],
    document_quality: Dict[str, Any],
    evidence_quality: str,
) -> EvidenceStrengthClass:
    if (
        authority.get("quality") == "sufficient"
        and temporal.get("quality") == "sufficient"
        and document_quality.get("quality") == "complete"
        and evidence_quality == "qualified_identity"
    ):
        return EvidenceStrengthClass.strong
    if authority.get("quality") == "sufficient" and evidence_quality == "qualified_identity":
        return EvidenceStrengthClass.qualified
    if authority.get("quality") in {"insufficient", "unknown"} or evidence_quality != "qualified_identity":
        return EvidenceStrengthClass.weak
    return EvidenceStrengthClass.unknown


def _derive_context_completeness_score(document_metadata: Dict[str, Any], document_quality: Dict[str, Any]) -> int:
    present = sum(
        1
        for key in ("source_ref", "source_type", "source_rank", "manufacturer_name", "material_family", "grade_name")
        if document_metadata.get(key) not in (None, "", [])
    )
    temporal_present = any(
        document_metadata.get(key) not in (None, "", [])
        for key in ("revision_date", "published_at", "edition_year", "document_revision")
    )
    score = present * 10
    if temporal_present:
        score += 25
    if document_quality.get("quality") == "complete":
        score += 15
    return max(0, min(score, 100))


def _derive_document_collision_status(identity_quality: Dict[str, Dict[str, Any]]) -> DocumentCollisionStatus:
    if any(details.get("quality") == "conflict" for details in identity_quality.values()):
        return DocumentCollisionStatus.unresolved
    return DocumentCollisionStatus.none


def _derive_non_standard_unit_block(card_dict: dict, temp_max: Optional[float], pressure_max: Optional[float]) -> bool:
    units = str(card_dict.get("units") or "").strip().lower()
    if not units:
        return False
    if units in {"c", "°c", "bar", "psi"}:
        return False
    if temp_max is not None or pressure_max is not None:
        return False
    return True


def _build_datasheet_contract(
    card_dict: dict,
    document_metadata: Dict[str, Any],
    document_quality: Dict[str, Any],
    identity_quality: Dict[str, Dict[str, Any]],
    authority: Dict[str, Any],
    temporal: Dict[str, Any],
    evidence_quality: str,
    temp_min: Optional[float],
    temp_max: Optional[float],
    pressure_max: Optional[float],
) -> DatasheetContractV23:
    document_class = _map_document_class(document_metadata.get("source_type"))
    evidence_scope = document_metadata.get("evidence_scope") or []
    critical_test_context_present = bool(evidence_scope) or any(
        value is not None for value in (temp_min, temp_max, pressure_max)
    )
    unit_normalized_present = not _derive_non_standard_unit_block(card_dict, temp_max, pressure_max)
    audit_gate_passed = (
        authority.get("quality") == "sufficient"
        and temporal.get("quality") == "sufficient"
        and document_quality.get("quality") == "complete"
        and evidence_quality == "qualified_identity"
        and unit_normalized_present
    )
    return DatasheetContractV23(
        document_identity=DocumentIdentity(
            source_ref=str(document_metadata.get("source_ref") or card_dict.get("source_ref") or card_dict.get("source") or "unknown"),
            source_type=str(document_metadata.get("source_type") or "unknown"),
            source_rank=document_metadata.get("source_rank"),
            document_class=document_class,
            linked_manufacturer_grade_sheet_ref=(card_dict.get("metadata") or {}).get("linked_manufacturer_grade_sheet_ref"),
        ),
        document_metadata=DocumentMetadata(
            manufacturer_name=document_metadata.get("manufacturer_name"),
            product_line=document_metadata.get("product_line"),
            grade_name=document_metadata.get("grade_name"),
            material_family=document_metadata.get("material_family"),
            revision_date=document_metadata.get("revision_date"),
            published_at=document_metadata.get("published_at"),
            edition_year=document_metadata.get("edition_year"),
            document_revision=document_metadata.get("document_revision"),
            applies_to_color=(card_dict.get("metadata") or {}).get("applies_to_color"),
            certificate_color_dependent=bool((card_dict.get("metadata") or {}).get("certificate_color_dependent")),
            evidence_scope=list(document_metadata.get("evidence_scope") or []),
            scope_of_validity=list(document_metadata.get("scope_of_validity") or []),
        ),
        material_identity={
            "material_family": document_metadata.get("material_family"),
            "grade_name": document_metadata.get("grade_name"),
            "manufacturer_name": document_metadata.get("manufacturer_name"),
            "candidate_kind": _candidate_kind(
                document_metadata.get("material_family"),
                None,
                document_metadata.get("grade_name"),
                document_metadata.get("manufacturer_name"),
            ),
        },
        property_facts=[
            entry
            for entry in [
                {
                    "property_name": card_dict.get("property"),
                    "value": card_dict.get("value"),
                    "unit_original": card_dict.get("units"),
                    "unit_normalized": "C" if temp_max is not None else ("bar" if pressure_max is not None else None),
                    "normalized_value": temp_max if temp_max is not None else pressure_max,
                    "test_specimen_source": TestSpecimenSource.unknown.value,
                }
            ]
            if entry["property_name"]
        ],
        processing_dependency={
            "processing_dependency_declared": "processing" in str(card_dict.get("topic") or "").lower(),
            "test_specimen_source": TestSpecimenSource.unknown.value,
        },
        audit=AuditContract(
            document_binding_strength=_derive_document_binding_strength(card_dict, document_metadata),
            data_extraction_method=_derive_data_extraction_method(card_dict, identity_quality),
            data_origin_type=_read_data_origin_type(card_dict, document_metadata),
            evidence_strength_class=_derive_evidence_strength_class(authority, temporal, document_quality, evidence_quality),
            context_completeness_score=_derive_context_completeness_score(document_metadata, document_quality),
            document_collision_status=_derive_document_collision_status(identity_quality),
            audit_gate_passed=audit_gate_passed,
            human_review_status=HumanReviewStatus.not_required if audit_gate_passed else HumanReviewStatus.required,
            normalization_uncertainty=0.0 if evidence_quality == "qualified_identity" else 1.0,
            test_specimen_source=TestSpecimenSource.unknown,
            critical_test_context_present=critical_test_context_present,
            non_standard_unit_block=not unit_normalized_present,
            unit_normalized_present=unit_normalized_present,
        ),
    )


def _classify_source_authority(card_dict: dict) -> Dict[str, Any]:
    entry = _source_entry(card_dict)
    doc_meta = _document_metadata(card_dict)
    source_type = entry.get("source_type") or entry.get("type")
    source_rank = entry.get("source_rank", entry.get("rank"))
    try:
        source_rank = int(source_rank) if source_rank is not None else None
    except (TypeError, ValueError):
        source_rank = None
    candidate_kind = _candidate_kind(
        _extract_material_family(card_dict),
        _extract_filler_hint(card_dict),
        _extract_grade_name(card_dict),
        _extract_manufacturer_name(card_dict),
    )

    authoritative_types = {
        "manufacturer_datasheet",
        "standard_specification",
        "standard_test_method",
        "peer_reviewed_paper",
        "peer_reviewed_review",
        "government_report",
    }
    if source_type == "manufacturer_datasheet" and source_rank in {1, 2}:
        if candidate_kind == "manufacturer_grade" and doc_meta.get("manufacturer_name") and doc_meta.get("grade_name") and doc_meta.get("material_family"):
            return {"quality": "sufficient", "reason": f"authority:manufacturer_datasheet:grade_bound:rank_{source_rank}"}
        if candidate_kind in {"family", "filled_family", "grade"}:
            return {"quality": "sufficient", "reason": f"authority:manufacturer_datasheet:rank_{source_rank}"}
        return {"quality": "insufficient", "reason": f"authority_insufficient:manufacturer_datasheet:incomplete_identity:rank_{source_rank}"}
    if source_type in _MANUFACTURER_DOCUMENT_TYPES and candidate_kind == "manufacturer_grade":
        return {"quality": "insufficient", "reason": f"authority_insufficient:{source_type}:not_grade_specific:rank_{source_rank}"}
    if isinstance(source_type, str) and source_type in authoritative_types and source_rank in {1, 2}:
        return {"quality": "sufficient", "reason": f"authority:{source_type}:rank_{source_rank}"}
    if isinstance(source_type, str) and source_type in _MANUFACTURER_DOCUMENT_TYPES and source_rank in {1, 2}:
        return {"quality": "sufficient", "reason": f"authority:{source_type}:rank_{source_rank}"}
    if source_type or source_rank is not None:
        return {"quality": "insufficient", "reason": f"authority_insufficient:{source_type or 'unknown'}:rank_{source_rank}"}
    return {"quality": "unknown", "reason": "authority_missing"}


def _classify_source_temporal_validity(card_dict: dict) -> Dict[str, Any]:
    entry = _source_entry(card_dict)
    doc_meta = _document_metadata(card_dict)
    source_type = entry.get("source_type") or entry.get("type")
    candidate_kind = _candidate_kind(
        _extract_material_family(card_dict),
        _extract_filler_hint(card_dict),
        _extract_grade_name(card_dict),
        _extract_manufacturer_name(card_dict),
    )
    direct_candidates = [
        str(doc_meta.get("revision_date") or ""),
        str(doc_meta.get("published_at") or ""),
        str(doc_meta.get("edition_year") or ""),
        str(doc_meta.get("document_revision") or ""),
    ]
    years = []
    for candidate in direct_candidates:
        years.extend(int(match) for match in _YEAR_PATTERN.findall(candidate))
    if years:
        return {"quality": "sufficient", "reason": f"temporal_document_metadata:{max(years)}", "year": max(years)}
    if source_type in _MANUFACTURER_DOCUMENT_TYPES and candidate_kind in {"grade", "manufacturer_grade"}:
        return {"quality": "unknown", "reason": "temporal_document_metadata_missing"}

    fallback_candidates = [
        str(entry.get("title") or ""),
        str(entry.get("url") or ""),
        str(entry.get("edition") or ""),
    ]
    for candidate in fallback_candidates:
        years.extend(int(match) for match in _YEAR_PATTERN.findall(candidate))
    if years:
        return {"quality": "sufficient", "reason": f"temporal_fallback_year:{max(years)}", "year": max(years)}
    return {"quality": "unknown", "reason": "temporal_metadata_missing"}


def _extract_material_family(card_dict: dict) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    explicit = _read_metadata_str(metadata, "material_family", "material", "family")
    if explicit:
        return explicit.upper()

    text = f"{card_dict.get('topic', '')} {card_dict.get('content', '')}"
    match = _MATERIAL_PATTERN.search(text)
    if match:
        return match.group(1).upper()
    return None


def _extract_filler_hint(card_dict: dict) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    explicit = _read_metadata_str(metadata, "filler_hint", "filler", "fill")
    if explicit:
        return explicit

    text = f"{card_dict.get('topic', '')} {card_dict.get('content', '')}"
    match = _FILLER_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _extract_grade_name(card_dict: dict) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    explicit = _read_metadata_str(metadata, "grade_name", "grade", "compound_code", "compound")
    if explicit:
        return explicit

    text = f"{card_dict.get('topic', '')} {card_dict.get('content', '')}"
    match = _GRADE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _extract_manufacturer_name(card_dict: dict) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    return _read_metadata_str(metadata, "manufacturer_name", "manufacturer", "brand")


def _identity_text_value(card_dict: dict, field_name: str) -> Optional[str]:
    text = f"{card_dict.get('topic', '')} {card_dict.get('content', '')}"
    if field_name == "material_family":
        match = _MATERIAL_PATTERN.search(text)
        return match.group(1).upper() if match else None
    if field_name == "filler_hint":
        match = _FILLER_PATTERN.search(text)
        return match.group(1) if match else None
    if field_name == "grade_name":
        match = _GRADE_PATTERN.search(text)
        return match.group(1) if match else None
    return None


def _metadata_identity_value(card_dict: dict, field_name: str) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    if field_name == "material_family":
        value = _read_metadata_str(metadata, "material_family", "material", "family")
        return value.upper() if value else None
    if field_name == "filler_hint":
        return _read_metadata_str(metadata, "filler_hint", "filler", "fill")
    if field_name == "grade_name":
        return _read_metadata_str(metadata, "grade_name", "grade", "compound_code", "compound")
    if field_name == "manufacturer_name":
        return _read_metadata_str(metadata, "manufacturer_name", "manufacturer", "brand")
    return None


def _evaluate_identity_quality(card_dict: dict, field_name: str, resolved_value: Optional[str]) -> Dict[str, Any]:
    metadata_value = _metadata_identity_value(card_dict, field_name)
    text_value = _identity_text_value(card_dict, field_name)
    evidence_id = card_dict.get("evidence_id") or card_dict.get("id")
    source_ref = card_dict.get("source_ref")
    has_reference = bool(evidence_id) and bool(source_ref)

    if metadata_value and text_value and metadata_value.strip().upper() != text_value.strip().upper():
        return {
            "source": "metadata_conflict_text",
            "quality": "conflict",
            "reason": f"{field_name}_metadata_text_conflict",
        }
    if metadata_value and has_reference:
        return {
            "source": "metadata",
            "quality": "qualified",
            "reason": f"{field_name}_metadata_bound",
        }
    if metadata_value and not has_reference:
        return {
            "source": "metadata",
            "quality": "unqualified",
            "reason": f"{field_name}_metadata_missing_reference",
        }
    if text_value and resolved_value:
        return {
            "source": "text",
            "quality": "unqualified",
            "reason": f"{field_name}_text_extracted_only",
        }
    return {
        "source": "absent",
        "quality": "missing",
        "reason": f"{field_name}_missing",
    }


def _candidate_kind(
    family: Optional[str],
    filler_hint: Optional[str],
    grade_name: Optional[str],
    manufacturer_name: Optional[str],
) -> Optional[str]:
    if not family:
        return None
    if manufacturer_name and grade_name:
        return "manufacturer_grade"
    if grade_name:
        return "grade"
    if filler_hint:
        return "filled_family"
    return "family"


def _extract_temperature_limits(card_dict: dict) -> Tuple[Optional[float], Optional[float]]:
    metadata = card_dict.get("metadata") or {}
    temp_max = _read_metadata_float(metadata, "temperature_max_c", "temp_max_c", "temp_max", "max_temp_c")
    temp_min = _read_metadata_float(metadata, "temperature_min_c", "temp_min_c", "temp_min", "min_temp_c")
    if temp_max is not None:
        return temp_min if temp_min is not None else -50.0, temp_max

    content = card_dict.get("content", "")
    temp_max_match = re.search(r"(?:bis|max\.|maximal)\s*(-?\d+(?:[.,]\d+)?)\s*C", content, re.I)
    temp_min_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*bis", content, re.I)
    if not temp_max_match:
        return None, None

    t_max = float(temp_max_match.group(1).replace(",", "."))
    t_min = float(temp_min_match.group(1).replace(",", ".")) if temp_min_match else -50.0
    return t_min, t_max


def _extract_pressure_max(card_dict: dict) -> Optional[float]:
    metadata = card_dict.get("metadata") or {}
    explicit = _read_metadata_float(metadata, "pressure_max_bar", "pressure_max", "max_pressure_bar")
    if explicit is not None:
        return explicit

    content = card_dict.get("content", "")
    match = re.search(
        r"(?:max(?:\.|imal|imalen)?\s*(?:druck|pressure)?\s*(?:von)?|druck\s*(?:bis|max(?:\.|imal|imalen)?)?)\s*(\d+(?:[.,]\d+)?)\s*(bar|psi)\b",
        content,
        re.I,
    )
    if not match:
        match = re.search(r"(?:bis|max\.|maximal)\s*(\d+(?:[.,]\d+)?)\s*(bar|psi)\b", content, re.I)
    if not match:
        return None

    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit == "psi":
        return PhysicalParameter(value=value, unit="psi").to_base_unit()
    return value


def normalize_fact_card_evidence(card_dict: dict) -> Dict[str, Any]:
    family = _extract_material_family(card_dict)
    filler_hint = _extract_filler_hint(card_dict)
    grade_name = _extract_grade_name(card_dict)
    manufacturer_name = _extract_manufacturer_name(card_dict)
    temp_min, temp_max = _extract_temperature_limits(card_dict)
    pressure_max = _extract_pressure_max(card_dict)
    authority = _classify_source_authority(card_dict)
    temporal = _classify_source_temporal_validity(card_dict)
    document_metadata = _document_metadata(card_dict)
    document_quality = _document_metadata_quality(card_dict)
    identity_quality = {
        "material_family": _evaluate_identity_quality(card_dict, "material_family", family),
        "filler_hint": _evaluate_identity_quality(card_dict, "filler_hint", filler_hint),
        "grade_name": _evaluate_identity_quality(card_dict, "grade_name", grade_name),
        "manufacturer_name": _evaluate_identity_quality(card_dict, "manufacturer_name", manufacturer_name),
    }
    quality_reasons = [
        details["reason"]
        for details in identity_quality.values()
        if details["quality"] in {"conflict", "unqualified"}
    ]
    evidence_quality = "qualified_identity"
    if any(details["quality"] == "conflict" for details in identity_quality.values()):
        evidence_quality = "conflicted_identity"
    elif any(details["quality"] == "unqualified" for details in identity_quality.values()):
        evidence_quality = "unqualified_identity"
    datasheet_contract = _build_datasheet_contract(
        card_dict=card_dict,
        document_metadata=document_metadata,
        document_quality=document_quality,
        identity_quality=identity_quality,
        authority=authority,
        temporal=temporal,
        evidence_quality=evidence_quality,
        temp_min=temp_min,
        temp_max=temp_max,
        pressure_max=pressure_max,
    )

    return {
        "evidence_id": card_dict.get("evidence_id") or card_dict.get("id"),
        "source_ref": card_dict.get("source_ref") or card_dict.get("source"),
        "material_family": family,
        "filler_hint": filler_hint,
        "grade_name": grade_name,
        "manufacturer_name": manufacturer_name,
        "candidate_kind": _candidate_kind(family, filler_hint, grade_name, manufacturer_name),
        "normalized_temp_min": temp_min,
        "normalized_temp_max": temp_max,
        "normalized_pressure_max": pressure_max,
        "identity_quality": identity_quality,
        "evidence_quality": evidence_quality,
        "evidence_quality_reasons": quality_reasons,
        "authority_quality": authority["quality"],
        "authority_reason": authority["reason"],
        "temporal_quality": temporal["quality"],
        "temporal_reason": temporal["reason"],
        "temporal_year": temporal.get("year"),
        "document_metadata": document_metadata,
        "document_metadata_quality": document_quality["quality"],
        "document_metadata_missing": document_quality["missing_fields"],
        "datasheet_contract": datasheet_contract.model_dump(mode="json"),
    }

# Import existing model for compatibility if possible, or define a compatible one
try:
    from app.models.material_profile import MaterialPhysicalProfile as BaseMaterialPhysicalProfile
    
    class MaterialPhysicalProfile(BaseMaterialPhysicalProfile):
        @classmethod
        def from_fact_card(cls, card_dict: dict) -> Optional["MaterialPhysicalProfile"]:
            """
            Factory-Methode (Phase H7): Erzeugt ein Profil aus einer RAG FactCard.
            Extrahiert Materialnamen und Limits mittels RegEx.
            """
            normalized = card_dict.get("normalized_evidence") or normalize_fact_card_evidence(card_dict)
            mat_name = normalized.get("material_family")
            t_max = normalized.get("normalized_temp_max")
            if not mat_name or t_max is None:
                return None
            t_min = normalized.get("normalized_temp_min")
            if t_min is None:
                t_min = -50.0
            pressure_max = normalized.get("normalized_pressure_max")
            
            return cls(
                material_id=mat_name,
                temp_min=t_min,
                temp_max=t_max,
                pressure_max=pressure_max,
                v_surface_max=0, # Fallback
                pv_limit_critical=3.0 # Fallback
            )

except ImportError:
    # Fallback/Mock for standalone domain logic if backend is not in path
    class MaterialPhysicalProfile(BaseModel):
        material_id: str
        temp_min: float
        temp_max: float
        pressure_max: Optional[float] = None
        v_surface_max: float
        pv_limit_critical: float
        model_config = ConfigDict(extra="ignore")

        @classmethod
        def from_fact_card(cls, card_dict: dict) -> Optional["MaterialPhysicalProfile"]:
            """
            Factory-Methode (Phase H7): Erzeugt ein Profil aus einer RAG FactCard.
            """
            normalized = card_dict.get("normalized_evidence") or normalize_fact_card_evidence(card_dict)
            mat_name = normalized.get("material_family")
            t_max = normalized.get("normalized_temp_max")
            if not mat_name or t_max is None:
                return None
            t_min = normalized.get("normalized_temp_min")
            if t_min is None:
                t_min = -50.0
            pressure_max = normalized.get("normalized_pressure_max")
            
            return cls(
                material_id=mat_name,
                temp_min=t_min,
                temp_max=t_max,
                pressure_max=pressure_max,
                v_surface_max=0,
                pv_limit_critical=0
            )

class MaterialValidator:
    """
    Validiert ein Material gegen technische Einsatzbedingungen (Phase H3).
    Nutzt OperatingLimits zur deterministischen Prüfung.
    """
    def __init__(self, profile: MaterialPhysicalProfile):
        self.profile = profile
        
        # Erzeuge OperatingLimits aus dem Profil
        self.temp_limit = OperatingLimit(
            min_value=profile.temp_min,
            max_value=profile.temp_max,
            unit="C"
        )
        self.pressure_limit = None
        if getattr(profile, "pressure_max", None) is not None:
            self.pressure_limit = OperatingLimit(
                min_value=0.0,
                max_value=profile.pressure_max,
                unit="bar",
            )
        
        # Weitere Limits könnten hier initialisiert werden (PV, Speed etc.)

    def validate_temperature(self, temp: PhysicalParameter) -> bool:
        """Prüft, ob die Temperatur im zulässigen Bereich des Materials liegt."""
        return self.temp_limit.is_within_limits(temp)

    def validate_pressure(self, pressure: PhysicalParameter) -> bool:
        """Prüft, ob der Druck im zulässigen Bereich des Materials liegt, sofern explizit bekannt."""
        if self.pressure_limit is None:
            return True
        return self.pressure_limit.is_within_limits(pressure)

    def get_validation_report(self, conditions: Dict[str, PhysicalParameter]) -> Dict[str, Any]:
        """
        Erzeugt einen detaillierten Validierungsbericht für mehrere Bedingungen.
        """
        report = {
            "material_id": self.profile.material_id,
            "is_valid": True,
            "checks": {}
        }
        
        if "temperature" in conditions:
            is_ok = self.validate_temperature(conditions["temperature"])
            report["checks"]["temperature"] = {
                "status": "OK" if is_ok else "CRITICAL",
                "value": conditions["temperature"].to_base_unit(),
                "limit_min": self.profile.temp_min,
                "limit_max": self.profile.temp_max,
                "unit": "C"
            }
            if not is_ok:
                report["is_valid"] = False

        if "pressure" in conditions and self.pressure_limit is not None:
            is_ok = self.validate_pressure(conditions["pressure"])
            report["checks"]["pressure"] = {
                "status": "OK" if is_ok else "CRITICAL",
                "value": conditions["pressure"].to_base_unit(),
                "limit_min": 0.0,
                "limit_max": self.profile.pressure_max,
                "unit": "bar"
            }
            if not is_ok:
                report["is_valid"] = False
                
        return report
