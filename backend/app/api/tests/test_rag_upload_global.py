import pytest
from pathlib import Path
from fastapi import HTTPException
from app.api.v1.endpoints import rag as rag_endpoint
from app.services.auth.dependencies import RequestUser
from typing import Optional

class DummyResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None

class DummySession:
    def __init__(self) -> None:
        self.docs = {}

    def add(self, obj) -> None:
        self.docs[getattr(obj, "document_id")] = obj

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj) -> None:
        return None

    async def execute(self, stmt) -> DummyResult:
        # Just return empty result for deduplication logic
        return DummyResult([])

class DummyUploadFile:
    def __init__(self, filename: str, data: bytes, content_type: str = "text/plain") -> None:
        self.filename = filename
        self._data = data
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        d = self._data
        self._data = b""
        return d

    async def close(self) -> None:
        return None

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

@pytest.mark.anyio
async def test_rag_upload_global_admin_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    
    # Mock is_rag_admin
    monkeypatch.setattr("app.api.v1.endpoints.rag.is_rag_admin", lambda user: True)
    
    async def fake_enqueue(_channel: str, _payload):
        return None
    monkeypatch.setattr(rag_endpoint, "enqueue_job", fake_enqueue)

    user = RequestUser(user_id="user123", username="admin_user", sub="user123", roles=["sealai-admin"])
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")

    # Call with scope="global"
    status_payload = await rag_endpoint.upload_rag_document(
        file=file_obj,
        category=None,
        tags=None,
        visibility="public",
        scope="global",
        current_user=user,
        session=DummySession(),
    )
    assert status_payload["status"] == "processing"


@pytest.mark.anyio
async def test_rag_upload_global_non_admin_denied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rag_endpoint.UPLOAD_ROOT = str(tmp_path)
    
    # Mock is_rag_admin
    monkeypatch.setattr("app.api.v1.endpoints.rag.is_rag_admin", lambda user: False)

    user = RequestUser(user_id="user123", username="normal_user", sub="user123", roles=[])
    file_obj = DummyUploadFile(filename="doc.txt", data=b"hello")

    try:
        await rag_endpoint.upload_rag_document(
            file=file_obj,
            category=None,
            tags=None,
            visibility="public",
            scope="global",
            current_user=user,
            session=DummySession(),
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected 403 for non-admin attempting global upload")

