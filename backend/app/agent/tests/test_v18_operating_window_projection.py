"""V1.8 §5.6 Operating-Window projection from the governed case state (P2-L2).

Maps asserted requirement claims (+ the deterministic circumference speed) and
the chosen SolutionProfile onto the deterministic OperatingWindow.
"""

from __future__ import annotations

from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernedSessionState,
    SolutionField,
    SolutionProfile,
)
from app.agent.state.operating_window import project_operating_window


def _claim(field: str, value: object, status: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, status=status)


def _state(assertions=None, solutions=None) -> GovernedSessionState:
    return GovernedSessionState(
        asserted=AssertedState(assertions=assertions or {}),
        solution_profiles=solutions or [],
    )


def _sol(
    solution_id: str = "sol1", state: str = "selected", **limits: object
) -> SolutionProfile:
    return SolutionProfile(
        solution_id=solution_id,
        state=state,
        fields=[
            SolutionField(
                field=k,
                value=v,
                origin="datasheet_extracted",
                source_doc="d",
                source_page=1,
            )
            for k, v in limits.items()
        ],
    )


def _row(ow, field):
    return next(r for r in ow.rows if r.field == field)


def test_projection_maps_assertions_and_computed_speed() -> None:
    state = _state(
        assertions={
            "temperature_max_c": _claim("temperature_max_c", 120),
            "pressure_at_seal_bar": _claim("pressure_at_seal_bar", 0.3),
        },
        solutions=[_sol(temp_max_continuous_c=150, p_max_bar=0.5, v_max_m_s=12.0)],
    )
    ow = project_operating_window(
        state, compute_results=[{"calc_type": "rwdr", "v_surface_m_s": 8.0}]
    )
    assert _row(ow, "temp_max_continuous_c").flag == "ok"
    assert _row(ow, "p_max_bar").flag == "ok"
    assert _row(ow, "v_max_m_s").flag == "ok"  # calculated, within limit
    # limits absent on the datasheet stay visible as manufacturer questions
    assert _row(ow, "temp_min_continuous_c").flag == "limit_unknown"
    assert _row(ow, "dry_run_capable").flag == "limit_unknown"


def test_temperature_alias_falls_back_to_temperature_c() -> None:
    state = _state(
        assertions={"temperature_c": _claim("temperature_c", 120)},
        solutions=[_sol(temp_max_continuous_c=150)],
    )
    row = _row(project_operating_window(state), "temp_max_continuous_c")
    assert row.requirement_value == 120
    assert row.flag == "ok"


def test_compute_results_read_from_graphstate_when_not_passed() -> None:
    from app.agent.graph import GraphState  # noqa: PLC0415

    gs = GraphState(
        asserted=AssertedState(assertions={}),
        solution_profiles=[_sol(v_max_m_s=12.0)],
        compute_results=[{"calc_type": "rwdr", "v_surface_m_s": 8.0}],
    )
    row = _row(project_operating_window(gs), "v_max_m_s")
    assert row.requirement_value == 8.0
    assert row.requirement_status == "calculated"
    assert row.flag == "ok"


def test_selects_installed_solution_over_candidate() -> None:
    state = _state(
        assertions={"temperature_max_c": _claim("temperature_max_c", 120)},
        solutions=[
            _sol("sol_cand", state="candidate", temp_max_continuous_c=100),
            _sol("sol_inst", state="installed", temp_max_continuous_c=150),
        ],
    )
    row = _row(project_operating_window(state), "temp_max_continuous_c")
    assert row.limit_value == 150  # the installed profile, not the candidate
    assert row.flag == "ok"


def test_no_solution_profiles_makes_all_limits_unknown() -> None:
    state = _state(assertions={"temperature_max_c": _claim("temperature_max_c", 120)})
    ow = project_operating_window(state)
    assert all(r.flag == "limit_unknown" for r in ow.rows)
    assert ow.has_unknown_limit


def test_requirement_over_limit_projects_critical() -> None:
    state = _state(
        assertions={"temperature_max_c": _claim("temperature_max_c", 180)},
        solutions=[_sol(temp_max_continuous_c=150)],
    )
    ow = project_operating_window(state)
    assert _row(ow, "temp_max_continuous_c").flag == "critical"
    assert ow.has_critical
