from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

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
from app.services.auth.dependencies import RequestUser  # noqa: E402


class DummySession:
    def add(self, _obj) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj) -> None:
        return None


class DummyUploadFile:
    def __init__(self, filename: str, data: bytes, content_type: str | None) -> None:
        self.filename = filename
        self.content_type = content_type
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
async def test_rag_upload_too_large(tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    rag_endpoint.RAG_UPLOAD_MAX_BYTES = 4
    user = RequestUser(user_id="tenant-1", tenant_id="tenant-1", username="user", sub="tenant-1", roles=["admin"])
    file_obj = DummyUploadFile("doc.txt", b"hello", "text/plain")
    try:
        await rag_endpoint.upload_rag_document(
            file=file_obj,
            visibility="private",
            current_user=user,
            session=DummySession(),
        )
    except HTTPException as exc:
        assert exc.status_code == 413
    else:
        raise AssertionError("Expected upload_too_large")


@pytest.mark.anyio
async def test_rag_upload_invalid_ext(tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    user = RequestUser(user_id="tenant-1", tenant_id="tenant-1", username="user", sub="tenant-1", roles=["admin"])
    file_obj = DummyUploadFile("doc.exe", b"hello", "application/pdf")
    try:
        await rag_endpoint.upload_rag_document(
            file=file_obj,
            visibility="private",
            current_user=user,
            session=DummySession(),
        )
    except HTTPException as exc:
        assert exc.status_code == 415
    else:
        raise AssertionError("Expected unsupported_extension")


@pytest.mark.anyio
async def test_rag_upload_invalid_content_type(tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    user = RequestUser(user_id="tenant-1", tenant_id="tenant-1", username="user", sub="tenant-1", roles=["admin"])
    file_obj = DummyUploadFile("doc.txt", b"hello", "application/octet-stream")
    try:
        await rag_endpoint.upload_rag_document(
            file=file_obj,
            visibility="private",
            current_user=user,
            session=DummySession(),
        )
    except HTTPException as exc:
        assert exc.status_code == 415
    else:
        raise AssertionError("Expected unsupported_content_type")
