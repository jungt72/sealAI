from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.rag_document import RagDocument
from app.services.jobs.queue import get_queue_client

IngestFunc = Callable[..., Any]

JOB_QUEUE = os.getenv("RAG_JOB_QUEUE", "rag_ingest")
SCHEDULED_QUEUE = f"{JOB_QUEUE}:scheduled"
DLQ_KEY = os.getenv("RAG_JOB_DLQ", "rag:dlq")
BRPOP_TIMEOUT_SEC = float(os.getenv("JOB_WORKER_BRPOP_TIMEOUT_SEC", "1.0"))
MAX_ATTEMPTS = int(os.getenv("JOB_WORKER_MAX_ATTEMPTS", "3"))
BACKOFF_BASE_SEC = float(os.getenv("JOB_WORKER_BACKOFF_BASE_SEC", "5"))
BACKOFF_MAX_SEC = float(os.getenv("JOB_WORKER_BACKOFF_MAX_SEC", "300"))

REQUIRED_KEYS = {
    "tenant_id",
    "document_id",
    "filepath",
    "original_filename",
    "uploader_id",
    "visibility",
    "tags",
    "sha256",
}


async def pick_next_rag_document(session: AsyncSession) -> RagDocument | None:
    stmt = (
        select(RagDocument)
        .where(RagDocument.status == "queued")
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
            stats = await asyncio.to_thread(
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
            stats = ingest_func(
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
        stats = stats if isinstance(stats, dict) else {}
        stats.setdefault("elapsed_ms", elapsed_ms)
        if file_size is not None:
            stats["file_size"] = file_size
        doc.status = "done"
        doc.ingest_stats = stats
        doc.error = None
        if doc.size_bytes is None and file_size is not None:
            doc.size_bytes = file_size
    except Exception as exc:
        doc.status = "failed"
        doc.error = f"{type(exc).__name__}: {exc}"
        doc.attempt_count = int(doc.attempt_count or 0) + 1
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        error_stage = getattr(exc, "stage", None)
        stats = {"elapsed_ms": elapsed_ms}
        if error_stage:
            stats["error_stage"] = error_stage
        loader_used = getattr(exc, "loader", None)
        if loader_used:
            stats["loader"] = loader_used
        chunks = getattr(exc, "chunks", None)
        if isinstance(chunks, int):
            stats["chunks"] = chunks
        if file_size is not None:
            stats["file_size"] = file_size
        doc.ingest_stats = stats
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
    redis = get_queue_client()
    while True:
        processed = await consume_redis_job_once(redis)
        if not processed:
            await asyncio.sleep(BRPOP_TIMEOUT_SEC)


async def _promote_scheduled(redis) -> None:
    now = time.time()
    jobs = await redis.zrangebyscore(SCHEDULED_QUEUE, 0, now)
    if not jobs:
        return
    await redis.zrem(SCHEDULED_QUEUE, *jobs)
    for job in jobs:
        await redis.rpush(JOB_QUEUE, job)


def _compute_backoff(attempt: int) -> float:
    return min(BACKOFF_BASE_SEC * (2 ** attempt), BACKOFF_MAX_SEC)


async def _requeue_with_delay(redis, payload: dict, delay_sec: float) -> None:
    score = time.time() + max(delay_sec, 0.0)
    await redis.zadd(SCHEDULED_QUEUE, {json.dumps(payload, ensure_ascii=False): score})


async def _load_doc(session: AsyncSession, payload: dict) -> RagDocument | None:
    doc_id = payload.get("document_id")
    tenant_id = payload.get("tenant_id")
    if not doc_id or not tenant_id:
        return None
    doc = await session.get(RagDocument, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        return None
    return doc


def _normalize_payload(payload: dict) -> dict:
    if "filepath" not in payload and "path" in payload:
        payload["filepath"] = payload.get("path")
    return payload


async def _handle_job_payload(
    payload: dict,
    *,
    session: AsyncSession,
    redis,
    ingest_func: IngestFunc | None = None,
    use_thread: bool = True,
) -> None:
    payload = _normalize_payload(payload)
    missing = REQUIRED_KEYS.difference(payload.keys())
    if missing:
        return
    doc = await _load_doc(session, payload)
    if not doc:
        return
    await process_rag_document(session, doc, ingest_func=ingest_func, use_thread=use_thread)
    if doc.status != "failed":
        return
    attempts = int(doc.attempt_count or 0)
    if attempts >= MAX_ATTEMPTS:
        doc.failed_at = datetime.now(timezone.utc)
        session.add(doc)
        await session.commit()
        await redis.rpush(DLQ_KEY, json.dumps(payload, ensure_ascii=False))
        return
    delay = _compute_backoff(attempts)
    await _requeue_with_delay(redis, payload, delay)


async def consume_redis_job_once(
    redis,
    *,
    ingest_func: IngestFunc | None = None,
    use_thread: bool = True,
    session_factory: Callable[[], AsyncSession] = AsyncSessionLocal,
) -> bool:
    await _promote_scheduled(redis)
    item = await redis.brpop(JOB_QUEUE, timeout=BRPOP_TIMEOUT_SEC)
    if not item:
        return False
    _queue, raw = item
    try:
        payload = json.loads(raw)
    except Exception:
        return True
    async with session_factory() as session:
        await _handle_job_payload(payload, session=session, redis=redis, ingest_func=ingest_func, use_thread=use_thread)
    return True
