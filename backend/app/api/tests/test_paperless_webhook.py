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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_internal_paperless_webhook_accepts_valid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag_endpoint.settings, "paperless_webhook_token", "secret-token")

    async def _fake_sync(_session):
        return {"status": "success", "queued": 1, "ingest_ready": 1, "pilot_ready": 1}

    monkeypatch.setattr("app.services.rag.paperless.sync_paperless_to_rag", _fake_sync)

    payload = await rag_endpoint.ingest_paperless_webhook(
        payload={"document_id": 123},
        x_sealai_webhook_token="secret-token",
        session=object(),
    )

    assert payload["status"] == "accepted"
    assert payload["document_id"] == "123"
    assert payload["sync"]["queued"] == 1


@pytest.mark.anyio
async def test_internal_paperless_webhook_rejects_missing_document_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rag_endpoint.settings, "paperless_webhook_token", "secret-token")

    with pytest.raises(HTTPException) as exc:
        await rag_endpoint.ingest_paperless_webhook(
            payload={},
            x_sealai_webhook_token="secret-token",
            session=object(),
        )

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_internal_paperless_webhook_rejects_bad_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag_endpoint.settings, "paperless_webhook_token", "secret-token")

    with pytest.raises(HTTPException) as exc:
        await rag_endpoint.ingest_paperless_webhook(
            payload={"document_id": 123},
            x_sealai_webhook_token="wrong-token",
            session=object(),
        )

    assert exc.value.status_code == 403
