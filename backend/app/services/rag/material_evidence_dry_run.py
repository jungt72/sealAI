"""Read-only Paperless/RAG dry-run reporting for material evidence cards."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.agent.domain.material_evidence_adapter import (
    AdapterResult,
    dry_run_material_evidence_candidates,
)
from app.models.rag_document import RagDocument


_TEXT_KEYS = (
    "text",
    "content",
    "chunk_text",
    "excerpt",
    "excerpt_short",
    "statement_short",
)
_MAX_ADAPTER_TEXT_CHARS = 1200
_MAX_RESPONSE_TEXT_CHARS = 320
_MAX_INDEXED_SNIPPET_TEXT_CHARS = 1600
_MAX_INDEXED_SNIPPETS_PER_DOCUMENT = 3
_MAX_STRUCTURED_CANDIDATES_PER_SNIPPET = 3
_QDRANT_COLLECTION = (os.getenv("QDRANT_COLLECTION") or "sealai_knowledge").strip()
_QDRANT_URL = (os.getenv("QDRANT_URL") or "http://qdrant:6333").rstrip("/")
_QDRANT_API_KEY = (os.getenv("QDRANT_API_KEY") or "").strip() or None
_JSON_BLOCK_RE = re.compile(r"\{[^{}]{20,2500}\}", re.DOTALL)
_STRUCTURED_TEXT_FIELDS = (
    "material",
    "compound",
    "material_code",
    "material_family",
    "medium",
    "medium_name",
    "fluid",
    "medium_family",
    "statement_short",
    "excerpt_short",
    "source_title",
    "source_url",
    "doi",
    "manufacturer",
    "evidence_date",
    "concentration",
)
_STRUCTURED_NUMBER_FIELDS = (
    "temperature_min_c",
    "temperature_max_c",
    "temp_min_c",
    "temp_max_c",
    "ph_min",
    "ph_max",
)
_KNOWN_MATERIAL_RE = re.compile(
    r"\b(FKM|FPM|VITON|NBR|HNBR|EPDM|PTFE|FVMQ|VMQ|PEEK|UHMW[- ]?PE|PE[- ]?UHMW|SIC|SI[- ]?C|SILICON CARBIDE)\b",
    re.IGNORECASE,
)
_UNSPECIFIC_MEDIUM_KEYS = {
    "generic",
    "unknown",
    "unbekannt",
    "not specified",
    "not_specified",
    "n/a",
    "na",
    "lubricated_or_dry",
}
_GENERIC_MEDIUM_RE = re.compile(
    r"\b(solvents?|fluids?|media|chemicals?|lubricated|dry|generic|unknown)\b|/",
    re.IGNORECASE,
)


def rag_document_to_material_evidence_raw_items(
    doc: RagDocument,
) -> list[dict[str, Any]]:
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
        metadata = _merge_mappings(
            base.get("metadata"), candidate_payload.get("metadata")
        )
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
    indexed_snippet_items: Sequence[Mapping[str, Any]] | None = None,
    indexed_snippet_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a redacted read-only report from RAG documents through the adapter."""

    raw_items: list[dict[str, Any]] = []
    snippet_items_by_document = _group_indexed_snippet_items(
        indexed_snippet_items or []
    )
    used_indexed_snippet_candidates = 0
    for doc in docs:
        candidates = _candidate_mappings(doc.extracted_candidates)
        fallback_items = snippet_items_by_document.get(_text(doc.document_id), [])
        if candidates:
            raw_items.extend(rag_document_to_material_evidence_raw_items(doc))
            if fallback_items:
                raw_items.extend(fallback_items)
                used_indexed_snippet_candidates += len(fallback_items)
            continue
        if fallback_items:
            raw_items.extend(fallback_items)
            used_indexed_snippet_candidates += len(fallback_items)
            continue
        raw_items.extend(rag_document_to_material_evidence_raw_items(doc))

    report = dry_run_material_evidence_candidates(raw_items)
    results = [
        _result_payload(result)
        for result in report.results
        if include_invalid or result.status not in {"invalid", "skipped"}
    ]
    quality = _data_quality_assessment(
        valid_count=report.valid_count,
        invalid_count=report.invalid_count,
        downgraded_count=report.downgraded_count,
        skipped_count=report.skipped_count,
        grouped_missing_fields=dict(report.grouped_missing_fields),
        grouped_limitations=dict(report.grouped_limitations),
        indexed_snippet_count=used_indexed_snippet_candidates,
    )
    enrichment = _snippet_enrichment_payload(
        indexed_snippet_summary,
        indexed_snippet_items=indexed_snippet_items or [],
        used_indexed_snippet_candidates=used_indexed_snippet_candidates,
    )
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
        "data_quality_status": quality["data_quality_status"],
        "persistable_card_count": report.valid_count,
        "persistence_recommendation": quality["persistence_recommendation"],
        "recommended_actions": quality["recommended_actions"],
        "indexed_snippet_enrichment": enrichment,
        "results": results,
    }


def load_material_evidence_indexed_snippet_raw_items(
    docs: Sequence[RagDocument],
    *,
    tenant_id: str,
    collection_name: str | None = None,
    max_documents: int = 25,
    max_snippets_per_document: int = _MAX_INDEXED_SNIPPETS_PER_DOCUMENT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read capped Qdrant payload snippets and convert them into adapter inputs.

    This is intentionally read-only: it only calls Qdrant ``scroll`` with
    payloads enabled and vectors disabled. Failures are reported as enrichment
    status so the dry-run endpoint remains safe and inspectable.
    """

    selected_docs = [
        doc
        for doc in docs[: max(max_documents, 0)]
        if _text(getattr(doc, "document_id", None))
    ]
    summary: dict[str, Any] = {
        "enabled": True,
        "source": "qdrant_payload",
        "status": "not_attempted" if not selected_docs else "attempted",
        "attempted_document_count": len(selected_docs),
        "loaded_snippet_count": 0,
        "loaded_candidate_count": 0,
        "max_snippets_per_document": max_snippets_per_document,
    }
    if not selected_docs:
        summary["status"] = "no_source_documents"
        return [], summary

    try:
        from qdrant_client import QdrantClient, models as qmodels  # type: ignore
    except Exception as exc:  # noqa: BLE001
        summary["status"] = "qdrant_client_unavailable"
        summary["reason"] = _truncate(str(exc), limit=160)
        return [], summary

    try:
        client = QdrantClient(url=_QDRANT_URL, api_key=_QDRANT_API_KEY)
        collection = collection_name or _QDRANT_COLLECTION
        items: list[dict[str, Any]] = []
        loaded_snippets = 0
        for doc in selected_docs:
            payloads = _scroll_indexed_snippet_payloads(
                client=client,
                qmodels=qmodels,
                collection_name=collection,
                tenant_id=tenant_id,
                document_id=_text(doc.document_id),
                limit=max_snippets_per_document,
            )
            loaded_snippets += len(payloads)
            for index, payload in enumerate(payloads):
                items.extend(
                    indexed_snippet_payload_to_material_evidence_raw_items(
                        doc, payload, snippet_index=index
                    )
                )
        summary["loaded_snippet_count"] = loaded_snippets
        summary["loaded_candidate_count"] = len(items)
        summary["status"] = "loaded" if items else "no_indexed_snippets"
        return items, summary
    except Exception as exc:  # noqa: BLE001
        summary["status"] = "qdrant_scroll_failed"
        summary["reason"] = _truncate(str(exc), limit=160)
        return [], summary


def indexed_snippet_payload_to_material_evidence_raw_items(
    doc: RagDocument,
    payload_source: Mapping[str, Any],
    *,
    snippet_index: int = 0,
) -> list[dict[str, Any]]:
    """Convert one indexed payload into one or more conservative raw candidates."""

    payload = _payload_mapping(payload_source)
    base = _base_raw_item(doc)
    metadata = _sanitize_indexed_snippet_metadata(
        _merge_mappings(base.get("metadata"), payload.get("metadata"))
    )
    metadata["snippet_index"] = snippet_index
    metadata["snippet_source"] = "qdrant_payload"
    metadata["indexed_snippet_text_available"] = bool(_payload_text(payload))
    text = _truncate(_payload_text(payload), limit=_MAX_INDEXED_SNIPPET_TEXT_CHARS)
    raw = _indexed_snippet_base_raw_item(
        base=base, payload=payload, metadata=metadata, text=text
    )
    structured_candidates = _structured_candidates_from_text(text)
    if not structured_candidates:
        return [_truncate_text_fields(raw, limit=_MAX_ADAPTER_TEXT_CHARS)]

    items: list[dict[str, Any]] = []
    for candidate_index, structured in enumerate(
        structured_candidates[:_MAX_STRUCTURED_CANDIDATES_PER_SNIPPET]
    ):
        candidate_metadata = _merge_mappings(metadata, structured.get("metadata"))
        candidate_metadata["structured_candidate_index"] = candidate_index
        candidate_metadata["structured_candidate_source"] = "indexed_snippet_text"
        candidate_payload = _safe_candidate_payload(structured)
        candidate_text = (
            _text(candidate_payload.get("text"))
            or _text(candidate_payload.get("statement_short"))
            or text
        )
        candidate_raw = {
            **raw,
            **candidate_payload,
            "metadata": candidate_metadata,
            "text": _truncate(candidate_text, limit=_MAX_INDEXED_SNIPPET_TEXT_CHARS),
            "excerpt": _truncate(candidate_text, limit=_MAX_INDEXED_SNIPPET_TEXT_CHARS),
        }
        items.append(
            _truncate_text_fields(candidate_raw, limit=_MAX_ADAPTER_TEXT_CHARS)
        )
    return items


def _data_quality_assessment(
    *,
    valid_count: int,
    invalid_count: int,
    downgraded_count: int,
    skipped_count: int,
    grouped_missing_fields: Mapping[str, int],
    grouped_limitations: Mapping[str, int],
    indexed_snippet_count: int = 0,
) -> dict[str, Any]:
    reviewed_count = valid_count + invalid_count + downgraded_count + skipped_count
    actions: list[str] = []
    if grouped_missing_fields.get("medium", 0):
        actions.append("add_or_extract_exact_medium_metadata")
    if grouped_missing_fields.get("material", 0) or grouped_missing_fields.get(
        "material_or_medium", 0
    ):
        actions.append("add_or_extract_material_metadata")
    if grouped_missing_fields.get("source_title", 0) or grouped_missing_fields.get(
        "source_metadata", 0
    ):
        actions.append("repair_source_metadata")
    if grouped_limitations.get("tags_only_context", 0):
        actions.append("extract_text_snippets_or_structured_candidates_from_paperless")
    if grouped_limitations.get("exact_medium_specification_missing", 0):
        actions.append("replace_generic_medium_tags_with_exact_medium_family_and_grade")
    if valid_count == 0 and indexed_snippet_count:
        actions.append(
            "curate_indexed_snippets_into_explicit_material_medium_candidates"
        )
    if not actions:
        actions.append("review_valid_cards_before_persistence")

    if reviewed_count == 0:
        status = "no_source_documents"
        recommendation = "do_not_persist_no_candidates"
    elif valid_count == 0:
        status = "metadata_gap_no_valid_cards"
        recommendation = "do_not_persist_improve_metadata_first"
    elif invalid_count or downgraded_count or skipped_count:
        status = "mixed_quality_review_required"
        recommendation = "persist_only_valid_cards_after_admin_review"
    else:
        status = "valid_cards_review_ready"
        recommendation = "admin_review_before_persistence"

    return {
        "data_quality_status": status,
        "persistence_recommendation": recommendation,
        "recommended_actions": list(dict.fromkeys(actions)),
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


def _group_indexed_snippet_items(
    items: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if not isinstance(item, Mapping):
            continue
        document_id = _text(item.get("document_id"))
        if not document_id:
            document_id = _text(_mapping(item.get("metadata")).get("document_id"))
        if document_id:
            grouped[document_id].append(
                _truncate_text_fields(item, limit=_MAX_ADAPTER_TEXT_CHARS)
            )
    return dict(grouped)


def _snippet_enrichment_payload(
    summary: Mapping[str, Any] | None,
    *,
    indexed_snippet_items: Sequence[Mapping[str, Any]],
    used_indexed_snippet_candidates: int,
) -> dict[str, Any]:
    payload = _safe_mapping(summary or {})
    if not payload:
        payload = {
            "enabled": False,
            "source": "qdrant_payload",
            "status": "not_requested",
            "loaded_candidate_count": len(indexed_snippet_items),
        }
    payload["used_candidate_count"] = used_indexed_snippet_candidates
    payload["fallback_mode"] = "fused_with_extracted_candidates"
    return payload


def _scroll_indexed_snippet_payloads(
    *,
    client: Any,
    qmodels: Any,
    collection_name: str,
    tenant_id: str,
    document_id: str,
    limit: int,
) -> list[Mapping[str, Any]]:
    result = client.scroll(
        collection_name=collection_name,
        scroll_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="tenant_id", match=qmodels.MatchValue(value=tenant_id)
                ),
                qmodels.FieldCondition(
                    key="document_id", match=qmodels.MatchValue(value=document_id)
                ),
            ]
        ),
        limit=max(1, min(limit, _MAX_INDEXED_SNIPPETS_PER_DOCUMENT)),
        with_payload=True,
        with_vectors=False,
    )
    points = (
        result[0] if isinstance(result, tuple) else getattr(result, "points", result)
    )
    payloads: list[Mapping[str, Any]] = []
    for point in points or []:
        payload = getattr(point, "payload", None)
        if isinstance(payload, Mapping):
            payloads.append(payload)
    return payloads


def _indexed_snippet_base_raw_item(
    *,
    base: Mapping[str, Any],
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any],
    text: str,
) -> dict[str, Any]:
    source_url = (
        _text(payload.get("source_url"))
        or _text(_mapping(payload.get("metadata")).get("source_url"))
        or _text(base.get("source_url"))
    )
    source_title = (
        _text(payload.get("source_title"))
        or _text(payload.get("title"))
        or _text(payload.get("filename"))
        or _text(_mapping(payload.get("metadata")).get("title"))
        or _text(base.get("source_title"))
    )
    additional_metadata = _sanitize_indexed_snippet_metadata(
        _merge_mappings(
            payload.get("additional_metadata"),
            _mapping(payload.get("metadata")).get("additional_metadata"),
        )
    )
    raw = {
        **base,
        "metadata": metadata,
        "source_title": source_title,
        "source_url": source_url,
        "text": text,
        "excerpt": text,
        "chunk_text": text,
        "material_code": _trusted_material_or_empty(
            _text(payload.get("material_code"))
            or _text(_mapping(payload.get("metadata")).get("material_code"))
        ),
        "additional_metadata": additional_metadata,
    }
    return {key: value for key, value in raw.items() if value not in (None, "", [])}


def _payload_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        payload = value.get("payload")
        if isinstance(payload, Mapping):
            return dict(payload)
        return dict(value)
    payload = getattr(value, "payload", None)
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _payload_text(payload: Mapping[str, Any]) -> str:
    metadata = _mapping(payload.get("metadata"))
    for key in ("text", "content", "chunk_text", "excerpt", "statement_short"):
        text = _text(payload.get(key)) or _text(metadata.get(key))
        if text:
            return text
    return ""


def _structured_candidates_from_text(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    candidates: list[dict[str, Any]] = []
    for match in _JSON_BLOCK_RE.finditer(text):
        parsed = _loads_structured_mapping(match.group(0))
        if not parsed:
            continue
        candidate = _material_candidate_from_mapping(parsed)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= _MAX_STRUCTURED_CANDIDATES_PER_SNIPPET:
            return candidates
    if candidates:
        return candidates
    regex_candidate = _regex_structured_candidate(text)
    if regex_candidate:
        candidates.append(regex_candidate)
    return candidates[:_MAX_STRUCTURED_CANDIDATES_PER_SNIPPET]


def _loads_structured_mapping(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    return dict(parsed)


def _material_candidate_from_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    nested = value
    for key in ("material_evidence_card", "evidence_card", "card", "candidate"):
        item = value.get(key)
        if isinstance(item, Mapping):
            nested = item
            break
    candidate: dict[str, Any] = {}
    for key in _STRUCTURED_TEXT_FIELDS:
        text = _text(nested.get(key))
        if text:
            candidate[key] = text
    for key in _STRUCTURED_NUMBER_FIELDS:
        number = _number(nested.get(key))
        if number is not None:
            candidate[key] = number
    limitations = nested.get("limitations")
    if isinstance(limitations, list):
        candidate["limitations"] = [_text(item) for item in limitations if _text(item)]
    candidate_text = _text(candidate.get("statement_short")) or _text(
        candidate.get("excerpt_short")
    )
    if candidate_text:
        candidate["text"] = candidate_text
    candidate = _sanitize_structured_candidate(candidate)
    if not any(
        candidate.get(key)
        for key in (
            "material",
            "compound",
            "material_code",
            "material_family",
            "medium",
            "medium_name",
            "fluid",
            "medium_family",
        )
    ):
        return {}
    return candidate


def _regex_structured_candidate(text: str) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    for key in _STRUCTURED_TEXT_FIELDS:
        found = re.search(
            rf"['\"]{re.escape(key)}['\"]\s*:\s*['\"]([^'\"]+)['\"]",
            text,
            re.IGNORECASE,
        )
        if found:
            candidate[key] = found.group(1).strip()
    for key in _STRUCTURED_NUMBER_FIELDS:
        found = re.search(
            rf"['\"]{re.escape(key)}['\"]\s*:\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE
        )
        if found:
            candidate[key] = _number(found.group(1))
    if not any(
        candidate.get(key)
        for key in (
            "material",
            "compound",
            "material_code",
            "material_family",
            "medium",
            "medium_name",
            "fluid",
            "medium_family",
        )
    ):
        return {}
    candidate.setdefault("text", _truncate(text, limit=_MAX_INDEXED_SNIPPET_TEXT_CHARS))
    sanitized = _sanitize_structured_candidate(candidate)
    if not any(
        sanitized.get(key)
        for key in (
            "material",
            "compound",
            "material_code",
            "material_family",
            "medium",
            "medium_name",
            "fluid",
            "medium_family",
        )
    ):
        return {}
    return sanitized


def _sanitize_structured_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = dict(candidate)
    for key in ("material", "compound", "material_code", "material_family"):
        value = _text(sanitized.get(key))
        if value and not _trusted_material_value(value):
            sanitized.pop(key, None)

    for key in ("medium", "medium_name", "fluid"):
        value = _text(sanitized.get(key))
        if not value:
            continue
        medium_key = value.casefold().strip()
        if medium_key in _UNSPECIFIC_MEDIUM_KEYS:
            sanitized.pop(key, None)
            _append_candidate_limitation(
                sanitized, "exact_medium_specification_missing"
            )
            continue
        if _GENERIC_MEDIUM_RE.search(value):
            sanitized.pop(key, None)
            sanitized.setdefault("medium_family", value)
            _append_candidate_limitation(
                sanitized, "exact_medium_specification_missing"
            )
    return sanitized


def _sanitize_indexed_snippet_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = _safe_mapping(metadata)
    for key in ("material", "compound", "material_code", "entity"):
        value = _text(sanitized.get(key))
        if value and not _trusted_material_value(value):
            sanitized.pop(key, None)
    for key in ("medium", "medium_name", "fluid"):
        value = _text(sanitized.get(key))
        if not value:
            continue
        medium_key = value.casefold().strip()
        if medium_key in _UNSPECIFIC_MEDIUM_KEYS or _GENERIC_MEDIUM_RE.search(value):
            sanitized.pop(key, None)
    additional = sanitized.get("additional_metadata")
    if isinstance(additional, Mapping):
        sanitized["additional_metadata"] = _sanitize_indexed_snippet_metadata(
            additional
        )
    return sanitized


def _trusted_material_or_empty(value: str) -> str:
    return value if value and _trusted_material_value(value) else ""


def _trusted_material_value(value: str) -> bool:
    return bool(_KNOWN_MATERIAL_RE.search(value))


def _append_candidate_limitation(candidate: dict[str, Any], limitation: str) -> None:
    limitations = candidate.get("limitations")
    if not isinstance(limitations, list):
        limitations = []
    if limitation not in limitations:
        limitations.append(limitation)
    candidate["limitations"] = limitations


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return number


def _safe_candidate_payload(candidate: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in candidate.items():
        if key == "raw_text":
            continue
        if key in _TEXT_KEYS:
            payload[key] = _truncate(value, limit=_MAX_ADAPTER_TEXT_CHARS)
        elif key == "metadata":
            payload[key] = _safe_mapping(value)
        elif (
            isinstance(value, (str, int, float, bool, list, tuple, set, dict))
            or value is None
        ):
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
            "compliance_claim_allowed": validation.compliance_claim_allowed
            if validation
            else False,
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
    safe = {
        key: candidate.get(key)
        for key in allowed_keys
        if candidate.get(key) not in (None, "", [])
    }
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
                _safe_mapping(entry)
                if isinstance(entry, Mapping)
                else _truncate(entry, limit=_MAX_RESPONSE_TEXT_CHARS)
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
    "indexed_snippet_payload_to_material_evidence_raw_items",
    "load_material_evidence_indexed_snippet_raw_items",
    "rag_document_to_material_evidence_raw_items",
]
