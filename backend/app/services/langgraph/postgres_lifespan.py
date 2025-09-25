# backend/app/services/langgraph/postgres_lifespan.py
"""
Kompatibler Postgres-Checkpointer (LangGraph).
– Neuer Namespace: langgraph_checkpoint.postgres
– Alter Namespace: langgraph.checkpoint.postgres
– Fallback: AsyncRedisSaver oder InMemorySaver
Zusatz: prewarm Long-Term-Memory (Qdrant) beim Start.
"""
from __future__ import annotations

import atexit
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from langgraph.checkpoint.memory import InMemorySaver

log = logging.getLogger(__name__)

from app.core.config import settings

POSTGRES_URL = settings.POSTGRES_SYNC_URL

# LTM prewarm
try:
    from app.services.langgraph.tools import long_term_memory as _ltm
except Exception:  # pragma: no cover
    _ltm = None

# ─────────────────────────────────────────────────────────────────────────────
# Kompatibler Import für PostgresSaver
# ─────────────────────────────────────────────────────────────────────────────
try:
    from langgraph_checkpoint.postgres.aio import AsyncPostgresSaver as _PgSaver
    log.info("AsyncPostgresSaver importiert aus langgraph_checkpoint.postgres.aio")
except ModuleNotFoundError:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as _PgSaver
        log.info("AsyncPostgresSaver importiert aus langgraph.checkpoint.postgres.aio")
    except ModuleNotFoundError:
        _PgSaver = None
        log.warning("❗ Postgres-Modul nicht gefunden – Priorisiere RedisSaver")


@asynccontextmanager
async def get_checkpointer(app) -> AsyncGenerator:
    """Universal-Initialisierung (async) + LTM-Prewarm."""
    # Prewarm LTM (nicht-blockierend)
    try:
        if _ltm:
            _ltm.prewarm_ltm()
            log.info("LTM prewarm gestartet.")
    except Exception as e:
        log.warning("LTM prewarm fehlgeschlagen (ignoriert): %s", e)

    checkpointer = None
    if _PgSaver:
        try:
            async with _PgSaver.from_conn_string(POSTGRES_URL) as saver:
                await saver.setup()
                checkpointer = saver
                log.info("✅ AsyncPostgresSaver initialisiert")
                yield saver
                return
        except Exception as e:
            log.warning("PostgresSaver-Init fehlgeschlagen: %s – Fallback auf RedisSaver", e)

    # Redis-Fallback (primär für Memory)
    try:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver
        from redis.asyncio import Redis
        redis_url = settings.REDIS_URL or "redis://redis:6379/0"
        redis_client = Redis.from_url(redis_url)
        saver = AsyncRedisSaver(redis_client)
        await saver.setup()
        checkpointer = saver
        log.info("✅ AsyncRedisSaver als Fallback initialisiert")
        yield saver
        return
    except Exception as e:
        log.warning("RedisSaver-Init fehlgeschlagen: %s – Ultimativer Fallback: InMemorySaver", e)

    saver = InMemorySaver()
    yield saver
    log.info("InMemorySaver initialisiert – keine persistente LangGraph-History")


async def get_saver():
    async with get_checkpointer(None) as saver:
        return saver


@asynccontextmanager
async def lifespan(app) -> AsyncGenerator[None, None]:
    async with get_checkpointer(app):
        yield


def cleanup():
    pass


atexit.register(cleanup)
