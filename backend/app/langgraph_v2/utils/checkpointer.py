"""
LangGraph V2 Checkpointer mit optimierter Redis-Konfiguration.

Dieses Modul stellt einen Redis-basierten Checkpointer für LangGraph V2 bereit,
mit Fallback auf MemorySaver bei Verbindungsproblemen.

Features:
- Connection Pooling mit konfigurierbarer Größe
- Timeout und Retry-Logik
- Health Checks
- Graceful Fallback zu MemorySaver
"""

import asyncio
import os
from typing import Optional

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

logger = structlog.get_logger("langgraph_v2.checkpointer")

# Namespace für V2-Checkpoints (per Konstanten gemeinsam mit dem Graph-Builder)
from app.langgraph_v2.constants import (
    CHECKPOINT_BLOB_PREFIX_V2,
    CHECKPOINT_PREFIX_V2,
    CHECKPOINT_WRITE_PREFIX_V2,
    CHECKPOINTER_NAMESPACE_V2,
)

# Lazy import für Redis-Abhängigkeiten
try:
    from langgraph.checkpoint.redis import AsyncRedisSaver
    from redis.asyncio import ConnectionPool, Redis
except ImportError:
    AsyncRedisSaver = None
    ConnectionPool = None
    Redis = None


async def make_v2_checkpointer_async(
    require_async: bool = True,
    namespace: str = CHECKPOINTER_NAMESPACE_V2,
) -> BaseCheckpointSaver:
    """
    Erstellt einen Checkpointer für LangGraph V2.

    Versucht zunächst, einen Redis-basierten AsyncRedisSaver zu erstellen.
    Falls Redis nicht verfügbar ist oder die Verbindung fehlschlägt,
    wird auf einen MemorySaver zurückgegriffen.

    Args:
        require_async: Ob ein asynchroner Checkpointer erforderlich ist
        namespace: Namespace für die Checkpoints (Standard: langgraph_v2)

    Returns:
        BaseCheckpointSaver: Ein Redis- oder Memory-basierter Checkpointer
    """
    backend = os.getenv("CHECKPOINTER_BACKEND", "redis")
    namespace = (namespace or "").strip() or CHECKPOINTER_NAMESPACE_V2

    allow_memory_fallback = os.getenv("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if backend == "redis" and AsyncRedisSaver is not None:
        conn_string = os.getenv("LANGGRAPH_V2_REDIS_URL") or os.getenv("REDIS_URL")
        if conn_string:
            try:
                ttl_seconds_raw = (
                    os.getenv("LANGGRAPH_V2_CHECKPOINTER_TTL_SECONDS")
                    or ""
                ).strip()
                ttl_config: dict[str, int] | None = None
                if ttl_seconds_raw:
                    try:
                        ttl_seconds = int(ttl_seconds_raw)
                        if ttl_seconds > 0:
                            # AsyncRedisSaver expects TTL in minutes.
                            ttl_minutes = max(1, ttl_seconds // 60)
                            ttl_config = {"default_ttl": ttl_minutes}
                    except ValueError:
                        ttl_config = None
                logger.info(
                    "langgraph_v2_checkpointer_init",
                    backend="redis",
                    async_mode=require_async,
                    allow_memory_fallback=allow_memory_fallback,
                    namespace=namespace,
                    checkpoint_prefix=CHECKPOINT_PREFIX_V2,
                    ttl_minutes=(ttl_config or {}).get("default_ttl"),
                )

                # Optimierte Connection Pool Konfiguration
                pool = ConnectionPool.from_url(
                    conn_string,
                    max_connections=50,  # Erhöht für höhere Last
                    socket_timeout=5,    # 5 Sekunden Timeout für Socket-Operationen
                    socket_connect_timeout=5,  # 5 Sekunden für Verbindungsaufbau
                    retry_on_timeout=True,     # Automatische Wiederholung bei Timeout
                    health_check_interval=30,  # Health Check alle 30 Sekunden
                    decode_responses=False,    # Binäre Daten für Checkpoints
                )

                redis_client = Redis(connection_pool=pool)
                saver = AsyncRedisSaver(
                    redis_client=redis_client,
                    checkpoint_prefix=CHECKPOINT_PREFIX_V2,
                    checkpoint_blob_prefix=CHECKPOINT_BLOB_PREFIX_V2,
                    checkpoint_write_prefix=CHECKPOINT_WRITE_PREFIX_V2,
                    ttl=ttl_config,
                )
                await saver.asetup()
                return saver

            except Exception as exc:  # pragma: no cover - protected fallback
                logger.exception(
                    "langgraph_v2_checkpointer_init_failed",
                    backend="redis",
                    error=str(exc),
                    fallback="memory",
                )
                if not allow_memory_fallback:
                    raise RuntimeError(
                        "LangGraph v2 Redis checkpointer init failed and memory fallback is disabled."
                    ) from exc

    logger.info(
        "langgraph_v2_checkpointer_init",
        backend="memory",
        async_mode=require_async,
        allow_memory_fallback=True,
        namespace=namespace,
    )
    return MemorySaver()


def make_v2_checkpointer(
    require_async: bool = True,
    namespace: str = CHECKPOINTER_NAMESPACE_V2,
) -> BaseCheckpointSaver:
    return asyncio.run(
        make_v2_checkpointer_async(require_async=require_async, namespace=namespace)
    )
