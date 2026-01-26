from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.langgraph_v2.contracts import error_detail
from app.models.rag_document import RagDocument
from app.services.auth.dependencies import RequestUser, get_current_request_user_strict_tenant
from app.services.rag.rag_orchestrator import delete_qdrant_points
from app.services.jobs.queue import enqueue_job

router = APIRouter(prefix="/rag", tags=["rag"])
logger = logging.getLogger(__name__)

UPLOAD_ROOT = os.getenv("RAG_UPLOAD_DIR", "/app/data/uploads")
RAG_UPLOAD_MAX_BYTES = int(os.getenv("RAG_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024)))

ALLOWED_VISIBILITY = {"private", "public"}
ALLOWED_EXT = {".pdf", ".txt", ".md", ".docx"}
ALLOWED_CT = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _sanitize_filename(filename: str) -> str:
    base = Path(filename or "").name or "upload"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload"
    return safe


def _is_privileged(user: RequestUser) -> bool:
    roles = set(user.roles or [])
    return bool(roles.intersection({"admin"}))


def _normalize_tags(raw: Optional[str]) -> Optional[List[str]]:
    """
    Accepts:
      - None / empty -> None
      - CSV: "ptfe, test2"
      - JSON: ["ptfe","test2"]
    Returns: list[str] | None
    """
    if not raw:
        return None

    raw = raw.strip()
    if not raw:
        return None

    # Try JSON array
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                tags = [str(x).strip() for x in parsed if str(x).strip()]
                return tags or None
        except Exception:
            # fallback to CSV parsing
            pass

    # CSV fallback
    tags = [item.strip() for item in raw.split(",") if item and item.strip()]
    return tags or None


async def _find_existing_document(
    session: AsyncSession, tenant_id: str, sha256: str
) -> Optional[RagDocument]:
    stmt = (
        select(RagDocument)
        .where(RagDocument.tenant_id == tenant_id, RagDocument.sha256 == sha256)
        .order_by(RagDocument.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


def _cleanup_upload_path(target_path: Path) -> None:
    """Best-effort cleanup for duplicate/failed uploads."""
    try:
        target_path.unlink()
    except OSError:
        pass
    try:
        target_path.parent.rmdir()
    except OSError:
        pass


def _ensure_upload_dir_writable(path: Path) -> None:
    """
    Ensure the upload root exists and is writable.
    Raise HTTPException with helpful error if not.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise HTTPException(
            status_code=500,
            detail=error_detail("upload_storage_not_writable", path=str(path), reason=str(e)),
        ) from e
    except OSError as e:
        raise HTTPException(
            status_code=500,
            detail=error_detail("upload_storage_error", path=str(path), reason=str(e)),
        ) from e


@router.post("/upload")
async def upload_rag_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None),
    visibility: str = Form(default="public"),
    current_user: RequestUser = Depends(get_current_request_user_strict_tenant),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    # IMPORTANT: tenant_id must come from the tenant claim, not from user_id/sub
    tenant_id = current_user.tenant_id

    if not isinstance(visibility, str):
        visibility = getattr(visibility, "default", visibility)

    if visibility not in ALLOWED_VISIBILITY:
        raise HTTPException(status_code=400, detail=error_detail("invalid_visibility"))

    # Uploads require privileged roles (admin/editor).
    if not _is_privileged(current_user):
        raise HTTPException(status_code=403, detail=error_detail("forbidden"))

    document_id = uuid.uuid4().hex
    safe_name = _sanitize_filename(file.filename or "")
    ext = Path(safe_name).suffix.lower()

    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=415,
            detail=error_detail("unsupported_extension", extension=ext or None),
        )

    content_type = getattr(file, "content_type", None)
    if content_type:
        if content_type == "application/octet-stream":
            if not safe_name.lower().endswith(".docx"):
                raise HTTPException(
                    status_code=415,
                    detail=error_detail("unsupported_content_type", content_type=content_type),
                )
        elif content_type not in ALLOWED_CT:
            raise HTTPException(
                status_code=415,
                detail=error_detail("unsupported_content_type", content_type=content_type),
            )

    # Ensure base root is writable before building subdirs
    base_root = Path(UPLOAD_ROOT)
    _ensure_upload_dir_writable(base_root)

    target_dir = base_root / tenant_id / document_id
    _ensure_upload_dir_writable(target_dir)
    target_path = target_dir / f"original{ext}"

    digest = hashlib.sha256()
    byte_count = 0

    try:
        with target_path.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                byte_count += len(chunk)
                if byte_count > RAG_UPLOAD_MAX_BYTES:
                    await file.close()
                    _cleanup_upload_path(target_path)
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
    finally:
        try:
            await file.close()
        except Exception:
            pass

    sha256 = digest.hexdigest()
    try:
        size_bytes = target_path.stat().st_size
    except OSError:
        size_bytes = None

    tags_list = _normalize_tags(tags)
    filename = safe_name or f"upload{ext}"

    # Dedup within tenant by sha256
    existing_doc = await _find_existing_document(session, tenant_id, sha256)
    if existing_doc:
        # If existing doc is healthy, reuse and delete new bytes
        if existing_doc.status != "failed":
            _cleanup_upload_path(target_path)
            return {"document_id": existing_doc.document_id, "status": existing_doc.status}

        # Retry failed doc: reuse same document_id folder
        retry_dir = base_root / tenant_id / existing_doc.document_id
        _ensure_upload_dir_writable(retry_dir)
        retry_path = retry_dir / f"original{ext}"

        if retry_path != target_path:
            try:
                target_path.replace(retry_path)
                try:
                    target_path.parent.rmdir()
                except OSError:
                    pass
            except OSError:
                # If replace fails, keep the new path
                retry_path = target_path

        existing_doc.status = "queued"
        existing_doc.error = None
        existing_doc.visibility = visibility
        existing_doc.filename = filename
        existing_doc.content_type = content_type
        existing_doc.size_bytes = size_bytes
        existing_doc.category = category
        existing_doc.tags = tags_list
        existing_doc.sha256 = sha256
        existing_doc.path = str(retry_path)

        session.add(existing_doc)
        await session.commit()
        await session.refresh(existing_doc)

        await enqueue_job(
            "rag_ingest",
            {
                "document_id": existing_doc.document_id,
                "tenant_id": tenant_id,
                "path": str(retry_path),
                "filepath": str(retry_path),
                "original_filename": existing_doc.filename,
                "uploader_id": current_user.user_id,
                "category": category,
                "tags": tags_list,
                "visibility": visibility,
                "sha256": sha256,
            },
        )

        return {"document_id": existing_doc.document_id, "status": "queued"}

    # New doc
    doc = RagDocument(
        document_id=document_id,
        tenant_id=tenant_id,
        status="queued",
        visibility=visibility,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        category=category,
        tags=tags_list,
        sha256=sha256,
        path=str(target_path),
    )

    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    await enqueue_job(
        "rag_ingest",
        {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "path": str(target_path),
            "filepath": str(target_path),
            "original_filename": filename,
            "uploader_id": current_user.user_id,
            "category": category,
            "tags": tags_list,
            "visibility": visibility,
            "sha256": sha256,
        },
    )

    return {"document_id": document_id, "status": "queued"}


@router.get("/documents/{document_id}")
async def get_rag_document(
    document_id: str,
    current_user: RequestUser = Depends(get_current_request_user_strict_tenant),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    doc = await session.get(RagDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=error_detail("document_not_found"))

    # Strict tenant isolation
    if doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail=error_detail("forbidden"))

    return {
        "document_id": doc.document_id,
        "tenant_id": doc.tenant_id,
        "status": doc.status,
        "visibility": doc.visibility,
        "filename": doc.filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "category": doc.category,
        "tags": doc.tags,
        "sha256": doc.sha256,
        "path": doc.path,
        "error": doc.error,
        "ingest_stats": doc.ingest_stats,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


@router.get("/documents")
async def list_rag_documents(
    limit: int = Query(default=20, ge=1, le=200),
    status: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    visibility: Optional[str] = Query(default=None),
    current_user: RequestUser = Depends(get_current_request_user_strict_tenant),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    stmt = select(RagDocument).where(RagDocument.tenant_id == current_user.tenant_id)

    if status:
        stmt = stmt.where(RagDocument.status == status)
    if category:
        stmt = stmt.where(RagDocument.category == category)
    if visibility:
        if visibility not in ALLOWED_VISIBILITY:
            raise HTTPException(status_code=400, detail=error_detail("invalid_visibility"))
        stmt = stmt.where(RagDocument.visibility == visibility)

    stmt = stmt.order_by(RagDocument.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    docs = result.scalars().all()

    items: List[Dict[str, Any]] = []
    for doc in docs:
        items.append(
            {
                "document_id": doc.document_id,
                "tenant_id": doc.tenant_id,
                "status": doc.status,
                "visibility": doc.visibility,
                "filename": doc.filename,
                "content_type": doc.content_type,
                "size_bytes": doc.size_bytes,
                "category": doc.category,
                "tags": doc.tags,
                "sha256": doc.sha256,
                "path": doc.path,
                "error": doc.error,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
            }
        )

    return {"items": items}


@router.delete("/documents/{document_id}")
async def delete_rag_document(
    document_id: str,
    current_user: RequestUser = Depends(get_current_request_user_strict_tenant),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not _is_privileged(current_user):
        raise HTTPException(status_code=403, detail=error_detail("forbidden"))

    doc = await session.get(RagDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=error_detail("document_not_found"))

    # Strict tenant isolation
    if doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail=error_detail("forbidden"))

    try:
        delete_qdrant_points(tenant_id=doc.tenant_id, document_id=doc.document_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=error_detail("qdrant_delete_failed", reason=str(exc)),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=error_detail("qdrant_delete_failed", reason=str(exc)),
        ) from exc

    # Best-effort delete stored file
    try:
        p = Path(doc.path)
        if p.exists():
            p.unlink(missing_ok=True)  # py3.11+: ok
        # try remove empty dir levels
        try:
            p.parent.rmdir()
        except OSError:
            pass
    except Exception:
        # Do not fail deletion on file-system errors
        pass

    await session.delete(doc)
    await session.commit()

    return {"deleted": True, "document_id": document_id}


@router.post("/documents/{document_id}/retry")
async def retry_rag_document(
    document_id: str,
    current_user: RequestUser = Depends(get_current_request_user_strict_tenant),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    is_privileged = _is_privileged(current_user)
    if os.getenv("AUTH_DEBUG") == "1":
        user_id = getattr(current_user, "user_id", None) or getattr(current_user, "sub", None)
        print(
            "rag_retry_auth_debug",
            {
                "path": "/rag/documents/{id}/retry",
                "user_id": user_id,
                "tenant_id": current_user.tenant_id,
                "roles": list(current_user.roles or []),
                "is_privileged": is_privileged,
            },
        )

    if not is_privileged:
        raise HTTPException(status_code=403, detail=error_detail("forbidden"))

    doc = await session.get(RagDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=error_detail("document_not_found"))

    if doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail=error_detail("forbidden"))

    payload = {
        "document_id": doc.document_id,
        "tenant_id": doc.tenant_id,
        "filepath": doc.path,
        "original_filename": doc.filename,
        "uploader_id": current_user.user_id,
        "visibility": doc.visibility,
        "tags": doc.tags,
        "sha256": doc.sha256,
    }
    await enqueue_job("rag_ingest", payload)

    doc.status = "queued"
    doc.error = None
    doc.attempt_count = 0
    doc.failed_at = None
    session.add(doc)
    await session.commit()

    return {"document_id": doc.document_id, "status": "queued"}
