from app.agent.domain.dependency_graph import (
    dependent_derived_value_ids,
    mark_stale_derived_values,
    mark_stale_snapshot_derived_values,
)
from app.agent.state.models import DerivedState, DerivedValue


def test_dependency_graph_expands_aliases_and_transitive_dependents() -> None:
    impacted = dependent_derived_value_ids(["pressure_bar"])

    assert "pv_load" in impacted
    assert "rwdr_pv_precheck" in impacted
    assert "readiness_level" not in impacted


def test_dependency_graph_treats_rpm_as_speed_alias() -> None:
    impacted = dependent_derived_value_ids(["rpm"])

    assert "circumferential_speed" in impacted
    assert "pv_load" in impacted


def test_dependency_graph_treats_pressure_peak_as_pv_input() -> None:
    impacted = dependent_derived_value_ids(["pressure_peak"])

    assert "pv_load" in impacted


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
    assert (
        updated.derived_values["rwdr_pv_precheck"].stale_reason
        == "accepted_case_delta_changed_inputs"
    )
    assert "rwdr_pv_precheck" in updated.stale_derived_value_ids
    assert updated.field_status["rwdr_pv_precheck"] == "stale"
    assert updated.derived_values["material_direction"].status == "stale"


def test_snapshot_stale_marking_handles_plain_durable_state_dict() -> None:
    state_json = {
        "derived": {
            "derived_values": {
                "circumferential_speed": {
                    "value": 3.14,
                    "status": "valid",
                    "derived_from_fields": ["shaft_diameter_mm", "speed_rpm"],
                    "derived_from_revision": 2,
                    "calculation_id": "circumferential_speed",
                },
                "pv_load": {
                    "value": 0.63,
                    "status": "valid",
                    "derived_from_fields": [
                        "pressure_nominal",
                        "circumferential_speed",
                    ],
                    "derived_from_revision": 2,
                    "calculation_id": "pv_load",
                },
            },
            "field_status": {
                "circumferential_speed": "valid",
                "pv_load": "valid",
            },
            "stale_derived_value_ids": [],
        }
    }

    updated = mark_stale_snapshot_derived_values(
        state_json,
        changed_fields=["shaft_diameter_mm"],
        new_revision=3,
        reason="accepted_case_delta_changed_inputs",
    )

    assert (
        state_json["derived"]["derived_values"]["circumferential_speed"]["status"]
        == "valid"
    )
    assert (
        updated["derived"]["derived_values"]["circumferential_speed"]["status"]
        == "stale"
    )
    assert (
        updated["derived"]["derived_values"]["circumferential_speed"]["value"] == 3.14
    )
    assert updated["derived"]["derived_values"]["pv_load"]["status"] == "stale"
    assert updated["derived"]["field_status"]["pv_load"] == "stale"
    assert updated["derived"]["stale_derived_value_ids"] == [
        "circumferential_speed",
        "pv_load",
        "rwdr_pv_precheck",
        "rwdr_dn_value",
        "rwdr_circumferential_speed",
    ]


def test_snapshot_stale_marking_updates_existing_top_level_derived_values() -> None:
    state_json = {
        "derived_values": {
            "circumferential_speed": {
                "value": 3.14,
                "status": "valid",
                "derived_from_fields": ["shaft_diameter_mm", "speed_rpm"],
                "derived_from_revision": 2,
                "calculation_id": "circumferential_speed",
            }
        },
        "field_status": {"circumferential_speed": "valid"},
        "stale_derived_value_ids": [],
    }

    updated = mark_stale_snapshot_derived_values(
        state_json,
        changed_fields=["speed_rpm"],
        new_revision=3,
        reason="accepted_case_delta_changed_inputs",
    )

    assert state_json["derived_values"]["circumferential_speed"]["status"] == "valid"
    assert updated["derived_values"]["circumferential_speed"]["status"] == "stale"
    assert updated["derived_values"]["circumferential_speed"]["value"] == 3.14
    assert updated["field_status"]["circumferential_speed"] == "stale"
    assert updated["stale_derived_value_ids"] == ["circumferential_speed"]
    assert "derived" not in updated
