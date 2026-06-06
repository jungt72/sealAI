"""V1.8 §5.6: the Operating-Window surfaces in the workspace projection (P2-L3).

It appears only once a SolutionProfile exists; otherwise the field is omitted.
"""

from __future__ import annotations

from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernedSessionState,
    SolutionField,
    SolutionProfile,
)
from app.api.v1.projections.case_workspace import (
    project_case_workspace_from_governed_state,
)


def _state(with_solution: bool) -> GovernedSessionState:
    solutions = []
    if with_solution:
        solutions = [
            SolutionProfile(
                solution_id="sol1",
                state="selected",
                fields=[
                    SolutionField(
                        field="temp_max_continuous_c",
                        value=150,
                        origin="datasheet_extracted",
                        source_doc="doc_1",
                        source_page=2,
                    )
                ],
            )
        ]
    return GovernedSessionState(
        asserted=AssertedState(
            assertions={
                "temperature_max_c": AssertedClaim(
                    field_name="temperature_max_c",
                    asserted_value=120,
                    status="confirmed",
                )
            }
        ),
        solution_profiles=solutions,
    )


def test_workspace_includes_operating_window_when_solution_exists() -> None:
    proj = project_case_workspace_from_governed_state(
        _state(with_solution=True), chat_id="case-1"
    )
    assert proj.operating_window is not None
    rows = {r["field"]: r for r in proj.operating_window["rows"]}
    assert rows["temp_max_continuous_c"]["flag"] == "ok"
    assert rows["temp_max_continuous_c"]["limit_source_doc"] == "doc_1"
    # missing datasheet limits stay visible as manufacturer questions
    assert proj.operating_window["has_unknown_limit"] is True


def test_workspace_omits_operating_window_without_solution() -> None:
    proj = project_case_workspace_from_governed_state(
        _state(with_solution=False), chat_id="case-1"
    )
    assert proj.operating_window is None
