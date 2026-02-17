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
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.base import CheckpointTuple, get_checkpoint_id, get_checkpoint_metadata
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

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


class AsyncSqlAlchemyPostgresSaver(BaseCheckpointSaver[str]):
    def __init__(self, *, conn_string: str, engine: AsyncEngine | None = None) -> None:
        super().__init__()
        self._engine = engine or create_async_engine(conn_string, future=True, pool_pre_ping=True)
        self._owns_engine = engine is None

    async def asetup(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS langgraph_v2_checkpoints (
                      thread_id TEXT NOT NULL,
                      checkpoint_ns TEXT NOT NULL DEFAULT '',
                      checkpoint_id TEXT NOT NULL,
                      parent_checkpoint_id TEXT NULL,
                      checkpoint_type TEXT NOT NULL,
                      checkpoint_data BYTEA NOT NULL,
                      metadata_type TEXT NOT NULL,
                      metadata_data BYTEA NOT NULL,
                      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                      PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS langgraph_v2_checkpoint_writes (
                      thread_id TEXT NOT NULL,
                      checkpoint_ns TEXT NOT NULL DEFAULT '',
                      checkpoint_id TEXT NOT NULL,
                      task_id TEXT NOT NULL,
                      idx INTEGER NOT NULL,
                      channel TEXT NOT NULL,
                      value_type TEXT NOT NULL,
                      value_data BYTEA NOT NULL,
                      task_path TEXT NOT NULL DEFAULT '',
                      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                      PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                    )
                    """
                )
            )

    async def aget_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        configurable = dict(config.get("configurable") or {})
        thread_id = str(configurable.get("thread_id") or "")
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
        if not thread_id:
            return None
        checkpoint_id = get_checkpoint_id(config)
        async with self._engine.connect() as conn:
            if checkpoint_id:
                result = await conn.execute(
                    text(
                        """
                        SELECT checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data
                        FROM langgraph_v2_checkpoints
                        WHERE thread_id=:thread_id AND checkpoint_ns=:checkpoint_ns AND checkpoint_id=:checkpoint_id
                        LIMIT 1
                        """
                    ),
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    },
                )
            else:
                result = await conn.execute(
                    text(
                        """
                        SELECT checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data
                        FROM langgraph_v2_checkpoints
                        WHERE thread_id=:thread_id AND checkpoint_ns=:checkpoint_ns
                        ORDER BY created_at DESC, checkpoint_id DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                    },
                )
            row = result.mappings().first()
            if row is None:
                return None

            resolved_checkpoint_id = str(row["checkpoint_id"])
            writes_result = await conn.execute(
                text(
                    """
                    SELECT task_id, idx, channel, value_type, value_data
                    FROM langgraph_v2_checkpoint_writes
                    WHERE thread_id=:thread_id AND checkpoint_ns=:checkpoint_ns AND checkpoint_id=:checkpoint_id
                    ORDER BY task_id ASC, idx ASC
                    """
                ),
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": resolved_checkpoint_id,
                },
            )
            writes_rows = list(writes_result.mappings().all())

        checkpoint = self.serde.loads_typed((str(row["checkpoint_type"]), bytes(row["checkpoint_data"])))
        metadata = self.serde.loads_typed((str(row["metadata_type"]), bytes(row["metadata_data"])))
        pending_writes = [
            (str(w["task_id"]), str(w["channel"]), self.serde.loads_typed((str(w["value_type"]), bytes(w["value_data"]))))
            for w in writes_rows
        ]
        parent_checkpoint_id = row["parent_checkpoint_id"]
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": resolved_checkpoint_id,
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": str(parent_checkpoint_id),
                    }
                }
                if parent_checkpoint_id
                else None
            ),
            pending_writes=pending_writes,
        )

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        del new_versions  # not needed for persisted envelope
        configurable = dict(config.get("configurable") or {})
        thread_id = str(configurable.get("thread_id") or "")
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
        if not thread_id:
            raise ValueError("thread_id is required for checkpoint persistence")
        checkpoint_id = str(checkpoint.get("id") or "")
        if not checkpoint_id:
            raise ValueError("checkpoint.id is required")
        parent_checkpoint_id = get_checkpoint_id(config)
        checkpoint_t, checkpoint_b = self.serde.dumps_typed(checkpoint)
        metadata_t, metadata_b = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))

        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    DELETE FROM langgraph_v2_checkpoints
                    WHERE thread_id=:thread_id AND checkpoint_ns=:checkpoint_ns AND checkpoint_id=:checkpoint_id
                    """
                ),
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO langgraph_v2_checkpoints (
                      thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                      checkpoint_type, checkpoint_data, metadata_type, metadata_data, created_at
                    ) VALUES (
                      :thread_id, :checkpoint_ns, :checkpoint_id, :parent_checkpoint_id,
                      :checkpoint_type, :checkpoint_data, :metadata_type, :metadata_data, :created_at
                    )
                    """
                ),
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "parent_checkpoint_id": parent_checkpoint_id,
                    "checkpoint_type": checkpoint_t,
                    "checkpoint_data": checkpoint_b,
                    "metadata_type": metadata_t,
                    "metadata_data": metadata_b,
                    "created_at": datetime.now(timezone.utc),
                },
            )
        return {
            **config,
            "configurable": {
                **configurable,
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            },
        }

    async def aput_writes(
        self,
        config: dict[str, Any],
        writes: list[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        configurable = dict(config.get("configurable") or {})
        thread_id = str(configurable.get("thread_id") or "")
        checkpoint_ns = str(configurable.get("checkpoint_ns") or "")
        checkpoint_id = str(get_checkpoint_id(config) or "")
        if not thread_id or not checkpoint_id:
            return
        async with self._engine.begin() as conn:
            for idx, (channel, value) in enumerate(writes):
                value_t, value_b = self.serde.dumps_typed(value)
                await conn.execute(
                    text(
                        """
                        DELETE FROM langgraph_v2_checkpoint_writes
                        WHERE thread_id=:thread_id AND checkpoint_ns=:checkpoint_ns
                          AND checkpoint_id=:checkpoint_id AND task_id=:task_id AND idx=:idx
                        """
                    ),
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                        "task_id": task_id,
                        "idx": idx,
                    },
                )
                await conn.execute(
                    text(
                        """
                        INSERT INTO langgraph_v2_checkpoint_writes (
                          thread_id, checkpoint_ns, checkpoint_id, task_id, idx,
                          channel, value_type, value_data, task_path, created_at
                        ) VALUES (
                          :thread_id, :checkpoint_ns, :checkpoint_id, :task_id, :idx,
                          :channel, :value_type, :value_data, :task_path, :created_at
                        )
                        """
                    ),
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                        "task_id": task_id,
                        "idx": idx,
                        "channel": str(channel),
                        "value_type": value_t,
                        "value_data": value_b,
                        "task_path": str(task_path or ""),
                        "created_at": datetime.now(timezone.utc),
                    },
                )


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
    backend = (
        os.getenv("LANGGRAPH_V2_CHECKPOINTER_BACKEND")
        or os.getenv("CHECKPOINTER_BACKEND")
        or "redis"
    ).strip().lower()
    namespace = (namespace or "").strip() or CHECKPOINTER_NAMESPACE_V2

    allow_memory_fallback = os.getenv("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if backend == "postgres":
        conn_string = os.getenv("LANGGRAPH_V2_POSTGRES_URL") or os.getenv("DATABASE_URL")
        if not conn_string:
            if allow_memory_fallback:
                logger.warning("langgraph_v2_checkpointer_postgres_url_missing_fallback_memory")
                return MemorySaver()
            raise RuntimeError("LangGraph v2 Postgres checkpointer selected but no DATABASE_URL configured.")
        try:
            saver = AsyncSqlAlchemyPostgresSaver(conn_string=conn_string)
            await saver.asetup()
            logger.info(
                "langgraph_v2_checkpointer_init",
                backend="postgres",
                async_mode=require_async,
                allow_memory_fallback=allow_memory_fallback,
                namespace=namespace,
            )
            return saver
        except Exception as exc:  # pragma: no cover - protected fallback
            logger.exception(
                "langgraph_v2_checkpointer_init_failed",
                backend="postgres",
                error=str(exc),
                fallback="memory",
            )
            if not allow_memory_fallback:
                raise RuntimeError(
                    "LangGraph v2 Postgres checkpointer init failed and memory fallback is disabled."
                ) from exc
            return MemorySaver()

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
        elif not allow_memory_fallback:
            raise RuntimeError("LangGraph v2 Redis checkpointer selected but no REDIS_URL configured.")

    if backend not in {"redis", "postgres"} and not allow_memory_fallback:
        raise RuntimeError(f"Unsupported LangGraph v2 checkpointer backend: {backend}")

    if backend == "redis" and AsyncRedisSaver is None and not allow_memory_fallback:
        raise RuntimeError(
            "LangGraph v2 Redis checkpointer selected but langgraph-checkpoint-redis is not installed."
        )

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


def get_checkpointer_v2(
    require_async: bool = True,
    namespace: str = CHECKPOINTER_NAMESPACE_V2,
) -> BaseCheckpointSaver:
    return make_v2_checkpointer(require_async=require_async, namespace=namespace)
