from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.utils.confirm_go import apply_confirm_decision
from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id
from app.models.rag_document import RagDocument
from app.services.jobs.queue import get_queue_client

IngestFunc = Callable[..., Any]
logger = logging.getLogger(__name__)

JOB_QUEUE = os.getenv("RAG_JOB_QUEUE", "rag_ingest")
SCHEDULED_QUEUE = f"{JOB_QUEUE}:scheduled"
DLQ_KEY = os.getenv("RAG_JOB_DLQ", "rag:dlq")
BRPOP_TIMEOUT_SEC = float(os.getenv("JOB_WORKER_BRPOP_TIMEOUT_SEC", "1.0"))
MAX_ATTEMPTS = int(os.getenv("JOB_WORKER_MAX_ATTEMPTS", "3"))
BACKOFF_BASE_SEC = float(os.getenv("JOB_WORKER_BACKOFF_BASE_SEC", "5"))
BACKOFF_MAX_SEC = float(os.getenv("JOB_WORKER_BACKOFF_MAX_SEC", "300"))
ENABLE_HITL_TIMEOUT_JOB = os.getenv("ENABLE_HITL_TIMEOUT_JOB", "0").strip().lower() in {"1", "true", "yes", "on"}
HITL_TIMEOUT_SCAN_INTERVAL_SEC = float(os.getenv("HITL_TIMEOUT_SCAN_INTERVAL_SEC", "300"))
HITL_TIMEOUT_HOURS = float(os.getenv("HITL_TIMEOUT_HOURS", "4"))

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
    next_timeout_scan = 0.0
    while True:
        if ENABLE_HITL_TIMEOUT_JOB and time.monotonic() >= next_timeout_scan:
            try:
                await process_hitl_timeouts_once(redis)
            except Exception:
                logger.exception("hitl_timeout_scan_failed")
            finally:
                next_timeout_scan = time.monotonic() + max(HITL_TIMEOUT_SCAN_INTERVAL_SEC, 1.0)
        processed = await consume_redis_job_once(redis)
        task = asyncio.current_task()
        if task is not None and task.cancelling():
            return
        if not processed:
            try:
                await asyncio.sleep(BRPOP_TIMEOUT_SEC)
            except asyncio.CancelledError:
                return


def _to_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_iso_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _extract_tenant_owner_from_key(key: str) -> tuple[str, str] | None:
    # chat:conversations:{tenant_id}:{owner_id}
    parts = key.split(":")
    if len(parts) < 4 or parts[0] != "chat" or parts[1] != "conversations":
        return None
    tenant_id = parts[2]
    owner_id = ":".join(parts[3:])
    if not tenant_id or not owner_id:
        return None
    return tenant_id, owner_id


async def _iter_conversation_index_keys(redis) -> list[str]:
    if hasattr(redis, "scan_iter"):
        out: list[str] = []
        async for item in redis.scan_iter(match="chat:conversations:*:*"):
            out.append(_to_text(item))
        return out
    if hasattr(redis, "keys"):
        keys = await redis.keys("chat:conversations:*:*")
        return [_to_text(item) for item in (keys or [])]
    if hasattr(redis, "zsets"):
        return [str(k) for k in getattr(redis, "zsets", {}).keys() if str(k).startswith("chat:conversations:")]
    return []


async def process_hitl_timeouts_once(redis, *, now_ts: float | None = None) -> int:
    now_ts = now_ts if now_ts is not None else time.time()
    threshold_ts = float(now_ts) - float(HITL_TIMEOUT_HOURS) * 3600.0
    graph = await get_sealai_graph_v2()
    rejected = 0

    for index_key in await _iter_conversation_index_keys(redis):
        tenant_owner = _extract_tenant_owner_from_key(index_key)
        if not tenant_owner:
            continue
        tenant_id, owner_id = tenant_owner

        conversation_ids = await redis.zrevrange(index_key, 0, -1)
        for conversation_raw in conversation_ids or []:
            chat_id = _to_text(conversation_raw)
            if not chat_id:
                continue
            try:
                checkpoint_thread_id = resolve_checkpoint_thread_id(
                    tenant_id=tenant_id,
                    user_id=owner_id,
                    chat_id=chat_id,
                )
            except ValueError:
                continue

            config = build_v2_config(thread_id=chat_id, user_id=owner_id, tenant_id=tenant_id)
            config.setdefault("configurable", {})["thread_id"] = checkpoint_thread_id
            snapshot = await graph.aget_state(config)
            values = snapshot.values if isinstance(getattr(snapshot, "values", None), dict) else {}

            if not bool(values.get("awaiting_user_confirmation")):
                continue
            if str(values.get("confirm_status") or "").lower() == "resolved":
                continue
            confirm_payload = values.get("confirm_checkpoint") if isinstance(values.get("confirm_checkpoint"), dict) else {}
            required_sub = str(confirm_payload.get("required_user_sub") or "")
            if required_sub and required_sub != owner_id:
                continue

            created_at = _parse_iso_utc(confirm_payload.get("created_at"))
            if created_at is None or created_at.timestamp() > threshold_ts:
                continue

            policy_report = dict(values.get("policy_report") or {})
            policy_report["hitl_timeout"] = {
                "reason": "timeout",
                "at": datetime.fromtimestamp(float(now_ts), tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            await apply_confirm_decision(
                graph=graph,
                config=config,
                decision="reject",
                edits={"parameters": {}, "instructions": "Auto-reject due to timeout.", "reason": "timeout"},
                as_node="confirm_checkpoint_node",
                extra_updates={"policy_report": policy_report},
            )
            rejected += 1

    return rejected


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
    try:
        await _promote_scheduled(redis)
        item = await redis.brpop(JOB_QUEUE, timeout=BRPOP_TIMEOUT_SEC)
    except asyncio.CancelledError:
        return False
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
