from __future__ import annotations

import os
from typing import Optional

try:
    from redis.asyncio import ConnectionPool, Redis
except ImportError:  # pragma: no cover - optional dependency
    ConnectionPool = None
    Redis = None


DEFAULT_REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
DEFAULT_REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
DEFAULT_REDIS_SOCKET_CONNECT_TIMEOUT = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))
DEFAULT_REDIS_HEALTH_CHECK_INTERVAL = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))


def make_async_redis_client(
    redis_url: str,
    *,
    decode_responses: bool = False,
    encoding: Optional[str] = None,
    max_connections: Optional[int] = None,
    socket_timeout: Optional[float] = None,
    socket_connect_timeout: Optional[float] = None,
    retry_on_timeout: bool = True,
    health_check_interval: Optional[int] = None,
) -> "Redis":
    if ConnectionPool is None or Redis is None:
        raise RuntimeError("redis.asyncio is not available")

    pool_kwargs = {
        "max_connections": max_connections or DEFAULT_REDIS_MAX_CONNECTIONS,
        "socket_timeout": socket_timeout or DEFAULT_REDIS_SOCKET_TIMEOUT,
        "socket_connect_timeout": socket_connect_timeout or DEFAULT_REDIS_SOCKET_CONNECT_TIMEOUT,
        "retry_on_timeout": retry_on_timeout,
        "health_check_interval": health_check_interval or DEFAULT_REDIS_HEALTH_CHECK_INTERVAL,
        "decode_responses": decode_responses,
    }
    if encoding is not None:
        pool_kwargs["encoding"] = encoding

    pool = ConnectionPool.from_url(redis_url, **pool_kwargs)
    return Redis(connection_pool=pool)
