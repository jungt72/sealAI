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
import inspect
import os
from typing import Any, Optional

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

logger = structlog.get_logger("langgraph_v2.checkpointer")

# Namespace für V2-Checkpoints (per Konstanten gemeinsam mit dem Graph-Builder)
from app.langgraph_v2.constants import resolve_checkpointer_namespace_v2

# Lazy import für Redis-Abhängigkeiten
try:
    from langgraph.checkpoint.redis import AsyncRedisSaver
    from redis.asyncio import ConnectionPool, Redis
except ImportError:
    AsyncRedisSaver = None
    ConnectionPool = None
    Redis = None


def _parse_checkpointer_ttl() -> Optional[int]:
    ttl_env = (os.getenv("LANGGRAPH_CHECKPOINT_TTL") or "").strip()
    return int(ttl_env) if ttl_env.isdigit() else None


def _resolve_checkpointer_settings(namespace: str | None) -> tuple[str, str, Optional[int]]:
    resolved_namespace = resolve_checkpointer_namespace_v2(namespace)
    prefix = (os.getenv("LANGGRAPH_CHECKPOINT_PREFIX") or "lg:cp").strip() or "lg:cp"
    ttl = _parse_checkpointer_ttl()
    return resolved_namespace, prefix, ttl


def _async_redis_saver_supported_params() -> set[str] | None:
    try:
        signature = inspect.signature(AsyncRedisSaver.__init__)  # type: ignore[misc]
    except Exception:  # pragma: no cover - best effort introspection
        return None
    return {name for name in signature.parameters if name != "self"}


def _build_async_redis_saver_kwargs(
    *,
    redis_client: Any,
    namespace: str,
    prefix: str,
    ttl: Optional[int],
    supported_params: set[str] | None,
) -> tuple[tuple[Any, ...], dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    warnings: list[tuple[str, dict[str, Any]]] = []
    combined_namespace = f"{prefix}:{namespace}"

    if supported_params:
        client_param = None
        for candidate in ("redis_client", "redis", "client"):
            if candidate in supported_params:
                client_param = candidate
                break
        ttl_param = None
        for candidate in ("ttl", "ttl_seconds"):
            if candidate in supported_params:
                ttl_param = candidate
                break
        prefix_param = None
        for candidate in ("key_prefix", "prefix"):
            if candidate in supported_params:
                prefix_param = candidate
                break
        has_namespace = "namespace" in supported_params

        kwargs: dict[str, Any] = {}
        args: tuple[Any, ...] = ()
        if client_param:
            kwargs[client_param] = redis_client
        else:
            args = (redis_client,)

        if has_namespace and prefix_param:
            kwargs["namespace"] = namespace
            kwargs[prefix_param] = prefix
        elif has_namespace:
            kwargs["namespace"] = combined_namespace
            warnings.append(
                (
                    "langgraph_v2_checkpointer_prefix_unsupported",
                    {
                        "namespace": namespace,
                        "prefix": prefix,
                        "combined_namespace": combined_namespace,
                    },
                )
            )
        elif prefix_param:
            kwargs[prefix_param] = prefix
            warnings.append(
                (
                    "langgraph_v2_checkpointer_namespace_unsupported",
                    {"namespace": namespace, "prefix": prefix},
                )
            )
        else:
            warnings.append(
                (
                    "langgraph_v2_checkpointer_namespace_prefix_unsupported",
                    {"namespace": namespace, "prefix": prefix},
                )
            )

        if ttl is not None and ttl_param:
            kwargs[ttl_param] = ttl
        elif ttl is not None:
            warnings.append(("langgraph_v2_checkpointer_ttl_unsupported", {"ttl": ttl}))

        return args, kwargs, warnings

    kwargs = {
        "redis_client": redis_client,
        "namespace": namespace,
        "key_prefix": prefix,
    }
    if ttl is not None:
        kwargs["ttl"] = ttl
    return (), kwargs, warnings


def _construct_async_redis_saver(
    *,
    redis_client: Any,
    namespace: str,
    prefix: str,
    ttl: Optional[int],
) -> BaseCheckpointSaver:
    supported_params = _async_redis_saver_supported_params()
    args, kwargs, warnings = _build_async_redis_saver_kwargs(
        redis_client=redis_client,
        namespace=namespace,
        prefix=prefix,
        ttl=ttl,
        supported_params=supported_params,
    )

    attempts: list[tuple[tuple[Any, ...], dict[str, Any], list[tuple[str, dict[str, Any]]]]] = [
        (args, kwargs, warnings)
    ]

    combined_namespace = f"{prefix}:{namespace}"
    fallback_kwargs = [
        {"namespace": namespace, "key_prefix": prefix, "ttl": ttl},
        {"namespace": namespace, "key_prefix": prefix, "ttl_seconds": ttl},
        {"namespace": namespace, "prefix": prefix, "ttl": ttl},
        {"namespace": namespace, "prefix": prefix, "ttl_seconds": ttl},
        {"namespace": namespace, "ttl": ttl},
        {"namespace": namespace, "ttl_seconds": ttl},
        {"key_prefix": prefix, "ttl": ttl},
        {"key_prefix": prefix, "ttl_seconds": ttl},
        {"prefix": prefix, "ttl": ttl},
        {"prefix": prefix, "ttl_seconds": ttl},
        {"namespace": combined_namespace, "ttl": ttl},
        {"namespace": combined_namespace, "ttl_seconds": ttl},
        {"key_prefix": combined_namespace, "ttl": ttl},
        {"key_prefix": combined_namespace, "ttl_seconds": ttl},
        {},
    ]

    if supported_params is not None:
        for entry in fallback_kwargs:
            attempts.append(
                (
                    args,
                    {k: v for k, v in entry.items() if v is not None and k in supported_params},
                    [],
                )
            )
    else:
        for entry in fallback_kwargs:
            attempts.append(
                (
                    (redis_client,),
                    {k: v for k, v in entry.items() if v is not None},
                    [],
                )
            )

    last_error: Exception | None = None
    for attempt_args, attempt_kwargs, attempt_warnings in attempts:
        try:
            saver = AsyncRedisSaver(*attempt_args, **attempt_kwargs)  # type: ignore[misc]
        except Exception as exc:
            last_error = exc
            continue
        logged_events = set()
        for event, payload in attempt_warnings:
            logged_events.add(event)
            logger.warning(event, **payload)
        has_namespace = "namespace" in attempt_kwargs
        has_prefix = any(key in attempt_kwargs for key in ("key_prefix", "prefix"))
        has_ttl = any(key in attempt_kwargs for key in ("ttl", "ttl_seconds"))

        if ttl is not None and not has_ttl and "langgraph_v2_checkpointer_ttl_unsupported" not in logged_events:
            logger.warning("langgraph_v2_checkpointer_ttl_unsupported", ttl=ttl)

        if not has_namespace and not has_prefix and "langgraph_v2_checkpointer_namespace_prefix_unsupported" not in logged_events:
            logger.warning(
                "langgraph_v2_checkpointer_namespace_prefix_unsupported",
                namespace=namespace,
                prefix=prefix,
            )
        elif not has_namespace and has_prefix and "langgraph_v2_checkpointer_namespace_unsupported" not in logged_events:
            logger.warning(
                "langgraph_v2_checkpointer_namespace_unsupported",
                namespace=namespace,
                prefix=prefix,
            )
        elif has_namespace and not has_prefix and "langgraph_v2_checkpointer_prefix_unsupported" not in logged_events:
            logger.warning(
                "langgraph_v2_checkpointer_prefix_unsupported",
                namespace=namespace,
                prefix=prefix,
                combined_namespace=f"{prefix}:{namespace}",
            )
        return saver

    if last_error:
        raise last_error
    raise RuntimeError("AsyncRedisSaver construction failed without error details")


async def make_v2_checkpointer_async(
    require_async: bool = True,
    namespace: str | None = None,
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
    resolved_namespace, prefix, ttl = _resolve_checkpointer_settings(namespace)

    if backend == "redis" and AsyncRedisSaver is not None:
        conn_string = os.getenv("LANGGRAPH_V2_REDIS_URL") or os.getenv("REDIS_URL")
        if conn_string:
            try:
                logger.info(
                    "langgraph_v2_checkpointer_init",
                    backend="redis",
                    async_mode=require_async,
                    allow_memory_fallback=True,
                    namespace=resolved_namespace,
                    prefix=prefix,
                    ttl=ttl,
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
                saver = _construct_async_redis_saver(
                    redis_client=redis_client,
                    namespace=resolved_namespace,
                    prefix=prefix,
                    ttl=ttl,
                )
                await saver.asetup()
                return saver

            except Exception as exc:  # pragma: no cover - protected fallback
                logger.warning(
                    "langgraph_v2_checkpointer_init_failed",
                    backend="redis",
                    error=str(exc),
                    fallback="memory",
                )

    logger.info(
        "langgraph_v2_checkpointer_init",
        backend="memory",
        async_mode=require_async,
        allow_memory_fallback=True,
        namespace=resolved_namespace,
        prefix=prefix,
        ttl=ttl,
    )
    return MemorySaver()


def make_v2_checkpointer(
    require_async: bool = True,
    namespace: str | None = None,
) -> BaseCheckpointSaver:
    return asyncio.run(
        make_v2_checkpointer_async(require_async=require_async, namespace=namespace)
    )
