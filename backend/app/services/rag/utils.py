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
from app.common.redaction import redact_internal_paths, safe_error_message
from app.models.rag_document import RagDocument

logger = structlog.get_logger("services.rag.utils")

UPLOAD_ROOT = (os.getenv("RAG_UPLOAD_DIR") or "/app/data/uploads").strip() or "/app/data/uploads"
RAG_UPLOAD_MAX_BYTES = int(os.getenv("RAG_UPLOAD_MAX_BYTES", str(50 * 1024 * 1024)))
ALLOWED_VISIBILITY = {"private", "public"}
ALLOWED_EXT = {".pdf", ".txt", ".md", ".docx"}
ALLOWED_CT: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAGIC_READ_BYTES = 4096
_DOCX_ZIP_MAGIC = b"PK\x03\x04"
_UPLOAD_DIR_READY = False


def _looks_like_text(sample: bytes) -> bool:
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
            return True
        except UnicodeDecodeError:
            return False


def validate_upload_signature(*, extension: str, content_type: str | None, sample: bytes) -> str:
    ext = extension.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=415, detail=error_detail("unsupported_extension", extension=ext or None)
        )

    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower() or None
    allowed_for_ext = ALLOWED_CT.get(ext, set())
    if normalized_content_type and normalized_content_type not in allowed_for_ext:
        raise HTTPException(
            status_code=415,
            detail=error_detail("unsupported_content_type", content_type=normalized_content_type),
        )

    if ext == ".pdf" and not sample.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail=error_detail("upload_signature_mismatch"))
    if ext == ".docx" and not sample.startswith(_DOCX_ZIP_MAGIC):
        raise HTTPException(status_code=415, detail=error_detail("upload_signature_mismatch"))
    if ext in {".txt", ".md"} and not _looks_like_text(sample):
        raise HTTPException(status_code=415, detail=error_detail("upload_signature_mismatch"))

    if normalized_content_type:
        return normalized_content_type
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext == ".md":
        return "text/markdown"
    return "text/plain"

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
