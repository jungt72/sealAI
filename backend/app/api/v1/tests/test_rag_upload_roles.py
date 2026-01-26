from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

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
from app.services.auth.dependencies import RequestUser  # noqa: E402


class DummySession:
    def __init__(self) -> None:
        self.docs = {}

    def add(self, obj) -> None:
        self.docs[getattr(obj, "document_id")] = obj

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj) -> None:
        return None

    async def execute(self, _stmt):
        class _Result:
            def scalars(self):
                return self

            def first(self):
                return None

        return _Result()


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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_rag_upload_rejects_viewer_roles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    dummy_session = DummySession()

    async def fake_enqueue(_channel: str, _payload):
        return None

    monkeypatch.setattr(rag_endpoint, "enqueue_job", fake_enqueue)
    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="viewer",
        sub="sub-1",
        roles=[],
    )
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    try:
        await rag_endpoint.upload_rag_document(
            file=file_obj,
            category=None,
            tags=None,
            visibility="private",
            current_user=user,
            session=dummy_session,
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for viewer upload.")


@pytest.mark.anyio
async def test_kb_upload_admin_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    dummy_session = DummySession()

    async def fake_enqueue(_channel: str, _payload):
        return None

    monkeypatch.setattr(rag_endpoint, "enqueue_job", fake_enqueue)
    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="admin",
        sub="sub-1",
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
    assert payload["status"] == "queued"


@pytest.mark.anyio
async def test_kb_upload_default_visibility_public(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    dummy_session = DummySession()

    async def fake_enqueue(_channel: str, _payload):
        return None

    monkeypatch.setattr(rag_endpoint, "enqueue_job", fake_enqueue)
    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="admin",
        sub="sub-1",
        roles=["admin"],
    )
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    payload = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        current_user=user,
        session=dummy_session,
    )
    doc = dummy_session.docs.get(payload["document_id"])
    assert doc is not None
    assert doc.visibility == "public"


@pytest.mark.anyio
async def test_rag_upload_rejects_editor_role(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    dummy_session = DummySession()

    async def fake_enqueue(_channel: str, _payload):
        return None

    monkeypatch.setattr(rag_endpoint, "enqueue_job", fake_enqueue)
    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="editor",
        sub="sub-1",
        roles=["editor"],
    )
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    try:
        await rag_endpoint.upload_rag_document(
            file=file_obj,
            category=None,
            tags=None,
            visibility="private",
            current_user=user,
            session=dummy_session,
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for editor upload.")
