from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.models.rag_document import RagDocument
from app.observability.metrics import track_rag_ingest
from app.common.redaction import safe_error_message

IngestFunc = Callable[..., Any]
_PAPERLESS_SOURCE_SYSTEM = "paperless"


async def pick_next_rag_document(session: AsyncSession) -> RagDocument | None:
    stmt = (
        select(RagDocument)
        .where(
            RagDocument.status.in_(("queued", "processing")),
            RagDocument.enabled.is_(True),
        )
        .order_by(RagDocument.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def process_rag_document(
    session: AsyncSession,
    doc: RagDocument,
    *,
    ingest_func: IngestFunc | None = None,
    use_thread: bool = True,
) -> None:
    doc.status = "processing"
    session.add(doc)
    await session.commit()

    started = time.perf_counter()
    file_size = None
    try:
        file_size = os.path.getsize(doc.path)
    except OSError:
        pass
    try:
        if ingest_func is None:
            from app.services.rag import rag_ingest

            ingest_func = rag_ingest.ingest_file

        if use_thread:
            await asyncio.to_thread(
                ingest_func,
                doc.path,
                tenant_id=doc.tenant_id,
                document_id=doc.document_id,
                category=doc.category,
                route_key=doc.route_key,
                tags=doc.tags,
                visibility=doc.visibility,
                sha256=doc.sha256,
                source_system=doc.source_system,
                source_document_id=doc.source_document_id,
                source_modified_at=doc.source_modified_at,
                source=doc.source_system or "upload",
            )
        else:
            ingest_func(
                doc.path,
                tenant_id=doc.tenant_id,
                document_id=doc.document_id,
                category=doc.category,
                route_key=doc.route_key,
                tags=doc.tags,
                visibility=doc.visibility,
                sha256=doc.sha256,
                source_system=doc.source_system,
                source_document_id=doc.source_document_id,
                source_modified_at=doc.source_modified_at,
                source=doc.source_system or "upload",
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        stats = {"elapsed_ms": elapsed_ms}
        if file_size is not None:
            stats["file_size"] = file_size
        doc.status = "indexed"
        doc.provenance = doc.provenance or "documented"
        if doc.evidence_refs is None:
            doc.evidence_refs = []
        extracted_candidates, extraction_summary = (
            _extract_material_evidence_candidates_for_indexed_doc(doc)
        )
        if extracted_candidates:
            doc.extracted_candidates = extracted_candidates
            doc.extraction_status = "candidate_extraction_ready"
        else:
            if doc.extracted_candidates is None:
                doc.extracted_candidates = []
            doc.extraction_status = (
                "indexed_no_candidates" if _is_paperless_doc(doc) else "indexed"
            )
        if extraction_summary:
            stats["candidate_extraction"] = extraction_summary
        doc.ingest_stats = stats
        doc.error = None
        track_rag_ingest(doc.source_system or "upload", "indexed", elapsed_ms / 1000.0)
        if doc.size_bytes is None and file_size is not None:
            doc.size_bytes = file_size
    except Exception as exc:
        doc.status = "error"
        doc.extraction_status = "error"
        doc.error = safe_error_message(exc)
        track_rag_ingest(
            doc.source_system or "upload", "error", time.perf_counter() - started
        )
    session.add(doc)
    await session.commit()


def _extract_material_evidence_candidates_for_indexed_doc(
    doc: RagDocument,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not _is_paperless_doc(doc):
        return [], {}
    try:
        from app.services.rag.material_evidence_dry_run import (  # noqa: PLC0415
            load_material_evidence_indexed_snippet_raw_items,
        )

        candidates, summary = load_material_evidence_indexed_snippet_raw_items(
            [doc],
            tenant_id=doc.tenant_id,
            max_documents=1,
        )
        return candidates, dict(summary or {})
    except Exception as exc:  # noqa: BLE001
        return [], {
            "enabled": True,
            "source": "qdrant_payload",
            "status": "candidate_extraction_failed",
            "reason": safe_error_message(exc),
        }


def _is_paperless_doc(doc: RagDocument) -> bool:
    return str(doc.source_system or "").casefold() == _PAPERLESS_SOURCE_SYSTEM


async def process_once(
    session: AsyncSession,
    *,
    ingest_func: IngestFunc | None = None,
    use_thread: bool = True,
    picker: Callable[
        [AsyncSession], Awaitable[Optional[RagDocument]]
    ] = pick_next_rag_document,
) -> bool:
    doc = await picker(session)
    if not doc:
        return False
    await process_rag_document(
        session, doc, ingest_func=ingest_func, use_thread=use_thread
    )
    return True


async def start_job_worker() -> None:
    poll_sec = settings.job_worker_poll_sec
    while True:
        async with AsyncSessionLocal() as session:
            processed = await process_once(session)
        if not processed:
            await asyncio.sleep(poll_sec)
