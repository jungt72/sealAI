from __future__ import annotations

import asyncio
import os
import sys
import types

import pytest

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

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub

from app.services.jobs import worker


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class CancelledBrpopRedis:
    async def zrangebyscore(self, _key: str, _min: float, _max: float):
        return []

    async def zrem(self, _key: str, *_members: str) -> None:
        return None

    async def brpop(self, _key: str, timeout: float = 0):
        raise asyncio.CancelledError


@pytest.mark.anyio
async def test_consume_redis_job_once_returns_false_on_brpop_cancellation() -> None:
    redis = CancelledBrpopRedis()
    processed = await worker.consume_redis_job_once(redis)
    assert processed is False
