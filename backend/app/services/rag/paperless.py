from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.rag.paperless_tags import evaluate_paperless_tag_readiness
from app.core.config import settings
from app.models.rag_document import RagDocument
from app.services.rag.constants import (
    RAG_SHARED_TENANT_ID,
    RAG_VISIBILITY_PUBLIC,
)
from app.services.rag.route_resolver import coerce_tag_strings, resolve_route_key
from app.services.rag.utils import (
    ALLOWED_EXT,
    cleanup_upload_path,
    ensure_upload_directory,
    find_existing_document,
    find_existing_document_by_source,
    resolve_upload_dir,
    sanitize_filename,
)

logger = structlog.get_logger("services.rag.paperless")

_PAPERLESS_SOURCE_SYSTEM = "paperless"


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

async def sync_paperless_to_rag(session: AsyncSession) -> Dict[str, Any]:
    """Fetch documents from Paperless and sync them to the global RAG tenant.
    
    This is an admin-only operation that populates the shared knowledge base.
    It avoids duplicates by checking SHA256 of the downloaded files.
    """
    url = settings.paperless_url
    token = settings.paperless_token

    if not url or not token:
        logger.error("paperless_config_missing")
        return {"error": "Paperless configuration missing", "scanned": 0, "queued": 0}

    url = url.rstrip("/")
    headers = {"Authorization": f"Token {token}"}

    scanned = 0
    queued = 0
    skipped = 0
    errors = 0
    ingest_ready = 0
    pilot_ready = 0
    missing_pilot_tags = 0

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Fetch documents from Paperless (limited to 100 recent for now)
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
                p_tags = coerce_tag_strings(pdoc.get("tag_names") or pdoc.get("tags"))
                readiness = evaluate_paperless_tag_readiness(p_tags)
                if readiness["ingest_ready"]:
                    ingest_ready += 1
                if readiness["pilot_ready"]:
                    pilot_ready += 1
                else:
                    missing_pilot_tags += 1
                p_source_document_id = str(p_id) if p_id is not None else ""
                p_source_modified_at = _parse_source_modified_at(
                    pdoc.get("modified")
                    or pdoc.get("updated")
                    or pdoc.get("created")
                    or pdoc.get("added")
                )

                safe_name = sanitize_filename(p_filename)
                route_key = resolve_route_key(tags=p_tags, filename=safe_name)
                ext = Path(safe_name).suffix.lower()
                if ext not in ALLOWED_EXT:
                    logger.debug("paperless_sync_skipped_extension", id=p_id, ext=ext)
                    skipped += 1
                    continue

                existing_source_doc = None
                if p_source_document_id:
                    existing_source_doc = await find_existing_document_by_source(
                        session,
                        tenant_id=RAG_SHARED_TENANT_ID,
                        source_system=_PAPERLESS_SOURCE_SYSTEM,
                        source_document_id=p_source_document_id,
                    )
                if (
                    existing_source_doc
                    and existing_source_doc.status not in {"failed", "error"}
                    and _same_source_modified_at(existing_source_doc.source_modified_at, p_source_modified_at)
                ):
                    skipped += 1
                    continue

                # 2. Download document to check SHA256
                # (Paperless API doesn't provide SHA256 in the list results usually)
                download_url = f"{url}/api/documents/{p_id}/download/"
                dl_res = await client.get(download_url, headers=headers)
                if dl_res.status_code != 200:
                    logger.error("paperless_download_failed", id=p_id, status=dl_res.status_code)
                    errors += 1
                    continue
                
                content = dl_res.content
                sha256 = hashlib.sha256(content).hexdigest()

                # 3. Resolve delta against existing source identity first, then fall back
                # to the existing shared-tenant sha256 dedupe.
                existing = existing_source_doc
                if existing is None:
                    existing = await find_existing_document(session, RAG_SHARED_TENANT_ID, sha256)

                if (
                    existing
                    and existing.status not in {"failed", "error"}
                    and existing.sha256 == sha256
                ):
                    if (
                        existing.source_system in (None, _PAPERLESS_SOURCE_SYSTEM)
                        and existing.source_document_id in (None, p_source_document_id)
                    ):
                        existing.source_system = _PAPERLESS_SOURCE_SYSTEM
                        existing.source_document_id = p_source_document_id or existing.source_document_id
                        existing.source_modified_at = p_source_modified_at
                        existing.filename = safe_name
                        existing.size_bytes = len(content)
                        existing.route_key = route_key
                        existing.tags = p_tags or existing.tags
                        session.add(existing)
                        await session.commit()
                    skipped += 1
                    continue

                # 4. Save to RAG storage
                doc_id = existing.document_id if existing else uuid.uuid4().hex
                target_dir = resolve_upload_dir(tenant_id=RAG_SHARED_TENANT_ID, document_id=doc_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / f"original{ext}"

                if existing and existing.path and existing.path != str(target_path):
                    try:
                        Path(existing.path).unlink()
                    except OSError:
                        pass
                with target_path.open("wb") as f:
                    f.write(content)
                
                doc = existing or RagDocument(
                    document_id=doc_id,
                    tenant_id=RAG_SHARED_TENANT_ID,
                    status="processing",
                    visibility=RAG_VISIBILITY_PUBLIC,
                    enabled=True,
                )
                doc.status = "processing"
                doc.error = None
                doc.visibility = RAG_VISIBILITY_PUBLIC
                doc.filename = safe_name
                doc.size_bytes = len(content)
                doc.sha256 = sha256
                doc.path = str(target_path)
                doc.tags = p_tags or None
                doc.route_key = route_key
                doc.source_system = _PAPERLESS_SOURCE_SYSTEM
                doc.source_document_id = p_source_document_id or None
                doc.source_modified_at = p_source_modified_at
                session.add(doc)
                await session.commit()
                
                queued += 1

    except Exception as exc:
        logger.exception("paperless_sync_error", error=str(exc))
        return {
            "error": str(exc),
            "scanned": scanned,
            "queued": queued,
            "skipped": skipped,
            "errors": errors,
            "ingest_ready": ingest_ready,
            "pilot_ready": pilot_ready,
            "missing_pilot_tags": missing_pilot_tags,
        }

    return {
        "status": "success",
        "scanned": scanned,
        "queued": queued,
        "skipped": skipped,
        "errors": errors,
        "ingest_ready": ingest_ready,
        "pilot_ready": pilot_ready,
        "missing_pilot_tags": missing_pilot_tags,
    }
