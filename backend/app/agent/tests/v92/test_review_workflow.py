from __future__ import annotations

from app.agent.state.models import GovernedSessionState
from app.agent.v92.models import ReviewState
from app.agent.v92.review_workflow import (
    apply_human_review_decision,
    build_review_workflow_contract,
)


def test_review_workflow_contract_exposes_required_actions_and_claim_boundary() -> None:
    state = GovernedSessionState(
        review_state=ReviewState(
            status="pending",
            required_review_types=["claim_boundary_review"],
            blocking_findings=[],
            required_corrections=[],
        )
    )

    workflow = build_review_workflow_contract(state, session_id="case-1")

    assert workflow["schema_version"] == "human_review_workflow_v9_2"
    assert workflow["review_required"] is True
    assert "approve_scope" in workflow["allowed_actions"]
    assert workflow["claim_boundary"]["no_final_technical_release"] is True
    assert workflow["dashboard_contract"]["review_status"]["human_review_required"] is True


def test_apply_human_review_decision_requires_scope_and_sets_l6_only_for_approved_scope() -> None:
    state = GovernedSessionState(
        review_state=ReviewState(
            status="pending",
            required_review_types=["rfq_scope_review"],
            blocking_findings=[],
        )
    )

    updated = apply_human_review_decision(
        state,
        session_id="case-1",
        reviewer_id="expert-1",
        action="approve_scope",
        scope=["rfq_handover"],
        notes="Scope reviewed.",
    )

    assert updated.review_state.status == "approved_scope"
    assert updated.review_state.approved_claim_level == "L6_expert_approved"
    assert updated.review_state.required_review_types == []
    assert updated.review_state.decisions[0]["reviewer_id"] == "expert-1"
    assert updated.review_state.decisions[0]["scope"] == ["rfq_handover"]


def test_apply_human_review_decision_does_not_approve_when_blockers_remain() -> None:
    state = GovernedSessionState(
        review_state=ReviewState(
            status="pending",
            blocking_findings=["compound_datasheet_missing"],
        )
    )

    updated = apply_human_review_decision(
        state,
        session_id="case-1",
        reviewer_id="expert-1",
        action="approve_scope",
    )

    assert updated.review_state.status == "changes_required"
    assert updated.review_state.approved_claim_level is None
    assert "compound_datasheet_missing" in updated.review_state.blocking_findings
