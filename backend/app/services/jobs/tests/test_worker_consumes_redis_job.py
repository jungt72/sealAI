from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

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

from app.models.rag_document import RagDocument
from app.services.jobs import worker


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def brpop(self, key: str, timeout: float = 0) -> tuple[str, str] | None:
        items = self.lists.get(key) or []
        if not items:
            return None
        value = items.pop(0)
        return key, value

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        bucket = self.zsets.setdefault(key, {})
        bucket.update(mapping)

    async def zrangebyscore(self, key: str, _min: float, _max: float):
        bucket = self.zsets.get(key) or {}
        return [member for member, score in bucket.items() if score <= _max]

    async def zrem(self, key: str, *members: str) -> None:
        bucket = self.zsets.get(key) or {}
        for member in members:
            bucket.pop(member, None)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class DummySession:
    def __init__(self, doc: RagDocument) -> None:
        self.doc = doc

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb):
        return None

    async def get(self, _model, key):
        return self.doc if key == self.doc.document_id else None

    def add(self, _obj) -> None:
        return None

    async def commit(self) -> None:
        return None


@pytest.mark.anyio
async def test_worker_consumes_redis_job(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.txt"
    file_path.write_text("test")
    doc = RagDocument(
        document_id="doc-1",
        tenant_id="tenant-1",
        status="queued",
        visibility="private",
        filename="doc.txt",
        content_type="text/plain",
        size_bytes=4,
        category=None,
        tags=None,
        sha256="sha-1",
        path=str(file_path),
    )

    redis = FakeRedis()
    payload = {
        "tenant_id": "tenant-1",
        "document_id": "doc-1",
        "filepath": str(file_path),
        "original_filename": "doc.txt",
        "uploader_id": "user-1",
        "visibility": "private",
        "tags": None,
        "sha256": "sha-1",
    }
    await redis.rpush(worker.JOB_QUEUE, json.dumps(payload))

    def fake_ingest(_path, **_kwargs):
        return {"chunks": 1}

    processed = await worker.consume_redis_job_once(
        redis,
        ingest_func=fake_ingest,
        use_thread=False,
        session_factory=lambda: DummySession(doc),
    )

    assert processed is True
    assert doc.status == "done"
