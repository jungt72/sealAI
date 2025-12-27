from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure backend is on path
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Minimal env defaults for settings to load
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


def _client() -> TestClient:
    import importlib

    app_mod = importlib.import_module("app.main")
    return TestClient(getattr(app_mod, "app"))


def _auth(monkeypatch: pytest.MonkeyPatch, *, user: str = "test-user") -> None:
    import importlib

    deps = importlib.import_module("app.services.auth.dependencies")
    monkeypatch.setattr(deps, "verify_access_token", lambda _t: {"preferred_username": user})


class DummyGraphTrace:
    checkpointer = object()

    def astream(self, _input, config=None, *, stream_mode=None, **_kwargs):
        async def gen():
            yield ("messages", ("Hi", {"node": "frontdoor_node"}))
            yield ("values", {"phase": "analysis", "last_node": "frontdoor_node"})
            yield ("messages", (" there", {"node": "response_node"}))
            yield ("values", {"phase": "final", "last_node": "response_node"})

        return gen()


def _stream_text(client: TestClient) -> str:
    text = ""
    with client.stream(
        "POST",
        "/api/v1/langgraph/chat/v2",
        headers={"Authorization": "Bearer test-token", "X-Request-Id": "trace-1"},
        json={"input": "hi", "chat_id": "default"},
    ) as res:
        assert res.status_code == 200
        for chunk in res.iter_text():
            text += chunk
            if "event: done" in text:
                break
    return text


def test_chat_v2_sse_trace_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    monkeypatch.setenv("SEALAI_LG_TRACE", "1")

    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphTrace()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    text = _stream_text(_client())
    assert "event: trace" in text


def test_chat_v2_sse_trace_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    monkeypatch.setenv("SEALAI_LG_TRACE", "0")

    import importlib

    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _dummy_graph():
        return DummyGraphTrace()

    monkeypatch.setattr(ep, "get_sealai_graph_v2", _dummy_graph)

    text = _stream_text(_client())
    assert "event: trace" not in text
