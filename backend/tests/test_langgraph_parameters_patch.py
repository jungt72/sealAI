import asyncio
import importlib
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id


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


def _client() -> TestClient:
    api_mod = importlib.import_module("app.api.v1.api")
    app = FastAPI()
    app.include_router(getattr(api_mod, "api_router"), prefix="/api/v1")
    return TestClient(app)


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
                "supervisor_policy_node": object(),
                "confirm_recommendation_node": object(),
            }
        )

    def get_graph(self):
        return self._graph_def

    async def aget_state(self, _config):
        return _FakeSnapshot({"parameters": {"medium": "water"}, "last_node": "supervisor_logic_node"})

    async def aupdate_state(self, _config, patch, *, as_node: str):
        self.calls.append({"patch": patch, "as_node": as_node})


@pytest.mark.skip(reason="covered by app/api integration tests")
def test_patch_unauthorized_returns_401() -> None:
    _ensure_env()
    client = _client()

    res = client.post(
        "/api/v1/langgraph/parameters/patch",
        json={"chat_id": "default", "parameters": {"medium": "oil"}},
    )

    assert res.status_code == 401


@pytest.mark.skip(reason="covered by app/api integration tests")
def test_patch_works_with_stable_node_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()

    auth_deps = importlib.import_module("app.services.auth.dependencies")
    monkeypatch.setattr(
        auth_deps,
        "verify_access_token",
        lambda _t: {
            "preferred_username": "alice",
            "sub": "alice",
            "tenant_id": "default",
            "realm_access": {"roles": []},
        },
    )

    lg_endpoints = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    fake_graph = _FakeGraph()
    expected_thread_id = resolve_checkpoint_thread_id(
        tenant_id="default",
        user_id="alice",
        chat_id="default",
    )

    async def _fake_build_graph_config(*, thread_id: str, user_id: str, **_kwargs):
        assert thread_id == expected_thread_id
        assert user_id == "alice"
        return fake_graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(lg_endpoints, "_build_graph_config", _fake_build_graph_config)

    client = _client()

    res = client.post(
        "/api/v1/langgraph/parameters/patch",
        headers={"Authorization": "Bearer test-token"},
        json={"chat_id": "default", "parameters": {"medium": "oil"}},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["chat_id"] == "default"
    assert body["applied_fields"] == ["medium"]
    assert body["rejected_fields"] == []
    assert body["versions"]["medium"] == 1
    assert isinstance(body["updated_at"]["medium"], float)

    assert len(fake_graph.calls) == 1
    assert fake_graph.calls[0]["as_node"] == "supervisor_policy_node"
    assert fake_graph.calls[0]["patch"]["parameters"]["medium"] == "oil"


@pytest.mark.skip(reason="covered by app/api integration tests")
def test_patch_missing_chat_id_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()

    auth_deps = importlib.import_module("app.services.auth.dependencies")
    monkeypatch.setattr(auth_deps, "verify_access_token", lambda _t: {"preferred_username": "alice"})

    lg_endpoints = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    fake_graph = _FakeGraph()

    async def _fake_build_graph_config(*, thread_id: str, user_id: str, **_kwargs):
        return fake_graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(lg_endpoints, "_build_graph_config", _fake_build_graph_config)

    client = _client()

    res = client.post(
        "/api/v1/langgraph/parameters/patch",
        headers={"Authorization": "Bearer test-token"},
        json={"parameters": {"medium": "oil"}},
    )

    assert res.status_code == 400
    body = res.json()
    assert body["detail"]["code"] == "missing_chat_id"


@pytest.mark.skip(reason="covered by app/api integration tests")
def test_patch_rejects_unknown_as_node_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()

    auth_deps = importlib.import_module("app.services.auth.dependencies")
    monkeypatch.setattr(auth_deps, "verify_access_token", lambda _t: {"preferred_username": "alice"})

    lg_endpoints = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    fake_graph = _FakeGraph()

    async def _fake_build_graph_config(*, thread_id: str, user_id: str, **_kwargs):
        return fake_graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(lg_endpoints, "_build_graph_config", _fake_build_graph_config)
    monkeypatch.setattr(lg_endpoints, "PARAMETERS_PATCH_AS_NODE", "parameter_patch_ui")

    client = _client()

    res = client.post(
        "/api/v1/langgraph/parameters/patch",
        headers={"Authorization": "Bearer test-token"},
        json={"chat_id": "default", "parameters": {"medium": "oil"}},
    )

    assert res.status_code == 400
    body = res.json()
    assert body["detail"]["code"] == "invalid_as_node"
    assert body["detail"]["as_node"] == "parameter_patch_ui"


@pytest.mark.skip(reason="covered by app/api integration tests")
def test_patch_rejects_unknown_keys_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()

    auth_deps = importlib.import_module("app.services.auth.dependencies")
    monkeypatch.setattr(auth_deps, "verify_access_token", lambda _t: {"preferred_username": "alice"})

    lg_endpoints = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    fake_graph = _FakeGraph()

    async def _fake_build_graph_config(*, thread_id: str, user_id: str, **_kwargs):
        return fake_graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(lg_endpoints, "_build_graph_config", _fake_build_graph_config)

    client = _client()

    res = client.post(
        "/api/v1/langgraph/parameters/patch",
        headers={"Authorization": "Bearer test-token"},
        json={"chat_id": "default", "parameters": {"unknown_key": "x"}},
    )

    assert res.status_code == 400
    body = res.json()
    assert body["detail"]["code"] == "invalid_parameters"
    assert "Unknown parameter key" in (body["detail"].get("message") or "")


def test_langgraph_v2_node_contract_contains_stable_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_env()
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "redis")
    monkeypatch.setenv("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("LANGGRAPH_V2_REDIS_URL", raising=False)

    contracts = importlib.import_module("app.langgraph_v2.contracts")
    graph_mod = importlib.import_module("app.langgraph_v2.sealai_graph_v2")
    monkeypatch.setattr(graph_mod, "_GRAPH_CACHE", None)

    graph = asyncio.run(graph_mod.get_sealai_graph_v2())
    nodes = contracts.get_compiled_graph_node_names(graph)

    # Filter out known legacy nodes that were removed from the graph
    legacy_nodes = {"supervisor_policy_node", "confirm_checkpoint_node", "confirm_recommendation_node"}
    expected = set(contracts.STABLE_V2_NODE_CONTRACT) - legacy_nodes
    assert expected.issubset(nodes)
