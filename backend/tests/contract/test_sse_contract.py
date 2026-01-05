from __future__ import annotations

import asyncio
import json
import datetime as dt
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Tuple

import pytest


def _parse_sse_frames(frames: List[str]) -> List[Tuple[str, Dict[str, Any]]]:
    parsed: List[Tuple[str, Dict[str, Any]]] = []
    for frame in frames:
        event = None
        data = None
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                data = json.loads(raw)
        if event is None or data is None:
            continue
        parsed.append((event, data))
    return parsed


def _set_minimal_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # app.core.config.Settings has many required fields; set minimal dummy values so that
    # importing API endpoints does not fail during settings initialization.
    monkeypatch.setenv("postgres_user", "test")
    monkeypatch.setenv("postgres_password", "test")
    monkeypatch.setenv("postgres_host", "localhost")
    monkeypatch.setenv("postgres_port", "5432")
    monkeypatch.setenv("postgres_db", "test")
    monkeypatch.setenv("database_url", "postgresql+psycopg://test:test@localhost:5432/test")
    monkeypatch.setenv("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/test")

    monkeypatch.setenv("openai_api_key", "dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    monkeypatch.setenv("qdrant_url", "http://localhost:6333")
    monkeypatch.setenv("qdrant_collection", "test")

    monkeypatch.setenv("redis_url", "redis://localhost:6379/0")

    monkeypatch.setenv("nextauth_url", "http://localhost:3000")
    monkeypatch.setenv("nextauth_secret", "dummy")

    monkeypatch.setenv("keycloak_issuer", "http://localhost:8080/realms/test")
    monkeypatch.setenv("keycloak_jwks_url", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
    monkeypatch.setenv("keycloak_client_id", "dummy")
    monkeypatch.setenv("keycloak_client_secret", "dummy")
    monkeypatch.setenv("keycloak_expected_azp", "dummy")


@dataclass
class _Snapshot:
    values: Dict[str, Any]


class _DummyGraph:
    def __init__(self, events: List[Dict[str, Any]], final_values: Dict[str, Any]):
        self._events = list(events)
        self._final_values = dict(final_values)

    async def astream_events(self, *_args: Any, **_kwargs: Any) -> AsyncGenerator[Dict[str, Any], None]:
        for item in self._events:
            await asyncio.sleep(0)
            yield item

    async def aget_state(self, *_args: Any, **_kwargs: Any) -> _Snapshot:
        return _Snapshot(values=self._final_values)


async def _collect_async(gen: AsyncGenerator[str, None]) -> List[str]:
    chunks: List[str] = []
    async for item in gen:
        chunks.append(item)
    return chunks


def test_sse_stream_emits_done_once_and_is_last_for_normal_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.api.v1.endpoints import langgraph_v2 as endpoint

    dummy_events = [
        {
            "event": "on_node_start",
            "name": "final_answer_node",
            "data": {},
        },
        {
            "event": "on_chat_model_stream",
            "name": "final_answer_node",
            "data": {"chunk": {"content": "Hallo "}},
        },
        {
            "event": "on_chat_model_stream",
            "name": "final_answer_node",
            "data": {"chunk": {"content": "Welt"}},
        },
        {
            "event": "on_node_end",
            "name": "final_answer_node",
            "data": {"output": {"parameters": {"temperature_C": 80}}},
        },
    ]
    final_values = {"final_text": "Hallo Welt", "parameters": {"temperature_C": 80}}
    dummy_graph = _DummyGraph(dummy_events, final_values)

    async def _get_graph() -> _DummyGraph:
        return dummy_graph

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _get_graph)

    request = endpoint.LangGraphV2Request(input="Hi", thread_id="t1", user_id="u1")
    frames = asyncio.run(_collect_async(endpoint._event_stream_v2(request)))

    events = _parse_sse_frames(frames)
    assert events, "SSE produced no frames"

    node_start = [payload for evt, payload in events if evt == "node_start"]
    node_end = [payload for evt, payload in events if evt == "node_end"]
    assert node_start, "expected at least one node_start event"
    assert node_end, "expected at least one node_end event"
    for payload in node_start + node_end:
        node = payload.get("node")
        assert isinstance(node, str) and node, f"expected node field in {payload}"
        ts = payload.get("ts")
        assert isinstance(ts, str) and ts, f"expected ts field in {payload}"
        # iso parseable
        dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))

    done_events = [evt for evt, payload in events if evt == "done"]
    assert len(done_events) == 1, f"expected exactly one done event, got {len(done_events)}"
    assert events[-1][0] == "done", f"expected last event to be done, got {events[-1][0]!r}"


def test_sse_stream_emits_error_then_done_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.api.v1.endpoints import langgraph_v2 as endpoint

    async def _error_events() -> AsyncGenerator[Dict[str, Any], None]:
        yield {"event": "on_error", "name": "final_answer_node", "data": {"error": "boom"}}

    class _ErrorGraph(_DummyGraph):
        async def astream_events(self, *_args: Any, **_kwargs: Any) -> AsyncGenerator[Dict[str, Any], None]:
            async for item in _error_events():
                yield item

        async def aget_state(self, *_args: Any, **_kwargs: Any) -> _Snapshot:
            return _Snapshot(values={})

    async def _get_graph() -> _ErrorGraph:
        return _ErrorGraph([], {})

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _get_graph)

    request = endpoint.LangGraphV2Request(input="Hi", thread_id="t1", user_id="u1")
    frames = asyncio.run(_collect_async(endpoint._event_stream_v2(request)))

    events = _parse_sse_frames(frames)
    event_names = [name for name, _ in events]
    assert "error" in event_names, f"expected error event, got: {event_names}"
    assert event_names[-1] == "done", f"expected stream to end with done, got: {event_names[-1]!r}"


def test_sse_does_not_emit_duplicate_parameter_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.api.v1.endpoints import langgraph_v2 as endpoint

    dummy_events = [
        {
            "event": "on_node_end",
            "name": "calculator_node",
            # Include a state-like marker so _extract_state_like picks it up.
            "data": {"output": {"final_text": "ok", "parameters": {"temperature_C": 80}}},
        }
    ]
    final_values = {"final_text": "ok", "parameters": {"temperature_C": 80}}
    dummy_graph = _DummyGraph(dummy_events, final_values)

    async def _get_graph() -> _DummyGraph:
        return dummy_graph

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _get_graph)

    request = endpoint.LangGraphV2Request(input="Hi", thread_id="t1", user_id="u1")
    frames = asyncio.run(_collect_async(endpoint._event_stream_v2(request)))
    events = _parse_sse_frames(frames)

    param_updates = [payload for evt, payload in events if evt == "parameter_update"]
    state_updates = [payload for evt, payload in events if evt == "state_update"]

    assert (
        not param_updates
    ), f"expected no per-key parameter_update when state_update is emitted, got {param_updates}"
    assert state_updates, "expected a state_update event when parameters change"
    assert (
        state_updates[0].get("delta", {}).get("parameters", {}).get("temperature_C") == 80
    ), f"expected state_update.delta.parameters.temperature_C=80, got {state_updates[0]}"
