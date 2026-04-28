from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import error_detail
from app.services.rag.constants import (
    RAG_SHARED_TENANT_ID,
    RAG_VISIBILITY_PUBLIC,
    RAG_VISIBILITY_PRIVATE,
    RAG_SCOPE_GLOBAL,
    ALLOWED_VISIBILITY,
    ALLOWED_SCOPES,
)

from app.core.config import settings
from app.database import get_db
from app.models.rag_document import RagDocument
from app.services.auth.dependencies import RequestUser, get_current_request_user, is_rag_admin

from app.services.rag.route_resolver import resolve_route_key
from app.services.rag.utils import (
    MAGIC_READ_BYTES,
    RAG_UPLOAD_MAX_BYTES,
    cleanup_upload_path,
    ensure_upload_directory,
    find_existing_document,
    normalize_tags,
    redact_internal_paths,
    resolve_upload_dir,
    safe_error_message,
    sanitize_filename,
    validate_upload_signature,
)

router = APIRouter(prefix="/rag", tags=["rag"])
internal_router = APIRouter(prefix="/internal/rag", tags=["rag-internal"])
logger = structlog.get_logger("api.rag")


def _request_tenant_id(current_user: RequestUser) -> str:
    return str(current_user.tenant_id or current_user.user_id)


async def _check_upload_rate_limit(tenant_id: str) -> None:
    """Sliding-window rate limit using Redis incr/expire (no extra dependencies).

    Raises HTTP 429 when the tenant exceeds ``settings.rate_limit_upload``
    requests within ``settings.rate_limit_window_s`` seconds.
    Silently skips when Redis is unavailable (fail-open to avoid blocking uploads).
    """
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return
    try:
        from redis.asyncio import Redis

        window = settings.rate_limit_window_s
        limit = settings.rate_limit_upload
        bucket = int(time.time()) // window
        key = f"rl:rag_upload:{tenant_id}:{bucket}"
        async with Redis.from_url(redis_url, decode_responses=True) as r:
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, window * 2)
        if count > limit:
            logger.warning(
                "rag_upload_rate_limited",
                tenant_id=tenant_id,
                count=count,
                limit=limit,
                window_s=window,
            )
            raise HTTPException(
                status_code=429,
                detail=error_detail(
                    "rate_limit_exceeded",
                    limit=limit,
                    window_s=window,
                    retry_after=window - (int(time.time()) % window),
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("rag_upload_rate_limit_check_skipped", reason=str(exc))


QDRANT_URL = (os.getenv("QDRANT_URL") or "http://qdrant:6333").rstrip("/")
QDRANT_API_KEY = (os.getenv("QDRANT_API_KEY") or "").strip() or None
QDRANT_COLLECTION = (os.getenv("QDRANT_COLLECTION") or "sealai_knowledge").strip()


async def _load_rag_document_for_user(
    *,
    session: AsyncSession,
    document_id: str,
    current_user: RequestUser,
    allow_shared_admin: bool = False,
) -> RagDocument | None:
    request_tenant_id = _request_tenant_id(current_user)
    result = await session.execute(
        select(RagDocument)
        .where(RagDocument.document_id == document_id)
        .where(RagDocument.tenant_id == request_tenant_id)
        .limit(1)
    )
    doc = result.scalar_one_or_none()
    if doc is not None or not (allow_shared_admin and is_rag_admin(current_user)):
        return doc
    shared_result = await session.execute(
        select(RagDocument)
        .where(RagDocument.document_id == document_id)
        .where(RagDocument.tenant_id == RAG_SHARED_TENANT_ID)
        .limit(1)
    )
    return shared_result.scalar_one_or_none()


def _require_paperless_webhook_token(received_token: str | None) -> None:
    expected = (getattr(settings, "paperless_webhook_token", None) or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=error_detail("paperless_webhook_not_configured"),
        )
    if not received_token or not hmac.compare_digest(received_token, expected):
        raise HTTPException(
            status_code=403,
            detail=error_detail("paperless_webhook_forbidden"),
        )


def _safe_backend_error_detail(code: str, exc: BaseException) -> dict[str, Any]:
    return error_detail(code, reason=safe_error_message(exc))


def _qdrant_client():
    try:
        from qdrant_client import QdrantClient  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=_safe_backend_error_detail("qdrant_client_unavailable", exc),
        ) from exc
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def _qdrant_vector_count(*, tenant_id: str, document_id: str) -> int:
    try:
        from qdrant_client import models as qmodels  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=_safe_backend_error_detail("qdrant_models_unavailable", exc),
        ) from exc
    client = _qdrant_client()
    result = client.count(
        collection_name=QDRANT_COLLECTION,
        count_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="tenant_id",
                    match=qmodels.MatchValue(value=tenant_id),
                ),
                qmodels.FieldCondition(
                    key="document_id",
                    match=qmodels.MatchValue(value=document_id),
                ),
            ]
        ),
        exact=True,
    )
    return int(getattr(result, "count", 0) or 0)


def _qdrant_delete_document(*, tenant_id: str, document_id: str) -> None:
    try:
        from qdrant_client import models as qmodels  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=_safe_backend_error_detail("qdrant_models_unavailable", exc),
        ) from exc
    client = _qdrant_client()
    client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="tenant_id",
                        match=qmodels.MatchValue(value=tenant_id),
                    ),
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=document_id),
                    ),
                ]
            )
        ),
        wait=True,
    )


def _extract_text_preview_for_delta(path: Path, *, limit: int = 12000) -> str:
    try:
        from app.services.rag.rag_ingest import load_document  # noqa: PLC0415

        docs = load_document(str(path))
    except Exception as exc:  # noqa: BLE001
        logger.debug("document_delta_text_extraction_skipped", reason=safe_error_message(exc))
        return ""
    parts: list[str] = []
    remaining = limit
    for doc in docs:
        content = str(getattr(doc, "page_content", "") or "").strip()
        if not content:
            continue
        parts.append(content[:remaining])
        remaining -= len(parts[-1])
        if remaining <= 0:
            break
    return "\n\n".join(parts)


async def _try_persist_document_delta_for_case(
    *,
    current_user: RequestUser,
    case_id: str | None,
    doc: RagDocument,
    path: Path,
) -> dict[str, Any] | None:
    normalized_case_id = str(case_id or "").strip()
    if not normalized_case_id:
        return None
    text_preview = _extract_text_preview_for_delta(path)
    try:
        from app.agent.api.loaders import (  # noqa: PLC0415
            _load_live_governed_state,
            _persist_live_governed_state,
        )
        from app.agent.api.utils import _with_case_event  # noqa: PLC0415
        from app.agent.domain.case_delta import build_document_delta_event  # noqa: PLC0415
        from app.agent.domain.document_delta import document_delta_from_text  # noqa: PLC0415

        delta = document_delta_from_text(
            text=text_preview,
            filename=doc.filename,
            category=doc.category,
            tags=doc.tags or [],
        )
        if not delta.fields:
            return {
                "case_id": normalized_case_id,
                "document_id": doc.document_id,
                "status": "no_fields_detected",
                "field_count": 0,
                "fields": [],
            }
        governed = await _load_live_governed_state(
            current_user=current_user,
            session_id=normalized_case_id,
            create_if_missing=True,
        )
        event = build_document_delta_event(
            case_id=normalized_case_id,
            document_id=doc.document_id,
            filename=doc.filename,
            delta=delta,
            persistence_marker=governed.persistence_marker if governed else None,
        )
        updated = _with_case_event(governed, event=event) if governed else None
        if updated is None:
            return None
        await _persist_live_governed_state(
            current_user=current_user,
            session_id=normalized_case_id,
            state=updated,
        )
        return {
            "case_id": normalized_case_id,
            "document_id": doc.document_id,
            "event_id": event.event_id,
            "status": "proposed",
            "field_count": len(delta.fields),
            "fields": [field.model_dump(mode="json") for field in delta.fields],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "document_delta_persist_failed",
            case_id=normalized_case_id,
            document_id=doc.document_id,
            reason=safe_error_message(exc),
        )
        return {
            "case_id": normalized_case_id,
            "document_id": doc.document_id,
            "status": "error",
            "error": "document_candidate_extraction_failed",
            "field_count": 0,
            "fields": [],
        }
@router.get("/health")
async def rag_health() -> Dict[str, Any]:
    """Health check for the RAG subsystem."""
    return {"status": "ok", "service": "rag", "timestamp": time.time()}


@router.post("/upload")
async def upload_rag_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None),
    visibility: str = Form(default="private"),
    scope: str = Form(default="tenant"),
    case_id: Optional[str] = Form(default=None),
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        ensure_upload_directory()
    except PermissionError as exc:
        raise HTTPException(status_code=500, detail="Storage permission denied") from exc

    if scope == RAG_SCOPE_GLOBAL:
        if not is_rag_admin(current_user):
            raise HTTPException(status_code=403, detail="Admin rights required for global scope")
        tenant_id = RAG_SHARED_TENANT_ID
        visibility = RAG_VISIBILITY_PUBLIC
    else:
        tenant_id = _request_tenant_id(current_user)

    await _check_upload_rate_limit(tenant_id)
    if visibility not in ALLOWED_VISIBILITY:
        raise HTTPException(status_code=400, detail=error_detail("invalid_visibility"))

    document_id = uuid.uuid4().hex
    safe_name = sanitize_filename(file.filename or "")
    ext = Path(safe_name).suffix.lower()
    target_dir = resolve_upload_dir(tenant_id=tenant_id, document_id=document_id)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        logger.error(
            "rag_upload_storage_permission_denied",
            tenant_id=tenant_id,
            document_id=document_id,
            upload_dir=str(target_dir),
            uid=os.getuid(),
            gid=os.getgid(),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Storage permission denied") from exc
    target_path = target_dir / f"original{ext}"

    digest = hashlib.sha256()
    byte_count = 0
    signature_sample = b""
    content_type = None
    with target_path.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            if len(signature_sample) < MAGIC_READ_BYTES:
                remaining = MAGIC_READ_BYTES - len(signature_sample)
                signature_sample += chunk[:remaining]
            if byte_count > RAG_UPLOAD_MAX_BYTES:
                await file.close()
                try:
                    target_path.unlink()
                except OSError:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=error_detail(
                        "upload_too_large",
                        max_bytes=RAG_UPLOAD_MAX_BYTES,
                        bytes=byte_count,
                    ),
                )
            digest.update(chunk)
            handle.write(chunk)
    await file.close()
    try:
        content_type = validate_upload_signature(
            extension=ext,
            content_type=getattr(file, "content_type", None),
            sample=signature_sample,
        )
    except HTTPException:
        cleanup_upload_path(target_path)
        raise
    sha256 = digest.hexdigest()
    try:
        size_bytes = target_path.stat().st_size
    except OSError:
        size_bytes = None

    tags_list = normalize_tags(tags)
    filename = safe_name or f"upload{ext}"
    route_key = resolve_route_key(tags=tags_list, category=category, filename=filename)
    existing_doc = await find_existing_document(session, tenant_id, sha256)
    if existing_doc:
        if existing_doc.status not in {"failed", "error"}:
            cleanup_upload_path(target_path)
            document_delta = await _try_persist_document_delta_for_case(
                current_user=current_user,
                case_id=case_id,
                doc=existing_doc,
                path=Path(existing_doc.path),
            )
            return {
                "document_id": existing_doc.document_id,
                "status": existing_doc.status,
                "document_delta": document_delta,
            }

        retry_dir = resolve_upload_dir(tenant_id=tenant_id, document_id=existing_doc.document_id)
        try:
            retry_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            logger.error(
                "rag_upload_storage_permission_denied",
                tenant_id=tenant_id,
                document_id=existing_doc.document_id,
                upload_dir=str(retry_dir),
                uid=os.getuid(),
                gid=os.getgid(),
                error=str(exc),
            )
            raise HTTPException(status_code=500, detail="Storage permission denied") from exc
        retry_path = retry_dir / f"original{ext}"
        if retry_path != target_path:
            try:
                target_path.replace(retry_path)
                try:
                    target_path.parent.rmdir()
                except OSError:
                    pass
            except OSError:
                retry_path = target_path

        existing_doc.status = "processing"
        existing_doc.error = None
        existing_doc.visibility = visibility
        existing_doc.filename = filename
        existing_doc.content_type = content_type
        existing_doc.size_bytes = size_bytes
        existing_doc.category = category
        existing_doc.route_key = route_key
        existing_doc.tags = tags_list
        existing_doc.sha256 = sha256
        existing_doc.path = str(retry_path)
        existing_doc.enabled = True
        existing_doc.extraction_status = "candidate_extraction_pending" if case_id else (existing_doc.extraction_status or "not_extracted")
        existing_doc.extracted_candidates = existing_doc.extracted_candidates or []
        existing_doc.evidence_refs = existing_doc.evidence_refs or []
        existing_doc.provenance = "documented"
        session.add(existing_doc)
        await session.commit()
        await session.refresh(existing_doc)

        document_delta = await _try_persist_document_delta_for_case(
            current_user=current_user,
            case_id=case_id,
            doc=existing_doc,
            path=Path(existing_doc.path),
        )
        return {
            "document_id": existing_doc.document_id,
            "status": "processing",
            "document_delta": document_delta,
        }

    doc = RagDocument(
        document_id=document_id,
        tenant_id=tenant_id,
        status="processing",
        visibility=visibility,
        enabled=True,
        filename=filename,
        content_type=content_type,
        size_bytes=None,
        category=category,
        route_key=route_key,
        tags=tags_list,
        sha256=sha256,
        path=str(target_path),
        extraction_status="candidate_extraction_pending" if case_id else "not_extracted",
        extracted_candidates=[],
        evidence_refs=[],
        provenance="documented",
    )
    doc.size_bytes = size_bytes
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    document_delta = await _try_persist_document_delta_for_case(
        current_user=current_user,
        case_id=case_id,
        doc=doc,
        path=target_path,
    )
    return {"document_id": doc.document_id, "status": doc.status, "document_delta": document_delta}


@router.post("/sync-paperless")
async def sync_paperless(
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Manually trigger a sync from Paperless to the global RAG tenant."""
    if not is_rag_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin rights required for Paperless sync")

    from app.services.rag.paperless import sync_paperless_to_rag
    return await sync_paperless_to_rag(session)


@internal_router.post("/ingest")
async def ingest_paperless_webhook(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    x_sealai_webhook_token: Optional[str] = Header(default=None, alias="X-SeaLAI-Webhook-Token"),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Minimal internal webhook entry for the first Paperless ingest pilot."""
    _require_paperless_webhook_token(x_sealai_webhook_token)

    payload = payload or {}
    document_id = payload.get("document_id")
    if document_id in (None, ""):
        raise HTTPException(
            status_code=400,
            detail=error_detail("paperless_webhook_invalid_payload", field="document_id"),
        )

    from app.services.rag.paperless import sync_paperless_to_rag

    result = await sync_paperless_to_rag(session)
    return {
        "status": "accepted",
        "document_id": str(document_id),
        "sync": result,
    }


@router.get("/documents/{document_id}")
async def get_rag_document(
    document_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    doc = await _load_rag_document_for_user(
        session=session,
        document_id=document_id,
        current_user=current_user,
        allow_shared_admin=True,
    )
    if not doc:
        raise HTTPException(status_code=404, detail=error_detail("document_not_found"))

    return {
        "document_id": doc.document_id,
        "status": doc.status,
        "error": redact_internal_paths(doc.error),
        "ingest_stats": redact_internal_paths(doc.ingest_stats),
        "enabled": doc.enabled,
        "extraction_status": doc.extraction_status,
        "extracted_candidates": doc.extracted_candidates or [],
        "evidence_refs": doc.evidence_refs or [],
        "provenance": doc.provenance,
    }


@router.get("/documents/{document_id}/health-check")
async def rag_document_health_check(
    document_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    doc = await _load_rag_document_for_user(
        session=session,
        document_id=document_id,
        current_user=current_user,
        allow_shared_admin=True,
    )
    if not doc:
        raise HTTPException(status_code=404, detail=error_detail("document_not_found"))

    file_exists = Path(doc.path).exists()
    qdrant_points = 0
    qdrant_error = None
    try:
        qdrant_points = _qdrant_vector_count(tenant_id=doc.tenant_id, document_id=doc.document_id)
    except Exception as exc:
        qdrant_error = safe_error_message(exc)

    status_now = str(doc.status or "")
    indexed_like = status_now in {"indexed", "done"}
    vector_missing = indexed_like and qdrant_points <= 0
    file_missing = indexed_like and not file_exists

    issues: List[str] = []
    if file_missing:
        issues.append("missing_file_for_indexed_document")
    if vector_missing:
        issues.append("missing_qdrant_vectors_for_indexed_document")
    if qdrant_error:
        issues.append("qdrant_check_failed")

    return {
        "document_id": doc.document_id,
        "tenant_id": doc.tenant_id,
        "status": status_now,
        "collection": QDRANT_COLLECTION,
        "filesystem": {
            "exists": file_exists,
        },
        "qdrant": {
            "points": qdrant_points,
            "error": qdrant_error,
        },
        "is_consistent": len(issues) == 0,
        "issues": issues,
    }


@router.post("/documents/{document_id}/reingest")
async def reingest_rag_document(
    document_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    doc = await _load_rag_document_for_user(
        session=session,
        document_id=document_id,
        current_user=current_user,
        allow_shared_admin=True,
    )
    if not doc:
        raise HTTPException(status_code=404, detail=error_detail("document_not_found"))

    if not Path(doc.path).exists():
        raise HTTPException(
            status_code=409,
            detail=error_detail("source_file_missing"),
        )

    doc.status = "processing"
    doc.error = None
    doc.ingest_stats = None
    doc.enabled = True
    doc.extraction_status = doc.extraction_status or "not_extracted"
    doc.provenance = doc.provenance or "documented"
    session.add(doc)
    await session.commit()

    return {"document_id": doc.document_id, "status": doc.status}


@router.delete("/documents/{document_id}")
async def delete_rag_document(
    document_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    doc = await _load_rag_document_for_user(
        session=session,
        document_id=document_id,
        current_user=current_user,
        allow_shared_admin=True,
    )
    if not doc:
        raise HTTPException(status_code=404, detail=error_detail("document_not_found"))

    try:
        _qdrant_delete_document(tenant_id=doc.tenant_id, document_id=doc.document_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=_safe_backend_error_detail("qdrant_delete_failed", exc),
        ) from exc

    path = Path(doc.path)
    if path.exists():
        cleanup_upload_path(path)

    await session.delete(doc)
    await session.commit()
    return {"document_id": document_id, "deleted": True}


@router.get("/documents")
async def list_rag_documents(
    limit: int = Query(default=20, ge=1, le=200),
    status: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    visibility: Optional[str] = Query(default=None),
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    stmt = select(RagDocument).where(RagDocument.tenant_id == _request_tenant_id(current_user))
    if status:
        stmt = stmt.where(RagDocument.status == status)
    if category:
        stmt = stmt.where(RagDocument.category == category)
    if visibility:
        stmt = stmt.where(RagDocument.visibility == visibility)
    stmt = stmt.order_by(RagDocument.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    items = []
    for doc in result.scalars().all():
        items.append(
            {
                "document_id": doc.document_id,
                "filename": doc.filename,
                "content_type": doc.content_type,
                "size_bytes": doc.size_bytes,
                "category": doc.category,
                "tags": doc.tags,
                "visibility": doc.visibility,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "ingest_stats": redact_internal_paths(doc.ingest_stats),
                "error": redact_internal_paths(doc.error),
                "enabled": doc.enabled,
                "extraction_status": doc.extraction_status,
                "extracted_candidates": doc.extracted_candidates or [],
                "evidence_refs": doc.evidence_refs or [],
                "provenance": doc.provenance,
            }
        )
    return {"items": items}
