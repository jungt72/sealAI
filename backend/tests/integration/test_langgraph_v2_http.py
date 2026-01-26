import asyncio
import importlib
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient


class _FakeSnapshot:
    def __init__(self, values, *, next_=None, config=None):
        self.values = values
        self.next = next_ or []
        self.config = config or {}


class _FakeGraphDef:
    def __init__(self, nodes: dict):
        self.nodes = nodes


class _FakeGraph:
    def __init__(self, *, raise_on_get: Exception | None = None, raise_on_update: Exception | None = None):
        self.raise_on_get = raise_on_get
        self.raise_on_update = raise_on_update
        self._graph_def = _FakeGraphDef(
            {
                "__start__": object(),
                "__end__": object(),
                "supervisor_logic_node": object(),
                "confirm_recommendation_node": object(),
            }
        )
        self.checkpointer = object()

    def get_graph(self):
        return self._graph_def

    async def aget_state(self, _config):
        if self.raise_on_get:
            raise self.raise_on_get
        return _FakeSnapshot({"parameters": {"medium": "water"}, "last_node": "supervisor_logic_node"})

    async def aupdate_state(self, _config, patch, *, as_node: str):
        if self.raise_on_update:
            raise self.raise_on_update
        return None


class _StatefulGraph:
    def __init__(self):
        self._graph_def = _FakeGraphDef(
            {
                "__start__": object(),
                "__end__": object(),
                "supervisor_logic_node": object(),
                "confirm_recommendation_node": object(),
            }
        )
        self.checkpointer = object()
        self._values: dict = {"parameters": {}}

    def get_graph(self):
        return self._graph_def

    async def aget_state(self, _config):
        return _FakeSnapshot(self._values.copy())

    async def aupdate_state(self, _config, patch, *, as_node: str):
        if isinstance(patch, dict) and "parameters" in patch:
            self._values["parameters"] = patch["parameters"]
        self._values["last_node"] = as_node
        return None


@asynccontextmanager
async def _async_client():
    app_mod = importlib.import_module("app.main")
    transport = ASGITransport(app=getattr(app_mod, "app"))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _run(coro):
    return asyncio.run(coro)


def _auth(monkeypatch: pytest.MonkeyPatch, *, user: str = "test-user") -> None:
    deps = importlib.import_module("app.services.auth.dependencies")
    monkeypatch.setattr(
        deps,
        "verify_access_token",
        lambda _t: {
            "preferred_username": user,
            "sub": user,
            "tenant_id": "default",
            "realm_access": {"roles": []},
        },
    )


def test_health_200_no_auth_required() -> None:
    async def _case():
        async with _async_client() as client:
            res = await client.get("/api/v1/langgraph/health")
            assert res.status_code == 200
            assert res.json().get("status") == "ok"

    _run(_case())


def test_state_requires_auth_401() -> None:
    async def _case():
        async with _async_client() as client:
            res = await client.get("/api/v1/langgraph/state", params={"thread_id": "default"})
            assert res.status_code == 401

    _run(_case())


def test_state_200_with_auth_and_fake_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)

    state_ep = importlib.import_module("app.api.v1.endpoints.state")
    fake_graph = _FakeGraph()

    async def _fake_build_state_config_with_checkpointer(thread_id: str, user_id: str):
        assert thread_id == "default"
        assert user_id == "test-user"
        return fake_graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(state_ep, "_build_state_config_with_checkpointer", _fake_build_state_config_with_checkpointer)

    async def _case():
        async with _async_client() as client:
            res = await client.get(
                "/api/v1/langgraph/state",
                params={"thread_id": "default"},
                headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-state-1"},
            )
            assert res.status_code == 200
            body = res.json()
            assert "parameters" in body

    _run(_case())


def test_patch_then_state_returns_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)

    state_ep = importlib.import_module("app.api.v1.endpoints.state")
    lg_ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    graph = _StatefulGraph()

    async def _fake_build_state_config_with_checkpointer(thread_id: str, user_id: str):
        assert thread_id == "chat-123"
        assert user_id == "test-user"
        return graph, {"configurable": {}, "metadata": {}}

    async def _fake_build_graph_config(*, thread_id: str, user_id: str, **_kwargs):
        assert thread_id == "chat-123"
        assert user_id == "test-user"
        return graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(state_ep, "_build_state_config_with_checkpointer", _fake_build_state_config_with_checkpointer)
    monkeypatch.setattr(lg_ep, "_build_graph_config", _fake_build_graph_config)

    async def _case():
        async with _async_client() as client:
            res = await client.post(
                "/api/v1/langgraph/parameters/patch",
                headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-patch-4"},
                json={"chat_id": "chat-123", "parameters": {"medium": "oil", "pressure_bar": 1}},
            )
            assert res.status_code == 200

            state = await client.get(
                "/api/v1/langgraph/state",
                params={"thread_id": "chat-123"},
                headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-state-2"},
            )
            assert state.status_code == 200
            body = state.json()
            assert body["parameters"]["medium"] == "oil"
            assert body["parameters"]["pressure_bar"] == 1

    _run(_case())


def test_parameters_patch_missing_chat_id_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    async def _case():
        async with _async_client() as client:
            res = await client.post(
                "/api/v1/langgraph/parameters/patch",
                headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-patch-1"},
                json={"parameters": {"medium": "oil"}},
            )
            assert res.status_code == 400
            assert res.json()["detail"]["code"] == "missing_chat_id"

    _run(_case())


def test_parameters_patch_invalid_as_node_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    fake_graph = _FakeGraph()

    async def _fake_build_graph_config(*, thread_id: str, user_id: str, **_kwargs):
        return fake_graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(ep, "_build_graph_config", _fake_build_graph_config)
    monkeypatch.setattr(ep, "PARAMETERS_PATCH_AS_NODE", "parameter_patch_ui")

    async def _case():
        async with _async_client() as client:
            res = await client.post(
                "/api/v1/langgraph/parameters/patch",
                headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-patch-2"},
                json={"chat_id": "default", "parameters": {"medium": "oil"}},
            )
            assert res.status_code == 400
            detail = res.json()["detail"]
            assert detail["code"] == "invalid_as_node"
            assert detail["as_node"] == "parameter_patch_ui"

    _run(_case())


def test_parameters_patch_dependency_down_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    fake_graph = _FakeGraph(raise_on_get=TimeoutError("simulated timeout"))

    async def _fake_build_graph_config(*, thread_id: str, user_id: str, **_kwargs):
        return fake_graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(ep, "_build_graph_config", _fake_build_graph_config)

    async def _case():
        async with _async_client() as client:
            res = await client.post(
                "/api/v1/langgraph/parameters/patch",
                headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-patch-3"},
                json={"chat_id": "default", "parameters": {"medium": "oil"}},
            )
            assert res.status_code == 503
            assert res.json()["detail"]["code"] == "dependency_unavailable"

    _run(_case())


def test_confirm_go_requires_auth_401() -> None:
    async def _case():
        async with _async_client() as client:
            res = await client.post("/api/v1/langgraph/confirm/go", json={"chat_id": "default", "go": True})
            assert res.status_code == 401

    _run(_case())


def test_confirm_go_dependency_down_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    fake_graph = _FakeGraph(raise_on_update=TimeoutError("simulated timeout"))

    async def _fake_build_graph_config(*, thread_id: str, user_id: str, **_kwargs):
        return fake_graph, {"configurable": {}, "metadata": {}}

    monkeypatch.setattr(ep, "_build_graph_config", _fake_build_graph_config)

    async def _case():
        async with _async_client() as client:
            res = await client.post(
                "/api/v1/langgraph/confirm/go",
                headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-confirm-1"},
                json={"chat_id": "default", "go": True},
            )
            assert res.status_code == 503
            assert res.json()["detail"]["code"] == "dependency_unavailable"

    _run(_case())
