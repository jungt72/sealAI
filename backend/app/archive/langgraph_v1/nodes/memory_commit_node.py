from __future__ import annotations

import logging
import asyncio
import json
from typing import Any, Dict, List
from uuid import uuid4

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.langgraph.state import LongTermMemoryRef, SealAIState, format_requirements_summary
from app.models.long_term_memory import LongTermMemory
from app.services.memory import memory_core

logger = logging.getLogger(__name__)


async def _store_ltm_entry(user_id: str, key: str, value: str) -> int:
    async with AsyncSessionLocal() as session:
        entry = LongTermMemory(user_id=user_id, key=key, value=value[:4000])
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry.id


def _meta_snapshot(meta: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "confidence_score",
        "confidence_reason",
        "review_issues",
        "review_recommendations",
        "arbiter_reasoning",
        "handoff_history",
    )
    snapshot = {}
    for key in keys:
        value = meta.get(key)
        if value not in (None, ""):
            snapshot[key] = value
    return snapshot


async def memory_commit_node(state: SealAIState) -> Dict[str, Any]:
    if not settings.ltm_enable:
        logger.debug("memory_commit_node: LTM deaktiviert, überspringe Commit.")
        return {}

    meta = state.get("meta") or {}
    user_id = str(meta.get("user_id") or "").strip()
    if not user_id:
        return {}

    slots = state.get("slots") or {}
    chat_id = str(meta.get("thread_id") or "default").strip() or "default"
    final_recommendation = str(
        slots.get("final_recommendation")
        or slots.get("final_answer")
        or slots.get("candidate_answer")
        or ""
    ).strip()
    requirements = slots.get("requirements") or ""
    warmup = slots.get("warmup")

    summary_data = {
        "user_id": user_id,
        "thread_id": chat_id,
        "final_recommendation": final_recommendation,
        "requirements": requirements,
        "warmup": warmup,
        "meta": _meta_snapshot(meta),
    }

    summary_text_parts: List[str] = []
    if final_recommendation:
        summary_text_parts.append(f"Empfehlung:\n{final_recommendation}")
    if requirements:
        summary_text_parts.append(f"Anforderungen:\n{requirements}")
    warmup_text = ""
    if isinstance(warmup, dict):
        warmup_text = json.dumps(warmup, ensure_ascii=False, indent=2)
    elif isinstance(warmup, str):
        warmup_text = warmup
    if warmup_text:
        summary_text_parts.append(f"Warmup:\n{warmup_text}")
    req_summary = format_requirements_summary(state.get("rwd_requirements"))
    if req_summary:
        summary_text_parts.append(f"RWD:\n{req_summary}")
    summary_text = "\n\n".join(filter(None, summary_text_parts)).strip()
    if not summary_text:
        return {}

    key = f"{chat_id}:{uuid4().hex[:8]}"

    try:
        entry_id = await _store_ltm_entry(user_id, key, summary_text)
    except Exception:
        logger.warning("memory_commit_node: Persistierung der LTM-Zusammenfassung fehlgeschlagen.", exc_info=True)
        return {}

    try:
        await asyncio.to_thread(memory_core.commit_summary, user_id, chat_id, summary_data)
    except Exception:
        logger.warning("memory_commit_node: memory_core.commit_summary schlug fehl.", exc_info=True)

    refs = list(state.get("long_term_memory_refs") or [])
    refs.append(
        LongTermMemoryRef(
            storage="postgres",
            id=str(entry_id),
            summary=summary_text[:500],
            score=1.0,
        )
    )
    return {"long_term_memory_refs": refs}


__all__ = ["memory_commit_node"]
