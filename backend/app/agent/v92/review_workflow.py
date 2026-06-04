"""Human review workflow helpers for V9.2.

Expert review is a typed state transition, not a chat phrase. These helpers
create the UI contract and apply scoped reviewer decisions to GovernedSessionState.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from app.agent.state.models import GovernedSessionState
from app.agent.v92.dashboard_contract import (
    build_v92_dashboard_contract,
    extract_case_revision,
)
from app.agent.v92.models import ReviewState


ReviewAction = Literal["approve_scope", "request_changes", "block"]


def _stable_id(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_review_workflow_contract(
    state: GovernedSessionState,
    *,
    session_id: str,
    turn_id: str = "review-workflow",
) -> dict[str, Any]:
    dashboard = build_v92_dashboard_contract(
        state,
        turn_id=turn_id,
        route="expert_review_action",
        case_id=session_id,
    )
    review = dashboard.review_status
    dossier = dashboard.rfq_dossier_preview or {}
    return {
        "schema_version": "human_review_workflow_v9_2",
        "session_id": session_id,
        "case_id": session_id,
        "case_revision": extract_case_revision(state),
        "review_required": bool(review.get("human_review_required")),
        "review_status": review,
        "review_scope": list(review.get("scope") or []),
        "required_review_types": list(review.get("required_review_types") or []),
        "blocking_findings": list(review.get("blocking_findings") or []),
        "required_corrections": list(review.get("required_corrections") or []),
        "rfq_dossier_preview": dossier,
        "allowed_actions": _allowed_review_actions(review),
        "claim_boundary": {
            "approved_claim_level": review.get("approved_claim_level"),
            "forbidden_claims": list(dossier.get("forbidden_claims") or []),
            "no_final_technical_release": bool(
                dossier.get("no_final_technical_release", True)
            ),
        },
        "dashboard_contract": dashboard.model_dump(mode="json"),
    }


def _allowed_review_actions(review: dict[str, Any]) -> list[str]:
    status = str(review.get("status") or "not_started")
    if status == "approved_scope":
        return ["request_changes", "block"]
    return ["approve_scope", "request_changes", "block"]


def apply_human_review_decision(
    state: GovernedSessionState,
    *,
    session_id: str,
    reviewer_id: str,
    action: ReviewAction,
    scope: list[str] | None = None,
    notes: str | None = None,
) -> GovernedSessionState:
    now = datetime.now(UTC).isoformat()
    scope_items = list(
        scope or state.review_state.scope or ["rfq_handover", "claim_boundary"]
    )
    decision = {
        "decision_id": "review."
        + _stable_id(
            {
                "session_id": session_id,
                "reviewer_id": reviewer_id,
                "action": action,
                "scope": scope_items,
                "case_revision": extract_case_revision(state),
                "created_at": now,
            }
        ),
        "review_type": "human_expert_review",
        "reviewer_id": reviewer_id,
        "decision": action,
        "scope": scope_items,
        "case_revision": extract_case_revision(state),
        "created_at": now,
        "notes": str(notes or "").strip()[:1200],
    }
    existing = list(state.review_state.decisions or [])
    required_review_types = list(state.review_state.required_review_types or [])
    blocking_findings = list(state.review_state.blocking_findings or [])
    required_corrections = list(state.review_state.required_corrections or [])
    approved_claim_level = None
    status = "changes_required"
    summary = "Human review requested changes."
    if action == "approve_scope":
        status = "approved_scope" if not blocking_findings else "changes_required"
        approved_claim_level = (
            "L6_expert_approved" if status == "approved_scope" else None
        )
        if status == "approved_scope":
            required_review_types = []
        summary = (
            "Human expert approved the stated scope."
            if status == "approved_scope"
            else "Human approval requested, but blocking findings remain."
        )
    elif action == "block":
        status = "blocked"
        summary = "Human expert blocked the current scope."
        if "human_reviewer_blocked_scope" not in blocking_findings:
            blocking_findings.append("human_reviewer_blocked_scope")
    elif action == "request_changes":
        status = "changes_required"
        if "human_reviewer_requested_changes" not in required_corrections:
            required_corrections.append("human_reviewer_requested_changes")

    updated_review = ReviewState(
        status=status,  # type: ignore[arg-type]
        reviewer_id=reviewer_id,
        scope=scope_items,
        required_review_types=required_review_types,
        review_guard_notes=list(state.review_state.review_guard_notes or []),
        dossier_modules=list(state.review_state.dossier_modules or []),
        decisions=[*existing, decision],
        override_log_required=True,
        approved_claim_level=approved_claim_level,  # type: ignore[arg-type]
        decision_summary=summary,
        blocking_findings=blocking_findings,
        soft_findings=list(state.review_state.soft_findings or []),
        required_corrections=required_corrections,
        reviewed_claim_ids=list(state.review_state.reviewed_claim_ids or []),
    )
    return state.model_copy(update={"review_state": updated_review})


__all__ = [
    "ReviewAction",
    "apply_human_review_decision",
    "build_review_workflow_contract",
]
