from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import SystemMessage
from sqlalchemy.exc import ProgrammingError

from app.langgraph.state import SealAIState

logger = logging.getLogger(__name__)


class _DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def rollback(self):
        return None

    async def execute(self, *_args, **_kwargs):
        return None


def AsyncSessionLocal():
    return _DummySession()


async def _handle_missing_transcript_table(session, exc: ProgrammingError) -> bool:
    try:
        await session.rollback()
    except Exception:
        pass
    message = str(getattr(exc, "orig", exc)).lower()
    return "does not exist" in message or "relation" in message


async def _load_last_transcript(user_id: str) -> Dict[str, Any]:
    async with AsyncSessionLocal() as session:
        try:
            await session.execute("select 1")
        except ProgrammingError as exc:
            if await _handle_missing_transcript_table(session, exc):
                logger.warning("memory_bridge: chat_transcripts unavailable for %s", user_id)
                return {}
            raise
    return {}


async def _load_ltm_refs(_user_id: str) -> List[Dict[str, Any]]:
    return []


def _build_injections(transcript: Dict[str, Any], refs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    injections: List[Dict[str, Any]] = []
    summary = str(transcript.get("summary") or "").strip()
    if summary:
        injections.append({"summary": summary, "relevance": 0.95, "source": "postgres"})
    for ref in refs:
        summary = str(ref.get("summary") or "").strip()
        if not summary:
            continue
        injections.append(
            {
                "summary": summary,
                "relevance": float(ref.get("score") or 0.0),
                "source": str(ref.get("storage") or "qdrant"),
            }
        )
    return injections


async def memory_bridge_node(state: SealAIState) -> Dict[str, Any]:
    meta = state.get("meta") or {}
    user_id = str(meta.get("user_id") or "").strip()
    if not user_id:
        return {}

    transcript = await _load_last_transcript(user_id)
    refs = await _load_ltm_refs(user_id)
    injections = _build_injections(transcript, refs)

    messages = list(state.get("messages") or [])
    if injections:
        lines = [f"- {item['summary']}" for item in injections[:5]]
        messages.append(SystemMessage(content="Langzeit-Kontext:\n" + "\n".join(lines), id="msg-memory-bridge"))

    slots = dict(state.get("slots") or {})
    slots["memory_injections"] = injections

    return {
        "messages": messages,
        "long_term_memory_refs": refs,
        "slots": slots,
        "phase": "bedarfsanalyse",
    }


__all__ = [
    "AsyncSessionLocal",
    "_load_last_transcript",
    "_load_ltm_refs",
    "_build_injections",
    "memory_bridge_node",
]
