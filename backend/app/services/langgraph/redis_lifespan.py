# backend/app/services/langgraph/redis_lifespan.py
from __future__ import annotations

import os
import logging
from typing import Optional, Any

log = logging.getLogger("app.redis_checkpointer")

# RedisSaver (sync). Unterschiedliche Versionen haben verschiedene __init__-Signaturen.
try:
    from langgraph.checkpoint.redis import RedisSaver  # type: ignore
except Exception as e:  # pragma: no cover
    RedisSaver = None  # type: ignore
    log.warning("LangGraph RedisSaver nicht importierbar: %s", e)


def _redis_url() -> str:
    """
    Liefert eine normierte REDIS_URL (inkl. DB-Index), Default: redis://redis:6379/0
    """
    url = (os.getenv("REDIS_URL") or "redis://redis:6379/0").strip()
    return url or "redis://redis:6379/0"


def _namespace() -> tuple[str, Optional[int]]:
    """
    Erzeugt einen einheitlichen Namespace/Key-Präfix (kompatibel zu namespace|key_prefix).
    TTL optional.
    """
    raw_ns = (os.getenv("LANGGRAPH_CHECKPOINT_NS") or os.getenv("CHECKPOINT_NS") or "chat.supervisor.v1").strip()
    prefix = (os.getenv("LANGGRAPH_CHECKPOINT_PREFIX") or "lg:cp").strip()
    ttl_env = (os.getenv("LANGGRAPH_CHECKPOINT_TTL") or "").strip()
    ttl = int(ttl_env) if ttl_env.isdigit() else None
    ns = f"{prefix}:{raw_ns}"
    return ns, ttl


def _try_construct_redis_saver(redis_url: str, ns: str, ttl: Optional[int]) -> Any:
    """
    Probiert mehrere Konstruktor-Varianten – kompatibel zu alten/neuen Paketen.
    Gibt den ersten erfolgreichen Saver zurück, sonst Exception.
    """
    errors: list[tuple[dict, Exception]] = []

    # 1) Neuere Pakete – URL-basiert
    for kwargs in (
        {"redis_url": redis_url, "namespace": ns, "ttl_seconds": ttl},
        {"redis_url": redis_url, "key_prefix": ns, "ttl_seconds": ttl},
        {"redis_url": redis_url, "ttl_seconds": ttl},
        {"redis_url": redis_url},
    ):
        try:
            return RedisSaver(**{k: v for k, v in kwargs.items() if v is not None})  # type: ignore[misc]
        except Exception as e:
            errors.append((kwargs, e))

    # 2) Ältere Pakete – Client-basiert
    try:
        from redis import Redis as _Redis
        client = _Redis.from_url(redis_url)
        for kwargs in (
            {"redis": client, "namespace": ns, "ttl_seconds": ttl},
            {"redis": client, "key_prefix": ns, "ttl_seconds": ttl},
            {"redis": client, "ttl_seconds": ttl},
            {"redis": client},
        ):
            try:
                return RedisSaver(**{k: v for k, v in kwargs.items() if v is not None})  # type: ignore[misc]
            except Exception as e:
                errors.append((kwargs, e))
    except Exception as e:
        errors.append(({"redis_client_build": True}, e))

    # Letzte Fehlermeldung ausgeben und erneut werfen
    if errors:
        kw, err = errors[-1]
        log.warning("RedisSaver-Konstruktion fehlgeschlagen. Letzter Versuch %s: %r", kw, err)
        raise err
    raise RuntimeError("Unbekannter Fehler bei RedisSaver-Konstruktion")


def get_redis_checkpointer(app=None) -> Optional["RedisSaver"]:
    """
    Erzeugt einen LangGraph-RedisSaver (Checkpointer).
    Gibt None zurück, wenn Paket fehlt oder Konstruktion scheitert.
    ENV:
      REDIS_URL, LANGGRAPH_CHECKPOINT_NS | CHECKPOINT_NS,
      LANGGRAPH_CHECKPOINT_PREFIX, LANGGRAPH_CHECKPOINT_TTL
    """
    if RedisSaver is None:
        log.warning("LangGraph RedisSaver nicht verfügbar. Installiere 'langgraph-checkpoint-redis'.")
        return None

    redis_url = _redis_url()
    ns, ttl = _namespace()

    try:
        saver = _try_construct_redis_saver(redis_url, ns, ttl)
        log.info("LangGraph Checkpointer aktiv: url=%s ns/prefix=%s ttl=%s", redis_url, ns, ttl)
        return saver
    except Exception as e:
        log.warning("RedisSaver nicht nutzbar (%r). Fallback: None (In-Memory-Graph).", e)
        return None
