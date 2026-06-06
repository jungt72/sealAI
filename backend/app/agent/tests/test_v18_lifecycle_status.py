"""V1.8 §6.3 / AC9: the case lifecycle status is derived from the accumulated
state (most-advanced state wins) and stamped live at the commit seam."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.api.loaders import _update_governed_state_post_graph
from app.agent.graph import GraphState
from app.agent.state.lifecycle import derive_lifecycle_status
from app.agent.state.models import (
    ActionReadinessState,
    GovernedSessionState,
    OutcomeRecord,
    SolutionProfile,
)
from app.services.auth.dependencies import RequestUser


def _state(
    *, solutions=None, outcomes=None, inquiry_sent=False
) -> GovernedSessionState:
    return GovernedSessionState(
        solution_profiles=solutions or [],
        outcome_records=outcomes or [],
        action_readiness=ActionReadinessState(inquiry_sent=inquiry_sent),
    )


def _sol(state: str) -> SolutionProfile:
    return SolutionProfile(solution_id=f"sol_{state}", state=state)


def test_default_is_inquiring() -> None:
    assert derive_lifecycle_status(GovernedSessionState()) == "inquiring"


def test_inquiry_sent_is_rfq_sent() -> None:
    assert derive_lifecycle_status(_state(inquiry_sent=True)) == "rfq_sent"


def test_offer_is_quoted() -> None:
    assert derive_lifecycle_status(_state(solutions=[_sol("offer")])) == "quoted"


def test_selected_is_solution_selected() -> None:
    assert (
        derive_lifecycle_status(_state(solutions=[_sol("selected")]))
        == "solution_selected"
    )


def test_installed_is_installed() -> None:
    assert derive_lifecycle_status(_state(solutions=[_sol("installed")])) == "installed"


def test_installed_with_operation_outcome_is_in_operation() -> None:
    state = _state(
        solutions=[_sol("installed")],
        outcomes=[OutcomeRecord(event="in_operation")],
    )
    assert derive_lifecycle_status(state) == "in_operation"


def test_incident_outcome_wins_over_installed() -> None:
    state = _state(
        solutions=[_sol("installed")],
        outcomes=[OutcomeRecord(event="incident")],
    )
    assert derive_lifecycle_status(state) == "incident"


def test_replaced_outcome_wins_over_incident() -> None:
    state = _state(
        outcomes=[OutcomeRecord(event="incident"), OutcomeRecord(event="replaced")],
    )
    assert derive_lifecycle_status(state) == "replaced"


@pytest.mark.asyncio
async def test_commit_seam_stamps_live_lifecycle_status() -> None:
    result_state = GraphState(solution_profiles=[_sol("installed")])
    persist = AsyncMock()
    with (
        patch(
            "app.agent.api.loaders._load_live_governed_state",
            AsyncMock(return_value=GovernedSessionState()),
        ),
        patch("app.agent.api.loaders._persist_live_governed_state", persist),
    ):
        updated = await _update_governed_state_post_graph(
            current_user=RequestUser(
                user_id="u1",
                username="u1",
                sub="u1",
                roles=["user"],
                scopes=[],
                tenant_id="t1",
            ),
            session_id="case-lc",
            result_state=result_state,
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    assert updated.case_lifecycle.status == "installed"
    assert persist.await_args.kwargs["state"].case_lifecycle.status == "installed"
