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
