import asyncio
import importlib
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


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


def _ensure_env() -> None:
    for key, value in _ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    os.environ.setdefault("postgres_user", _ENV_DEFAULTS["POSTGRES_USER"])
    os.environ.setdefault("postgres_password", _ENV_DEFAULTS["POSTGRES_PASSWORD"])
    os.environ.setdefault("postgres_host", _ENV_DEFAULTS["POSTGRES_HOST"])
    os.environ.setdefault("postgres_port", _ENV_DEFAULTS["POSTGRES_PORT"])
    os.environ.setdefault("postgres_db", _ENV_DEFAULTS["POSTGRES_DB"])
    os.environ.setdefault("database_url", "sqlite+aiosqlite:///tmp.db")
    os.environ.setdefault("POSTGRES_SYNC_URL", "sqlite:///tmp.db")
    os.environ.setdefault("openai_api_key", _ENV_DEFAULTS["OPENAI_API_KEY"])
    os.environ.setdefault("qdrant_url", _ENV_DEFAULTS["QDRANT_URL"])
    os.environ.setdefault("qdrant_collection", _ENV_DEFAULTS["QDRANT_COLLECTION"])
    os.environ.setdefault("redis_url", _ENV_DEFAULTS["REDIS_URL"])
    os.environ.setdefault("nextauth_url", _ENV_DEFAULTS["NEXTAUTH_URL"])
    os.environ.setdefault("nextauth_secret", _ENV_DEFAULTS["NEXTAUTH_SECRET"])
    os.environ.setdefault("keycloak_issuer", _ENV_DEFAULTS["KEYCLOAK_ISSUER"])
    os.environ.setdefault("keycloak_jwks_url", _ENV_DEFAULTS["KEYCLOAK_JWKS_URL"])
    os.environ.setdefault("keycloak_client_id", _ENV_DEFAULTS["KEYCLOAK_CLIENT_ID"])
    os.environ.setdefault("keycloak_client_secret", _ENV_DEFAULTS["KEYCLOAK_CLIENT_SECRET"])
    os.environ.setdefault("keycloak_expected_azp", _ENV_DEFAULTS["KEYCLOAK_EXPECTED_AZP"])


class _FakeSnapshot:
    def __init__(self, values):
        self.values = values


class _FakeGraphDef:
    def __init__(self, nodes: dict):
        self.nodes = nodes


class _FakeGraph:
    def __init__(self):
        self.calls = []
        self._graph_def = _FakeGraphDef(
            {
                "__start__": object(),
                "__end__": object(),
                "supervisor_logic_node": object(),
                "confirm_recommendation_node": object(),
            }
        )

    def get_graph(self):
        return self._graph_def

    async def aget_state(self, _config):
        return _FakeSnapshot({"parameters": {"medium": "water"}, "last_node": "supervisor_logic_node"})

    async def aupdate_state(self, _config, patch, *, as_node: str):
        self.calls.append({"patch": patch, "as_node": as_node})


def _build_test_client() -> TestClient:
    app = FastAPI()
    endpoint_mod = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    app.include_router(getattr(endpoint_mod, "router"))
    return TestClient(app)


def test_patch_unauthorized_returns_401() -> None:
    _ensure_env()
    client = _build_test_client()

    res = client.post(
        "/parameters/patch",
        json={"chat_id": "default", "parameters": {"medium": "oil"}},
    )

    assert res.status_code == 401


def test_patch_returns_501_with_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()
    endpoint_mod = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    auth_deps = importlib.import_module("app.services.auth.dependencies")
    app = FastAPI()
    app.include_router(getattr(endpoint_mod, "router"))
    app.dependency_overrides[auth_deps.get_current_request_user] = lambda: auth_deps.RequestUser(
        user_id="alice",
        username="alice",
        sub="alice",
        roles=[],
        scopes=[],
        tenant_id="tenant-a",
    )
    client = TestClient(app)

    res = client.post(
        "/parameters/patch",
        json={"chat_id": "default", "parameters": {"medium": "oil"}},
    )

    assert res.status_code == 501
    body = res.json()
    assert body["detail"]["error"] == "endpoint_removed"


def test_patch_missing_chat_id_returns_501(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()
    endpoint_mod = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    auth_deps = importlib.import_module("app.services.auth.dependencies")
    app = FastAPI()
    app.include_router(getattr(endpoint_mod, "router"))
    app.dependency_overrides[auth_deps.get_current_request_user] = lambda: auth_deps.RequestUser(
        user_id="alice",
        username="alice",
        sub="alice",
        roles=[],
        scopes=[],
        tenant_id="tenant-a",
    )
    client = TestClient(app)

    res = client.post(
        "/parameters/patch",
        json={"parameters": {"medium": "oil"}},
    )

    assert res.status_code == 501
    body = res.json()
    assert body["detail"]["error"] == "endpoint_removed"


def test_patch_rejects_unknown_as_node_returns_501(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()
    endpoint_mod = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    auth_deps = importlib.import_module("app.services.auth.dependencies")
    app = FastAPI()
    app.include_router(getattr(endpoint_mod, "router"))
    app.dependency_overrides[auth_deps.get_current_request_user] = lambda: auth_deps.RequestUser(
        user_id="alice",
        username="alice",
        sub="alice",
        roles=[],
        scopes=[],
        tenant_id="tenant-a",
    )
    client = TestClient(app)

    res = client.post(
        "/parameters/patch",
        json={"chat_id": "default", "parameters": {"medium": "oil"}},
    )

    assert res.status_code == 501
    body = res.json()
    assert body["detail"]["error"] == "endpoint_removed"


def test_patch_rejects_unknown_keys_returns_501(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()
    endpoint_mod = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    auth_deps = importlib.import_module("app.services.auth.dependencies")
    app = FastAPI()
    app.include_router(getattr(endpoint_mod, "router"))
    app.dependency_overrides[auth_deps.get_current_request_user] = lambda: auth_deps.RequestUser(
        user_id="alice",
        username="alice",
        sub="alice",
        roles=[],
        scopes=[],
        tenant_id="tenant-a",
    )
    client = TestClient(app)

    res = client.post(
        "/parameters/patch",
        json={"chat_id": "default", "parameters": {"unknown_key": "x"}},
    )

    assert res.status_code == 501
    body = res.json()
    assert body["detail"]["error"] == "endpoint_removed"
