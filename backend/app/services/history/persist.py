from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from app.database import AsyncSessionLocal
from app.models.chat_transcript import ChatTranscript
from app.services.jobs.queue import enqueue_job

logger = logging.getLogger("app.history.persist")
QUEUE_NAME = "jobs:chat_transcripts"


async def persist_chat_result(
    *,
    chat_id: str,
    user_id: str,
    summary: str,
    contributors: Any,
    metadata: Dict[str, Any],
) -> None:
    if not chat_id or not summary:
        return

    job_payload = {
        "chat_id": chat_id,
        "user_id": user_id,
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
                existing = await session.get(ChatTranscript, chat_id)
                if existing:
                    existing.summary = summary
                    existing.contributors = contributors
                    existing.metadata_json = metadata
                else:
                    session.add(
                        ChatTranscript(
                            chat_id=chat_id,
                            user_id=user_id,
                            summary=summary,
                            contributors=contributors,
                            metadata_json=metadata,
                        )
                    )
                await session.commit()
        except Exception as exc:
            logger.error("Persisting chat transcript failed: %s", exc)

    asyncio.create_task(_store())
