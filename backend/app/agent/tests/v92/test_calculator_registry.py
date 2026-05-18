from __future__ import annotations

import pytest

from app.agent.v92.calculator_registry import get_calculator_registry


def test_surface_speed_calculator_returns_screening_result_with_hashes() -> None:
    registry = get_calculator_registry()

    result = registry.calculate(
        "surface_speed_from_rpm_and_diameter",
        inputs={"shaft_diameter_mm": 50, "speed_rpm": 3000},
        case_revision=7,
    )

    assert result.calculation_id == "rwdr.surface_speed"
    assert result.calculator == "surface_speed_from_rpm_and_diameter"
    assert result.outputs["v_surface_m_s"] == pytest.approx(7.854, rel=1e-3)
    assert result.units == {"v_surface_m_s": "m/s"}
    assert result.claim_level == "L3_deterministic_calculation"
    assert result.validity_status == "valid_for_screening"
    assert result.input_snapshot_hash
    assert result.output_snapshot_hash
    assert "Freigabe" not in " ".join(result.notes)


def test_surface_speed_calculator_reports_missing_inputs_without_guessing() -> None:
    registry = get_calculator_registry()

    result = registry.calculate(
        "surface_speed_from_rpm_and_diameter",
        inputs={"shaft_diameter_mm": 50},
    )

    assert result.status == "insufficient_data"
    assert result.validity_status == "input_missing"
    assert result.outputs == {}
    assert result.missing_inputs == ["speed_rpm"]
    assert result.output_snapshot_hash == ""


def test_calculator_registry_maps_changed_fields_to_stale_dependencies() -> None:
    registry = get_calculator_registry()

    assert registry.affected_calculator_ids_for_fields(["speed_rpm"]) == [
        "surface_speed_from_rpm_and_diameter"
    ]
    assert registry.affected_calculator_ids_for_fields(["medium"]) == [
        "material_family_counterindication_check"
    ]


def test_temperature_window_screening_uses_existing_material_limits_without_release_claim() -> None:
    registry = get_calculator_registry()

    result = registry.calculate(
        "temperature_window_screening",
        inputs={"material": "FKM", "temperature_c": 80, "pressure_bar": 10},
        case_revision=5,
    )

    assert result.calculation_id == "material.temperature_window_screening"
    assert result.outputs["material"] == "FKM"
    assert result.outputs["temp_ok"] is True
    assert result.validity_status == "valid_for_screening"
    assert "compound" in result.limitations[0].casefold()


def test_material_counterindication_flags_epdm_in_hydraulic_oil_as_review_required() -> None:
    registry = get_calculator_registry()

    result = registry.calculate(
        "material_family_counterindication_check",
        inputs={"material": "EPDM", "medium": "HLP"},
    )

    assert result.calculation_id == "material.chemical_resistance_screening"
    assert result.outputs["rating"] == "C"
    assert result.status == "warning"
    assert result.validity_status == "requires_expert_review"
    assert "counterindication_rating_c" in result.guardrail_violations
