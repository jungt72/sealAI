from __future__ import annotations

import asyncio
import os
import sys
import types

import pytest
from fastapi import FastAPI

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

from app import main as main_module


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_lifespan_shutdown_swallows_worker_cancelled_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_start_job_worker() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(main_module, "JOB_WORKER_ENABLED", True)
    monkeypatch.setattr(main_module, "start_job_worker", fake_start_job_worker)

    caplog.set_level("INFO", logger="uvicorn.error")
    app = FastAPI()
    async with main_module.lifespan(app):
        await asyncio.wait_for(started.wait(), timeout=1)

    assert cancelled.is_set()
    assert "Application shutdown failed. Exiting." not in caplog.text
    assert "CancelledError" not in caplog.text
