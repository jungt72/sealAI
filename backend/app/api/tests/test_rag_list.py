from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[3]))
if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub
if "multipart" not in sys.modules:
    multipart_stub = types.ModuleType("multipart")
    multipart_module = types.ModuleType("multipart.multipart")

    def _parse_options_header(_value):
        return {}

    multipart_module.parse_options_header = _parse_options_header
    multipart_stub.__version__ = "0.0.13"
    sys.modules["multipart"] = multipart_stub
    sys.modules["multipart.multipart"] = multipart_module
if "python_multipart" not in sys.modules:
    python_multipart = types.ModuleType("python_multipart")
    python_multipart.__version__ = "0.0.13"
    sys.modules["python_multipart"] = python_multipart

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

from app.api.v1.endpoints import rag as rag_endpoint  # noqa: E402
from app.models.rag_document import RagDocument  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


class DummyResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class DummySession:
    def __init__(self, docs, tenant_id: str):
        self.docs = list(docs)
        self.tenant_id = tenant_id

    async def execute(self, _stmt):
        items = [doc for doc in self.docs if doc.tenant_id == self.tenant_id]
        return DummyResult(items)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_rag_list_filters_by_tenant() -> None:
    doc_a = RagDocument(
        document_id="doc-a",
        tenant_id="tenant-1",
        status="queued",
        visibility="private",
        category="norms",
        tags=["a"],
        sha256="hash-a",
        path="/tmp/a.txt",
        filename="a.txt",
        content_type="text/plain",
        size_bytes=10,
    )
    doc_b = RagDocument(
        document_id="doc-b",
        tenant_id="tenant-2",
        status="queued",
        visibility="private",
        category="norms",
        tags=["b"],
        sha256="hash-b",
        path="/tmp/b.txt",
        filename="b.txt",
        content_type="text/plain",
        size_bytes=12,
    )
    user = RequestUser(user_id="tenant-1", username="user", sub="tenant-1", roles=[])
    session = DummySession([doc_a, doc_b], tenant_id=user.user_id)

    payload = await rag_endpoint.list_rag_documents(
        limit=20,
        current_user=user,
        session=session,
    )
    items = payload.get("items") or []
    assert len(items) == 1
    assert items[0]["document_id"] == "doc-a"


@pytest.mark.anyio
async def test_rag_list_prefers_tenant_claim_over_user_id() -> None:
    doc_a = RagDocument(
        document_id="doc-a",
        tenant_id="tenant-1",
        status="queued",
        visibility="private",
        category="norms",
        tags=["a"],
        sha256="hash-a",
        path="/tmp/a.txt",
        filename="a.txt",
        content_type="text/plain",
        size_bytes=10,
    )
    doc_b = RagDocument(
        document_id="doc-b",
        tenant_id="user-1",
        status="queued",
        visibility="private",
        category="norms",
        tags=["b"],
        sha256="hash-b",
        path="/tmp/b.txt",
        filename="b.txt",
        content_type="text/plain",
        size_bytes=12,
    )
    user = RequestUser(user_id="user-1", username="user", sub="user-1", roles=[], tenant_id="tenant-1")
    session = DummySession([doc_a, doc_b], tenant_id=user.tenant_id)

    payload = await rag_endpoint.list_rag_documents(
        limit=20,
        current_user=user,
        session=session,
    )
    items = payload.get("items") or []
    assert len(items) == 1
    assert items[0]["document_id"] == "doc-a"
