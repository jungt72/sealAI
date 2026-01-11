# backend/app/langgraph/utils/checkpointer.py
from __future__ import annotations

from typing import Optional

try:
    from redis.asyncio import Redis
    from langgraph.checkpoint.redis import RedisSaver
except ImportError:
    Redis = None
    RedisSaver = None

from app.services.redis_client import make_async_redis_client


async def make_redis_checkpointer(redis_url: Optional[str], namespace: str):
    """
    Builder für RedisSaver mit aktueller API.
    Erstellt RedisSaver mit async redis_client.
    Namespace wird über config gesetzt.
    """
    if not redis_url or not Redis or not RedisSaver:
        return None
    client = make_async_redis_client(redis_url)
    saver = RedisSaver(redis_client=client, namespace=namespace)
    await saver.setup()  # Einrichtung der Redis-Strukturen
    return saver
