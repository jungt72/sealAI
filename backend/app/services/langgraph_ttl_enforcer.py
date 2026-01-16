from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Iterable

from app.langgraph_v2.constants import resolve_checkpointer_namespace_v2
from app.services.redis_client import make_async_redis_client

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


@dataclass(frozen=True)
class TtlEnforcerSettings:
    enabled: bool
    redis_url: str | None
    prefix: str
    namespace: str
    ttl_seconds: int
    interval_seconds: int
    scan_count: int


def _load_settings() -> TtlEnforcerSettings:
    enabled = _bool_env("LANGGRAPH_V2_TTL_ENFORCER_ENABLED", "1")

    redis_url = (os.getenv("LANGGRAPH_V2_REDIS_URL") or os.getenv("REDIS_URL") or "").strip() or None

    # Must match checkpointer settings
    prefix = (os.getenv("LANGGRAPH_CHECKPOINT_PREFIX") or "lg:cp").strip() or "lg:cp"
    namespace = resolve_checkpointer_namespace_v2(None)

    # Prefer explicit TTL for enforcer, else fall back to checkpointer TTL env, else 7 days
    ttl_seconds = _int_env("LANGGRAPH_V2_TTL_ENFORCER_TTL_SECONDS", -1)
    if ttl_seconds <= 0:
        ttl_seconds = _int_env("LANGGRAPH_CHECKPOINT_TTL", 604800)

    interval_seconds = _int_env("LANGGRAPH_V2_TTL_ENFORCER_INTERVAL_SECONDS", 300)
    scan_count = _int_env("LANGGRAPH_V2_TTL_ENFORCER_SCAN_COUNT", 500)

    return TtlEnforcerSettings(
        enabled=enabled,
        redis_url=redis_url,
        prefix=prefix,
        namespace=namespace,
        ttl_seconds=ttl_seconds,
        interval_seconds=interval_seconds,
        scan_count=scan_count,
    )


def _patterns(prefix: str, namespace: str) -> list[str]:
    # Observed in your Redis:
    #   lg:cp:consult.v1:checkpoint_write:...
    # Keep a small set of patterns to be safe across saver variants.
    ns = (namespace or "").strip()
    p = (prefix or "").strip()
    patterns: list[str] = []
    if p and ns:
        patterns.append(f"{p}:{ns}:checkpoint_write:*")
        patterns.append(f"{p}:{ns}:checkpoint_blob:*")
        patterns.append(f"{p}:{ns}:checkpoint:*")
    if p:
        patterns.append(f"{p}:checkpoint_write:*")
        patterns.append(f"{p}:checkpoint_blob:*")
        patterns.append(f"{p}:checkpoint:*")
    # De-dup while preserving order
    seen = set()
    out: list[str] = []
    for pat in patterns:
        if pat in seen:
            continue
        seen.add(pat)
        out.append(pat)
    return out


async def _enforce_once(*, redis_url: str, settings: TtlEnforcerSettings) -> tuple[int, int]:
    """
    Returns: (touched_keys, leaked_keys_fixed)
    """
    client = make_async_redis_client(redis_url, decode_responses=True)
    touched = 0
    fixed = 0
    try:
        for pattern in _patterns(settings.prefix, settings.namespace):
            async for key in client.scan_iter(match=pattern, count=settings.scan_count):
                touched += 1
                try:
                    ttl = await client.ttl(key)
                    if ttl == -1:
                        # No TTL -> apply
                        ok = await client.expire(key, settings.ttl_seconds)
                        if ok:
                            fixed += 1
                except Exception:
                    logger.exception("ttl_enforcer_key_failed", extra={"key": key, "pattern": pattern})
                    continue
    finally:
        try:
            await client.aclose()
        except Exception:
            pass
    return touched, fixed


async def ttl_enforcer_loop(stop_event: asyncio.Event) -> None:
    settings = _load_settings()
    if not settings.enabled:
        logger.info("langgraph_v2_ttl_enforcer_disabled")
        return
    if not settings.redis_url:
        logger.warning("langgraph_v2_ttl_enforcer_no_redis_url")
        return

    logger.info(
        "langgraph_v2_ttl_enforcer_start",
        extra={
            "prefix": settings.prefix,
            "namespace": settings.namespace,
            "ttl_seconds": settings.ttl_seconds,
            "interval_seconds": settings.interval_seconds,
        },
    )

    while not stop_event.is_set():
        try:
            touched, fixed = await _enforce_once(redis_url=settings.redis_url, settings=settings)
            if fixed:
                logger.warning(
                    "langgraph_v2_ttl_enforcer_fixed",
                    extra={"touched": touched, "fixed": fixed},
                )
            else:
                logger.info(
                    "langgraph_v2_ttl_enforcer_ok",
                    extra={"touched": touched, "fixed": fixed},
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("langgraph_v2_ttl_enforcer_iteration_failed")

        # Sleep with stop support
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=float(settings.interval_seconds))
        except asyncio.TimeoutError:
            pass

    logger.info("langgraph_v2_ttl_enforcer_stop")


def start_ttl_enforcer() -> tuple[asyncio.Task[None], asyncio.Event] | tuple[None, None]:
    """
    Helper for FastAPI lifespan: returns (task, stop_event) if started else (None, None).
    """
    settings = _load_settings()
    if not settings.enabled:
        return (None, None)
    if not settings.redis_url:
        return (None, None)

    stop = asyncio.Event()
    task = asyncio.create_task(ttl_enforcer_loop(stop))
    return (task, stop)
