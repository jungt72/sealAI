import json
from types import SimpleNamespace

import pytest

from app.agent.api.sse_contract import SSEEventBuilder
from app.agent.api.streaming import _stream_fast_response


def _payload(frame: str) -> dict:
    raw = frame.removeprefix("data: ").strip()
    assert raw != "[DONE]"
    return json.loads(raw)


def test_sse_event_builder_adds_stable_turn_metadata_and_monotonic_sequence() -> None:
    builder = SSEEventBuilder(turn_id="turn-1")

    progress = builder.event({"type": "progress", "data": {"event_type": "final_guard.running"}})
    state = builder.event(
        {"type": "state_update", "reply": "Final", "answer_mode": "technical_case_challenge"},
        event_type="state_update",
        is_final=True,
    )
    done = builder.event({"type": "done"}, event_type="done")

    assert {progress["turn_id"], state["turn_id"], done["turn_id"]} == {"turn-1"}
    assert [progress["sequence"], state["sequence"], done["sequence"]] == [1, 2, 3]
    assert len({progress["event_id"], state["event_id"], done["event_id"]}) == 3
    assert progress["event_type"] == "metadata"
    assert state["event_type"] == "state_update"
    assert state["is_final"] is True
    assert state["answer_mode"] == "technical_case_challenge"
    assert state["data"]["answer_mode"] == "technical_case_challenge"
    assert done["event_type"] == "done"
    assert done["is_final"] is False


def test_sse_event_builder_allows_exactly_one_successful_final_event() -> None:
    builder = SSEEventBuilder(turn_id="turn-1")
    builder.event({"type": "state_update", "reply": "Final"}, event_type="state_update", is_final=True)

    with pytest.raises(ValueError, match="sse_final_event_already_emitted"):
        builder.event({"type": "state_update", "reply": "Duplicate"}, event_type="state_update", is_final=True)


def test_sse_event_builder_error_event_contains_error_code_without_final_success() -> None:
    builder = SSEEventBuilder(turn_id="turn-1")
    event = builder.event(
        {"type": "error", "message": "Deine Sitzung ist abgelaufen."},
        event_type="error",
        error_code="auth_expired",
    )

    assert event["event_type"] == "error"
    assert event["error_code"] == "auth_expired"
    assert event["is_final"] is False
    serialized = json.dumps(event)
    assert "Bearer " not in serialized
    assert "refresh_token" not in serialized


def test_sse_event_builder_generates_unique_turn_ids_without_explicit_id() -> None:
    first = SSEEventBuilder.for_request(
        SimpleNamespace(session_id="session-1", message="identische technische Nachricht")
    )
    second = SSEEventBuilder.for_request(
        SimpleNamespace(session_id="session-1", message="identische technische Nachricht")
    )

    assert first.turn_id != second.turn_id
    assert first.turn_id.startswith("turn:")
    assert second.turn_id.startswith("turn:")
    assert "identische technische Nachricht" not in first.turn_id
    assert "session-1" not in first.turn_id


def test_sse_event_builder_uses_explicit_turn_id() -> None:
    builder = SSEEventBuilder.for_request(
        SimpleNamespace(session_id="session-1", message="Hallo", turn_id="client-turn-1")
    )
    event = builder.event({"type": "progress"})

    assert builder.turn_id == "client-turn-1"
    assert event["turn_id"] == "client-turn-1"
    assert event["event_id"] == "client-turn-1:1"


def test_sse_event_builder_replaces_invalid_explicit_turn_id_with_uuid() -> None:
    builder = SSEEventBuilder.for_request(
        SimpleNamespace(session_id="session-1", message="Hallo", turn_id="raw user text with spaces")
    )

    assert builder.turn_id.startswith("turn:")
    assert "raw user text" not in builder.turn_id


@pytest.mark.asyncio
async def test_fast_response_stream_emits_contract_metadata_once() -> None:
    request = SimpleNamespace(session_id="session-1", message="Hallo")
    fast_response = SimpleNamespace(
        content="Hallo, womit kann ich helfen?",
        source_classification="GREETING",
    )
    frames = [
        frame
        async for frame in _stream_fast_response(
            request=request,
            fast_response=fast_response,
            event_builder=SSEEventBuilder(turn_id="turn-fast"),
        )
    ]
    payloads = [_payload(frame) for frame in frames if frame.startswith("data: {")]

    assert frames[-1] == "data: [DONE]\n\n"
    assert len(payloads) == 1
    event = payloads[0]
    assert event["type"] == "state_update"
    assert event["turn_id"] == "turn-fast"
    assert event["event_id"] == "turn-fast:1"
    assert event["sequence"] == 1
    assert event["event_type"] == "state_update"
    assert event["is_final"] is True
    assert event["error_code"] is None
    assert event["data"]["reply"] == "Hallo, womit kann ich helfen?"
