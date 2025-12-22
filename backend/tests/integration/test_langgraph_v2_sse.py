import importlib
import json

import pytest
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app_mod = importlib.import_module("app.main")
    return TestClient(getattr(app_mod, "app"))


def _auth(monkeypatch: pytest.MonkeyPatch, *, user: str = "test-user") -> None:
    deps = importlib.import_module("app.services.auth.dependencies")
    monkeypatch.setattr(deps, "verify_access_token", lambda _t: {"preferred_username": user})


def test_chat_v2_sse_streams_token_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    SealAIState = importlib.import_module("app.langgraph_v2.state").SealAIState

    async def _fake_run_graph_to_state(_req, *, user_id: str):
        return SealAIState(final_text=f"hello from {user_id}")

    monkeypatch.setattr(ep, "_run_graph_to_state", _fake_run_graph_to_state)

    client = _client()
    with client.stream(
        "POST",
        "/api/v1/langgraph/chat/v2",
        headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-sse-1"},
        json={"input": "hi", "chat_id": "default"},
    ) as res:
        assert res.status_code == 200
        assert (res.headers.get("content-type") or "").startswith("text/event-stream")
        text = ""
        for chunk in res.iter_text():
            text += chunk
            if "event: done" in text:
                break

    assert "event: token" in text
    assert "event: done" in text


def test_chat_v2_sse_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")

    async def _boom(_req, *, user_id: str):
        raise RuntimeError("secret: do not leak this")

    monkeypatch.setattr(ep, "_run_graph_to_state", _boom)

    client = _client()
    with client.stream(
        "POST",
        "/api/v1/langgraph/chat/v2",
        headers={"Authorization": "Bearer test-token", "X-Request-Id": "it-sse-2"},
        json={"input": "hi", "chat_id": "default"},
    ) as res:
        assert res.status_code == 200
        text = ""
        for chunk in res.iter_text():
            text += chunk
            if "event: error" in text and "event: done" in text:
                break

    assert "event: error" in text
    assert "secret: do not leak this" not in text
    assert "request_id" in text

    error_payload = None
    for block in text.split("\n\n"):
        if "event: error" in block:
            for line in block.splitlines():
                if line.startswith("data: "):
                    error_payload = json.loads(line.replace("data: ", "", 1))
                    break
            break
    assert error_payload is not None
    assert error_payload.get("request_id") == "it-sse-2"
