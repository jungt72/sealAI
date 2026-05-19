"""Read-only Paperless/RAG dry-run reporting for material evidence cards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.agent.domain.material_evidence_adapter import (
    AdapterResult,
    dry_run_material_evidence_candidates,
)
from app.models.rag_document import RagDocument


_TEXT_KEYS = ("text", "content", "chunk_text", "excerpt", "excerpt_short", "statement_short")
_MAX_ADAPTER_TEXT_CHARS = 480
_MAX_RESPONSE_TEXT_CHARS = 320


def rag_document_to_material_evidence_raw_items(doc: RagDocument) -> list[dict[str, Any]]:
    """Build conservative adapter inputs from a RAG document row.

    The function only uses already persisted metadata/extracted candidates. It
    never reads the document file path and never infers technical facts beyond
    passing tags/text snippets into the existing dry-run adapter.
    """

    base = _base_raw_item(doc)
    candidates = _candidate_mappings(doc.extracted_candidates)
    if not candidates:
        return [base]

    raw_items: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        candidate_payload = _safe_candidate_payload(candidate)
        metadata = _merge_mappings(base.get("metadata"), candidate_payload.get("metadata"))
        metadata["candidate_index"] = index

        raw = {**base, **candidate_payload}
        raw["metadata"] = metadata
        raw["document_id"] = doc.document_id
        raw["source_system"] = base.get("source_system")
        raw["source_id"] = base.get("source_id")
        raw["source_document_id"] = base.get("source_document_id")
        raw["route"] = base.get("route")
        raw["route_key"] = base.get("route_key")
        raw["tags"] = base.get("tags") or []
        raw["source_title"] = raw.get("source_title") or base.get("source_title")
        raw["source_url"] = raw.get("source_url") or base.get("source_url")
        raw["sha256"] = base.get("sha256")
        raw["source_hash"] = raw.get("source_hash") or base.get("source_hash")
        raw_items.append(_truncate_text_fields(raw, limit=_MAX_ADAPTER_TEXT_CHARS))
    return raw_items


def build_material_evidence_dry_run_report(
    docs: Sequence[RagDocument],
    *,
    include_invalid: bool = True,
    source_system: str = "paperless",
    route: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Return a redacted read-only report from RAG documents through the adapter."""

    raw_items: list[dict[str, Any]] = []
    for doc in docs:
        raw_items.extend(rag_document_to_material_evidence_raw_items(doc))

    report = dry_run_material_evidence_candidates(raw_items)
    results = [
        _result_payload(result)
        for result in report.results
        if include_invalid or result.status not in {"invalid", "skipped"}
    ]
    return {
        "mode": "material_evidence_card_dry_run",
        "read_only": True,
        "source_system": source_system,
        "route": route,
        "limit": limit,
        "total_considered": report.total,
        "valid_count": report.valid_count,
        "invalid_count": report.invalid_count,
        "downgraded_count": report.downgraded_count,
        "skipped_count": report.skipped_count,
        "grouped_missing_fields": dict(report.grouped_missing_fields),
        "grouped_limitations": dict(report.grouped_limitations),
        "safety_warnings": list(report.safety_warnings),
        "results": results,
    }


def _base_raw_item(doc: RagDocument) -> dict[str, Any]:
    source_system = _text(doc.source_system) or "rag"
    source_id = _text(doc.source_document_id) or _text(doc.document_id)
    route = _text(doc.route_key) or _text(doc.category)
    source_url = _paperless_source_url(source_system=source_system, source_id=source_id)
    source_modified_at = _isoformat(doc.source_modified_at)
    metadata = {
        "document_id": doc.document_id,
        "source_document_id": doc.source_document_id,
        "source_system": source_system,
        "route_key": doc.route_key,
        "category": doc.category,
        "filename": doc.filename,
        "tags": list(doc.tags or []),
        "extraction_status": doc.extraction_status,
        "evidence_refs": doc.evidence_refs or [],
        "provenance": doc.provenance,
        "source_modified_at": source_modified_at,
        "ingest_stats": _safe_mapping(doc.ingest_stats),
    }
    return {
        "document_id": doc.document_id,
        "source_system": source_system,
        "source_id": source_id,
        "source_document_id": doc.source_document_id,
        "source_title": doc.filename,
        "source_url": source_url,
        "source_hash": doc.sha256,
        "sha256": doc.sha256,
        "route": route,
        "route_key": route,
        "tags": list(doc.tags or []),
        "evidence_refs": doc.evidence_refs or [],
        "provenance": doc.provenance,
        "source_modified_at": source_modified_at,
        "metadata": metadata,
    }


def _candidate_mappings(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        for key in ("candidates", "items", "results"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, Mapping)]
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _safe_candidate_payload(candidate: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in candidate.items():
        if key == "raw_text":
            continue
        if key in _TEXT_KEYS:
            payload[key] = _truncate(value, limit=_MAX_ADAPTER_TEXT_CHARS)
        elif key == "metadata":
            payload[key] = _safe_mapping(value)
        elif isinstance(value, (str, int, float, bool, list, tuple, set, dict)) or value is None:
            payload[key] = value
    return payload


def _result_payload(result: AdapterResult) -> dict[str, Any]:
    candidate = result.card_candidate or {}
    validation = result.validation_result
    blocked_claims = list(validation.blocked_claims) if validation else []
    payload = {
        "source_system": candidate.get("source_system"),
        "source_id": candidate.get("source_id"),
        "source_title": candidate.get("source_title"),
        "route": candidate.get("route"),
        "status": result.status,
        "card_candidate": _safe_card_candidate(candidate),
        "validation_summary": {
            "card_id": validation.card_id if validation else None,
            "valid": validation.valid if validation else False,
            "status": validation.status if validation else None,
            "reasons": list(validation.reasons) if validation else [],
            "limitations": list(validation.limitations) if validation else [],
            "blocked_claims": blocked_claims,
            "support_allowed": validation.support_allowed if validation else False,
            "compliance_claim_allowed": validation.compliance_claim_allowed if validation else False,
        },
        "missing_fields": list(result.missing_fields),
        "limitations": list(result.limitations),
        "safety_warnings": blocked_claims,
        "source_reference": result.source_reference,
        "reason": result.reason,
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def _safe_card_candidate(candidate: Mapping[str, Any]) -> dict[str, Any] | None:
    if not candidate:
        return None
    allowed_keys = (
        "schema_version",
        "card_id",
        "material",
        "material_family",
        "medium",
        "medium_family",
        "temperature_min_c",
        "temperature_max_c",
        "concentration",
        "ph_min",
        "ph_max",
        "claim_level",
        "claim_type",
        "compatibility_status",
        "statement_short",
        "source_title",
        "source_type",
        "source_url",
        "doi",
        "manufacturer",
        "evidence_date",
        "limitations",
        "final_approval_claim_allowed",
        "compliance_claim_allowed",
        "created_by_pipeline",
        "source_hash",
        "excerpt_short",
        "confidence",
        "source_reference",
        "source_system",
        "source_id",
        "route",
        "tags",
    )
    safe = {key: candidate.get(key) for key in allowed_keys if candidate.get(key) not in (None, "", [])}
    return _truncate_text_fields(safe, limit=_MAX_RESPONSE_TEXT_CHARS)


def _truncate_text_fields(payload: Mapping[str, Any], *, limit: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _TEXT_KEYS or key in {"statement_short", "source_title"}:
            result[key] = _truncate(value, limit=limit)
        elif isinstance(value, Mapping):
            result[key] = _truncate_text_fields(value, limit=limit)
        else:
            result[key] = value
    return result


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    safe: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"raw_text", "full_text", "content"}:
            continue
        if key in _TEXT_KEYS:
            safe[str(key)] = _truncate(item, limit=_MAX_RESPONSE_TEXT_CHARS)
        elif isinstance(item, Mapping):
            safe[str(key)] = _safe_mapping(item)
        elif isinstance(item, list):
            safe[str(key)] = [
                _safe_mapping(entry) if isinstance(entry, Mapping) else _truncate(entry, limit=_MAX_RESPONSE_TEXT_CHARS)
                for entry in item[:20]
            ]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = _truncate(item, limit=_MAX_RESPONSE_TEXT_CHARS)
    return safe


def _merge_mappings(*values: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        if isinstance(value, Mapping):
            merged.update(_safe_mapping(value))
    return merged


def _paperless_source_url(*, source_system: str, source_id: str) -> str:
    if source_system.casefold() == "paperless" and source_id:
        return f"paperless://documents/{source_id}"
    return ""


def _isoformat(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    text = _text(value)
    return text or None


def _truncate(value: Any, *, limit: int) -> Any:
    if not isinstance(value, str):
        return value
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "build_material_evidence_dry_run_report",
    "rag_document_to_material_evidence_raw_items",
]
