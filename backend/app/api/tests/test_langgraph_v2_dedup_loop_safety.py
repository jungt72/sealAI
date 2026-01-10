from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from weakref import WeakKeyDictionary

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

from app.api.v1.endpoints import langgraph_v2 as endpoint


def _run_in_loop(loop: asyncio.AbstractEventLoop, coro):
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)


def test_dedup_redis_is_scoped_to_event_loop(monkeypatch) -> None:
    created = []

    def fake_make_client(url: str, *, decode_responses: bool = False):
        client = object()
        created.append((url, decode_responses, client))
        return client

    monkeypatch.setenv("LANGGRAPH_V2_REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(endpoint, "make_async_redis_client", fake_make_client)
    monkeypatch.setattr(endpoint, "Redis", object())
    monkeypatch.setattr(endpoint, "_DEDUP_STORE", WeakKeyDictionary())

    loop_a = asyncio.new_event_loop()
    try:
        client_a = _run_in_loop(loop_a, endpoint._get_dedup_redis())
        client_a_second = _run_in_loop(loop_a, endpoint._get_dedup_redis())
    finally:
        loop_a.close()

    loop_b = asyncio.new_event_loop()
    try:
        client_b = _run_in_loop(loop_b, endpoint._get_dedup_redis())
    finally:
        loop_b.close()

    assert client_a is client_a_second
    assert client_a is not client_b
    assert created[0][0] == "redis://example:6379/0"
    assert created[0][1] is True
