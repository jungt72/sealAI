from __future__ import annotations

from app.langgraph_v2.nodes.hitl_triage_node import hitl_triage_node
from app.langgraph_v2.state import SealAIState
from app.services.rag.state import WorkingProfile


def test_hitl_triage_routes_sev1_to_human_review() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            medium="Wasserstoff",
            pressure_max_bar=350.0,
            aed_required=True,
        )
    )

    command = hitl_triage_node(state)

    assert command.goto == "human_review_node"
    assert command.update["safety_class"] == "SEV-1"
    assert command.update["flags"]["hitl_pause_required"] is True


def test_hitl_triage_routes_low_risk_to_worm() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            medium="Wasser",
            pressure_max_bar=10.0,
            temperature_max_c=60.0,
            aed_required=False,
        )
    )

    command = hitl_triage_node(state)

    assert command.goto == "worm_evidence_node"
    assert command.update["safety_class"] == "SEV-4"
    assert command.update["flags"]["hitl_pause_required"] is False

