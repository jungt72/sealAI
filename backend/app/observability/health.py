"""Health checks for SealAI dependencies."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict

import structlog
from qdrant_client import QdrantClient
from redis.asyncio import Redis

from app.core.config import settings
from app.observability.metrics import DEPENDENCY_UP

log = structlog.get_logger("observability.health")


async def check_redis() -> Dict[str, Any]:
    """Check Redis connectivity."""
    start = time.perf_counter()
    redis = None
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
        latency_ms = (time.perf_counter() - start) * 1000
        DEPENDENCY_UP.labels(dependency="redis").set(1)
        return {"status": "healthy", "latency_ms": round(latency_ms, 2)}
    except Exception as exc:
        DEPENDENCY_UP.labels(dependency="redis").set(0)
        log.error("health.redis_check_failed", error=str(exc))
        return {"status": "unhealthy", "error": str(exc)}
    finally:
        if redis is not None:
            await redis.aclose()


async def check_qdrant() -> Dict[str, Any]:
    """Check Qdrant connectivity."""
    start = time.perf_counter()
    try:
        client = QdrantClient(
            url=str(settings.qdrant_url).rstrip("/"),
            api_key=(os.getenv("QDRANT_API_KEY") or None),
        )
        collections = await asyncio.to_thread(client.get_collections)
        latency_ms = (time.perf_counter() - start) * 1000
        DEPENDENCY_UP.labels(dependency="qdrant").set(1)
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "collections": len(collections.collections),
        }
    except Exception as exc:
        DEPENDENCY_UP.labels(dependency="qdrant").set(0)
        log.error("health.qdrant_check_failed", error=str(exc))
        return {"status": "unhealthy", "error": str(exc)}


async def run_all_health_checks() -> Dict[str, Any]:
    """Run all health checks in parallel and aggregate status."""
    results = await asyncio.gather(
        check_redis(),
        check_qdrant(),
        return_exceptions=True,
    )

    checks: Dict[str, Any] = {}
    names = ["redis", "qdrant"]

    for idx, name in enumerate(names):
        result = results[idx]
        if isinstance(result, Exception):
            checks[name] = {"status": "unhealthy", "error": str(result)}
        else:
            checks[name] = result

    all_healthy = all(
        isinstance(check, dict) and check.get("status") == "healthy"
        for check in checks.values()
    )

    return {"status": "healthy" if all_healthy else "degraded", "checks": checks}


__all__ = [
    "check_redis",
    "check_qdrant",
    "run_all_health_checks",
]
