from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.langgraph_v2.contracts import error_detail
from app.database import get_db
from app.models.rag_document import RagDocument
from app.services.auth.dependencies import RequestUser, get_current_request_user, canonical_tenant_id
from app.services.jobs.queue import enqueue_job

router = APIRouter(prefix="/rag", tags=["rag"])

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


def _normalize_tags(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    tags = [item.strip() for item in raw.split(",") if item and item.strip()]
    return tags or None


def _sanitize_filename(filename: str) -> str:
    base = Path(filename or "").name or "upload"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload"
    return safe


def _is_admin(user: RequestUser) -> bool:
    return "admin" in (user.roles or [])


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
    try:
        target_path.unlink()
    except OSError:
        pass
    try:
        target_path.parent.rmdir()
    except OSError:
        pass


@router.post("/upload")
async def upload_rag_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None),
    visibility: str = Form(default="private"),
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_id = canonical_tenant_id(current_user)
    if visibility not in ALLOWED_VISIBILITY:
        raise HTTPException(status_code=400, detail=error_detail("invalid_visibility"))

    document_id = uuid.uuid4().hex
    safe_name = _sanitize_filename(file.filename or "")
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=415, detail=error_detail("unsupported_extension", extension=ext or None)
        )
    content_type = getattr(file, "content_type", None)
    if content_type and content_type not in ALLOWED_CT:
        raise HTTPException(
            status_code=415,
            detail=error_detail("unsupported_content_type", content_type=content_type),
        )
    target_dir = Path(UPLOAD_ROOT) / tenant_id / document_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"original{ext}"

    digest = hashlib.sha256()
    byte_count = 0
    with target_path.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
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
    sha256 = digest.hexdigest()
    try:
        size_bytes = target_path.stat().st_size
    except OSError:
        size_bytes = None

    tags_list = _normalize_tags(tags)
    filename = safe_name or f"upload{ext}"
    existing_doc = await _find_existing_document(session, tenant_id, sha256)
    if existing_doc:
        if existing_doc.status != "failed":
            _cleanup_upload_path(target_path)
            return {"document_id": existing_doc.document_id, "status": existing_doc.status}

        retry_dir = Path(UPLOAD_ROOT) / tenant_id / existing_doc.document_id
        retry_dir.mkdir(parents=True, exist_ok=True)
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
                "category": category,
                "tags": tags_list,
                "visibility": visibility,
                "sha256": sha256,
            },
        )

        return {"document_id": existing_doc.document_id, "status": "queued"}

    doc = RagDocument(
        document_id=document_id,
        tenant_id=tenant_id,
        status="queued",
        visibility=visibility,
        filename=filename,
        content_type=content_type,
        size_bytes=None,
        category=category,
        tags=tags_list,
        sha256=sha256,
        path=str(target_path),
    )
    doc.size_bytes = size_bytes
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    await enqueue_job(
        "rag_ingest",
        {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "path": str(target_path),
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
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    doc = await session.get(RagDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=error_detail("document_not_found"))

    if doc.tenant_id != canonical_tenant_id(current_user):
        if not (doc.visibility == "public" and _is_admin(current_user)):
            raise HTTPException(status_code=403, detail=error_detail("forbidden"))

    return {
        "document_id": doc.document_id,
        "status": doc.status,
        "error": doc.error,
        "ingest_stats": doc.ingest_stats,
    }


@router.get("/documents")
async def list_rag_documents(
    limit: int = Query(default=20, ge=1, le=200),
    status: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    visibility: Optional[str] = Query(default=None),
    current_user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    stmt = select(RagDocument).where(RagDocument.tenant_id == canonical_tenant_id(current_user))
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
                "ingest_stats": doc.ingest_stats,
                "error": doc.error,
            }
        )
    return {"items": items}
