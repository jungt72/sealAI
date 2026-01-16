# backend/app/services/redis_ttl_enforcer.py
from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable

from app.langgraph_v2.constants import resolve_checkpointer_namespace_v2
from app.services.redis_client import make_async_redis_client

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _redis_url() -> str | None:
    # Prefer common env var names. If none present, enforcer will no-op safely.
    return (
        os.getenv("REDIS_URL")
        or os.getenv("REDIS_DSN")
        or os.getenv("SEALAI_REDIS_URL")
        or os.getenv("LANGGRAPH_REDIS_URL")
    )


def _patterns(prefix: str, namespace: str) -> list[str]:
    # Observed keys in your Redis:
    # - lg:cp:consult.v1:checkpoint_write:...
    # - lg:cp:consult.v1:<tenant/user>:thread-...:__empty__:...
    base = f"{prefix}:{namespace}"
    return [
        f"{base}:checkpoint_write:*",
        f"{base}:checkpoint_blob:*",
        f"{base}:checkpoint:*",
        f"{base}:*",
    ]


async def _enforce_ttl_for_patterns(
    redis,
    patterns: Iterable[str],
    *,
    ttl_seconds: int,
    scan_count: int,
) -> tuple[int, int]:
    """
    Returns (touched, fixed) where:
    - touched: number of keys checked (TTL read)
    - fixed: number of keys changed from TTL=-1 to EXPIRE ttl_seconds
    """
    touched = 0
    fixed = 0

    # Use small pipelining to reduce roundtrips without complex batching logic.
    for pattern in patterns:
        async for key in redis.scan_iter(match=pattern, count=scan_count):
            touched += 1
            try:
                ttl = await redis.ttl(key)
            except Exception:
                logger.exception("ttl_enforcer_ttl_failed", extra={"key": str(key), "pattern": pattern})
                continue

            # TTL meanings: -2 missing, -1 no expire, >=0 seconds
            if ttl == -1:
                try:
                    ok = await redis.expire(key, ttl_seconds)
                    if ok:
                        fixed += 1
                except Exception:
                    logger.exception(
                        "ttl_enforcer_expire_failed",
                        extra={"key": str(key), "pattern": pattern, "ttl_seconds": ttl_seconds},
                    )

    return touched, fixed


async def ttl_enforcer_loop(*, stop_event: asyncio.Event | None = None) -> None:
    """
    Background loop that fixes LangGraph RedisSaver TTL leaks by enforcing EXPIRE on lg:cp:* keys.

    Safe behavior:
    - If REDIS_URL missing -> no-op (logs once per cycle)
    - If TTL not configured -> no-op
    - Runs periodically, idempotent
    """
    enabled = _bool_env("LANGGRAPH_V2_TTL_ENFORCER_ENABLED", "1")
    if not enabled:
        logger.info("ttl_enforcer_disabled")
        return

    ttl_seconds = int(os.getenv("LANGGRAPH_V2_CHECKPOINTER_TTL_SECONDS", os.getenv("LANGGRAPH_CHECKPOINT_TTL", "0")) or "0")
    if ttl_seconds <= 0:
        logger.warning(
            "ttl_enforcer_no_ttl_configured",
            extra={"LANGGRAPH_V2_CHECKPOINTER_TTL_SECONDS": os.getenv("LANGGRAPH_V2_CHECKPOINTER_TTL_SECONDS"),
                   "LANGGRAPH_CHECKPOINT_TTL": os.getenv("LANGGRAPH_CHECKPOINT_TTL")},
        )
        return

    interval = int(os.getenv("LANGGRAPH_V2_TTL_ENFORCER_INTERVAL_SECONDS", "300"))
    scan_count = int(os.getenv("LANGGRAPH_V2_TTL_ENFORCER_SCAN_COUNT", "500"))
    prefix = (os.getenv("LANGGRAPH_CHECKPOINT_PREFIX") or "lg:cp").strip() or "lg:cp"
    namespace = resolve_checkpointer_namespace_v2(None)

    patterns = _patterns(prefix, namespace)

    # Create Redis client
    url = _redis_url()
    if not url:
        logger.warning("ttl_enforcer_missing_redis_url", extra={"checked": ["REDIS_URL", "REDIS_DSN", "SEALAI_REDIS_URL", "LANGGRAPH_REDIS_URL"]})
        return

    redis = make_async_redis_client(url, decode_responses=True)

    logger.info(
        "ttl_enforcer_started",
        extra={"ttl_seconds": ttl_seconds, "interval_seconds": interval, "namespace": namespace, "prefix": prefix},
    )

    try:
        while True:
            if stop_event and stop_event.is_set():
                break

            try:
                touched, fixed = await _enforce_ttl_for_patterns(
                    redis,
                    patterns,
                    ttl_seconds=ttl_seconds,
                    scan_count=scan_count,
                )
                if fixed:
                    logger.warning(
                        "ttl_enforcer_fixed_keys",
                        extra={"fixed": fixed, "touched": touched, "ttl_seconds": ttl_seconds, "namespace": namespace},
                    )
                else:
                    logger.info(
                        "ttl_enforcer_ok",
                        extra={"fixed": 0, "touched": touched, "ttl_seconds": ttl_seconds, "namespace": namespace},
                    )
            except Exception:
                logger.exception("ttl_enforcer_cycle_failed")

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
    finally:
        try:
            await redis.close()
        except Exception:
            pass
        logger.info("ttl_enforcer_stopped")
