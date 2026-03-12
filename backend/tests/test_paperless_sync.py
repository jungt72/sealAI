from __future__ import annotations

import hashlib
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub

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
from app.services.rag import paperless as paperless_mod  # noqa: E402
from app.services.rag.route_resolver import resolve_route_key  # noqa: E402
from app.services.rag import utils as rag_utils  # noqa: E402
from app.services.rag.constants import RAG_SHARED_TENANT_ID  # noqa: E402


class DummyResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None


class DummySession:
    def __init__(self) -> None:
        self.docs: dict[str, RagDocument] = {}

    def add(self, obj) -> None:
        self.docs[getattr(obj, "document_id")] = obj

    async def commit(self) -> None:
        return None

    async def execute(self, stmt):
        items = list(self.docs.values())
        filters = {}
        for criterion in getattr(stmt, "_where_criteria", []):
            left = getattr(criterion, "left", None)
            right = getattr(criterion, "right", None)
            name = getattr(left, "name", None)
            value = getattr(right, "value", None)
            if name:
                filters[name] = value
        for key, value in filters.items():
            items = [item for item in items if getattr(item, key, None) == value]
        created_at = getattr(RagDocument, "created_at", None)
        if stmt._order_by_clauses and created_at is not None:
            items = list(items)
        return DummyResult(items)


class _DummyResponse:
    def __init__(self, status_code: int, payload=None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")


class _DummyAsyncClient:
    def __init__(self, responses):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers=None):
        return self._responses[url]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _install_httpx_stub(monkeypatch: pytest.MonkeyPatch, responses: dict[str, _DummyResponse]) -> None:
    monkeypatch.setattr(
        paperless_mod.httpx,
        "AsyncClient",
        lambda timeout=60.0: _DummyAsyncClient(responses),
    )


def _configure_upload_root(tmp_path: Path) -> None:
    rag_utils.UPLOAD_ROOT = str(tmp_path)
    rag_utils._UPLOAD_DIR_READY = False


@pytest.mark.anyio
async def test_paperless_sync_skips_unchanged_document(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paperless_mod.settings, "paperless_url", "https://paperless.example")
    monkeypatch.setattr(paperless_mod.settings, "paperless_token", "token")
    _configure_upload_root(tmp_path)

    content = b"same"
    sha256 = hashlib.sha256(content).hexdigest()
    session = DummySession()
    session.add(
        RagDocument(
            document_id="doc-1",
            tenant_id=RAG_SHARED_TENANT_ID,
            status="indexed",
            visibility="public",
            filename="old.pdf",
            size_bytes=len(content),
            sha256=sha256,
                path=str(tmp_path / "sealai" / "doc-1" / "original.pdf"),
                tags=["norm", "knowledge"],
                route_key="standard_or_norm",
                source_system="paperless",
                source_document_id="11",
                source_modified_at=paperless_mod._parse_source_modified_at("2026-03-11T10:00:00Z"),
        )
    )

    base = "https://paperless.example"
    responses = {
        f"{base}/api/documents/?page_size=100": _DummyResponse(
            200,
            payload={
                "results": [
                    {
                        "id": 11,
                        "title": "Spec",
                        "original_file_name": "spec.pdf",
                        "modified": "2026-03-11T10:00:00Z",
                        "tags": ["norm", "knowledge"],
                    }
                ]
            },
        )
    }
    _install_httpx_stub(monkeypatch, responses)

    result = await paperless_mod.sync_paperless_to_rag(session)

    assert result["queued"] == 0
    assert result["skipped"] == 1
    assert len(session.docs) == 1
    stored = session.docs["doc-1"]
    assert stored.route_key == "standard_or_norm"
    assert stored.tags == ["norm", "knowledge"]


@pytest.mark.anyio
async def test_paperless_sync_reuses_existing_document_for_changed_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paperless_mod.settings, "paperless_url", "https://paperless.example")
    monkeypatch.setattr(paperless_mod.settings, "paperless_token", "token")
    _configure_upload_root(tmp_path)

    old_content = b"old"
    new_content = b"new"
    session = DummySession()
    existing_dir = tmp_path / RAG_SHARED_TENANT_ID / "doc-1"
    existing_dir.mkdir(parents=True, exist_ok=True)
    existing_path = existing_dir / "original.pdf"
    existing_path.write_bytes(old_content)
    session.add(
        RagDocument(
            document_id="doc-1",
            tenant_id=RAG_SHARED_TENANT_ID,
            status="indexed",
            visibility="public",
            filename="old.pdf",
            size_bytes=len(old_content),
                sha256=hashlib.sha256(old_content).hexdigest(),
                path=str(existing_path),
                tags=["material", "compound"],
                route_key="material_datasheet",
                source_system="paperless",
                source_document_id="11",
                source_modified_at=paperless_mod._parse_source_modified_at("2026-03-11T10:00:00Z"),
        )
    )

    base = "https://paperless.example"
    responses = {
        f"{base}/api/documents/?page_size=100": _DummyResponse(
            200,
            payload={
                "results": [
                    {
                        "id": 11,
                        "title": "Spec",
                        "original_file_name": "spec.pdf",
                        "modified": "2026-03-12T10:00:00Z",
                        "tags": ["norm", "knowledge"],
                    }
                ]
            },
        ),
        f"{base}/api/documents/11/download/": _DummyResponse(200, content=new_content),
    }
    _install_httpx_stub(monkeypatch, responses)

    result = await paperless_mod.sync_paperless_to_rag(session)

    assert result["queued"] == 1
    assert len(session.docs) == 1
    stored = session.docs["doc-1"]
    assert stored.status == "processing"
    assert stored.sha256 == hashlib.sha256(new_content).hexdigest()
    assert stored.source_system == "paperless"
    assert stored.source_document_id == "11"
    assert stored.source_modified_at == paperless_mod._parse_source_modified_at("2026-03-12T10:00:00Z")
    assert stored.route_key == "standard_or_norm"
    assert stored.tags == ["norm", "knowledge"]
    assert existing_path.read_bytes() == new_content


def test_route_key_resolver_is_deterministic() -> None:
    assert resolve_route_key(tags=["route:product_datasheet"], category="norms") == "product_datasheet"
    assert resolve_route_key(tags=["material", "compound"], category=None) == "material_datasheet"
    assert resolve_route_key(tags=["norm", "knowledge"], category=None) == "standard_or_norm"
    assert resolve_route_key(tags=None, category=None, filename="upload.txt") == "general_technical_doc"
