import importlib
import os
import sys
import types

import pytest

_ENV_DEFAULTS = {
    "POSTGRES_USER": "sealai",
    "POSTGRES_PASSWORD": "secret",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "sealai",
    "DATABASE_URL": "postgresql+asyncpg://sealai:secret@localhost:5432/sealai",
    "POSTGRES_SYNC_URL": "postgresql://sealai:secret@localhost:5432/sealai",
    "OPENAI_API_KEY": "test-key",
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_COLLECTION": "sealai",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEXTAUTH_URL": "http://localhost:3000",
    "NEXTAUTH_SECRET": "dummy-secret",
    "KEYCLOAK_ISSUER": "http://localhost:8080/realms/test",
    "KEYCLOAK_JWKS_URL": "http://localhost:8080/realms/test/protocol/openid-connect/certs",
    "KEYCLOAK_CLIENT_ID": "sealai-backend",
    "KEYCLOAK_CLIENT_SECRET": "client-secret",
    "KEYCLOAK_EXPECTED_AZP": "sealai-frontend",
}


def _ensure_env():
    for key, value in _ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    os.environ.setdefault("JOB_WORKER_ENABLED", "0")
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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_bootstrap_runs_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()
    monkeypatch.setenv("ENABLE_RAG_BOOTSTRAP", "1")
    main = importlib.reload(importlib.import_module("app.main"))
    called = {"count": 0}

    def _spy():
        called["count"] += 1

    monkeypatch.setattr(main, "bootstrap_rag_collection", _spy)
    app = main.create_app()
    async with app.router.lifespan_context(app):
        pass
    assert called["count"] == 1


@pytest.mark.anyio
async def test_bootstrap_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()
    monkeypatch.setenv("ENABLE_RAG_BOOTSTRAP", "0")
    main = importlib.reload(importlib.import_module("app.main"))
    called = {"count": 0}

    def _spy():
        called["count"] += 1

    monkeypatch.setattr(main, "bootstrap_rag_collection", _spy)
    app = main.create_app()
    async with app.router.lifespan_context(app):
        pass
    assert called["count"] == 0
