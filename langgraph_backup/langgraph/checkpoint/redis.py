"""Lightweight Redis-backed checkpointer compatible with LangGraph API."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

try:  # optional dependency
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


class RedisSaver:
    """Store graph checkpoints inside Redis (falls back to in-memory storage)."""

    def __init__(self, client: Any | None, *, key_prefix: str = "langgraph") -> None:
        self._client = client
        self._key_prefix = key_prefix.rstrip(":")
        self._memory_store: Dict[str, str] = {}

    @classmethod
    def from_conn_string(cls, conn_string: str, *, key_prefix: str = "langgraph") -> "RedisSaver":
        if not conn_string:
            return cls(None, key_prefix=key_prefix)
        if redis is None:
            raise RuntimeError("redis package not available to create RedisSaver")
        client = redis.from_url(conn_string)  # type: ignore[attr-defined]
        return cls(client, key_prefix=key_prefix)

    def _compose_key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    def put(self, key: str, value: Dict[str, Any]) -> None:
        payload = json.dumps(value)
        store_key = self._compose_key(key)
        if self._client is not None:
            self._client.set(store_key, payload)
            return
        self._memory_store[store_key] = payload

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        store_key = self._compose_key(key)
        if self._client is not None:
            data = self._client.get(store_key)
            if not data:
                return None
            if isinstance(data, bytes):
                data = data.decode("utf-8")
        else:
            data = self._memory_store.get(store_key)

        if not data:
            return None

        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)


__all__ = ["RedisSaver"]

