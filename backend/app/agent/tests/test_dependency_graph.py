from app.agent.domain.dependency_graph import (
    dependent_derived_value_ids,
    mark_stale_derived_values,
)
from app.agent.state.models import DerivedState, DerivedValue


def test_dependency_graph_expands_aliases_and_transitive_dependents() -> None:
    impacted = dependent_derived_value_ids(["pressure_bar"])

    assert "pv_load" in impacted
    assert "rwdr_pv_precheck" in impacted
    assert "readiness_level" not in impacted


def test_mark_stale_derived_values_preserves_values_and_marks_metadata() -> None:
    derived = DerivedState(
        derived_values={
            "rwdr_pv_precheck": DerivedValue(
                value=0.42,
                status="valid",
                derived_from_fields=["pressure_bar", "shaft_diameter_mm", "speed_rpm"],
                derived_from_revision=3,
                calculation_id="rwdr_pv_precheck",
            ),
            "material_direction": DerivedValue(
                value="PTFE Richtung",
                status="valid",
                derived_from_fields=["medium", "temperature_c"],
                derived_from_revision=3,
                calculation_id="material_direction",
            ),
        }
    )

    updated = mark_stale_derived_values(
        derived,
        changed_fields=["pressure_bar"],
        new_revision=4,
        reason="accepted_case_delta_changed_inputs",
    )

    assert updated.derived_values["rwdr_pv_precheck"].value == 0.42
    assert updated.derived_values["rwdr_pv_precheck"].status == "stale"
    assert updated.derived_values["rwdr_pv_precheck"].stale_reason == "accepted_case_delta_changed_inputs"
    assert "rwdr_pv_precheck" in updated.stale_derived_value_ids
    assert updated.field_status["rwdr_pv_precheck"] == "stale"
    assert updated.derived_values["material_direction"].status == "stale"
