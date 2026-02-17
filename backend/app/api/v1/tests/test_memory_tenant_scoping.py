from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

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
os.environ.setdefault("nextauth_url", "http://localhost")
os.environ.setdefault("nextauth_secret", "test")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from app.api.v1.endpoints import memory as memory_endpoint
from app.services.auth.dependencies import RequestUser, get_current_request_user_strict_tenant


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.last_upsert_payload = None

    def upsert(self, *, points, **_kwargs):
        self.last_upsert_payload = dict(points[0].payload or {})


@pytest.mark.anyio
async def test_memory_create_persists_tenant_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_endpoint.settings, "ltm_enable", True)
    fake = _FakeQdrantClient()
    monkeypatch.setattr(memory_endpoint, "_get_qdrant_client", lambda: fake)
    monkeypatch.setattr(memory_endpoint, "ensure_ltm_collection", lambda _client: None)

    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="u",
        sub="sub-1",
        roles=[],
    )
    response = await memory_endpoint.create_memory_item(payload={"text": "hello"}, user=user)
    body = json.loads(response.body.decode("utf-8"))

    assert body["success"] is True
    assert fake.last_upsert_payload is not None
    assert fake.last_upsert_payload.get("tenant_id") == "tenant-1"
    assert fake.last_upsert_payload.get("user") == "user-1"


def test_memory_routes_use_strict_tenant_dependency() -> None:
    endpoints = {
        memory_endpoint.create_memory_item,
        memory_endpoint.export_memory,
        memory_endpoint.delete_memory,
    }
    for route in memory_endpoint.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.endpoint not in endpoints:
            continue
        calls = {dep.call for dep in route.dependant.dependencies}
        assert get_current_request_user_strict_tenant in calls
