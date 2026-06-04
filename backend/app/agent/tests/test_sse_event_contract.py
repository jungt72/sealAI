import json
from types import SimpleNamespace

import pytest

from app.agent.api.dispatch import _MobileTriageFastResponse, _resolve_runtime_dispatch
from app.agent.api.models import ChatRequest
from app.agent.api.sse_contract import SSEEventBuilder, infer_event_type
from app.agent.api.streaming import _stream_fast_response, _stream_light_runtime
from app.agent.state.models import GovernedSessionState
from app.services.auth.dependencies import RequestUser


def _payload(frame: str) -> dict:
    raw = frame.removeprefix("data: ").strip()
    assert raw != "[DONE]"
    return json.loads(raw)


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


def test_sse_event_builder_adds_stable_turn_metadata_and_monotonic_sequence() -> None:
    builder = SSEEventBuilder(turn_id="turn-1")

    progress = builder.event(
        {"type": "progress", "data": {"event_type": "final_guard.running"}}
    )
    state = builder.event(
        {
            "type": "state_update",
            "reply": "Final",
            "answer_mode": "technical_case_challenge",
        },
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
    builder.event(
        {"type": "state_update", "reply": "Final"},
        event_type="state_update",
        is_final=True,
    )

    with pytest.raises(ValueError, match="sse_final_event_already_emitted"):
        builder.event(
            {"type": "state_update", "reply": "Duplicate"},
            event_type="state_update",
            is_final=True,
        )


def test_sse_event_builder_error_event_contains_error_code_without_final_success() -> (
    None
):
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
        SimpleNamespace(
            session_id="session-1", message="identische technische Nachricht"
        )
    )
    second = SSEEventBuilder.for_request(
        SimpleNamespace(
            session_id="session-1", message="identische technische Nachricht"
        )
    )

    assert first.turn_id != second.turn_id
    assert first.turn_id.startswith("turn:")
    assert second.turn_id.startswith("turn:")
    assert "identische technische Nachricht" not in first.turn_id
    assert "session-1" not in first.turn_id


def test_sse_event_builder_uses_explicit_turn_id() -> None:
    builder = SSEEventBuilder.for_request(
        SimpleNamespace(
            session_id="session-1", message="Hallo", turn_id="client-turn-1"
        )
    )
    event = builder.event({"type": "progress"})

    assert builder.turn_id == "client-turn-1"
    assert event["turn_id"] == "client-turn-1"
    assert event["event_id"] == "client-turn-1:1"


def test_sse_event_builder_replaces_invalid_explicit_turn_id_with_uuid() -> None:
    builder = SSEEventBuilder.for_request(
        SimpleNamespace(
            session_id="session-1", message="Hallo", turn_id="raw user text with spaces"
        )
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


# === Patch 4 — Current SSE stream contract baseline ========================
#
# Locks the current backend SSE event contract so a later V1.6 patch can add the
# AssistantTurnEnvelope / pocket_cockpit_patch / action_chips ADDITIVELY without
# breaking existing clients. These tests pin CURRENT behavior, not the V1.6
# target. Seams used (all deterministic, offline):
#   [SSE-SERIALIZER]  infer_event_type / SSEEventBuilder — the exact mapping and
#                     framing streaming.py emits through (event_builder.frame).
#   [SSE-FAST-HELPER] _stream_fast_response — the real streaming helper the live
#                     event_generator dispatches fast / mobile-triage turns to.

# The raw event names streaming.py actually frames, grouped by the canonical
# core SSE type a backward-compatible client depends on.
_CORE_DELTA_RAW = ("text_chunk", "answer.token", "delta")
_CORE_STATE_UPDATE_RAW = ("state_update",)
_CORE_DONE_RAW = ("turn_complete", "done", "stream_end")


def test_stream_contract_emits_backward_compatible_core_events() -> None:
    # [SSE-SERIALIZER] The three core event types every current client relies on
    # — delta (text), state_update (workspace projection), done (completion) —
    # are produced by the canonical mapping streaming.py uses.
    for raw in _CORE_DELTA_RAW:
        assert infer_event_type({"type": raw}) == "delta"
    for raw in _CORE_STATE_UPDATE_RAW:
        assert infer_event_type({"type": raw}) == "state_update"
    for raw in _CORE_DONE_RAW:
        assert infer_event_type({"type": raw}) == "done"

    # A text_chunk frames as a delta carrying the streamed text (the exact call
    # _stream_light_runtime / _stream_exploration_reply make).
    builder = SSEEventBuilder(turn_id="turn-core")
    delta = builder.event({"type": "text_chunk", "text": "Hallo"}, event_type="delta")
    assert delta["event_type"] == "delta"
    assert delta["data"]["text"] == "Hallo"


@pytest.mark.asyncio
async def test_stream_contract_fast_helper_emits_state_update_then_done() -> None:
    # [SSE-FAST-HELPER] The live fast helper ends a turn with a single final
    # state_update (the workspace projection) followed by the [DONE] terminator.
    request = SimpleNamespace(session_id="s-core", message="Hallo")
    fast_response = SimpleNamespace(content="Hallo!", source_classification="GREETING")
    frames = [
        frame
        async for frame in _stream_fast_response(
            request=request,
            fast_response=fast_response,
            event_builder=SSEEventBuilder(turn_id="turn-core-fast"),
        )
    ]
    assert frames[-1] == "data: [DONE]\n\n"  # completion terminator preserved
    events = [_payload(frame) for frame in frames if frame.startswith("data: {")]
    assert len(events) == 1
    final = events[0]
    assert final["event_type"] == "state_update"
    assert final["is_final"] is True
    assert final["data"]["reply"] == "Hallo!"


@pytest.mark.asyncio
async def test_stream_contract_does_not_replace_state_update_with_v16_envelope() -> (
    None
):
    # The terminal event is still the state_update workspace projection contract
    # (v92 dashboard / turn_envelope), NOT a V1.6 AssistantTurnEnvelope event.
    request = SimpleNamespace(session_id="s-env", message="Hallo")
    fast_response = SimpleNamespace(content="Hallo!", source_classification="GREETING")
    frames = [
        frame
        async for frame in _stream_fast_response(
            request=request,
            fast_response=fast_response,
            event_builder=SSEEventBuilder(turn_id="turn-env"),
        )
    ]
    final = [_payload(frame) for frame in frames if frame.startswith("data: {")][0]

    # Still a state_update, and it carries the existing workspace projection.
    assert final["event_type"] == "state_update"
    assert "v92_dashboard" in final["data"]  # workspace projection contract
    assert "turn_envelope" in final["data"]  # V9.2 envelope (not the V1.6 one)
    # A non-envelope (greeting) turn must NOT gain any V1.6 envelope fields — the
    # additive wiring only fires for mobile-triage turns; the state_update here
    # stays the plain workspace projection.
    assert "assistant_turn_envelope" not in final
    assert "assistant_turn_envelope" not in final["data"]
    assert "pocket_cockpit_patch" not in final["data"]
    assert "action_chips" not in final["data"]


@pytest.mark.asyncio
async def test_mobile_triage_envelope_is_serialized_over_sse_additively() -> None:
    # [SSE-FAST-HELPER] Patch 5: the mobile triage AssistantTurnEnvelope built in
    # dispatch now reaches the SSE client additively in the final state_update —
    # without replacing the existing workspace projection contract.
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="sifft", session_id="m-wire", has_attachment=True),
        current_user=_user(),
    )
    # (1) The envelope — with pocket cockpit patch + action chips — is built in
    # dispatch.
    assert isinstance(dispatch.fast_response, _MobileTriageFastResponse)
    envelope = dispatch.fast_response.mobile_triage_envelope
    assert envelope["pocket_cockpit_patch"]
    assert envelope["action_chips"]

    request = SimpleNamespace(session_id="m-wire", message="sifft")
    frames = [
        frame
        async for frame in _stream_fast_response(
            request=request,
            fast_response=dispatch.fast_response,
            event_builder=SSEEventBuilder(turn_id="turn-mobile"),
        )
    ]
    # done / [DONE] still terminates the stream.
    assert frames[-1] == "data: [DONE]\n\n"
    final = [_payload(frame) for frame in frames if frame.startswith("data: {")][0]
    data = final["data"]

    # (2) The state_update now carries the V1.6 fields additively.
    assert data["assistant_turn_envelope"] == envelope
    assert data["pocket_cockpit_patch"] == envelope["pocket_cockpit_patch"]
    assert data["action_chips"] == envelope["action_chips"]

    # (3) The existing state_update workspace projection is untouched.
    assert final["event_type"] == "state_update"
    assert final["is_final"] is True
    assert data["reply"] == dispatch.fast_response.content
    assert "v92_dashboard" in data  # workspace projection preserved
    assert "turn_envelope" in data  # V9.2 envelope still present alongside V1.6


@pytest.mark.asyncio
async def test_mobile_triage_v16_fields_are_json_native_not_stringified() -> None:
    # The V1.6 fields are real arrays/objects, and the whole frame round-trips
    # through JSON — not stringified JSON blobs.
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="sifft", session_id="m-json", has_attachment=True),
        current_user=_user(),
    )
    request = SimpleNamespace(session_id="m-json", message="sifft")
    frames = [
        frame
        async for frame in _stream_fast_response(
            request=request,
            fast_response=dispatch.fast_response,
            event_builder=SSEEventBuilder(turn_id="turn-json"),
        )
    ]
    final = [_payload(frame) for frame in frames if frame.startswith("data: {")][0]
    data = final["data"]
    assert isinstance(data["action_chips"], list)
    assert isinstance(data["pocket_cockpit_patch"], dict)
    assert isinstance(data["assistant_turn_envelope"], dict)
    assert data["action_chips"] and isinstance(data["action_chips"][0], dict)
    # Round-trips through JSON unchanged (the frame is already valid JSON).
    assert json.loads(json.dumps(final)) == final


def test_future_v16_fields_must_be_additive_not_replacing_core_events() -> None:
    # ADDITIVE CONTRACT: a future V1.6 patch may carry an AssistantTurnEnvelope
    # (and pocket_cockpit_patch / action_chips) as OPTIONAL extra fields inside
    # the existing state_update — it must not remove or replace the delta /
    # state_update / done semantics existing clients depend on.
    builder = SSEEventBuilder(turn_id="turn-additive")

    # An envelope can ride inside a state_update without changing its type.
    state = builder.event(
        {
            "type": "state_update",
            "reply": "Final",
            "assistant_turn_envelope": {"pocket_cockpit_patch": {"next_step": "x"}},
            "action_chips": [{"label": "Ja"}],
        },
        event_type="state_update",
        is_final=True,
    )
    assert state["event_type"] == "state_update"
    assert state["is_final"] is True
    assert state["data"]["reply"] == "Final"  # existing core field preserved
    assert state["data"]["assistant_turn_envelope"]["pocket_cockpit_patch"]  # additive
    assert state["data"]["action_chips"]  # additive

    # The completion terminator is still its own event after the additive payload.
    done = builder.event({"type": "done"}, event_type="done")
    assert done["event_type"] == "done"
    assert done["is_final"] is False
    assert done["sequence"] == state["sequence"] + 1


# === Patch 11 — Backend-owned Pocket Cockpit for the governed RWDR P0 text ===
#
# The governed RWDR P0 text turn now emits an additive pocket_cockpit_patch (and
# display-only action_chips) inside the existing state_update, alongside the
# workspace projection. Non-RWDR governed/light turns are unaffected.

_P0_KILLER_INPUT = "RWDR 45x62x8, Getriebe, Öl, 1500 rpm, staubig, undicht."


async def _light_state_update(message: str) -> dict:
    """Final state_update event from the light/exploration runtime (offline:
    direct_reply short-circuits the LLM; session_id=None skips Redis)."""
    frames = [
        frame
        async for frame in _stream_light_runtime(
            message=message,
            request=SimpleNamespace(session_id=None, message=message),
            current_user=_user(),
            mode="EXPLORATION",
            governed_state_override=GovernedSessionState(),
            direct_reply="Hinweis zum Fall.",
            event_builder=SSEEventBuilder(turn_id="turn-light"),
            force_conversation_runtime=True,
        )
    ]
    for frame in frames:
        if not frame.startswith("data: {"):
            continue
        event = json.loads(frame.removeprefix("data: ").strip())
        if event.get("event_type") == "state_update":
            return event
    raise AssertionError("no state_update frame emitted")


@pytest.mark.asyncio
async def test_governed_rwdr_p0_text_state_update_includes_pocket_cockpit_patch() -> (
    None
):
    event = await _light_state_update(_P0_KILLER_INPUT)
    data = event["data"]

    # The backend-owned Pocket Cockpit is attached additively.
    patch = data["pocket_cockpit_patch"]
    assert any("RWDR-Leckage" in str(item.get("value")) for item in patch["recognized"])
    assert any(
        "Wellenlauffläche" in str(item.get("label")) for item in patch["critical"]
    )
    assert "Rille" in patch["next_step"]["question"]
    assert isinstance(data["action_chips"], list) and isinstance(
        data["action_chips"][0], dict
    )

    # The existing state_update workspace projection is untouched.
    assert event["event_type"] == "state_update"
    assert data["reply"]
    assert "v92_dashboard" in data  # workspace projection preserved
    assert "turn_envelope" in data  # V9.2 envelope still present alongside V1.6


@pytest.mark.asyncio
async def test_non_rwdr_governed_turn_has_no_pocket_cockpit_patch() -> None:
    # A non-RWDR turn must not receive a bogus RWDR pocket cockpit.
    event = await _light_state_update("Was ist FFKM?")
    assert "pocket_cockpit_patch" not in event["data"]
    assert "action_chips" not in event["data"]
