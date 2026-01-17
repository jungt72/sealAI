from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.chat_transcript import ChatTranscript
from app.services.jobs.queue import enqueue_job

logger = logging.getLogger("app.history.persist")
QUEUE_NAME = "jobs:chat_transcripts"


async def persist_chat_result(
    *,
    chat_id: str,
    user_id: str,
    tenant_id: str,
    summary: str,
    contributors: Any,
    metadata: Dict[str, Any],
) -> None:
    # Strikt: ohne tenant_id/user_id nichts persistieren
    if not chat_id or not summary or not tenant_id or not user_id:
        return

    job_payload = {
        "chat_id": chat_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "summary": summary,
        "contributors": contributors,
        "metadata": metadata,
    }
    try:
        await enqueue_job(QUEUE_NAME, job_payload)
    except Exception as exc:
        logger.warning("Failed to enqueue transcript job: %s", exc)

    async def _store() -> None:
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ChatTranscript).where(
                    ChatTranscript.chat_id == chat_id,
                    ChatTranscript.tenant_id == tenant_id,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.summary = summary
                    existing.contributors = contributors
                    existing.metadata_json = metadata
                    existing.user_id = user_id
                else:
                    added = session.add(
                        ChatTranscript(
                            chat_id=chat_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            summary=summary,
                            contributors=contributors,
                            metadata_json=metadata,
                        )
                    )
                    if inspect.isawaitable(added):
                        await added
                await session.commit()
        except Exception as exc:
            logger.error("Persisting chat transcript failed: %s", exc)

    asyncio.create_task(_store())
