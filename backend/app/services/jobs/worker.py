from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.rag_document import RagDocument

IngestFunc = Callable[..., Any]


async def pick_next_rag_document(session: AsyncSession) -> RagDocument | None:
    stmt = (
        select(RagDocument)
        .where(RagDocument.status.in_(("queued", "processing")))
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
                tags=doc.tags,
                visibility=doc.visibility,
                sha256=doc.sha256,
                source="upload",
            )
        else:
            ingest_func(
                doc.path,
                tenant_id=doc.tenant_id,
                document_id=doc.document_id,
                category=doc.category,
                tags=doc.tags,
                visibility=doc.visibility,
                sha256=doc.sha256,
                source="upload",
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        stats = {"elapsed_ms": elapsed_ms}
        if file_size is not None:
            stats["file_size"] = file_size
        doc.status = "indexed"
        doc.ingest_stats = stats
        doc.error = None
        if doc.size_bytes is None and file_size is not None:
            doc.size_bytes = file_size
    except Exception as exc:
        doc.status = "error"
        doc.error = f"{type(exc).__name__}: {exc}"
    session.add(doc)
    await session.commit()


async def process_once(
    session: AsyncSession,
    *,
    ingest_func: IngestFunc | None = None,
    use_thread: bool = True,
    picker: Callable[[AsyncSession], Awaitable[Optional[RagDocument]]] = pick_next_rag_document,
) -> bool:
    doc = await picker(session)
    if not doc:
        return False
    await process_rag_document(session, doc, ingest_func=ingest_func, use_thread=use_thread)
    return True


async def start_job_worker() -> None:
    poll_sec = float(os.getenv("JOB_WORKER_POLL_SEC", "1.5"))
    while True:
        async with AsyncSessionLocal() as session:
            processed = await process_once(session)
        if not processed:
            await asyncio.sleep(poll_sec)
