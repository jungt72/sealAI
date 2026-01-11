from __future__ import annotations

import os
from functools import lru_cache

try:
    from qdrant_client import QdrantClient
except ImportError:  # pragma: no cover - optional dependency
    QdrantClient = None  # type: ignore[assignment]


def get_qdrant_url() -> str:
    return (os.getenv("QDRANT_URL") or "http://qdrant:6333").rstrip("/")


def get_qdrant_timeout_sec() -> float:
    raw = (os.getenv("QDRANT_TIMEOUT_SEC") or os.getenv("QDRANT_TIMEOUT_S") or "10").strip()
    try:
        return float(raw)
    except ValueError:
        return 10.0


@lru_cache(maxsize=1)
def get_qdrant_client() -> "QdrantClient":
    if QdrantClient is None:
        raise RuntimeError("qdrant-client is not available")
    url = get_qdrant_url()
    api_key = (os.getenv("QDRANT_API_KEY") or "").strip() or None
    timeout_s = get_qdrant_timeout_sec()
    return QdrantClient(url=url, api_key=api_key, timeout=timeout_s)


def build_httpx_timeout(timeout_s: float):
    import httpx

    return httpx.Timeout(
        timeout_s,
        connect=timeout_s,
        read=timeout_s,
        write=timeout_s,
        pool=timeout_s,
    )
