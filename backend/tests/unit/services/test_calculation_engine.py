from app.services.calculation_engine import CascadingCalculationEngine


def test_ptfe_rwdr_cascade_runs_follow_on_calculations() -> None:
    state, records = CascadingCalculationEngine().execute_cascade({
        "engineering_path": "rwdr",
        "sealing_material_family": "ptfe_glass_filled",
        "shaft": {"diameter_mm": 50},
        "operating": {"shaft_speed": {"rpm_nom": 1500}, "temperature": {"max_c": 120, "nom_c": 80}, "pressure": {"max_bar": 5}},
        "rwdr": {"lip": {"radial_force_n_per_mm": 2, "contact_width_mm": 0.5}, "extrusion_gap_mm": 0.1},
        "expected_service_duration_years": 2,
    })
    assert state["derived"]["surface_speed_ms"] > 0
    assert state["derived"]["pv_loading"] > 0
    assert state["derived"]["temperature_headroom_c"] == 140.0
    assert {record.calc_id for record in records} >= {"ptfe_rwdr.circumferential_speed", "ptfe_rwdr.pv_loading"}
