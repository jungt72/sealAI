"""Regression tests for tenant-safe conversation metadata keys."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable

sys.path.append(str(Path(__file__).resolve().parents[3]))

os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from app.services.chat import conversations  # noqa: E402


class DummyRedis:
    def __init__(self) -> None:
        self._hashes: Dict[str, Dict[str, str]] = {}
        self._sorted_sets: Dict[str, Dict[str, float]] = {}

    def hgetall(self, key: str) -> Dict[str, str]:
        return dict(self._hashes.get(key, {}))

    def hset(self, key: str, mapping: Dict[str, Any]) -> None:
        payload = {str(k): str(v) for k, v in (mapping or {}).items()}
        self._hashes.setdefault(key, {}).update(payload)

    def expire(self, key: str, _ttl: int) -> None:
        return None

    def zadd(self, key: str, mapping: Dict[str, float]) -> None:
        bucket = self._sorted_sets.setdefault(key, {})
        for member, score in (mapping or {}).items():
            bucket[str(member)] = float(score)

    def zcard(self, key: str) -> int:
        return len(self._sorted_sets.get(key, {}))

    def zrevrange(self, key: str, start: int, end: int) -> Iterable[str]:
        items = sorted(
            self._sorted_sets.get(key, {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )
        members = [member for member, _ in items]
        if end < 0:
            end = len(members) - 1
        return members[start : end + 1]

    def zrange(self, key: str, start: int, end: int) -> Iterable[str]:
        items = sorted(
            self._sorted_sets.get(key, {}).items(),
            key=lambda item: item[1],
        )
        members = [member for member, _ in items]
        if end < 0:
            end = len(members) - 1
        return members[start : end + 1]

    def zscore(self, key: str, member: str) -> float | None:
        return self._sorted_sets.get(key, {}).get(member)

    def zrem(self, key: str, *members: str) -> None:
        bucket = self._sorted_sets.get(key)
        if not bucket:
            return
        for member in members:
            bucket.pop(member, None)

    def delete(self, key: str) -> None:
        self._hashes.pop(key, None)
        self._sorted_sets.pop(key, None)

    def pipeline(self):
        parent = self

        class _Pipe:
            def hset(self, key: str, mapping: Dict[str, Any]):
                parent.hset(key, mapping=mapping)
                return self

            def expire(self, key: str, ttl: int):
                parent.expire(key, ttl)
                return self

            def zadd(self, key: str, mapping: Dict[str, float]):
                parent.zadd(key, mapping)
                return self

            def delete(self, key: str):
                parent.delete(key)
                return self

            def zrem(self, key: str, *members: str):
                parent.zrem(key, *members)
                return self

            def execute(self):
                return []

        return _Pipe()


def test_conversation_metadata_isolated_by_tenant(monkeypatch) -> None:
    redis = DummyRedis()
    monkeypatch.setattr(conversations, "_redis_client", lambda: redis)

    conversations.upsert_conversation(
        tenant_id="tenant-a",
        owner_id="user-1",
        conversation_id="conv-a",
        first_user_message="Hallo",
    )
    conversations.upsert_conversation(
        tenant_id="tenant-b",
        owner_id="user-1",
        conversation_id="conv-b",
        first_user_message="Hi",
    )

    tenant_a = conversations.list_conversations("tenant-a", "user-1")
    tenant_b = conversations.list_conversations("tenant-b", "user-1")

    assert {entry.id for entry in tenant_a} == {"conv-a"}
    assert {entry.id for entry in tenant_b} == {"conv-b"}
