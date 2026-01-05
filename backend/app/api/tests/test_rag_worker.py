from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

# Ensure backend is on path
sys.path.append(str(Path(__file__).resolve().parents[3]))
if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub

# Minimal env defaults for settings to load
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

from app.models.rag_document import RagDocument  # noqa: E402
from app.services.jobs import worker  # noqa: E402


class DummySession:
    def add(self, _obj) -> None:
        return None

    async def commit(self) -> None:
        return None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_process_once_updates_status(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello")
    doc = RagDocument(
        document_id="doc-1",
        tenant_id="tenant-1",
        status="queued",
        visibility="private",
        category="norms",
        tags=["a"],
        sha256="hash",
        path=str(file_path),
    )

    async def picker(_session):
        return doc

    def fake_ingest(_path, **_kwargs):
        return None

    done = await worker.process_once(
        DummySession(),
        ingest_func=fake_ingest,
        use_thread=False,
        picker=picker,
    )
    assert done is True
    assert doc.status == "done"
    assert isinstance(doc.ingest_stats, dict)
