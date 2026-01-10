from __future__ import annotations

import asyncio
import json
import os
from weakref import WeakKeyDictionary
from typing import Any, Dict

from redis.asyncio import Redis

from app.services.redis_client import make_async_redis_client

MAX_JOBS_QUEUE_LEN = 10000


_QUEUE_STORE: "WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, object]]" = WeakKeyDictionary()


def _get_queue_store(loop: asyncio.AbstractEventLoop) -> dict[str, object]:
    store = _QUEUE_STORE.get(loop)
    if store is None:
        store = {"client": None, "lock": asyncio.Lock()}
        _QUEUE_STORE[loop] = store
    return store


async def _get_queue_client() -> Redis:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    loop = asyncio.get_running_loop()
    store = _get_queue_store(loop)
    client = store.get("client")
    if client is not None:
        return client
    async with store["lock"]:
        client = store.get("client")
        if client is not None:
            return client
        client = make_async_redis_client(redis_url)
        store["client"] = client
        return client


def _queue_client() -> Redis:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        temp_loop = asyncio.new_event_loop()
        try:
            return temp_loop.run_until_complete(_get_queue_client())
        finally:
            temp_loop.close()
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    store = _get_queue_store(loop)
    client = store.get("client")
    if client is None:
        client = make_async_redis_client(redis_url)
        store["client"] = client
    return client


async def enqueue_job(channel: str, payload: Dict[str, Any]) -> None:
    client = await _get_queue_client()
    data = json.dumps(payload, ensure_ascii=False)
    await client.rpush(channel, data)
    await client.ltrim(channel, -MAX_JOBS_QUEUE_LEN, -1)
