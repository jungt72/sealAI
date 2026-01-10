from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

from redis.asyncio import Redis

from app.services.redis_client import make_async_redis_client

MAX_JOBS_QUEUE_LEN = 10000


@lru_cache(maxsize=1)
def _queue_client() -> Redis:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return make_async_redis_client(redis_url)


async def enqueue_job(channel: str, payload: Dict[str, Any]) -> None:
    client = _queue_client()
    data = json.dumps(payload, ensure_ascii=False)
    await client.rpush(channel, data)
    await client.ltrim(channel, -MAX_JOBS_QUEUE_LEN, -1)
