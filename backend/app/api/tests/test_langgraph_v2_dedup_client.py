from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

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

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402


def test_get_dedup_redis_uses_shared_helper(monkeypatch) -> None:
    called = {}
    dummy_client = object()

    def fake_make_client(url: str, *, decode_responses: bool = False):
        called["url"] = url
        called["decode_responses"] = decode_responses
        return dummy_client

    monkeypatch.setenv("LANGGRAPH_V2_REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(endpoint, "make_async_redis_client", fake_make_client)
    monkeypatch.setattr(endpoint, "Redis", object())
    endpoint._DEDUP_REDIS = None

    client = asyncio.run(endpoint._get_dedup_redis())

    assert client is dummy_client
    assert called == {"url": "redis://example:6379/0", "decode_responses": True}
