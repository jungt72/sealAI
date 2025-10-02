# backend/app/redis_checkpointer.py
import os
import logging

log = logging.getLogger(__name__)

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if (v is not None and str(v).strip() != "") else default

def normalize_pg_dsn(dsn: str) -> str:
    """Nur für Log-Ausgaben nützlich; hier nicht verwendet."""
    if dsn.startswith("postgresql+psycopg://"):
        return "postgresql://" + dsn.split("postgresql+psycopg://", 1)[1]
    if dsn.startswith("postgres://"):
        return "postgresql://" + dsn.split("postgres://", 1)[1]
    return dsn

def get_checkpointer():
    """
    Liefert einen LangGraph-Checkpointer (Redis bevorzugt).
    Verwendet redis.asyncio und decode_responses=True (kein .decode()-Murks).
    """
    # URL/Namensraum/TTL aus ENV lesen (mit sinnvollen Defaults)
    url = _env("LANGGRAPH_CP_URL", _env("REDIS_URL", "redis://redis:6379/0"))
    namespace = _env("LANGGRAPH_CP_NS", "lg:cp:chat.supervisor.v1")
    ttl_raw = _env("LANGGRAPH_CP_TTL", None)
    ttl = int(ttl_raw) if (ttl_raw and ttl_raw.isdigit()) else None

    try:
        # redis.asyncio verwenden, damit es mit async-Servern sauber skaliert
        import redis.asyncio as redis
        from langgraph.checkpoint.redis import RedisSaver

        client = redis.from_url(url, encoding="utf-8", decode_responses=True)
        saver = RedisSaver(client=client, namespace=namespace, ttl=ttl)

        log.info(
            "LangGraph Checkpointer aktiv: url=%s ns/prefix=%s ttl=%s",
            url, namespace, ttl
        )
        return saver
    except Exception as e:
        log.warning("RedisSaver-Init fehlgeschlagen: %s – Fallback auf InMemorySaver", e)
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()
