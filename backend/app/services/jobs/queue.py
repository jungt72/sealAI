from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

from redis.asyncio import Redis


@lru_cache(maxsize=1)
def _queue_client() -> Redis:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return Redis.from_url(redis_url)

def get_queue_client() -> Redis:
    return _queue_client()


async def enqueue_job(channel: str, payload: Dict[str, Any]) -> None:
    client = _queue_client()
    data = json.dumps(payload, ensure_ascii=False)
    await client.rpush(channel, data)


__all__ = ["enqueue_job", "get_queue_client"]
