import pytest

from app.agent.api.assembly import _assemble_governed_stream_payload, _build_governed_reply_context
from app.agent.domain.case_delta import (
    build_assistant_delta_event,
    build_case_delta_decision_event,
    latest_proposed_delta_event,
    proposed_case_delta_from_extractions,
    select_delta_fields,
)
from app.agent.graph import GraphState
from app.agent.state.models import GovernedSessionState, ObservedExtraction


def test_proposed_case_delta_uses_current_turn_extractions_only() -> None:
    delta = proposed_case_delta_from_extractions(
        [
            ObservedExtraction(field_name="medium", raw_value="Wasser", confidence=0.92, turn_index=1),
            ObservedExtraction(field_name="pressure_bar", raw_value=4, raw_unit="bar", confidence=0.75, turn_index=2),
            ObservedExtraction(field_name="unknown_internal", raw_value="x", confidence=1.0, turn_index=2),
        ],
        turn_index=2,
    )

    assert [field.field_name for field in delta.fields] == ["pressure_bar"]
    assert delta.fields[0].status == "proposed"
    assert delta.fields[0].confidence == "requires_confirmation"
    assert delta.fields[0].unit == "bar"
    assert delta.fields[0].engineering_value is not None
    assert delta.fields[0].engineering_value.unit == "bar"
    assert delta.fields[0].engineering_value.interpretation == "unknown"
    assert delta.fields[0].confirmation_required is True


def test_proposed_case_delta_allows_shared_critical_contract_fields() -> None:
    field_values = {
        "pressure_peak": (6, "barg"),
        "housing_bore": (62, "mm"),
        "housing_bore_mm": (62, None),
        "installation_width": (10, "mm"),
        "installation_width_mm": (10, None),
        "food_contact": (True, None),
        "atex_relevance": (False, None),
    }
    delta = proposed_case_delta_from_extractions(
        [
            ObservedExtraction(
                field_name=field_name,
                raw_value=raw_value,
                raw_unit=unit,
                confidence=0.92,
                turn_index=3,
            )
            for field_name, (raw_value, unit) in field_values.items()
        ],
        turn_index=3,
    )

    assert {field.field_name for field in delta.fields} == set(field_values)


def test_governed_stream_payload_exposes_structured_double_output() -> None:
    state = GraphState(
        output_reply="Ich habe 4 bar als Betriebsdruck verstanden.",
        output_response_class="structured_clarification",
        user_turn_index=3,
    )
    state = state.model_copy(
        update={
            "observed": state.observed.with_extraction(
                ObservedExtraction(
                    field_name="pressure_bar",
                    raw_value=4,
                    raw_unit="bar",
                    confidence=0.92,
                    turn_index=3,
                )
            )
        }
    )
    context = _build_governed_reply_context(
        result_state=state,
        persisted_state=GovernedSessionState(),
    )
    payload = _assemble_governed_stream_payload(
        context=context,
        visible_reply="Ich habe 4 bar als Betriebsdruck verstanden.",
    )

    assert payload["assistant_message"] == payload["reply"]
    assert payload["proposed_case_delta"]["schema_version"] == "case_delta_v0_4"
    assert payload["proposed_case_delta"]["fields"][0]["field_name"] == "pressure_bar"
    assert payload["proposed_case_delta"]["fields"][0]["status"] == "proposed"
    assert "case_state" not in payload["proposed_case_delta"]


def test_assistant_delta_case_event_is_append_only_non_authoritative() -> None:
    delta = proposed_case_delta_from_extractions(
        [ObservedExtraction(field_name="medium", raw_value="Salzwasser", confidence=0.92, turn_index=1)],
        turn_index=1,
    )
    event = build_assistant_delta_event(
        case_id="case-1",
        turn_index=1,
        assistant_message="Ich habe Salzwasser als Medium verstanden.",
        delta=delta,
    )

    assert event.event_type == "assistant_delta_proposed"
    assert event.actor_type == "assistant"
    assert event.source_turn_id == "turn-1"
    assert event.case_revision_after == event.case_revision_before + 1
    assert event.proposed_case_delta.fields[0].field_name == "medium"
    assert event.accepted_delta == {}
    assert event.rejected_delta == {}
    assert event.state_revision_after == event.state_revision_before + 1


def test_case_event_appends_to_governed_state_without_accepting_delta() -> None:
    from app.agent.api.utils import _with_case_event

    state = GovernedSessionState()
    delta = proposed_case_delta_from_extractions(
        [ObservedExtraction(field_name="medium", raw_value="Wasser", confidence=0.92, turn_index=1)],
        turn_index=1,
    )
    event = build_assistant_delta_event(
        case_id="case-1",
        turn_index=1,
        assistant_message="Ich habe Wasser als Medium verstanden.",
        delta=delta,
    )

    updated = _with_case_event(state, event=event)

    assert state.case_events == []
    assert len(updated.case_events) == 1
    assert updated.case_events[0].proposed_case_delta.fields[0].status == "proposed"
    assert updated.asserted.assertions == {}


def test_case_delta_decision_event_records_accepted_fields_without_source_mutation() -> None:
    delta = proposed_case_delta_from_extractions(
        [
            ObservedExtraction(field_name="pressure_bar", raw_value=4, raw_unit="barg", confidence=0.92, turn_index=1),
            ObservedExtraction(field_name="medium", raw_value="Wasser", confidence=0.91, turn_index=1),
        ],
        turn_index=1,
    )
    proposal = build_assistant_delta_event(
        case_id="case-1",
        turn_index=1,
        assistant_message="Ich habe Medium und Druck verstanden.",
        delta=delta,
    )
    state = GovernedSessionState(case_events=[proposal])

    latest = latest_proposed_delta_event(state)
    assert latest is proposal
    selected = select_delta_fields(latest.proposed_case_delta, field_names=["pressure_bar"])
    event = build_case_delta_decision_event(
        case_id="case-1",
        action="accept",
        fields=selected,
        source_event_id=proposal.event_id,
    )

    assert proposal.proposed_case_delta.fields[0].status == "proposed"
    assert event.event_type == "case_delta_accepted"
    assert event.actor_type == "user"
    assert event.source_turn_id == proposal.event_id
    assert list(event.accepted_delta) == ["pressure_bar"]
    assert event.accepted_delta["pressure_bar"]["status"] == "accepted"
    assert event.accepted_delta["pressure_bar"]["source_event_id"] == proposal.event_id
    assert event.accepted_delta["pressure_bar"]["engineering_value"]["unit"] == "bar"
    assert event.accepted_delta["pressure_bar"]["engineering_value"]["interpretation"] == "gauge"
    assert event.rejected_delta == {}


def test_case_delta_decision_event_rejects_unknown_pressure_acceptance() -> None:
    delta = proposed_case_delta_from_extractions(
        [
            ObservedExtraction(
                field_name="pressure_bar",
                raw_value=4,
                raw_unit="bar",
                confidence=0.92,
                turn_index=1,
            )
        ],
        turn_index=1,
    )
    selected = select_delta_fields(delta)

    with pytest.raises(ValueError, match="pressure_bar cannot be accepted"):
        build_case_delta_decision_event(
            case_id="case-1",
            action="accept",
            fields=selected,
            source_event_id="source-1",
        )


def test_case_delta_decision_event_records_rejected_fields() -> None:
    delta = proposed_case_delta_from_extractions(
        [ObservedExtraction(field_name="medium", raw_value="Wasser", confidence=0.92, turn_index=1)],
        turn_index=1,
    )
    selected = select_delta_fields(delta)

    event = build_case_delta_decision_event(
        case_id="case-1",
        action="reject",
        fields=selected,
        source_event_id="source-1",
    )

    assert event.event_type == "case_delta_rejected"
    assert event.accepted_delta == {}
    assert event.rejected_delta["medium"]["status"] == "rejected"
