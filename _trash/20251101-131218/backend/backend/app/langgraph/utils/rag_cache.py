# MIGRATION: Phase-2 – RAG caching utility with Redis TTL
"""Caching layer for RAG retrieval results using Redis with TTL."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from ..state import ContextRef


class RAGCache:
    """Redis-based cache for RAG retrieval results."""

    def __init__(self, redis_url: str | None = None, namespace: str = "rag"):
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.namespace = namespace
        self._redis = None

    def _get_redis(self):
        if self._redis is None and self.redis_url:
            try:
                import redis
                self._redis = redis.from_url(self.redis_url)
            except ImportError:
                pass
        return self._redis

    def _cache_key(self, query: str, filters: Dict[str, Any], index_id: str, top_k: int) -> str:
        """Generate deterministic cache key from query parameters."""
        key_data = {
            "query": query,
            "filters": json.dumps(filters, sort_keys=True),
            "index_id": index_id,
            "top_k": top_k,
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return f"{self.namespace}:{hashlib.sha256(key_str.encode()).hexdigest()[:16]}"

    def get(self, query: str, filters: Dict[str, Any], index_id: str, top_k: int) -> Optional[List[ContextRef]]:
        """Retrieve cached RAG results if available."""
        redis = self._get_redis()
        if not redis:
            return None

        try:
            cache_key = self._cache_key(query, filters, index_id, top_k)
            cached = redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return [ContextRef.model_validate(ref) for ref in data]
        except Exception:
            pass
        return None

    def set(self, query: str, filters: Dict[str, Any], index_id: str, top_k: int,
            results: List[ContextRef], ttl_seconds: int = 3600) -> None:
        """Cache RAG results with TTL."""
        redis = self._get_redis()
        if not redis:
            return

        try:
            cache_key = self._cache_key(query, filters, index_id, top_k)
            data = [ref.model_dump() for ref in results]
            redis.setex(cache_key, ttl_seconds, json.dumps(data))
        except Exception:
            pass


# Global cache instance
_rag_cache = RAGCache()


def get_rag_cache() -> RAGCache:
    """Get the global RAG cache instance."""
    return _rag_cache


__all__ = ["RAGCache", "get_rag_cache"]