from app.agent.domain.case_delta import build_document_delta_event, latest_proposed_delta_event
from app.agent.domain.document_delta import document_delta_from_text
from app.agent.state.models import GovernedSessionState


def test_document_delta_extracts_technical_fields_as_non_authoritative_proposal() -> None:
    delta = document_delta_from_text(
        text="Medium Oel. Betriebsdruck 4 bar. Temperatur max 80 degC. Drehzahl 1500 rpm. Welle 30 mm. PTFE RWDR.",
        filename="rwdr-datenblatt.txt",
        tags=["medium=Oel"],
    )

    fields = {field.field_name: field for field in delta.fields}

    assert delta.source == "document"
    assert fields["medium"].proposed_value == "Oel"
    assert fields["pressure_bar"].proposed_value == 4
    assert fields["pressure_bar"].unit == "bar"
    assert fields["temperature_max"].proposed_value == 80
    assert fields["speed_rpm"].proposed_value == 1500
    assert fields["shaft_diameter_mm"].proposed_value == 30
    assert fields["material"].proposed_value == "PTFE"
    assert fields["sealing_type"].proposed_value == "rwdr"
    assert all(field.status == "proposed" for field in delta.fields)
    assert all(field.provenance == "documented" for field in delta.fields)


def test_document_delta_event_is_latest_reviewable_case_delta() -> None:
    delta = document_delta_from_text(text="Druck 7 bar, Medium Wasser")
    event = build_document_delta_event(
        case_id="case-1",
        document_id="doc-1",
        filename="case.txt",
        delta=delta,
    )
    state = GovernedSessionState(case_events=[event])

    latest = latest_proposed_delta_event(state)

    assert event.event_type == "document_delta_proposed"
    assert latest is event
    assert latest.proposed_case_delta.source == "document"
    assert latest.accepted_delta == {}
    assert latest.rejected_delta == {}
    assert state.asserted.assertions == {}

from app.agent.domain.delta_conflicts import build_governed_conflict_summary
from app.agent.state.models import NormalizedParameter, NormalizedState
from app.api.v1.projections.case_workspace import project_case_workspace_from_governed_state


def test_document_delta_conflict_is_projected_until_delta_decision() -> None:
    delta = document_delta_from_text(text="Medium Oel, Druck 7 bar")
    event = build_document_delta_event(
        case_id="case-1",
        document_id="doc-1",
        filename="case.txt",
        delta=delta,
    )
    state = GovernedSessionState(
        normalized=NormalizedState(
            parameters={
                "medium": NormalizedParameter(
                    field_name="medium",
                    value="Wasser",
                    confidence="confirmed",
                    source="user_override",
                ),
                "pressure_bar": NormalizedParameter(
                    field_name="pressure_bar",
                    value=4,
                    unit="bar",
                    confidence="confirmed",
                    source="user_override",
                ),
            }
        ),
        case_events=[event],
    )

    summary = build_governed_conflict_summary(state)
    projection = project_case_workspace_from_governed_state(state, chat_id="case-1")

    assert summary["open"] == 2
    assert summary["by_severity"]["blocking"] == 2
    assert {item["field_name"] for item in summary["items"]} == {"medium", "pressure_bar"}
    assert projection.conflicts.open == 2
    assert projection.conflicts.items[0]["conflict_type"] == "DELTA_SOURCE_CONFLICT"
    assert projection.rfq_package.conflicts_visible_count == 2
