from app.agent.domain.case_delta import build_document_delta_event
from app.agent.domain.document_delta import document_delta_from_text
from app.agent.domain.risk_readiness import evaluate_readiness, evaluate_risks
from app.agent.state.models import GovernedSessionState
from app.domain.pre_gate_classification import PreGateClassification
from app.services.application_pattern_service import ApplicationPatternLibrary
from app.services.pre_gate_classifier import PreGateClassifier


def test_22_1_salzwasser_unscharf_starts_domain_case_without_overclaiming() -> None:
    route = PreGateClassifier().classify("Wir brauchen eine Dichtung fuer Salzwasser.")
    readiness = evaluate_readiness(
        {"medium": "Salzwasser", "asset_type": "Pumpe"},
        request_type="new_design",
        engineering_path="rwdr",
    )
    risks = evaluate_risks(
        {"medium": "Salzwasser", "asset_type": "Pumpe"}, engineering_path="rwdr"
    )

    assert route.classification is PreGateClassification.DOMAIN_INQUIRY
    assert readiness.readiness_level in {1, 2}
    assert any(risk.risk_name == "corrosion_risk" and risk.score >= 2 for risk in risks)


def test_22_2_ruehrwerk_pattern_marks_rotary_as_proposed_not_final() -> None:
    candidates = ApplicationPatternLibrary().match("Ruehrwerk mit Leckage an der Welle")

    assert candidates
    selected = candidates[0].pattern
    assert selected.canonical_name == "agitator_sealing"
    assert selected.auto_populated_fields["motion_type"].value == "rotary"
    assert selected.auto_populated_fields["motion_type"].confidence < 0.9
    assert "seal_location" in selected.required_clarification_fields


def test_22_3_ptfe_vs_fkm_stays_knowledge_query() -> None:
    route = PreGateClassifier().classify(
        "Was ist der Unterschied zwischen FKM und PTFE?"
    )

    assert route.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert route.escalate_to_graph is False


def test_22_3b_standalone_ptfe_limits_request_stays_knowledge_query() -> None:
    route = PreGateClassifier().classify("ich benötige die grenzwerte von PTFE")

    assert route.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert route.reasoning == "deterministic_material_limits_knowledge"
    assert route.escalate_to_graph is False


def test_22_3c_ptfe_limits_with_concrete_seal_context_stays_governed() -> None:
    route = PreGateClassifier().classify(
        "Ich benötige die Grenzwerte von PTFE für eine RWDR Dichtung mit Welle 40 mm."
    )

    assert route.classification is PreGateClassification.DOMAIN_INQUIRY
    assert route.escalate_to_graph is True


def test_22_4_pumpe_ethanol_high_temperature_pressure_flags_risk_without_rfq_ready() -> (
    None
):
    profile = {
        "asset_type": "Pumpe",
        "motion_type": "rotary",
        "medium": "Ethanol",
        "temperature_c": 150,
        "pressure_bar": 10,
        "shaft_diameter_mm": 50,
    }
    readiness = evaluate_readiness(
        profile, request_type="new_design", engineering_path="rwdr"
    )
    risks = evaluate_risks(profile, engineering_path="rwdr")

    assert readiness.readiness_level < 5
    assert readiness.rfq_possible is False
    assert any(
        risk.risk_name == "temperature_risk" and risk.score >= 3 for risk in risks
    )
    assert any(risk.risk_name == "pressure_risk" and risk.score >= 2 for risk in risks)


def test_22_5_getriebe_oel_pattern_keeps_medium_as_case_context() -> None:
    route = PreGateClassifier().classify(
        "Wir haben Leckage am Getriebe, Medium ist Oel."
    )
    candidates = ApplicationPatternLibrary().match("Leckage am Getriebe mit Oel")

    assert route.classification is PreGateClassification.DOMAIN_INQUIRY
    assert candidates
    assert candidates[0].pattern.canonical_name == "hydraulic_gearbox_standard"
    assert "temperature.max_c" in candidates[0].pattern.required_clarification_fields


def test_36_6_upload_zeichnung_creates_document_input_candidates_only() -> None:
    delta = document_delta_from_text(
        text="Zeichnung: Medium Salzwasser. Welle 42 mm. Temperatur max 80 degC. PTFE RWDR.",
        filename="zeichnung-rwdr.txt",
        tags=["drawing", "case-upload"],
    )
    event = build_document_delta_event(
        case_id="case-upload-1",
        document_id="doc-drawing-1",
        filename="zeichnung-rwdr.txt",
        delta=delta,
    )
    state = GovernedSessionState(case_events=[event])
    fields = {field.field_name: field for field in delta.fields}

    assert event.event_type == "document_delta_proposed"
    assert event.source_document_id == "doc-drawing-1"
    assert event.accepted_delta == {}
    assert event.rejected_delta == {}
    assert state.asserted.assertions == {}
    assert fields["medium"].proposed_value == "Salzwasser"
    assert fields["shaft_diameter_mm"].proposed_value == 42
    assert fields["temperature_max"].proposed_value == 80
    assert all(field.status == "proposed" for field in delta.fields)
    assert all(field.provenance == "documented" for field in delta.fields)
    assert all(field.confirmation_required is True for field in delta.fields)
