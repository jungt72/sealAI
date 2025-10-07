# backend/app/services/langgraph/postgres_lifespan.py
from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

log = logging.getLogger(__name__)

def _env(name: str, *alts: str) -> str | None:
    for n in (name, *alts):
        v = os.getenv(n)
        if v and str(v).strip():
            return str(v).strip()
    return None

def normalize_pg_dsn(dsn: str) -> str:
    """
    Akzeptiert versehentlich gesetzte SQLAlchemy-DSNs und wandelt sie in
    psycopg/libpq-kompatible DSNs um.
    """
    s = dsn.strip()
    if s.startswith("postgresql+psycopg://"):
        s = "postgresql://" + s.split("postgresql+psycopg://", 1)[1]
    if s.startswith("postgres://"):
        s = "postgresql://" + s.split("postgres://", 1)[1]
    return s

async def _try_pg_saver():
    dsn_raw = _env("POSTGRES_DSN", "DATABASE_URL", "PG_DSN", "SQLALCHEMY_DATABASE_URI")
    if not dsn_raw:
        raise RuntimeError("Kein Postgres-DSN in ENV gefunden")

    dsn = normalize_pg_dsn(dsn_raw)
    # AsyncPostgresSaver erwartet eine libpq/psycopg-kompatible URL
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    saver = AsyncPostgresSaver.from_conn_string(dsn)
    # Falls deine Version setup() benötigt, einfach einkommentieren:
    # await saver.setup()
    log.info("PostgresSaver bereit: %s", dsn.replace(os.getenv("POSTGRES_PASSWORD", ""), "*****"))
    return saver

async def _fallback_redis():
    """Fallback to the shared Redis checkpointer used by the LangGraph runtime."""
    from app.services.langgraph.redis_lifespan import get_redis_checkpointer

    saver = get_redis_checkpointer()
    if saver is None:
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    return saver

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("AsyncPostgresSaver importiert aus langgraph.checkpoint.postgres.aio")
    log.info("LTM prewarm gestartet.")
    try:
        app.state.checkpoint_saver = await _try_pg_saver()
    except Exception as e:
        log.warning("PostgresSaver-Init fehlgeschlagen: %s\n – Fallback auf RedisSaver", e)
        try:
            app.state.checkpoint_saver = await _fallback_redis()
        except Exception as e2:
            log.warning("RedisSaver-Init fehlgeschlagen: %s – Ultimativer Fallback: InMemorySaver", e2)
            from langgraph.checkpoint.memory import MemorySaver
            app.state.checkpoint_saver = MemorySaver()

    # App läuft
    yield

    # Optionale Aufräumarbeiten
    saver = getattr(app.state, "checkpoint_saver", None)
    aclose = getattr(saver, "aclose", None)
    if callable(aclose):
        try:
            await aclose()
        except Exception:
            pass
