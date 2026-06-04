from app.agent.state.models import ObservedExtraction, ObservedState
from app.agent.state.reducers import reduce_observed_to_normalized


def test_reducer_uses_tolerance_aware_conflict_detection() -> None:
    state = ObservedState(
        raw_extractions=[
            ObservedExtraction(
                field_name="temperature_c", raw_value=80.0, confidence=0.8, turn_index=1
            ),
            ObservedExtraction(
                field_name="temperature_c",
                raw_value="80.4 C",
                confidence=0.9,
                turn_index=2,
            ),
        ]
    )

    normalized = reduce_observed_to_normalized(state)

    assert normalized.conflicts == []
    assert normalized.parameters["temperature_c"].value == 80.4
    assert normalized.parameters["temperature_c"].unit == "degC"


def test_reducer_reports_real_observed_conflict() -> None:
    state = ObservedState(
        raw_extractions=[
            ObservedExtraction(
                field_name="medium", raw_value="Oel", confidence=0.9, turn_index=1
            ),
            ObservedExtraction(
                field_name="medium", raw_value="Wasser", confidence=0.9, turn_index=2
            ),
        ]
    )

    normalized = reduce_observed_to_normalized(state)

    assert len(normalized.conflicts) == 1
    assert normalized.conflicts[0].field_name == "medium"
    assert normalized.conflicts[0].severity == "warning"
