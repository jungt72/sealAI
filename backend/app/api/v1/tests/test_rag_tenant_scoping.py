from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

# Ensure backend is on path
sys.path.append(str(Path(__file__).resolve().parents[4]))

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

from app.api.v1.endpoints import rag as rag_endpoint  # noqa: E402
from app.models.rag_document import RagDocument  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


class DummyResult:
    def __init__(self, items) -> None:
        self._items = list(items)

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class DummySession:
    def __init__(self) -> None:
        self.docs: dict[str, RagDocument] = {}

    def add(self, obj) -> None:
        self.docs[getattr(obj, "document_id")] = obj

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj) -> None:
        return None

    async def execute(self, stmt):
        items = list(self.docs.values())
        tenant_id = None
        sha256 = None
        for criterion in getattr(stmt, "_where_criteria", []):
            left = getattr(criterion, "left", None)
            right = getattr(criterion, "right", None)
            name = getattr(left, "name", None)
            value = getattr(right, "value", None)
            if name == "tenant_id":
                tenant_id = value
            elif name == "sha256":
                sha256 = value
        if tenant_id is not None:
            items = [item for item in items if item.tenant_id == tenant_id]
        if sha256 is not None:
            items = [item for item in items if item.sha256 == sha256]
        return DummyResult(items)

    async def get(self, _model, key):
        return self.docs.get(key)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class DummyUploadFile:
    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self.content_type = "text/plain"
        self._data = data
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._data):
            return b""
        if size is None or size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    async def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_rag_upload_and_list_are_tenant_scoped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    dummy_session = DummySession()
    enqueued = []

    async def fake_enqueue(_channel: str, payload):
        enqueued.append(payload)
        return None

    monkeypatch.setattr(rag_endpoint, "enqueue_job", fake_enqueue)
    user = RequestUser(
        user_id="user-123",
        tenant_id="tenant-1",
        username="user",
        sub="sub-123",
        roles=["admin"],
    )
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    payload = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="private",
        current_user=user,
        session=dummy_session,
    )

    document_id = payload["document_id"]
    stored = dummy_session.docs.get(document_id)
    assert stored is not None
    assert stored.tenant_id == "tenant-1"
    assert stored.tenant_id != user.user_id
    assert stored.tenant_id != user.sub

    other_doc = RagDocument(
        document_id="doc-tenant-2",
        tenant_id="tenant-2",
        status="queued",
        visibility="private",
        sha256="hash-2",
        path=str(tmp_path / "tenant-2" / "doc-tenant-2" / "original.txt"),
    )
    dummy_session.add(other_doc)

    list_resp = await rag_endpoint.list_rag_documents(
        limit=20,
        status=None,
        category=None,
        visibility=None,
        current_user=user,
        session=dummy_session,
    )
    items = list_resp.get("items") or []
    assert all(item.get("tenant_id") == "tenant-1" for item in items)
    assert "doc-tenant-2" not in {item.get("document_id") for item in items}

    assert enqueued, "Expected enqueue_job to be called for upload."
