from app.services.conflict_detection_service import (
    ConflictCandidate,
    ConflictDetectionService,
)


def test_candidate_conflict_uses_provenance_priority_and_question() -> None:
    result = ConflictDetectionService().detect(
        {"medium": {"value": "Oel", "provenance": "confirmed"}},
        [ConflictCandidate(field_name="medium", value="Wasser", provenance="inferred")],
    )

    assert result.conflict_severity == "blocking"
    assert result.suggested_resolution_question
    assert result.conflicts[0].field_name == "medium"
    assert result.conflicts[0].current_value == "Oel"
    assert result.conflicts[0].candidate_value == "Wasser"


def test_numeric_values_inside_field_tolerance_do_not_conflict() -> None:
    result = ConflictDetectionService().detect(
        {"temperature_c": {"value": 80.0, "provenance": "documented"}},
        [ConflictCandidate(field_name="temperature_c", value="80.4 C", provenance="user_stated")],
    )

    assert result.has_conflicts is False
    assert result.conflict_severity == "none"


def test_observed_candidates_detect_warning_for_different_values() -> None:
    result = ConflictDetectionService().detect_observed_candidates(
        "pressure_bar",
        [
            ConflictCandidate(field_name="pressure_bar", value=4.0, provenance="llm", source_turn_index=1),
            ConflictCandidate(field_name="pressure_bar", value=6.0, provenance="llm", source_turn_index=2),
        ],
    )

    assert result.conflict_severity == "warning"
    assert result.conflicts[0].severity == "warning"
