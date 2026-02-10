from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

# Ensure backend is on path (tests run from repo root in some setups).
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Minimal env defaults for settings to load (avoid import-time config failures).
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

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402
from app.api.v1.endpoints import state as state_endpoint  # noqa: E402
from app.langgraph_v2.utils.confirm_go import ConfirmGoRequest  # noqa: E402
from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


def _request() -> Request:
    return Request({"type": "http", "headers": []})


async def _collect(aiter):
    chunks = []
    async for chunk in aiter:
        chunks.append(chunk)
    return chunks


class _Snapshot:
    def __init__(self, values):
        self.values = values
        self.config = {}


class DummyGraph:
    def __init__(self, state):
        self.state = state
        self.checkpointer = object()

    def get_graph(self):
        return type("G", (), {"nodes": {"confirm_checkpoint_node": None, "confirm_recommendation_node": None}})()

    async def aget_state(self, _config):
        return _Snapshot(self.state)

    async def aupdate_state(self, _config, updates, as_node=None):
        self.state.update(updates)

    async def ainvoke(self, _input, config=None):
        decision = self.state.get("confirm_decision")
        if decision == "reject":
            return {"final_text": "Abgebrochen", "phase": "confirm", "last_node": "confirm_reject_node"}
        if decision in {"approve", "edit"}:
            edits = (self.state.get("confirm_edits") or {}).get("parameters") or {}
            if edits:
                current = self.state.get("parameters") or {}
                current.update(edits)
                self.state["parameters"] = current
            return {"final_text": "Weiter", "phase": "final", "last_node": "final_answer_node"}
        return {"final_text": "", "phase": "final", "last_node": "final_answer_node"}


class DummyGraphCheckpointFlow:
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.state = {}
        self.checkpointer = object()

    def get_graph(self):
        return type("G", (), {"nodes": {"confirm_checkpoint_node": None, "confirm_recommendation_node": None}})()

    async def aget_state(self, _config):
        return _Snapshot(self.state)

    async def aupdate_state(self, _config, updates, as_node=None):
        self.state.update(updates)

    def astream(self, _input, config=None, *, stream_mode=None, **_kwargs):
        async def gen():
            yield (
                "values",
                {
                    "phase": "confirm",
                    "last_node": "confirm_checkpoint_node",
                    "pending_action": "FINALIZE",
                    "user_id": "user-1",
                    "tenant_id": "tenant-1",
                    "thread_id": self.thread_id,
                },
            )

        return gen()

    async def ainvoke(self, _input, config=None):
        return {"final_text": "Weiter", "phase": "final", "last_node": "rag_support_node"}


def _make_state():
    checkpoint_thread_id = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-1",
        chat_id="chat-1",
    )
    return {
        "confirm_checkpoint": {"required_user_sub": "user-1", "conversation_id": checkpoint_thread_id},
        "confirm_checkpoint_id": "chk-1",
        "pending_action": "RUN_PANEL_NORMS_RAG",
        "awaiting_user_confirmation": True,
    }


def test_confirm_go_approve_resumes(monkeypatch):
    state = _make_state()
    dummy = DummyGraph(state)

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    request = _request()
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    body = ConfirmGoRequest(chat_id="chat-1", checkpoint_id="chk-1", decision="approve")
    response = asyncio.run(endpoint.confirm_go(body, request, user=user))
    assert response["final_text"] == "Weiter"


def test_confirm_go_reject_returns_cancellation(monkeypatch):
    state = _make_state()
    dummy = DummyGraph(state)

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    request = _request()
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    body = ConfirmGoRequest(chat_id="chat-1", checkpoint_id="chk-1", decision="reject")
    response = asyncio.run(endpoint.confirm_go(body, request, user=user))
    assert "Abgebrochen" in response["final_text"]


def test_confirm_go_edit_applies_parameters(monkeypatch):
    state = _make_state()
    dummy = DummyGraph(state)

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    request = _request()
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    body = ConfirmGoRequest(
        chat_id="chat-1",
        checkpoint_id="chk-1",
        decision="edit",
        edits={"parameters": {"pressure_bar": 7}, "instructions": "Bitte korrigieren"},
    )
    response = asyncio.run(endpoint.confirm_go(body, request, user=user))
    assert response["final_text"] == "Weiter"
    assert dummy.state.get("parameters", {}).get("pressure_bar") == 7


def test_confirm_go_conversation_mismatch(monkeypatch):
    state = _make_state()
    state["confirm_checkpoint"]["conversation_id"] = "chat-2"
    dummy = DummyGraph(state)

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    request = _request()
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    body = ConfirmGoRequest(chat_id="chat-1", checkpoint_id="chk-1", decision="approve")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.confirm_go(body, request, user=user))
    assert getattr(excinfo.value, "status_code", None) == 403
    assert excinfo.value.detail["code"] == "checkpoint_conversation_mismatch"


def test_confirm_go_no_pending_checkpoint(monkeypatch):
    state = {}
    dummy = DummyGraph(state)

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    request = _request()
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    body = ConfirmGoRequest(chat_id="chat-1", checkpoint_id="chk-1", decision="approve")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.confirm_go(body, request, user=user))
    assert getattr(excinfo.value, "status_code", None) == 409
    assert excinfo.value.detail["code"] == "no_pending_checkpoint"


def test_confirm_go_double_submit(monkeypatch):
    state = {"confirm_status": "resolved"}
    dummy = DummyGraph(state)

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    request = _request()
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    body = ConfirmGoRequest(chat_id="chat-1", checkpoint_id="chk-1", decision="approve")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.confirm_go(body, request, user=user))
    assert getattr(excinfo.value, "status_code", None) == 409
    assert excinfo.value.detail["code"] == "checkpoint_already_resolved"


def test_confirm_go_wrong_user(monkeypatch):
    state = _make_state()
    dummy = DummyGraph(state)

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    request = _request()
    user = RequestUser(user_id="user-2", tenant_id="tenant-1", username="tester", sub="user-2", roles=[])
    body = ConfirmGoRequest(chat_id="chat-1", checkpoint_id="chk-1", decision="approve")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.confirm_go(body, request, user=user))
    assert getattr(excinfo.value, "status_code", None) == 403
    assert excinfo.value.detail["code"] == "checkpoint_conversation_mismatch"


def test_confirm_go_resume_after_sse_checkpoint(monkeypatch):
    checkpoint_thread_id = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-1",
        chat_id="chat-1",
    )
    dummy = DummyGraphCheckpointFlow(thread_id=checkpoint_thread_id)

    async def _dummy_graph():
        return dummy

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)

    req = endpoint.LangGraphV2Request(input="Hi", chat_id="chat-1")
    asyncio.run(
        _collect(
            endpoint._event_stream_v2(
                req,
                user_id="user-1",
                tenant_id="tenant-1",
                can_read_private=False,
                request_id="req-1",
                checkpoint_thread_id=checkpoint_thread_id,
            )
        )
    )

    assert dummy.state.get("awaiting_user_confirmation") is True
    assert dummy.state.get("pending_checkpoint_id")

    request = _request()
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    body = ConfirmGoRequest(
        chat_id="chat-1",
        checkpoint_id=dummy.state.get("pending_checkpoint_id"),
        decision="approve",
    )
    response = asyncio.run(endpoint.confirm_go(body, request, user=user))
    assert response["last_node"] == "rag_support_node"
def test_resolved_thread_key_consistent_across_state_patch_and_confirm_go(monkeypatch):
    expected_thread_id = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-1",
        chat_id="chat-1",
    )
    captured: dict[str, str | None] = {
        "state": None,
        "patch": None,
        "confirm": None,
    }

    class _StateSnapshot:
        def __init__(self, thread_id: str):
            self.values = {"parameters": {}}
            self.next = []
            self.config = {"configurable": {"thread_id": thread_id}}

    async def _fake_resolve_state_snapshot(*, thread_id, user, request_id=None, checkpoint_thread_id=None):
        captured["state"] = checkpoint_thread_id
        return object(), {"configurable": {"thread_id": checkpoint_thread_id}}, _StateSnapshot(checkpoint_thread_id), False

    dummy = DummyGraph(_make_state())

    async def _fake_build_graph_config(*, thread_id, **_kwargs):
        if captured["patch"] is None:
            captured["patch"] = thread_id
        else:
            captured["confirm"] = thread_id
        return dummy, {"configurable": {"thread_id": thread_id}}

    async def _noop_broadcast(**_kwargs):
        return None

    monkeypatch.setattr(state_endpoint, "_resolve_state_snapshot", _fake_resolve_state_snapshot)
    monkeypatch.setattr(endpoint, "_build_graph_config", _fake_build_graph_config)
    monkeypatch.setattr(endpoint, "assert_node_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(endpoint.sse_broadcast, "broadcast", _noop_broadcast)

    async def _run():
        request = _request()
        user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])

        await state_endpoint.get_state(request, thread_id="chat-1", user=user)

        patch_body = endpoint.ParametersPatchRequest(chat_id="chat-1", parameters={"pressure_bar": 7})
        await endpoint.patch_parameters(patch_body, request, user=user)

        confirm_body = ConfirmGoRequest(chat_id="chat-1", checkpoint_id="chk-1", decision="approve")
        await endpoint.confirm_go(confirm_body, request, user=user)

    asyncio.run(_run())

    assert captured["state"] == expected_thread_id
    assert captured["patch"] == expected_thread_id
    assert captured["confirm"] == expected_thread_id


def test_tenant_user_isolation_state_patch_confirm_with_same_chat_id(monkeypatch):
    chat_id = "same"
    key_a = resolve_checkpoint_thread_id(tenant_id="tenant-1", user_id="user-1", chat_id=chat_id)
    key_b = resolve_checkpoint_thread_id(tenant_id="tenant-1", user_id="user-2", chat_id=chat_id)
    key_c = resolve_checkpoint_thread_id(tenant_id="tenant-2", user_id="user-1", chat_id=chat_id)
    assert len({key_a, key_b, key_c}) == 3

    class _StateSnapshot:
        def __init__(self, values, thread_id: str):
            self.values = values
            self.next = []
            self.config = {"configurable": {"thread_id": thread_id}}

    class _TenantScopedGraph:
        def __init__(self, store):
            self.store = store
            self.checkpointer = object()

        def get_graph(self):
            return type(
                "G",
                (),
                {"nodes": {"confirm_checkpoint_node": None, "confirm_recommendation_node": None, "supervisor_policy_node": None}},
            )()

        async def aget_state(self, config):
            thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
            return _StateSnapshot(self.store.get(thread_id, {}).copy(), thread_id)

        async def aupdate_state(self, config, updates, as_node=None):
            thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
            current = dict(self.store.get(thread_id, {}))
            current.update(dict(updates or {}))
            self.store[thread_id] = current

        async def ainvoke(self, _input, config=None):
            thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
            state = self.store.get(thread_id, {})
            decision = state.get("confirm_decision")
            if decision == "approve":
                return {"final_text": "Weiter", "phase": "final", "last_node": "final_answer_node"}
            return {"final_text": "", "phase": "final", "last_node": "final_answer_node"}

    store = {
        key_a: {
            "parameters": {},
            "confirm_checkpoint": {"required_user_sub": "user-1", "conversation_id": key_a},
            "confirm_checkpoint_id": "chk-a",
            "pending_action": "RUN_PANEL_NORMS_RAG",
            "awaiting_user_confirmation": True,
        },
        key_b: {"parameters": {}},
        key_c: {"parameters": {}},
    }
    graph = _TenantScopedGraph(store)
    captured = {"state": [], "build": []}

    async def _fake_resolve_state_snapshot(*, thread_id, user, request_id=None, checkpoint_thread_id=None):
        captured["state"].append(checkpoint_thread_id)
        config = {"configurable": {"thread_id": checkpoint_thread_id}}
        return graph, config, _StateSnapshot(store.get(checkpoint_thread_id, {}).copy(), checkpoint_thread_id), False

    async def _fake_build_graph_config(*, thread_id, **_kwargs):
        captured["build"].append(thread_id)
        return graph, {"configurable": {"thread_id": thread_id}}

    async def _noop_broadcast(**_kwargs):
        return None

    monkeypatch.setattr(state_endpoint, "_resolve_state_snapshot", _fake_resolve_state_snapshot)
    monkeypatch.setattr(endpoint, "_build_graph_config", _fake_build_graph_config)
    monkeypatch.setattr(endpoint, "assert_node_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(endpoint.sse_broadcast, "broadcast", _noop_broadcast)

    async def _run():
        request = _request()
        user_a = RequestUser(user_id="user-1", tenant_id="tenant-1", username="a", sub="user-1", roles=[])
        user_b = RequestUser(user_id="user-2", tenant_id="tenant-1", username="b", sub="user-2", roles=[])
        user_c = RequestUser(user_id="user-1", tenant_id="tenant-2", username="c", sub="user-1", roles=[])

        # State resolves per caller scope.
        await state_endpoint.get_state(request, thread_id=chat_id, user=user_a)
        await state_endpoint.get_state(request, thread_id=chat_id, user=user_b)
        await state_endpoint.get_state(request, thread_id=chat_id, user=user_c)

        # Patch A must not bleed into B/C for same chat_id.
        patch_a = endpoint.ParametersPatchRequest(chat_id=chat_id, parameters={"pressure_bar": 7})
        await endpoint.patch_parameters(patch_a, request, user=user_a)
        assert store[key_a].get("parameters", {}).get("pressure_bar") == 7
        assert store[key_b].get("parameters", {}).get("pressure_bar") is None
        assert store[key_c].get("parameters", {}).get("pressure_bar") is None

        patch_b = endpoint.ParametersPatchRequest(chat_id=chat_id, parameters={"temperature_C": 50})
        await endpoint.patch_parameters(patch_b, request, user=user_b)
        assert store[key_b].get("parameters", {}).get("temperature_C") == 50
        assert store[key_a].get("parameters", {}).get("temperature_C") is None

        # Confirm/go with foreign checkpoint id from A as B/C must not access A state.
        body_b = ConfirmGoRequest(chat_id=chat_id, checkpoint_id="chk-a", decision="approve")
        with pytest.raises(HTTPException) as exc_b:
            await endpoint.confirm_go(body_b, request, user=user_b)
        assert getattr(exc_b.value, "status_code", None) == 409
        assert exc_b.value.detail["code"] == "no_pending_checkpoint"

        body_c = ConfirmGoRequest(chat_id=chat_id, checkpoint_id="chk-a", decision="approve")
        with pytest.raises(HTTPException) as exc_c:
            await endpoint.confirm_go(body_c, request, user=user_c)
        assert getattr(exc_c.value, "status_code", None) == 409
        assert exc_c.value.detail["code"] == "no_pending_checkpoint"

    asyncio.run(_run())

    assert captured["state"] == [key_a, key_b, key_c]
    # build captures patch(A), patch(B), confirm(B), confirm(C) resolved keys
    assert captured["build"] == [key_a, key_b, key_b, key_c]

    # Evidence:
    # - backend/app/api/v1/endpoints/state.py:265-277, 363-375 (resolved checkpoint key passed to resolver)
    # - backend/app/api/v1/endpoints/langgraph_v2.py:1477-1491 (/parameters/patch uses resolved key)
    # - backend/app/api/v1/endpoints/langgraph_v2.py:1339-1349 (/confirm/go uses resolved key)


def test_parameters_patch_lww_disjoint_fields_same_base_versions(monkeypatch):
    chat_id = "chat-lww-disjoint"
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    expected_thread_id = resolve_checkpoint_thread_id(tenant_id=user.tenant_id, user_id=user.user_id, chat_id=chat_id)
    captured = {"build": [], "acks": []}

    class _StateSnapshot:
        def __init__(self, values):
            self.values = values
            self.config = {}

    class _PatchGraph:
        def __init__(self):
            self.checkpointer = object()
            self.store = {
                expected_thread_id: {
                    "parameters": {},
                    "parameter_versions": {"pressure_bar": 0, "temperature_C": 0},
                    "parameter_updated_at": {},
                    "parameter_provenance": {},
                }
            }

        async def aget_state(self, config):
            thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
            return _StateSnapshot(dict(self.store.get(thread_id, {})))

        async def aupdate_state(self, config, updates, as_node=None):
            thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
            current = dict(self.store.get(thread_id, {}))
            current.update(dict(updates or {}))
            self.store[thread_id] = current

    graph = _PatchGraph()

    async def _fake_build_graph_config(*, thread_id, **_kwargs):
        captured["build"].append(thread_id)
        return graph, {"configurable": {"thread_id": thread_id}}

    async def _capture_broadcast(**kwargs):
        captured["acks"].append(kwargs)
        return None

    monkeypatch.setattr(endpoint, "_build_graph_config", _fake_build_graph_config)
    monkeypatch.setattr(endpoint, "assert_node_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(endpoint.sse_broadcast, "broadcast", _capture_broadcast)

    async def _run():
        request = _request()
        base_versions = {"pressure_bar": 0, "temperature_C": 0}
        patch_a = endpoint.ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"pressure_bar": 7},
            base_versions=base_versions,
        )
        patch_b = endpoint.ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"temperature_C": 50},
            base_versions=base_versions,
        )
        response_a = await endpoint.patch_parameters(patch_a, request, user=user)
        response_b = await endpoint.patch_parameters(patch_b, request, user=user)
        return response_a, response_b

    response_a, response_b = asyncio.run(_run())

    assert captured["build"] == [expected_thread_id, expected_thread_id]
    assert response_a["ok"] is True
    assert response_b["ok"] is True
    assert response_a["rejected_fields"] == []
    assert response_b["rejected_fields"] == []
    assert response_a["applied_fields"] == ["pressure_bar"]
    assert response_b["applied_fields"] == ["temperature_C"]

    final_state = graph.store[expected_thread_id]
    assert final_state["parameters"]["pressure_bar"] == 7
    assert final_state["parameters"]["temperature_C"] == 50
    assert final_state["parameter_versions"]["pressure_bar"] == 1
    assert final_state["parameter_versions"]["temperature_C"] == 1
    assert "pressure_bar" in final_state["parameter_updated_at"]
    assert "temperature_C" in final_state["parameter_updated_at"]

    assert len(captured["acks"]) == 2
    assert captured["acks"][0]["event"] == "parameter_patch_ack"
    assert captured["acks"][1]["event"] == "parameter_patch_ack"
    assert captured["acks"][0]["data"]["rejected_fields"] == []
    assert captured["acks"][1]["data"]["rejected_fields"] == []

    # Evidence:
    # - backend/app/api/v1/endpoints/langgraph_v2.py:1514-1522 (LWW call with base_versions)
    # - backend/app/api/v1/endpoints/langgraph_v2.py:1564-1571 (response includes rejected_fields/versions/updated_at)
    # - backend/app/langgraph_v2/utils/parameter_patch.py:331-335 (base_v < current_v => stale rejection)
    # - backend/app/langgraph_v2/utils/parameter_patch.py:352-358 (accepted fields bump versions and updated_at)


def test_parameters_patch_lww_conflict_same_field_same_base_versions(monkeypatch):
    chat_id = "chat-lww-conflict"
    user = RequestUser(user_id="user-1", tenant_id="tenant-1", username="tester", sub="user-1", roles=[])
    expected_thread_id = resolve_checkpoint_thread_id(tenant_id=user.tenant_id, user_id=user.user_id, chat_id=chat_id)
    captured = {"build": [], "acks": []}

    class _StateSnapshot:
        def __init__(self, values):
            self.values = values
            self.config = {}

    class _PatchGraph:
        def __init__(self):
            self.checkpointer = object()
            self.store = {
                expected_thread_id: {
                    "parameters": {"pressure_bar": 0},
                    "parameter_versions": {"pressure_bar": 0},
                    "parameter_updated_at": {},
                    "parameter_provenance": {"pressure_bar": "user"},
                }
            }

        async def aget_state(self, config):
            thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
            return _StateSnapshot(dict(self.store.get(thread_id, {})))

        async def aupdate_state(self, config, updates, as_node=None):
            thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
            current = dict(self.store.get(thread_id, {}))
            current.update(dict(updates or {}))
            self.store[thread_id] = current

    graph = _PatchGraph()

    async def _fake_build_graph_config(*, thread_id, **_kwargs):
        captured["build"].append(thread_id)
        return graph, {"configurable": {"thread_id": thread_id}}

    async def _capture_broadcast(**kwargs):
        captured["acks"].append(kwargs)
        return None

    monkeypatch.setattr(endpoint, "_build_graph_config", _fake_build_graph_config)
    monkeypatch.setattr(endpoint, "assert_node_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(endpoint.sse_broadcast, "broadcast", _capture_broadcast)

    async def _run():
        request = _request()
        patch_a = endpoint.ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"pressure_bar": 7},
            base_versions={"pressure_bar": 0},
        )
        patch_b = endpoint.ParametersPatchRequest(
            chat_id=chat_id,
            parameters={"pressure_bar": 9},
            base_versions={"pressure_bar": 0},
        )
        response_a = await endpoint.patch_parameters(patch_a, request, user=user)
        response_b = await endpoint.patch_parameters(patch_b, request, user=user)
        return response_a, response_b

    response_a, response_b = asyncio.run(_run())

    assert captured["build"] == [expected_thread_id, expected_thread_id]
    assert response_a["ok"] is True
    assert response_b["ok"] is True
    assert response_a["applied_fields"] == ["pressure_bar"]
    assert response_a["rejected_fields"] == []
    assert response_b["applied_fields"] == []
    assert response_b["rejected_fields"] == [{"field": "pressure_bar", "reason": "stale"}]
    # Frontend resync signal for conflict is rejected_fields in response/ack.
    assert response_b["versions"]["pressure_bar"] == 1

    final_state = graph.store[expected_thread_id]
    assert final_state["parameters"]["pressure_bar"] == 7
    assert final_state["parameter_versions"]["pressure_bar"] == 1
    first_ts = response_a["updated_at"]["pressure_bar"]
    second_ts = response_b["updated_at"]["pressure_bar"]
    assert isinstance(first_ts, float)
    assert second_ts == first_ts

    assert len(captured["acks"]) == 2
    assert captured["acks"][0]["event"] == "parameter_patch_ack"
    assert captured["acks"][1]["event"] == "parameter_patch_ack"
    assert captured["acks"][0]["data"]["rejected_fields"] == []
    assert captured["acks"][1]["data"]["rejected_fields"] == [{"field": "pressure_bar", "reason": "stale"}]

    # Evidence:
    # - backend/app/api/v1/endpoints/langgraph_v2.py:1477-1491 (resolved checkpoint_thread_id -> _build_graph_config)
    # - backend/app/api/v1/endpoints/langgraph_v2.py:1564-1587 (response + parameter_patch_ack carry rejected_fields)
    # - backend/app/langgraph_v2/utils/parameter_patch.py:331-335 (stale rejection rule)
    # - backend/app/langgraph_v2/utils/parameter_patch.py:352-358 (only applied fields mutate versions/updated_at)
