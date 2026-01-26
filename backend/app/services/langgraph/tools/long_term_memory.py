"""Postgres-backed long-term memory helpers."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.long_term_memory import LongTermMemory


async def _insert_memory(user_id: str, key: str, value: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(LongTermMemory(user_id=user_id, key=key, value=value))
        await session.commit()


async def _fetch_memories(
    user_id: str,
    *,
    keys: Optional[List[str]] = None,
    limit: int = 20,
) -> List[LongTermMemory]:
    async with AsyncSessionLocal() as session:
        stmt = select(LongTermMemory).where(LongTermMemory.user_id == user_id)
        if keys:
            stmt = stmt.where(LongTermMemory.key.in_(keys))
        stmt = stmt.order_by(LongTermMemory.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


def _run_async(coro) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        loop.create_task(coro)
        return True


def prewarm_ltm() -> None:
    """No-op prewarm to keep interface stable."""
    return None


def upsert_memory(
    *,
    user: str,
    chat_id: str,
    text: str,
    kind: str = "note",
) -> bool:
    payload = {"chat_id": chat_id, "text": text, "kind": kind}
    key = f"{kind}:{chat_id}"
    return bool(_run_async(_insert_memory(user, key, json.dumps(payload))))


def upsert_parameters(
    *,
    user_id: Optional[str],
    tenant_id: Optional[str],
    chat_id: Optional[str],
    parameters: Dict[str, Any],
) -> bool:
    if not user_id:
        return False
    scoped_key = f"golden_parameters:{tenant_id or 'global'}:{chat_id or 'default'}"
    payload = {"tenant_id": tenant_id, "chat_id": chat_id, "parameters": parameters}
    return bool(_run_async(_insert_memory(user_id, scoped_key, json.dumps(payload))))


def fetch_latest_parameters(
    *,
    user_id: Optional[str],
    tenant_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not user_id:
        return {}
    scoped_key = f"golden_parameters:{tenant_id or 'global'}:{chat_id or 'default'}"
    records = _run_async(_fetch_memories(user_id, keys=[scoped_key], limit=1)) or []
    if not records:
        return {}
    record = records[0]
    try:
        payload = json.loads(record.value)
        params = payload.get("parameters")
        return params if isinstance(params, dict) else {}
    except Exception:
        return {}


__all__ = [
    "prewarm_ltm",
    "upsert_memory",
    "upsert_parameters",
    "fetch_latest_parameters",
]
