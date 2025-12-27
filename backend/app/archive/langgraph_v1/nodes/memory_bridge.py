from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List

from langchain_core.messages import SystemMessage
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError

from app.database import AsyncSessionLocal
from app.langgraph.state import LongTermMemoryRef, MemoryInjection, SealAIState
from app.models.chat_transcript import ChatTranscript
from app.services.memory import memory_core

try:  # psycopg2 may be missing in some contexts (e.g., unit tests).
    from psycopg2.errors import UndefinedTable
except Exception:  # pragma: no cover - optional dependency
    UndefinedTable = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

MAX_LTM_ITEMS = int(os.getenv("MEMORY_BRIDGE_MAX_ITEMS", "3"))


async def _load_last_transcript(user_id: str) -> Dict[str, Any]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ChatTranscript)
            .where(ChatTranscript.user_id == user_id)
            .order_by(ChatTranscript.created_at.desc())
            .limit(1)
        )
        try:
            result = await session.execute(stmt)
        except ProgrammingError as exc:
            if await _handle_missing_transcript_table(session, user_id, exc):
                return {}
            raise
        row = result.scalar_one_or_none()
        if not row:
            return {}
        return {
            "chat_id": row.chat_id,
            "summary": row.summary or "",
            "metadata": row.metadata_json or {},
        }


async def _load_ltm_refs(user_id: str) -> List[LongTermMemoryRef]:
    try:
        entries = await asyncio.to_thread(memory_core.ltm_export_all, user=user_id, chat_id=None, limit=MAX_LTM_ITEMS)
    except Exception as exc:  # pragma: no cover - network/driver issues
        logger.warning("memory_bridge: ltm_export_all failed: %s", exc)
        return []

    refs: List[LongTermMemoryRef] = []
    for entry in entries:
        payload = entry.get("payload") or {}
        summary = str(payload.get("text") or payload.get("summary") or "").strip()
        if not summary:
            continue
        refs.append(
            LongTermMemoryRef(
                storage=str(payload.get("storage") or "qdrant"),
                id=str(entry.get("id")),
                summary=summary,
                score=float(payload.get("score") or payload.get("confidence") or 0.0),
            )
        )
    return refs[:MAX_LTM_ITEMS]


def _build_injections(transcript: Dict[str, Any], refs: List[LongTermMemoryRef]) -> List[MemoryInjection]:
    injections: List[MemoryInjection] = []
    if transcript.get("summary"):
        injections.append(
            MemoryInjection(summary=str(transcript["summary"]).strip(), relevance=0.95, source="postgres")
        )
    for ref in refs:
        summary = ref.get("summary", "").strip()
        if not summary:
            continue
        injections.append(
            MemoryInjection(
                summary=summary,
                relevance=float(ref.get("score") or 0.0),
                source=str(ref.get("storage") or "qdrant"),
            )
        )
    return injections


async def _handle_missing_transcript_table(session, user_id: str, exc: ProgrammingError) -> bool:
    try:
        await session.rollback()
    except Exception:  # pragma: no cover - best effort
        pass
    if _is_missing_transcript_table_error(exc):
        logger.warning("memory_bridge: chat_transcripts unavailable for %s: %s", user_id, exc)
        return True
    return False


def _is_missing_transcript_table_error(exc: ProgrammingError) -> bool:
    orig = getattr(exc, "orig", None)
    if UndefinedTable is not None and isinstance(orig, UndefinedTable):
        return True
    message = str(orig or exc).lower()
    return "undefined table" in message or "does not exist" in message or "relation" in message


async def memory_bridge_node(state: SealAIState) -> Dict[str, Any]:
    meta = state.get("meta") or {}
    user_id = str(meta.get("user_id") or "").strip()
    if not user_id:
        logger.debug("memory_bridge: missing user_id in meta.")
        return {}

    try:
        transcript = await _load_last_transcript(user_id)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.warning("memory_bridge: unexpected transcript load failure for %s: %s", user_id, exc)
        transcript = {}
    refs = await _load_ltm_refs(user_id)
    injections = _build_injections(transcript, refs)

    messages = list(state.get("messages") or [])
    if injections:
        lines = [f"- {item['summary']}" for item in injections[:5]]
        messages.append(
            SystemMessage(content="Langzeit-Kontext:\n" + "\n".join(lines), id="msg-memory-bridge")
        )

    slots = dict(state.get("slots") or {})
    slots["memory_injections"] = injections

    return {
        "messages": messages,
        "long_term_memory_refs": refs,
        "slots": slots,
        "phase": "bedarfsanalyse",
    }


__all__ = ["memory_bridge_node"]
