from __future__ import annotations

import hashlib
import os
import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

# Ensure backend is on path
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
from app.services.auth.dependencies import RequestUser, get_current_request_user  # noqa: E402
from app.services.rag import utils as rag_utils  # noqa: E402


class DummyResult:
    def __init__(self, items) -> None:
        self._items = list(items)

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return self._items


class DummySession:
    def __init__(self) -> None:
        self.docs = {}

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


def _configure_upload_root(tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    rag_utils.UPLOAD_ROOT = str(tmp_path)
    rag_utils._UPLOAD_DIR_READY = False


@pytest.mark.anyio
async def test_rag_upload_unauthorized(tmp_path: Path) -> None:
    _configure_upload_root(tmp_path)
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    try:
        await rag_endpoint.upload_rag_document(
            file=file_obj,
            current_user=await get_current_request_user(authorization=None),
            session=DummySession(),
        )
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected HTTPException for missing auth.")


@pytest.mark.anyio
async def test_rag_upload_and_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_upload_root(tmp_path)
    dummy_session = DummySession()

    user = RequestUser(user_id="tenant-1", username="user", sub="tenant-1", roles=[])
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    payload = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="private",
        current_user=user,
        session=dummy_session,
    )
    assert payload["status"] == "processing"
    document_id = payload["document_id"]

    status_payload = await rag_endpoint.get_rag_document(
        document_id=document_id,
        current_user=user,
        session=dummy_session,
    )
    assert status_payload["status"] == "processing"

    stored = next(iter(dummy_session.docs.values()))
    assert Path(stored.path).exists()
    assert stored.route_key == "general_technical_doc"


@pytest.mark.anyio
async def test_rag_upload_dedup_same_tenant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_upload_root(tmp_path)
    dummy_session = DummySession()

    user = RequestUser(user_id="tenant-1", username="user", sub="tenant-1", roles=[])
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    first = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="private",
        current_user=user,
        session=dummy_session,
    )

    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    second = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="private",
        current_user=user,
        session=dummy_session,
    )

    assert first["document_id"] == second["document_id"]
    assert len(dummy_session.docs) == 1


@pytest.mark.anyio
async def test_rag_upload_same_sha_different_tenant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_upload_root(tmp_path)
    dummy_session = DummySession()

    user_a = RequestUser(user_id="tenant-a", username="user", sub="tenant-a", roles=[])
    user_b = RequestUser(user_id="tenant-b", username="user", sub="tenant-b", roles=[])

    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    first = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="private",
        current_user=user_a,
        session=dummy_session,
    )

    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    second = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="private",
        current_user=user_b,
        session=dummy_session,
    )

    assert first["document_id"] != second["document_id"]
    assert len(dummy_session.docs) == 2


@pytest.mark.anyio
async def test_rag_upload_retry_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_upload_root(tmp_path)
    dummy_session = DummySession()

    tenant_id = "tenant-1"
    existing_id = "existing-doc"
    existing_dir = tmp_path / tenant_id / existing_id
    existing_dir.mkdir(parents=True, exist_ok=True)
    existing_path = existing_dir / "original.txt"
    existing_path.write_bytes(b"hello")

    sha256 = hashlib.sha256(b"hello").hexdigest()
    failed_doc = RagDocument(
        document_id=existing_id,
        tenant_id=tenant_id,
        status="failed",
        visibility="private",
        filename="doc.txt",
        content_type="text/plain",
        size_bytes=len(b"hello"),
        category=None,
        tags=None,
        sha256=sha256,
        path=str(existing_path),
        error="failed",
    )
    dummy_session.add(failed_doc)

    user = RequestUser(user_id=tenant_id, username="user", sub=tenant_id, roles=[])
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    payload = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="private",
        current_user=user,
        session=dummy_session,
    )

    assert payload["document_id"] == existing_id
    stored = dummy_session.docs[existing_id]
    assert stored.status == "processing"
    assert stored.error is None


@pytest.mark.anyio
async def test_rag_upload_prefers_tenant_claim_over_user_id(tmp_path: Path) -> None:
    _configure_upload_root(tmp_path)
    dummy_session = DummySession()

    user = RequestUser(user_id="user-1", username="user", sub="user-1", roles=[], tenant_id="tenant-1")
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")
    payload = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="private",
        current_user=user,
        session=dummy_session,
    )

    stored = dummy_session.docs[payload["document_id"]]
    assert stored.tenant_id == "tenant-1"


@pytest.mark.anyio
async def test_rag_document_access_prefers_tenant_claim_over_user_id(tmp_path: Path) -> None:
    _configure_upload_root(tmp_path)
    dummy_session = DummySession()

    doc = RagDocument(
        document_id="doc-1",
        tenant_id="tenant-1",
        status="indexed",
        visibility="private",
        filename="doc.txt",
        content_type="text/plain",
        size_bytes=5,
        category=None,
        tags=None,
        sha256=hashlib.sha256(b"hello").hexdigest(),
        path=str(tmp_path / "tenant-1" / "doc-1" / "original.txt"),
    )
    dummy_session.add(doc)

    user = RequestUser(user_id="user-1", username="user", sub="user-1", roles=[], tenant_id="tenant-1")
    payload = await rag_endpoint.get_rag_document(
        document_id="doc-1",
        current_user=user,
        session=dummy_session,
    )

    assert payload["document_id"] == "doc-1"
