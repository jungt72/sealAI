import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import ai as ai_module


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ai_module.router)
    return app


def test_chat_ws_emits_structured_events(monkeypatch):
    expected_ui = {"ui_action": "open_form", "form_id": "rwdr_params_v1"}

    async def fake_stream(state):
        yield {
            "event": "on_custom_event",
            "data": {"type": "stream_text", "text": "Ant", "node": "recommend"},
        }
        yield {
            "event": "on_graph_end",
            "data": {
                "result": {
                    "messages": [{"role": "assistant", "content": "Antwort"}],
                    "ui_event": expected_ui,
                }
            },
        }

    def fake_invoke(state):  # pragma: no cover - fallback should not trigger
        raise AssertionError("stream fallback should not be used in test")

    monkeypatch.setattr(ai_module, "_invoke_consult", fake_invoke)
    monkeypatch.setattr(ai_module, "_stream_consult", fake_stream)
    monkeypatch.setattr(ai_module, "_maybe_handle_memory_intent", lambda text, tid: None)

    app = _make_app()
    client = TestClient(app)

    with client.websocket_connect("/api/v1/ai/ws") as ws:
        ws.send_text(json.dumps({"chat_id": "thread1", "input": "Hallo"}))

        starting = ws.receive_json()
        assert starting.get("event") == "starting"
        assert starting.get("phase") == "starting"
        assert starting.get("thread_id") == "api:thread1"

        stream_evt = ws.receive_json()
        assert stream_evt.get("event") == "stream"
        assert stream_evt.get("thread_id") == "api:thread1"
        assert stream_evt.get("text") == "Ant"

        ui_msg = ws.receive_json()
        assert ui_msg.get("event") == "ui_action"
        assert ui_msg.get("thread_id") == "api:thread1"
        assert ui_msg.get("ui_action") == expected_ui["ui_action"]
        assert ui_msg.get("ui_event") == expected_ui

        final = ws.receive_json()
        assert final.get("event") == "final"
        assert final.get("thread_id") == "api:thread1"
        assert final.get("text") == "Antwort"
        assert final.get("final", {}).get("text") == "Antwort"

        done = ws.receive_json()
        assert done.get("event") == "done"
        assert done.get("thread_id") == "api:thread1"
