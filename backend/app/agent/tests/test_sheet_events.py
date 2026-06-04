"""Patch 8 tests — Sheet-Chat contract (Blueprint §9, §29.5, §12.6, §32.11).

Covers the four sheet events through the shared State Gate, client_event_id
idempotency, case_revision_seen stale degradation (warning, not block), and
relevance-gated chat output.
"""

from __future__ import annotations

from app.agent.communication.sheet_events import (
    SheetEvent,
    SheetFieldValue,
    apply_sheet_event,
)
from app.agent.state.models import GovernedSessionState


def _event(event_type: str, fields: list[tuple], **kwargs) -> SheetEvent:
    return SheetEvent(
        event_type=event_type,  # type: ignore[arg-type]
        fields=[SheetFieldValue(field_name=f, value=v, unit=u) for (f, v, u) in fields],
        **kwargs,
    )


# --- The four events run through the State Gate (§9.4) ----------------------


def test_sheet_field_edit_mutates_via_state_gate_with_provenance() -> None:
    result = apply_sheet_event(
        GovernedSessionState(),
        _event("sheet_field_edit", [("temperature_c", 90, "°C")], client_event_id="e1"),
    )
    assert result.applied is True
    param = result.state.normalized.parameters["temperature_c"]
    assert param.value == 90
    assert param.provenance == "sheet_field_edit"
    # Temperature is liability-bearing → chat is relevant (§9.5).
    assert result.chat_relevant is True


def test_sheet_bulk_input_applies_all_fields() -> None:
    result = apply_sheet_event(
        GovernedSessionState(),
        _event(
            "sheet_bulk_input",
            [("speed_rpm", 3000, None), ("temperature_c", 90, "°C"), ("medium", "Öl", None)],
            client_event_id="bulk1",
        ),
    )
    params = result.state.normalized.parameters
    assert params["speed_rpm"].value == 3000
    assert params["temperature_c"].value == 90
    assert "medium" in params
    assert params["speed_rpm"].provenance == "sheet_bulk_input"
    assert result.chat_relevant is True


def test_sheet_conflict_resolution_applies_and_is_relevant() -> None:
    result = apply_sheet_event(
        GovernedSessionState(),
        _event(
            "sheet_conflict_resolution",
            [("temperature_c", 190, "°C")],
            client_event_id="res1",
        ),
    )
    assert result.state.normalized.parameters["temperature_c"].value == 190
    assert result.chat_relevant is True


def test_sheet_to_rfq_requests_rfq_without_mutating() -> None:
    state = GovernedSessionState()
    result = apply_sheet_event(state, _event("sheet_to_rfq", [], client_event_id="rfq1"))
    assert result.rfq_requested is True
    assert result.applied is False
    assert result.state is state  # no mutation here (RFQ generation is Patch 9)
    assert result.chat_relevant is True


# --- (a) Idempotency via client_event_id (§9 / §13.4) -----------------------


def test_same_client_event_id_does_not_mutate_twice() -> None:
    seen: set[str] = set()
    event = _event("sheet_field_edit", [("speed_rpm", 1500, None)], client_event_id="dup")

    first = apply_sheet_event(GovernedSessionState(), event, seen_event_ids=seen)
    assert first.applied is True
    assert first.already_applied is False
    assert "dup" in seen

    second = apply_sheet_event(first.state, event, seen_event_ids=seen)
    assert second.applied is False
    assert second.already_applied is True
    # No re-processing: state is returned unchanged on the duplicate.
    assert second.state is first.state


# --- (b) Stale case_revision_seen degrades, does not block (§12.6) ----------


def test_stale_case_revision_degrades_to_warning_not_block() -> None:
    # current revision derives from user_turn_index when no markers exist.
    state = GovernedSessionState(user_turn_index=5)
    result = apply_sheet_event(
        state,
        _event(
            "sheet_field_edit",
            [("temperature_c", 120, "°C")],
            client_event_id="stale1",
            case_revision_seen=2,  # older than current (5)
        ),
    )
    assert result.stale is True
    # The field is still applied (case stays usable, not blocked).
    assert result.state.normalized.parameters["temperature_c"].value == 120
    # The stale write surfaces as a field-level warning conflict.
    warnings = [c for c in result.conflicts if c["severity"] == "warning"]
    assert warnings, "expected a stale warning conflict"
    assert any(c["field_name"] == "temperature_c" for c in warnings)


def test_stale_write_keeps_other_fields_usable() -> None:
    state = GovernedSessionState(user_turn_index=5)
    result = apply_sheet_event(
        state,
        _event(
            "sheet_bulk_input",
            [("temperature_c", 120, "°C"), ("speed_rpm", 2000, None)],
            case_revision_seen=1,
        ),
    )
    # Both fields applied despite the stale flag — no global case block.
    assert result.state.normalized.parameters["temperature_c"].value == 120
    assert result.state.normalized.parameters["speed_rpm"].value == 2000


# --- (c) Irrelevant edit produces no chat output (§32.11 / §9.6) ------------


def test_irrelevant_field_edit_is_silent() -> None:
    result = apply_sheet_event(
        GovernedSessionState(),
        _event("sheet_field_edit", [("operator_note", "Schichtnotiz", None)], client_event_id="note1"),
    )
    assert result.applied is True
    # Non-critical, no conflict → cockpit updates but chat stays silent.
    assert result.chat_relevant is False
