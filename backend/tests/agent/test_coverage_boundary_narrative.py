from app.agent.api.models import VisibleCaseNarrativeResponse
from app.agent.case_state import _build_visible_coverage_scope, build_visible_case_narrative


def test_coverage_scope_empty_without_policy_context():
    result = build_visible_case_narrative(state={"messages": [], "sealing_state": {}, "working_profile": {}}, case_state={"case_meta": {"binding_level": "ORIENTATION"}}, binding_level="ORIENTATION", policy_context=None)
    assert result["coverage_scope"] == []


def test_partial_coverage_produces_medium_boundary_and_prefixed_summary():
    result = build_visible_case_narrative(
        state={"messages": [], "sealing_state": {}, "working_profile": {}},
        case_state={"case_meta": {"binding_level": "ORIENTATION"}},
        binding_level="ORIENTATION",
        policy_context={"coverage_status": "partial", "boundary_flags": ["orientation_only"], "escalation_reason": None, "required_fields": []},
    )
    assert result["coverage_scope"][0]["severity"] == "medium"
    assert result["governed_summary"].startswith("[Teilweise abgedeckt]")


def test_out_of_scope_produces_high_severity_boundary():
    items = _build_visible_coverage_scope({"coverage_status": "out_of_scope", "boundary_flags": [], "escalation_reason": None, "required_fields": []})
    assert items[0]["severity"] == "high"


def test_visible_case_narrative_response_accepts_coverage_scope():
    response = VisibleCaseNarrativeResponse(governed_summary="summary", coverage_scope=[{"key": "coverage_boundary", "label": "Coverage", "value": "partial", "detail": None, "severity": "medium"}])
    assert response.coverage_scope[0].key == "coverage_boundary"
