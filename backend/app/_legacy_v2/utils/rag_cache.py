"""RAG cache utility with Redis primary storage and in-memory fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Optional

from app.core.config import settings

log = logging.getLogger("app._legacy_v2.utils.rag_cache")


class RAGCache:
    """Tenant-scoped cache for RAG retrieval payloads."""

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        key_prefix: str = "sealai:rag_cache:v1",
        max_entries: int = 1024,
    ) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL") or settings.redis_url
        self._key_prefix = key_prefix
        self._max_entries = max_entries
        self._local: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()
        self._redis = self._init_redis_client()

    def _init_redis_client(self) -> Any:
        try:
            from redis import Redis

            return Redis.from_url(self._redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - fallback path
            log.debug("rag_cache.redis_unavailable", extra={"error": str(exc)})
            return None

    def _key(self, tenant_id: str, query: str) -> str:
        normalized_query = " ".join((query or "").strip().lower().split())
        query_hash = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
        tenant = (tenant_id or "global").strip() or "global"
        return f"{self._key_prefix}:{tenant}:{query_hash}"

    def get(self, tenant_id: str, query: str) -> Optional[Any]:
        key = self._key(tenant_id, query)

        if self._redis is not None:
            try:
                raw = self._redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as exc:  # pragma: no cover - fallback path
                log.debug("rag_cache.redis_get_failed", extra={"error": str(exc)})

        now = time.time()
        with self._lock:
            entry = self._local.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at <= now:
                self._local.pop(key, None)
                return None
            self._local.move_to_end(key)
            return value

    def set(self, tenant_id: str, query: str, results: Any, ttl: int = 3600) -> None:
        key = self._key(tenant_id, query)

        if self._redis is not None:
            try:
                self._redis.setex(key, ttl, json.dumps(results, ensure_ascii=True))
            except Exception as exc:  # pragma: no cover - fallback path
                log.debug("rag_cache.redis_set_failed", extra={"error": str(exc)})

        expires_at = time.time() + max(int(ttl), 1)
        with self._lock:
            self._local[key] = (expires_at, results)
            self._local.move_to_end(key)
            while len(self._local) > self._max_entries:
                self._local.popitem(last=False)

