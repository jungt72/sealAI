from __future__ import annotations

import os
from typing import Any, Optional

try:
    from redis.asyncio import Redis as AsyncRedis  # type: ignore
except Exception:
    AsyncRedis = None  # type: ignore

try:
    from redis import Redis as SyncRedis  # type: ignore
except Exception:
    SyncRedis = None  # type: ignore

from app.services.redis_client import make_async_redis_client, make_redis_client
try:
    from langgraph.checkpoint.redis import RedisSaver  # type: ignore
except Exception:
    RedisSaver = None  # type: ignore

try:
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
except Exception:
    MemorySaver = None  # type: ignore


class _NoopSaver:
    async def aget_tuple(self, *_args: Any, **_kwargs: Any) -> Any:
        return None

    async def aput(self, *_args: Any, **_kwargs: Any) -> Any:
        return None

    def get_tuple(self, *_args: Any, **_kwargs: Any) -> Any:
        return None

    def put(self, *_args: Any, **_kwargs: Any) -> Any:
        return None


def _make_memory() -> object:
    if MemorySaver is None:
        return _NoopSaver()
    try:
        return MemorySaver()
    except Exception:
        return _NoopSaver()


def _try_create_redis_saver(client: Any, namespace: str) -> Optional[object]:
    if not RedisSaver:
        return None
    attempts = (
        lambda: RedisSaver(redis_client=client, namespace=namespace),
        lambda: RedisSaver(redis_client=client),
        lambda: RedisSaver(client),
    )
    for attempt in attempts:
        try:
            return attempt()
        except TypeError:
            continue
        except Exception:
            return None
    return None


def _make_sync_saver(redis_url: str, namespace: str) -> Optional[object]:
    if SyncRedis:
        try:
            client = make_redis_client(redis_url)
            pipe = client.pipeline()
            has_cm = hasattr(pipe, "__enter__") and hasattr(pipe, "__exit__")
            if not has_cm:
                return None
            saver = _try_create_redis_saver(client, namespace)
            if saver:
                return saver
        except Exception:
            return None
    return None


def _make_async_saver(redis_url: str, namespace: str) -> Optional[object]:
    if AsyncRedis:
        try:
            client = make_async_redis_client(redis_url)
            pipe = client.pipeline()
            has_acm = hasattr(pipe, "__aenter__") and hasattr(pipe, "__aexit__")
            if not has_acm:
                return None
            saver = _try_create_redis_saver(client, namespace)
            if saver and hasattr(saver, "aget_tuple"):
                if getattr(saver.aget_tuple, "__module__", "") == "langgraph.checkpoint.base":
                    return None
                return saver
        except Exception:
            return None
    return None


def make_checkpointer(require_async: bool = False, *, namespace_env: str = "CHECKPOINTER_NAMESPACE_MAIN") -> object:
    """
    Best-effort checkpointer used by tests and local runs.
    """
    use_redis = (os.getenv("USE_REDIS_CHECKPOINTER") or "").strip().lower() in {"1", "true", "on"}
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    namespace = os.getenv(namespace_env, "sealai:main")

    if not use_redis:
        return _make_memory()

    if require_async:
        saver = _make_async_saver(redis_url, namespace)
        if saver:
            return saver
        return _make_memory()

    saver = _make_sync_saver(redis_url, namespace)
    if saver:
        return saver

    fallback = _make_async_saver(redis_url, namespace)
    if fallback:
        return fallback

    return _make_memory()


__all__ = ["make_checkpointer"]
