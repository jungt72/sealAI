from __future__ import annotations

import os
import sys
import types
from pathlib import Path

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

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import rag as rag_endpoint
from app.models.rag_document import RagDocument
from app.services.auth.dependencies import RequestUser


class DummySession:
    def __init__(self, doc: RagDocument) -> None:
        self.doc = doc
        self.deleted = False

    async def get(self, _model, key):
        if key == self.doc.document_id:
            return self.doc
        return None

    async def delete(self, _doc) -> None:
        self.deleted = True

    async def commit(self) -> None:
        return None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_rag_delete_removes_qdrant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    document_id = "doc-1"
    tenant_id = "tenant-1"
    doc = RagDocument(
        document_id=document_id,
        tenant_id=tenant_id,
        status="queued",
        visibility="private",
        sha256="sha-1",
        path=str(tmp_path / tenant_id / document_id / "original.txt"),
    )
    session = DummySession(doc)
    captured = {}

    def fake_delete_qdrant_points(*, tenant_id: str, document_id: str):
        captured["tenant_id"] = tenant_id
        captured["document_id"] = document_id
        return {"status": "ok"}

    monkeypatch.setattr(rag_endpoint, "delete_qdrant_points", fake_delete_qdrant_points)

    user = RequestUser(
        user_id="user-1",
        tenant_id=tenant_id,
        username="admin",
        sub="sub-1",
        roles=["admin"],
    )

    payload = await rag_endpoint.delete_rag_document(
        document_id=document_id,
        current_user=user,
        session=session,
    )

    assert payload == {"deleted": True, "document_id": document_id}
    assert captured == {"tenant_id": tenant_id, "document_id": document_id}


@pytest.mark.anyio
async def test_rag_delete_denies_non_admin(tmp_path: Path) -> None:
    document_id = "doc-1"
    tenant_id = "tenant-1"
    doc = RagDocument(
        document_id=document_id,
        tenant_id=tenant_id,
        status="queued",
        visibility="private",
        sha256="sha-1",
        path=str(tmp_path / tenant_id / document_id / "original.txt"),
    )
    session = DummySession(doc)
    user = RequestUser(
        user_id="user-1",
        tenant_id=tenant_id,
        username="viewer",
        sub="sub-1",
        roles=[],
    )
    try:
        await rag_endpoint.delete_rag_document(
            document_id=document_id,
            current_user=user,
            session=session,
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for non-admin delete.")
