from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Tuple

import pytest


def _parse_sse_frames(frames: List[str | bytes]) -> List[Tuple[str, Dict[str, Any]]]:
    parsed: List[Tuple[str, Dict[str, Any]]] = []
    for frame in frames:
        text = frame.decode("utf-8") if isinstance(frame, bytes) else frame
        event = None
        data = None
        for line in text.splitlines():
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
        self.checkpointer = object()

    async def astream(self, *_args: Any, **_kwargs: Any) -> AsyncGenerator[tuple[str, Any], None]:
        for item in self._events:
            await asyncio.sleep(0)
            event = item.get("event")
            if event == "on_chat_model_stream":
                text = (((item.get("data") or {}).get("chunk") or {}).get("content") or "")
                yield ("messages", ({"content": text}, {"langgraph_node": item.get("name")}))
            elif event == "on_node_end":
                output = (item.get("data") or {}).get("output")
                if isinstance(output, dict):
                    yield ("values", output)
        yield ("values", self._final_values)

    async def aget_state(self, *_args: Any, **_kwargs: Any) -> _Snapshot:
        return _Snapshot(values=self._final_values)


async def _collect_async(gen: AsyncGenerator[bytes, None]) -> List[bytes]:
    chunks: List[bytes] = []
    async for item in gen:
        chunks.append(item)
    return chunks


def _checkpoint_thread_id(endpoint: Any, *, tenant_id: str, user_id: str, chat_id: str) -> str:
    return endpoint.resolve_checkpoint_thread_id(
        tenant_id=tenant_id,
        user_id=user_id,
        chat_id=chat_id,
    )


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
    frames = asyncio.run(
        _collect_async(
            endpoint._event_stream_v2(
                request,
                user_id="u1",
                tenant_id="tenant-1",
                can_read_private=False,
                checkpoint_thread_id=_checkpoint_thread_id(
                    endpoint, tenant_id="tenant-1", user_id="u1", chat_id="t1"
                ),
            )
        )
    )

    events = _parse_sse_frames(frames)
    assert events, "SSE produced no frames"

    token_events = [payload for evt, payload in events if evt == "token"]
    assert token_events, "expected streamed token events"

    done_events = [evt for evt, payload in events if evt == "done"]
    assert len(done_events) == 1, f"expected exactly one done event, got {len(done_events)}"
    assert events[-1][0] == "done", f"expected last event to be done, got {events[-1][0]!r}"


def test_sse_stream_emits_error_then_done_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    from app.api.v1.endpoints import langgraph_v2 as endpoint

    class _ErrorGraph(_DummyGraph):
        async def astream(self, *_args: Any, **_kwargs: Any) -> AsyncGenerator[tuple[str, Any], None]:
            if False:
                yield ("values", {})
            raise RuntimeError("boom")

        async def aget_state(self, *_args: Any, **_kwargs: Any) -> _Snapshot:
            return _Snapshot(values={})

    async def _get_graph() -> _ErrorGraph:
        return _ErrorGraph([], {})

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _get_graph)

    request = endpoint.LangGraphV2Request(input="Hi", thread_id="t1", user_id="u1")
    frames = asyncio.run(
        _collect_async(
            endpoint._event_stream_v2(
                request,
                user_id="u1",
                tenant_id="tenant-1",
                can_read_private=False,
                checkpoint_thread_id=_checkpoint_thread_id(
                    endpoint, tenant_id="tenant-1", user_id="u1", chat_id="t1"
                ),
            )
        )
    )

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
    frames = asyncio.run(
        _collect_async(
            endpoint._event_stream_v2(
                request,
                user_id="u1",
                tenant_id="tenant-1",
                can_read_private=False,
                checkpoint_thread_id=_checkpoint_thread_id(
                    endpoint, tenant_id="tenant-1", user_id="u1", chat_id="t1"
                ),
            )
        )
    )
    events = _parse_sse_frames(frames)

    param_updates = [payload for evt, payload in events if evt == "parameter_update"]
    state_updates = [payload for evt, payload in events if evt == "state_update"]

    assert (
        not param_updates
    ), f"expected no per-key parameter_update when state_update is emitted, got {param_updates}"
    assert state_updates, "expected a state_update event when parameters change"
    assert (
        state_updates[0].get("parameters", {}).get("temperature_C") == 80
    ), f"expected state_update.parameters.temperature_C=80, got {state_updates[0]}"
