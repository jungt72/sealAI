from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import error_detail
from app.models.rag_document import RagDocument
from app.core.config import settings

logger = structlog.get_logger("services.rag.utils")

UPLOAD_ROOT = (os.getenv("RAG_UPLOAD_DIR") or "/app/data/uploads").strip() or "/app/data/uploads"
RAG_UPLOAD_MAX_BYTES = int(os.getenv("RAG_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024)))
ALLOWED_VISIBILITY = {"private", "public"}
ALLOWED_EXT = {".pdf", ".txt", ".md", ".docx"}
ALLOWED_CT = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_UPLOAD_DIR_READY = False

def normalize_tags(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    tags = [item.strip() for item in raw.split(",") if item and item.strip()]
    return tags or None

def sanitize_filename(filename: str) -> str:
    base = Path(filename or "").name or "upload"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload"
    return safe

async def find_existing_document(
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


async def find_existing_document_by_source(
    session: AsyncSession,
    *,
    tenant_id: str,
    source_system: str,
    source_document_id: str,
) -> Optional[RagDocument]:
    stmt = (
        select(RagDocument)
        .where(
            RagDocument.tenant_id == tenant_id,
            RagDocument.source_system == source_system,
            RagDocument.source_document_id == source_document_id,
        )
        .order_by(RagDocument.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()

def cleanup_upload_path(target_path: Path) -> None:
    try:
        target_path.unlink()
    except OSError:
        pass
    try:
        target_path.parent.rmdir()
    except OSError:
        pass

def resolve_upload_dir(*, tenant_id: str, document_id: str) -> Path:
    root = Path(UPLOAD_ROOT).resolve()
    target_dir = (root / tenant_id / document_id).resolve()
    if target_dir != root and root not in target_dir.parents:
        raise HTTPException(status_code=500, detail="Invalid upload path")
    return target_dir

def ensure_upload_directory() -> Path:
    global _UPLOAD_DIR_READY
    root = Path(UPLOAD_ROOT).resolve()
    if _UPLOAD_DIR_READY and root.is_dir():
        return root
    try:
        root.mkdir(parents=True, exist_ok=True)
        _UPLOAD_DIR_READY = True
    except PermissionError as exc:
        logger.error(
            "rag_upload_root_permission_denied",
            upload_root=str(root),
            uid=os.getuid(),
            gid=os.getgid(),
            error=str(exc),
        )
        raise
    return root
