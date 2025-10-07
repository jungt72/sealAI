# backend/tests/test_ai_endpoints.py
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from typing import Any, Dict, AsyncGenerator

import pytest
from fastapi.testclient import TestClient

from app.main import app  # lädt Router
from app.api.v1.endpoints import ai as ai_mod


# ─────────────────────────────────────────────────────────────
# Helfer
# ─────────────────────────────────────────────────────────────
@contextmanager
def ws_optional_auth():
    """Setzt WS_AUTH_OPTIONAL=True für die Dauer des Blocks."""
    old = ai_mod.WS_AUTH_OPTIONAL
    ai_mod.WS_AUTH_OPTIONAL = True
    try:
        yield
    finally:
        ai_mod.WS_AUTH_OPTIONAL = old


@contextmanager
def ws_required_auth():
    """Setzt WS_AUTH_OPTIONAL=False für die Dauer des Blocks."""
    old = ai_mod.WS_AUTH_OPTIONAL
    ai_mod.WS_AUTH_OPTIONAL = False
    try:
        yield
    finally:
        ai_mod.WS_AUTH_OPTIONAL = old


def fake_invoke(result_text: str, out_state_ref: Dict[str, Any] | None = None):
    """Baut eine Fake-Funktion für invoke_consult, optional mit State-Capture."""
    def _impl(state: Dict[str, Any]) -> Dict[str, Any]:
        if out_state_ref is not None:
            out_state_ref.clear()
            out_state_ref.update(state)
        return {"final": {"text": result_text}}
    return _impl


def fake_stream(events: list[Dict[str, Any]]):
    """Baut einen Fake-Async-Generator für stream_consult."""
    async def _gen(_state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        for ev in events:
            await asyncio.sleep(0)  # kooperatives Scheduling
            yield ev
    return _gen


# ─────────────────────────────────────────────────────────────
# REST: Params-Forwarding & Memory-Intents
# ─────────────────────────────────────────────────────────────
def test_rest_params_are_forwarded(monkeypatch):
    captured: Dict[str, Any] = {}
    monkeypatch.setattr(ai_mod, "invoke_consult", fake_invoke("OK", captured))

    client = TestClient(app)
    payload = {
        "chat_id": "thread-test",
        "input": "Bitte bewerten.",
        "params": {
            "falltyp": "RWDR",
            "wellen_mm": 25,
            "gehause_mm": 47,
            "breite_mm": 7,
            "medium": "Hydrauliköl",
            "temp_max_c": 80,
            "druck_bar": 2,
            "drehzahl_u_min": 1500,
        },
    }
    r = client.post("/api/v1/ai/beratung", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "OK"

    # Wichtige Felder geprüft
    assert captured["chat_id"] == "api:thread-test"
    assert captured["input"] == "Bitte bewerten."
    assert captured["params"] == payload["params"]
    assert captured["messages"][0]["content"] == "Bitte bewerten."


def test_rest_memory_intent_number(monkeypatch):
    # invoke_consult sollte NICHT aufgerufen werden
    called = {"value": False}

    def _guard(_state):
        called["value"] = True
        return {"final": {"text": "should-not-be-used"}}

    monkeypatch.setattr(ai_mod, "invoke_consult", _guard)

    client = TestClient(app)
    r = client.post("/api/v1/ai/beratung", json={"chat_id": "t1", "input": "merke dir 42"})
    assert r.status_code == 200, r.text
    assert "gemerkt" in r.json()["text"].lower()
    assert called["value"] is False


# ─────────────────────────────────────────────────────────────
# WS: Auth, Heartbeat, Params, Memory-Intents
# ─────────────────────────────────────────────────────────────
def test_ws_accepts_bearer_header_when_required(monkeypatch):
    # Fake-Stream: minimaler Durchlauf
    monkeypatch.setattr(
        ai_mod,
        "stream_consult",
        fake_stream(
            [
                {"event": "start", "thread_id": "api:thread-test", "route": "graph", "graph": "consult"},
                {"event": "final", "text": "WS OK"},
                {"event": "done"},
            ]
        ),
    )

    client = TestClient(app)
    with ws_required_auth():
        with client.websocket_connect(
            "/api/v1/ai/ws",
            headers={"Authorization": "Bearer dummy"},
        ) as ws:
            ws.send_json({"chat_id": "thread-test", "input": "Hallo"})
            msgs = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
            types = [m.get("event") for m in msgs]
            assert types == ["start", "final", "done"]
            assert msgs[1]["text"] == "WS OK"


def test_ws_rejects_without_token_when_required():
    client = TestClient(app)
    with ws_required_auth():
        with pytest.raises(Exception):
            # Verbindung sollte mit Policy Violation (1008) beendet werden
            with client.websocket_connect("/api/v1/ai/ws") as _:
                pass


def test_ws_heartbeat(monkeypatch):
    monkeypatch.setattr(
        ai_mod,
        "stream_consult",
        fake_stream([]),  # wir treiben keinen eigentlichen Stream an
    )
    client = TestClient(app)
    with ws_optional_auth():
        with client.websocket_connect("/api/v1/ai/ws") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            assert ws.receive_text() == '{"type":"pong"}'


def test_ws_params_and_memory_intent(monkeypatch):
    # Wenn Memory-Intent anschlägt, sendet die WS-Schicht token/final/done
    client = TestClient(app)
    with ws_optional_auth():
        with client.websocket_connect("/api/v1/ai/ws") as ws:
            ws.send_json({"chat_id": "t2", "input": "merke dir 7"})
            ev1 = ws.receive_json()
            ev2 = ws.receive_json()
            ev3 = ws.receive_json()
            assert ev1["event"] == "token"
            assert "gemerkt" in ev1["delta"].lower()
            assert ev2["event"] == "final"
            assert "gemerkt" in ev2["text"].lower()
            assert ev3["event"] == "done"

    # Und normaler Flow mit params:
    captured_state: Dict[str, Any] = {}

    async def _cap_stream(state: Dict[str, Any]):
        captured_state.clear()
        captured_state.update(state)
        # Simulierter, kurzer Stream
        yield {"event": "start", "thread_id": state["chat_id"]}
        yield {"event": "final", "text": "alles klar"}
        yield {"event": "done"}

    monkeypatch.setattr(ai_mod, "stream_consult", _cap_stream)

    with ws_optional_auth():
        with client.websocket_connect("/api/v1/ai/ws") as ws:
            ws.send_json(
                {
                    "chat_id": "t3",
                    "input": "Hallo",
                    "params": {"falltyp": "RWDR", "wellen_mm": 25},
                }
            )
            ws.receive_json()  # start
            ws.receive_json()  # final
            ws.receive_json()  # done

    assert captured_state["chat_id"] == "api:t3"
    assert captured_state["input"] == "Hallo"
    assert captured_state["params"] == {"falltyp": "RWDR", "wellen_mm": 25}
    assert captured_state["messages"][0]["content"] == "Hallo"
