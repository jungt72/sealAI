from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

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
os.environ.setdefault("keycloak_client_id", "test-client")
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

from app.api.v1.endpoints import rag as rag_endpoint
from app.models.rag_document import RagDocument
from app.services.auth import dependencies as auth_dependencies
from app.services.auth.dependencies import RequestUser


class DummySession:
    def __init__(self, doc: RagDocument) -> None:
        self.doc = doc
        self.saved = False

    async def get(self, _model, key):
        return self.doc if key == self.doc.document_id else None

    def add(self, _obj) -> None:
        self.saved = True

    async def commit(self) -> None:
        return None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_rag_retry_endpoint_denies_without_privileged_role(tmp_path: Path) -> None:
    doc = RagDocument(
        document_id="doc-1",
        tenant_id="tenant-1",
        status="failed",
        visibility="private",
        filename="doc.txt",
        content_type="text/plain",
        size_bytes=4,
        category=None,
        tags=None,
        sha256="sha-1",
        path=str(tmp_path / "doc.txt"),
    )
    session = DummySession(doc)
    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="viewer",
        sub="sub-1",
        roles=[],
    )

    try:
        await rag_endpoint.retry_rag_document(
            document_id="doc-1",
            current_user=user,
            session=session,
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for viewer retry.")


@pytest.mark.anyio
async def test_rag_retry_endpoint_allows_realm_admin_role(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    doc = RagDocument(
        document_id="doc-1",
        tenant_id="tenant-1",
        status="failed",
        visibility="private",
        filename="doc.txt",
        content_type="text/plain",
        size_bytes=4,
        category=None,
        tags=None,
        sha256="sha-1",
        path=str(tmp_path / "doc.txt"),
    )
    session = DummySession(doc)

    payload = {
        "sub": "user-1",
        "tenant_id": "tenant-1",
        "preferred_username": "realm-admin",
        "realm_access": {"roles": ["admin"]},
        "resource_access": {"account": {"roles": ["manage-account"]}},
        "azp": "sealai-dev-cli",
    }

    monkeypatch.setattr(auth_dependencies, "verify_access_token", lambda _token: payload)

    user = await auth_dependencies.get_current_request_user(authorization="Bearer test-token")

    captured = {}

    async def fake_enqueue(_channel: str, job_payload):
        captured.update(job_payload)
        return None

    monkeypatch.setattr(rag_endpoint, "enqueue_job", fake_enqueue)

    result = await rag_endpoint.retry_rag_document(
        document_id="doc-1",
        current_user=user,
        session=session,
    )

    assert result == {"document_id": "doc-1", "status": "queued"}
    assert captured.get("tenant_id") == "tenant-1"
    assert doc.status == "queued"


@pytest.mark.anyio
async def test_retry_endpoint_enqueues_job(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    doc = RagDocument(
        document_id="doc-1",
        tenant_id="tenant-1",
        status="failed",
        visibility="private",
        filename="doc.txt",
        content_type="text/plain",
        size_bytes=4,
        category=None,
        tags=None,
        sha256="sha-1",
        path=str(tmp_path / "doc.txt"),
    )
    session = DummySession(doc)
    captured = {}

    async def fake_enqueue(_channel: str, payload):
        captured.update(payload)
        return None

    monkeypatch.setattr(rag_endpoint, "enqueue_job", fake_enqueue)

    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="admin",
        sub="sub-1",
        roles=["admin"],
    )

    payload = await rag_endpoint.retry_rag_document(
        document_id="doc-1",
        current_user=user,
        session=session,
    )

    assert payload == {"document_id": "doc-1", "status": "queued"}
    assert captured.get("document_id") == "doc-1"
    assert captured.get("tenant_id") == "tenant-1"
    assert doc.status == "queued"
