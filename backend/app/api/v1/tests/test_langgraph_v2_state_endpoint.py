from __future__ import annotations

import os
import sys
import types

import pytest
from fastapi import HTTPException
from starlette.requests import Request

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
os.environ.setdefault("nextauth_secret", "test-secret")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_expected_azp", "test-client")

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub

from app.api.v1.endpoints import state as state_endpoint  # noqa: E402
from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


class _Snapshot:
    def __init__(self, values, config):
        self.values = values
        self.next = []
        self.config = config


class _FakeGraph:
    def __init__(self):
        self.checkpointer = object()
        self.ns_calls: list[str] = []

    async def aget_state(self, config):
        checkpoint_ns = config.get("configurable", {}).get("checkpoint_ns", "")
        self.ns_calls.append(checkpoint_ns)
        if checkpoint_ns == "sealai:v2:":
            return _Snapshot({"parameters": {"medium": "oil"}, "phase": "discovery"}, config)
        return _Snapshot({}, config)


class _EmptyV2Graph:
    def __init__(self):
        self.checkpointer = object()
        self.ns_calls: list[str] = []

    async def aget_state(self, config):
        checkpoint_ns = config.get("configurable", {}).get("checkpoint_ns", "")
        self.ns_calls.append(checkpoint_ns)
        return _Snapshot({}, config)


class _FallbackNsGraph:
    def __init__(self):
        self.checkpointer = object()
        self.ns_calls: list[str] = []

    async def aget_state(self, config):
        checkpoint_ns = config.get("configurable", {}).get("checkpoint_ns", "")
        self.ns_calls.append(checkpoint_ns)
        if checkpoint_ns == "":
            return _Snapshot({"parameters": {"pressure_bar": 5.0}, "phase": "rag"}, config)
        return _Snapshot({}, config)


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/v1/langgraph/state", "headers": []})


@pytest.mark.anyio
async def test_state_endpoint_returns_non_empty_snapshot_for_v2_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _FakeGraph()

    async def _fake_get_graph():
        return graph

    monkeypatch.setattr(state_endpoint, "get_sealai_graph_v2", _fake_get_graph)

    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="tester",
        sub="user-1",
        roles=[],
    )

    response = await state_endpoint.get_state(_request(), thread_id="chat-1", user=user)
    expected_checkpoint_thread_id = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-1",
        chat_id="chat-1",
    )

    assert response["parameters"]["medium"] == "oil"
    assert response["metadata"]["phase"] == "discovery"
    assert response["config"]["configurable"]["thread_id"] == expected_checkpoint_thread_id
    assert response["config"]["configurable"]["checkpoint_ns"] == "sealai:v2:"
    assert graph.ns_calls == ["sealai:v2:"]


@pytest.mark.anyio
async def test_state_endpoint_returns_404_when_no_v2_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _EmptyV2Graph()

    async def _fake_get_graph():
        return graph

    monkeypatch.setattr(state_endpoint, "get_sealai_graph_v2", _fake_get_graph)

    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="tester",
        sub="user-1",
        roles=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await state_endpoint.get_state(_request(), thread_id="chat-1", user=user)

    assert getattr(exc_info.value, "status_code", None) == 404
    assert graph.ns_calls == ["sealai:v2:", ""]


@pytest.mark.anyio
async def test_state_endpoint_falls_back_to_empty_namespace_when_v2_namespace_has_no_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _FallbackNsGraph()

    async def _fake_get_graph():
        return graph

    monkeypatch.setattr(state_endpoint, "get_sealai_graph_v2", _fake_get_graph)

    user = RequestUser(
        user_id="user-1",
        tenant_id="tenant-1",
        username="tester",
        sub="user-1",
        roles=[],
    )

    response = await state_endpoint.get_state(_request(), thread_id="chat-1", user=user)
    assert response["parameters"]["pressure_bar"] == 5.0
    assert response["metadata"]["phase"] == "rag"
    assert response["config"]["configurable"]["checkpoint_ns"] == ""
    assert graph.ns_calls == ["sealai:v2:", ""]
