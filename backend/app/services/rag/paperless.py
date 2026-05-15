from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.redaction import safe_error_message

from app.agent.rag.paperless_tags import augment_paperless_tags_for_rag, evaluate_paperless_tag_readiness
from app.core.config import settings
from app.models.rag_document import RagDocument
from app.observability.metrics import track_rag_sync
from app.services.rag.constants import (
    RAG_SHARED_TENANT_ID,
    RAG_VISIBILITY_PUBLIC,
)
from app.services.rag.route_resolver import coerce_tag_strings, resolve_route_key
from app.services.rag.utils import (
    ALLOWED_EXT,
    MAGIC_READ_BYTES,
    RAG_UPLOAD_MAX_BYTES,
    cleanup_upload_path,
    ensure_upload_directory,
    find_existing_document,
    find_existing_document_by_source,
    resolve_upload_dir,
    sanitize_filename,
    validate_upload_signature,
)

logger = structlog.get_logger("services.rag.paperless")

_PAPERLESS_SOURCE_SYSTEM = "paperless"
_REMOVED_STATUSES = {"removed", "disabled", "deleted"}
_ACTIVE_STATUSES = {"queued", "processing", "indexed", "done", "error", "failed"}


def _parse_source_modified_at(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _same_source_modified_at(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return left is right
    return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)


def _document_input_payload(*, doc: RagDocument, readiness: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "document_id": doc.document_id,
        "case_id": None,
        "file_type": Path(str(doc.filename or doc.path or "")).suffix.lower().lstrip(".") or None,
        "file_name": doc.filename,
        "uploaded_at": doc.created_at.isoformat() if getattr(doc, "created_at", None) else None,
        "extraction_status": doc.extraction_status,
        "extracted_candidates": doc.extracted_candidates or [],
        "evidence_refs": doc.evidence_refs or [],
        "provenance": doc.provenance or "documented",
        "source_system": doc.source_system,
        "source_document_id": doc.source_document_id,
        "source_modified_at": doc.source_modified_at.isoformat() if doc.source_modified_at else None,
        "paperless_tag_readiness": readiness or {},
    }


def _delete_qdrant_document(*, tenant_id: str, document_id: str) -> bool:
    try:
        from qdrant_client import QdrantClient, models as qmodels  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency boundary
        logger.warning("paperless_qdrant_delete_unavailable", document_id=document_id, reason=str(exc))
        return False

    try:
        qdrant_url = getattr(settings, "qdrant_url", None) or "http://qdrant:6333"
        collection = getattr(settings, "qdrant_collection", None) or "sealai_knowledge"
        api_key = getattr(settings, "qdrant_api_key", None) or None
        client = QdrantClient(url=qdrant_url, api_key=api_key)
        client.delete(
            collection_name=collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value=tenant_id)),
                        qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=document_id)),
                    ]
                )
            ),
            wait=True,
        )
        return True
    except Exception as exc:  # pragma: no cover - network/storage boundary
        logger.warning("paperless_qdrant_delete_failed", document_id=document_id, reason=str(exc))
        return False


async def _disable_existing_paperless_doc(
    session: AsyncSession,
    doc: RagDocument,
    *,
    reason: str,
) -> bool:
    if doc.status in _REMOVED_STATUSES and doc.enabled is False:
        return False
    _delete_qdrant_document(tenant_id=doc.tenant_id, document_id=doc.document_id)
    if doc.path:
        cleanup_upload_path(Path(doc.path))
    doc.enabled = False
    doc.status = "removed"
    doc.error = reason
    doc.ingest_stats = dict(doc.ingest_stats or {}) | {"removed_reason": reason}
    doc.extraction_status = "removed"
    doc.extracted_candidates = []
    doc.evidence_refs = []
    doc.provenance = "documented"
    session.add(doc)
    await session.commit()
    return True


async def _pick_next_pending_paperless_document(session: AsyncSession) -> RagDocument | None:
    result = await session.execute(
        select(RagDocument)
        .where(
            RagDocument.tenant_id == RAG_SHARED_TENANT_ID,
            RagDocument.source_system == _PAPERLESS_SOURCE_SYSTEM,
            RagDocument.status.in_(("queued", "processing")),
            RagDocument.enabled.is_(True),
        )
        .order_by(RagDocument.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    return result.scalars().first()


async def process_pending_paperless_documents(
    session: AsyncSession,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Index pending Paperless RAG records through the normal RAG worker path.

    This is intentionally bounded and explicit. It gives the internal Paperless
    webhook a safe automatic ingest path without enabling the global startup
    worker in production.
    """
    from app.services.jobs.worker import process_once

    max_documents = max(0, int(limit if limit is not None else settings.paperless_sync_process_limit))
    processed = 0
    errors = 0
    document_ids: list[str] = []
    for _ in range(max_documents):
        before = await _pick_next_pending_paperless_document(session)
        if before is None:
            break
        document_ids.append(before.document_id)
        try:
            did_process = await process_once(
                session,
                picker=_pick_next_pending_paperless_document,
            )
        except Exception as exc:  # pragma: no cover - defensive boundary around worker side effects
            logger.warning(
                "paperless_process_pending_failed",
                document_id=before.document_id,
                reason=safe_error_message(exc),
            )
            errors += 1
            continue
        if not did_process:
            break
        processed += 1
    return {
        "processed": processed,
        "errors": errors,
        "limit": max_documents,
        "document_ids": document_ids,
    }


async def _list_existing_paperless_docs(session: AsyncSession) -> list[RagDocument]:
    result = await session.execute(
        select(RagDocument).where(
            RagDocument.tenant_id == RAG_SHARED_TENANT_ID,
            RagDocument.source_system == _PAPERLESS_SOURCE_SYSTEM,
        )
    )
    return list(result.scalars().all())


async def sync_paperless_to_rag(session: AsyncSession) -> Dict[str, Any]:
    """Synchronize Paperless documents into RAG only when explicitly flagged.

    Paperless remains the content-management source. A document enters the shared
    RAG only when it has the configured RAG tag (for example ``rag:enabled`` or
    ``sealai:rag``). Removing that tag, deleting the Paperless source document,
    or making it otherwise absent removes the corresponding vectors and disables
    the local RAG document record.
    """
    url = getattr(settings, "paperless_url", None)
    token = getattr(settings, "paperless_token", None)

    if not url or not token:
        logger.error("paperless_config_missing")
        return {"error": "Paperless configuration missing", "scanned": 0, "queued": 0}

    url = url.rstrip("/")
    headers = {"Authorization": f"Token {token}"}

    scanned = 0
    queued = 0
    skipped = 0
    removed = 0
    errors = 0
    ingest_ready = 0
    pilot_ready = 0
    missing_pilot_tags = 0
    tag_not_enabled = 0
    seen_source_ids: set[str] = set()

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            tag_id_to_name: dict[int, str] = {}
            tag_response = await client.get(f"{url}/api/tags/?page_size=500", headers=headers)
            if tag_response.status_code == 200:
                for tag in tag_response.json().get("results", []):
                    tag_id_to_name[tag["id"]] = tag["name"]

            response = await client.get(f"{url}/api/documents/?page_size=100", headers=headers)
            response.raise_for_status()
            data = response.json()

            paperless_docs = data.get("results", [])
            scanned = len(paperless_docs)

            ensure_upload_directory()

            for pdoc in paperless_docs:
                p_id = pdoc.get("id")
                p_title = pdoc.get("title")
                p_filename = pdoc.get("original_file_name") or f"{p_title}.pdf"
                raw_tag_field = pdoc.get("tag_names") or pdoc.get("tags") or []
                resolved_tags = [
                    tag_id_to_name[t] if isinstance(t, int) and t in tag_id_to_name else t
                    for t in (raw_tag_field if isinstance(raw_tag_field, list) else [raw_tag_field])
                ]
                p_tags = augment_paperless_tags_for_rag(
                    coerce_tag_strings(resolved_tags),
                    title=str(p_title or ""),
                    filename=str(p_filename or ""),
                )
                readiness = evaluate_paperless_tag_readiness(p_tags)
                if readiness["ingest_ready"]:
                    ingest_ready += 1
                if readiness["pilot_ready"]:
                    pilot_ready += 1
                else:
                    missing_pilot_tags += 1

                p_source_document_id = str(p_id) if p_id is not None else ""
                if p_source_document_id:
                    seen_source_ids.add(p_source_document_id)
                p_source_modified_at = _parse_source_modified_at(
                    pdoc.get("modified")
                    or pdoc.get("updated")
                    or pdoc.get("created")
                    or pdoc.get("added")
                )

                existing_source_doc = None
                if p_source_document_id:
                    existing_source_doc = await find_existing_document_by_source(
                        session,
                        tenant_id=RAG_SHARED_TENANT_ID,
                        source_system=_PAPERLESS_SOURCE_SYSTEM,
                        source_document_id=p_source_document_id,
                    )

                if not readiness["rag_enabled"]:
                    tag_not_enabled += 1
                    if existing_source_doc and await _disable_existing_paperless_doc(
                        session,
                        existing_source_doc,
                        reason="paperless_rag_flag_removed",
                    ):
                        removed += 1
                    else:
                        skipped += 1
                    continue

                safe_name = sanitize_filename(p_filename)
                route_key = resolve_route_key(tags=p_tags, filename=safe_name)
                ext = Path(safe_name).suffix.lower()
                if ext not in ALLOWED_EXT:
                    logger.debug("paperless_sync_skipped_extension", id=p_id, ext=ext)
                    if existing_source_doc and await _disable_existing_paperless_doc(
                        session,
                        existing_source_doc,
                        reason="paperless_extension_no_longer_allowed",
                    ):
                        removed += 1
                    else:
                        skipped += 1
                    continue

                if (
                    existing_source_doc
                    and existing_source_doc.status not in {"failed", "error", * _REMOVED_STATUSES}
                    and existing_source_doc.enabled is not False
                    and _same_source_modified_at(existing_source_doc.source_modified_at, p_source_modified_at)
                ):
                    existing_source_doc.tags = p_tags or existing_source_doc.tags
                    existing_source_doc.route_key = route_key
                    existing_source_doc.extraction_status = existing_source_doc.extraction_status or "not_extracted"
                    existing_source_doc.provenance = existing_source_doc.provenance or "documented"
                    session.add(existing_source_doc)
                    await session.commit()
                    skipped += 1
                    continue

                download_url = f"{url}/api/documents/{p_id}/download/"
                dl_res = await client.get(download_url, headers=headers)
                if dl_res.status_code != 200:
                    logger.error("paperless_download_failed", id=p_id, status=dl_res.status_code)
                    errors += 1
                    continue

                content = dl_res.content
                if len(content) > RAG_UPLOAD_MAX_BYTES:
                    logger.warning(
                        "paperless_sync_skipped_size",
                        id=p_id,
                        size_bytes=len(content),
                        max_bytes=RAG_UPLOAD_MAX_BYTES,
                    )
                    if existing_source_doc and await _disable_existing_paperless_doc(
                        session,
                        existing_source_doc,
                        reason="paperless_file_too_large",
                    ):
                        removed += 1
                    errors += 1
                    continue

                try:
                    content_type = validate_upload_signature(
                        extension=ext,
                        content_type=dl_res.headers.get("content-type"),
                        sample=content[:MAGIC_READ_BYTES],
                    )
                except Exception as exc:
                    logger.warning(
                        "paperless_sync_skipped_signature",
                        id=p_id,
                        ext=ext,
                        reason=str(exc),
                    )
                    if existing_source_doc and await _disable_existing_paperless_doc(
                        session,
                        existing_source_doc,
                        reason="paperless_signature_invalid",
                    ):
                        removed += 1
                    errors += 1
                    continue

                sha256 = hashlib.sha256(content).hexdigest()

                existing = existing_source_doc
                if existing is None:
                    existing = await find_existing_document(session, RAG_SHARED_TENANT_ID, sha256)

                if (
                    existing
                    and existing.status not in {"failed", "error", * _REMOVED_STATUSES}
                    and existing.enabled is not False
                    and existing.sha256 == sha256
                ):
                    if (
                        existing.source_system in (None, _PAPERLESS_SOURCE_SYSTEM)
                        and existing.source_document_id in (None, p_source_document_id)
                    ):
                        existing.enabled = True
                        existing.source_system = _PAPERLESS_SOURCE_SYSTEM
                        existing.source_document_id = p_source_document_id or existing.source_document_id
                        existing.source_modified_at = p_source_modified_at
                        existing.filename = safe_name
                        existing.content_type = content_type
                        existing.size_bytes = len(content)
                        existing.route_key = route_key
                        existing.tags = p_tags or existing.tags
                        existing.extraction_status = existing.extraction_status or "not_extracted"
                        existing.extracted_candidates = existing.extracted_candidates or []
                        existing.evidence_refs = existing.evidence_refs or []
                        existing.provenance = "documented"
                        session.add(existing)
                        await session.commit()
                    skipped += 1
                    continue

                doc_id = existing.document_id if existing else uuid.uuid4().hex
                target_dir = resolve_upload_dir(tenant_id=RAG_SHARED_TENANT_ID, document_id=doc_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / f"original{ext}"

                if existing and existing.path and existing.path != str(target_path):
                    cleanup_upload_path(Path(existing.path))
                with target_path.open("wb") as f:
                    f.write(content)

                doc = existing or RagDocument(
                    document_id=doc_id,
                    tenant_id=RAG_SHARED_TENANT_ID,
                    status="processing",
                    visibility=RAG_VISIBILITY_PUBLIC,
                    enabled=True,
                )
                doc.enabled = True
                doc.status = "processing"
                doc.error = None
                doc.visibility = RAG_VISIBILITY_PUBLIC
                doc.filename = safe_name
                doc.content_type = content_type
                doc.size_bytes = len(content)
                doc.sha256 = sha256
                doc.path = str(target_path)
                doc.tags = p_tags or None
                doc.route_key = route_key
                doc.source_system = _PAPERLESS_SOURCE_SYSTEM
                doc.source_document_id = p_source_document_id or None
                doc.source_modified_at = p_source_modified_at
                doc.extraction_status = "candidate_extraction_pending"
                doc.extracted_candidates = []
                doc.evidence_refs = [f"paperless:{p_source_document_id}"] if p_source_document_id else []
                doc.provenance = "documented"
                doc.ingest_stats = dict(doc.ingest_stats or {}) | {
                    "document_input": _document_input_payload(doc=doc, readiness=readiness),
                    "paperless_tag_readiness": readiness,
                }
                session.add(doc)
                await session.commit()

                queued += 1

            for existing in await _list_existing_paperless_docs(session):
                source_id = str(existing.source_document_id or "")
                if not source_id or source_id in seen_source_ids:
                    continue
                if await _disable_existing_paperless_doc(
                    session,
                    existing,
                    reason="paperless_source_missing",
                ):
                    removed += 1

    except Exception as exc:
        logger.exception("paperless_sync_error", error=str(exc))
        result = {
            "error": str(exc),
            "scanned": scanned,
            "queued": queued,
            "skipped": skipped,
            "removed": removed,
            "errors": errors,
            "ingest_ready": ingest_ready,
            "pilot_ready": pilot_ready,
            "missing_pilot_tags": missing_pilot_tags,
            "tag_not_enabled": tag_not_enabled,
        }
        track_rag_sync(_PAPERLESS_SOURCE_SYSTEM, "error", result)
        return result

    result = {
        "status": "success",
        "scanned": scanned,
        "queued": queued,
        "skipped": skipped,
        "removed": removed,
        "errors": errors,
        "ingest_ready": ingest_ready,
        "pilot_ready": pilot_ready,
        "missing_pilot_tags": missing_pilot_tags,
        "tag_not_enabled": tag_not_enabled,
    }
    track_rag_sync(_PAPERLESS_SOURCE_SYSTEM, "success", result)
    return result
