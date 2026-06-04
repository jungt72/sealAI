from app.agent.domain.delta_conflicts import detect_delta_conflicts


def test_detect_delta_conflicts_honors_tolerance() -> None:
    result = detect_delta_conflicts(
        current_case_state={"temperature_max": {"value": 80.0, "provenance": "user_stated"}},
        accepted_delta_candidate={"temperature_max": {"proposed_value": 80.4, "provenance": "documented"}},
        field_tolerances={"temperature_max": 0.5},
        provenance_priority={"user_stated": 10, "documented": 8},
    )

    assert result["conflicts"] == []
    assert result["conflict_severity"] == "none"


def test_detect_delta_conflicts_returns_resolution_question_when_lower_priority_replaces_value() -> None:
    result = detect_delta_conflicts(
        current_case_state={"temperature_max": {"value": 80, "provenance": "user_stated"}},
        accepted_delta_candidate={"temperature_max": {"proposed_value": 180, "provenance": "documented"}},
        field_tolerances={"temperature_max": 0.5},
        provenance_priority={"user_stated": 10, "documented": 8},
    )

    assert result["conflict_severity"] == "blocking"
    assert result["conflicts"][0]["conflict_type"] == "value_replacement"
    assert result["conflicts"][0]["resolution"] == "requires_user_resolution"
    assert "temperature_max" in result["suggested_resolution_question"]
