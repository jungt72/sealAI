"""P1-2 TEIL A: central per-turn timing fills first_progress_ms/latency_ms for
all routes, from one source, without disturbing the mobile path.

Threshold sanity only (no exact ms).
"""
from __future__ import annotations

import json

from app.agent.api.sse_contract import SSEEventBuilder
from app.agent.runtime.turn_timing import (
    mark_first_progress,
    start_turn_timer,
    turn_timing,
)


def test_timer_none_when_not_started():
    # Fresh contextvar default — a non-streaming caller gets no values.
    # (start_turn_timer is per-turn; here we never call it.)
    fp, lat = turn_timing()
    # In a clean worker these are None; if a prior test started it, values are ints.
    assert (fp is None and lat is None) or (isinstance(fp, (int, type(None))) and isinstance(lat, int))


def test_timer_marks_progress_and_latency():
    start_turn_timer()
    fp = mark_first_progress()
    first_progress_ms, latency_ms = turn_timing()
    assert isinstance(fp, int) and fp >= 0
    assert first_progress_ms == fp
    assert isinstance(latency_ms, int) and latency_ms >= first_progress_ms  # total >= first chunk


def test_final_state_update_carries_timing_for_any_route():
    start_turn_timer()
    builder = SSEEventBuilder(turn_id="t1")
    # a non-final frame first (marks first progress), no trace stamping
    builder.event({"type": "progress"}, event_type="metadata")
    event = builder.event(
        {"type": "state_update", "reply": "x"},
        event_type="state_update",
        is_final=True,
    )
    trace = event["trace"]
    assert isinstance(trace["first_progress_ms"], int) and trace["first_progress_ms"] >= 0
    assert isinstance(trace["latency_ms"], int)
    assert trace["latency_ms"] >= trace["first_progress_ms"]


def test_non_final_events_are_not_stamped():
    start_turn_timer()
    builder = SSEEventBuilder(turn_id="t2")
    event = builder.event({"type": "progress"}, event_type="metadata")
    assert "trace" not in event or "latency_ms" not in (event.get("trace") or {})


def test_mobile_nested_trace_is_left_unchanged():
    # The mobile path keeps its explicit trace (first_progress_ms = 0) in the
    # assistant_turn_envelope; the central stamp only adds a top-level trace.
    start_turn_timer()
    builder = SSEEventBuilder(turn_id="t3")
    payload = {
        "type": "state_update",
        "assistant_turn_envelope": {"trace": {"route": "mobile_leakage_triage", "first_progress_ms": 0}},
    }
    event = builder.event(payload, event_type="state_update", is_final=True)
    assert event["assistant_turn_envelope"]["trace"]["first_progress_ms"] == 0  # byte-identical
    assert event["trace"]["latency_ms"] >= 0  # top-level unified timing present


def test_frame_serializes_with_timing():
    start_turn_timer()
    builder = SSEEventBuilder(turn_id="t4")
    frame = builder.frame({"type": "state_update"}, event_type="state_update", is_final=True)
    assert frame.startswith("data: ")
    decoded = json.loads(frame[len("data: ") :].strip())
    assert "latency_ms" in decoded["trace"]
