from __future__ import annotations

import pytest

from app.agent.state.models import (
    GovernedSessionState,
    ObservedExtraction,
    ObservedState,
)
from app.agent.state.projections import project_for_ui
from app.agent.state.reducers import (
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)
from app.agent.v92.calculation_projection import calculation_ledger_derivations
from app.agent.v92.orchestrator import build_calculation_state


def _observed_case() -> ObservedState:
    observed = ObservedState()
    for field_name, raw_value, raw_unit in (
        ("sealing_type", "rwdr", None),
        ("shaft_diameter_mm", 50.0, "mm"),
        ("speed_rpm", 3000.0, "rpm"),
        ("temperature_c", 80.0, "°C"),
        ("material", "PTFE", None),
        ("medium", "Öl", None),
        ("pressure_bar", 5.0, "bar"),
    ):
        observed = observed.with_extraction(
            ObservedExtraction(
                field_name=field_name,
                raw_value=raw_value,
                raw_unit=raw_unit,
                confidence=1.0,
                turn_index=1,
            )
        )
    return observed


def test_user_stated_rwdr_inputs_reach_asserted_state_and_calculation_ledger() -> None:
    observed = _observed_case()
    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)

    assert asserted.assertions["shaft_diameter_mm"].asserted_value == 50.0
    assert asserted.assertions["speed_rpm"].asserted_value == 3000.0
    assert asserted.assertions["temperature_c"].asserted_value == 80.0
    assert asserted.assertions["sealing_type"].asserted_value == "rwdr"
    assert "pressure_bar" not in asserted.assertions
    assert "ambiguous_pressure_bar" in asserted.blocking_unknowns

    state = GovernedSessionState(
        observed=observed,
        normalized=normalized,
        asserted=asserted,
    )
    calculation = build_calculation_state(state)
    surface_speed = next(
        result
        for result in calculation.results
        if result.calculation_id == "rwdr.surface_speed"
    )

    assert surface_speed.status == "ok"
    assert surface_speed.outputs["v_surface_m_s"] == pytest.approx(7.854)

    projected_state = state.model_copy(update={"calculation": calculation})
    compute_items = project_for_ui(projected_state).compute.items
    assert any(item.calc_type == "rwdr" for item in compute_items)
    assert any(item.v_surface_m_s == pytest.approx(7.854) for item in compute_items)


def test_persisted_calculation_ledger_projects_legacy_rwdr_derivation_shape() -> None:
    observed = _observed_case()
    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)
    state = GovernedSessionState(
        observed=observed,
        normalized=normalized,
        asserted=asserted,
    )

    derivations = calculation_ledger_derivations(build_calculation_state(state))

    assert derivations[0]["calc_type"] == "rwdr"
    assert derivations[0]["v_surface_m_s"] == pytest.approx(7.854)
    assert derivations[0]["status"] == "ok"
