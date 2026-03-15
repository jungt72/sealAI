from __future__ import annotations

from app.agent.deterministic_foundation import (
    build_calculation_foundation,
    build_engineering_signal_foundation,
)


def test_calculation_foundation_produces_expected_structured_outputs():
    sealing_state = {
        "asserted": {
            "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
            "machine_profile": {"material": "PTFE"},
            "medium_profile": {"name": "Wasser"},
        }
    }
    working_profile = {
        "diameter": 50.0,
        "speed": 1500.0,
        "pressure": 10.0,
        "material": "PTFE",
    }
    rwdr_state = {
        "derived": {
            "surface_speed_mps": 3.927,
            "confidence_score": 0.92,
        }
    }

    calculations = build_calculation_foundation(sealing_state, working_profile, rwdr_state)

    assert calculations["surface_speed_mps"]["value"] == 3.927
    assert calculations["surface_speed_mps"]["formula_id"] == "surface_speed_from_diameter_and_rpm_v1"
    assert calculations["pv_value_bar_mps"]["value"] == 39.27
    assert calculations["rwdr_surface_speed_mps"]["value"] == 3.927
    assert calculations["rwdr_confidence_score"]["value"] == 0.92


def test_engineering_signal_foundation_produces_expected_structured_outputs():
    sealing_state = {
        "asserted": {
            "operating_conditions": {"pressure": 250.0},
            "machine_profile": {"material": "PTFE"},
        },
        "governance": {
            "conflicts": [{"severity": "CRITICAL"}],
            "unknowns_release_blocking": ["shaft_diameter_unresolved"],
        },
        "selection": {
            "output_blocked": True,
        },
    }
    working_profile = {
        "diameter": 50.0,
        "speed": 1500.0,
        "pressure": 250.0,
        "material": "PTFE",
    }
    rwdr_state = {
        "derived": {
            "pressure_risk_level": "high",
            "surface_speed_class": "high",
            "review_due_to_water_pressure": True,
        }
    }
    derived = build_calculation_foundation(sealing_state, working_profile, rwdr_state)

    signals = build_engineering_signal_foundation(sealing_state, working_profile, rwdr_state, derived)

    assert "material_risk_warning" in signals
    assert signals["governance_conflicts_present"]["value"] == 1
    assert signals["release_blocking_unknowns_present"]["value"] == 1
    assert signals["selection_output_blocked"]["value"] is True
    assert signals["rwdr_pressure_risk_level"]["value"] == "high"
    assert signals["rwdr_review_due_to_water_pressure"]["value"] is True
