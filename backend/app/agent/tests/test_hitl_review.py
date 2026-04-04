"""
Unit tests for Phase A3 — HITL Review Grundstruktur.

Tests cover:
1. ReviewLayer fields exist in state type system (structural)
2. evaluate_review_trigger — manufacturer_validation_required fires pending
3. evaluate_review_trigger — demo_data_in_scope fires pending
4. evaluate_review_trigger — no trigger → review_state "none"
5. evaluate_review_trigger — precedence: manufacturer_validation beats demo_data
6. Boundary block contains review pending notice when review_required=True
7. Boundary block does NOT contain notice when review_required=False
8. build_final_reply forwards review_required/reason into boundary
9. Integration: selection_state with manufacturer_validation_required
   produces output containing the review pending marker
"""
from __future__ import annotations

import pytest

from app.agent.agent.boundaries import (
    REVIEW_PENDING_PREFIX,
    STRUCTURED_PATH_SUFFIX,
    build_boundary_block,
)
from app.agent.agent.review import (
    REASON_DEMO_DATA,
    REASON_MANUFACTURER_VALIDATION,
    evaluate_review_trigger,
)
from app.agent.agent.selection import build_final_reply, NO_CANDIDATES_REPLY
from app.agent.agent.state import ReviewLayer, SealingAIState


# ---------------------------------------------------------------------------
# 1. Structural: ReviewLayer fields and SealingAIState typing
# ---------------------------------------------------------------------------

class TestReviewLayerStructure:
    def test_review_layer_fields_exist(self):
        """All six A3 fields must be expressible in ReviewLayer."""
        record: ReviewLayer = {
            "review_required": True,
            "review_state": "pending",
            "review_reason": "test reason",
            "reviewed_by": "engineer_a",
            "review_decision": "approved",
            "review_note": "looks fine",
        }
        assert record["review_required"] is True
        assert record["review_state"] == "pending"
        assert record["review_reason"] == "test reason"
        assert record["reviewed_by"] == "engineer_a"
        assert record["review_decision"] == "approved"
        assert record["review_note"] == "looks fine"

    def test_review_layer_optional_fields_can_be_none(self):
        record: ReviewLayer = {
            "review_required": False,
            "review_state": "none",
            "review_reason": "",
            "reviewed_by": None,
            "review_decision": None,
            "review_note": None,
        }
        assert record["reviewed_by"] is None
        assert record["review_decision"] is None
        assert record["review_note"] is None

    def test_review_states_are_valid_literals(self):
        for state in ("none", "pending", "approved", "rejected"):
            r: ReviewLayer = {
                "review_required": state != "none",
                "review_state": state,  # type: ignore[typeddict-item]
                "review_reason": "",
                "reviewed_by": None,
                "review_decision": None,
                "review_note": None,
            }
            assert r["review_state"] == state


# ---------------------------------------------------------------------------
# 2–5. evaluate_review_trigger
# ---------------------------------------------------------------------------

class TestEvaluateReviewTrigger:
    def test_manufacturer_validation_required_fires_pending(self):
        result = evaluate_review_trigger(
            governance_state={"release_status": "manufacturer_validation_required"}
        )
        assert result["review_required"] is True
        assert result["review_state"] == "pending"
        assert result["review_reason"] == REASON_MANUFACTURER_VALIDATION

    def test_manufacturer_validation_sets_nil_operator_fields(self):
        result = evaluate_review_trigger(
            governance_state={"release_status": "manufacturer_validation_required"}
        )
        assert result["reviewed_by"] is None
        assert result["review_decision"] is None
        assert result["review_note"] is None

    def test_demo_data_in_scope_fires_pending(self):
        result = evaluate_review_trigger(
            governance_state={"release_status": "inadmissible"},
            demo_data_in_scope=True,
        )
        assert result["review_required"] is True
        assert result["review_state"] == "pending"
        assert result["review_reason"] == REASON_DEMO_DATA

    def test_no_trigger_returns_none_state(self):
        result = evaluate_review_trigger(
            governance_state={"release_status": "rfq_ready"},
            demo_data_in_scope=False,
        )
        assert result["review_required"] is False
        assert result["review_state"] == "none"
        assert result["review_reason"] == ""

    def test_inadmissible_without_demo_data_is_not_pending(self):
        result = evaluate_review_trigger(
            governance_state={"release_status": "inadmissible"},
            demo_data_in_scope=False,
        )
        assert result["review_required"] is False
        assert result["review_state"] == "none"

    def test_rfq_ready_without_demo_data_is_not_pending(self):
        result = evaluate_review_trigger(
            governance_state={"release_status": "rfq_ready"},
            demo_data_in_scope=False,
        )
        assert result["review_required"] is False

    def test_manufacturer_validation_takes_precedence_over_demo_data(self):
        """When both triggers fire, manufacturer_validation reason wins."""
        result = evaluate_review_trigger(
            governance_state={"release_status": "manufacturer_validation_required"},
            demo_data_in_scope=True,
        )
        assert result["review_required"] is True
        assert result["review_reason"] == REASON_MANUFACTURER_VALIDATION

    def test_missing_release_status_does_not_crash(self):
        """Absent release_status defaults to inadmissible — no trigger."""
        result = evaluate_review_trigger(governance_state={})
        assert result["review_required"] is False

    def test_precheck_only_without_demo_data_is_not_pending(self):
        result = evaluate_review_trigger(
            governance_state={"release_status": "precheck_only"},
            demo_data_in_scope=False,
        )
        assert result["review_required"] is False


# ---------------------------------------------------------------------------
# 6–7. build_boundary_block review notice injection
# ---------------------------------------------------------------------------

class TestBoundaryBlockReviewNotice:
    def test_review_pending_notice_present_when_flagged(self):
        block = build_boundary_block(
            "structured",
            review_required=True,
            review_reason="Hersteller-Validierung erforderlich.",
        )
        assert REVIEW_PENDING_PREFIX in block
        assert "Hersteller-Validierung erforderlich." in block

    def test_review_pending_notice_absent_when_not_flagged(self):
        block = build_boundary_block("structured", review_required=False)
        assert REVIEW_PENDING_PREFIX not in block

    def test_review_pending_notice_absent_by_default(self):
        block = build_boundary_block("structured")
        assert REVIEW_PENDING_PREFIX not in block

    def test_review_notice_appended_after_scope_block(self):
        """Review line must come after the scope-of-validity suffix."""
        block = build_boundary_block(
            "structured",
            review_required=True,
            review_reason="Demo-Daten.",
        )
        suffix_pos = block.index(STRUCTURED_PATH_SUFFIX)
        notice_pos = block.index(REVIEW_PENDING_PREFIX)
        assert suffix_pos < notice_pos

    def test_fast_path_ignores_review_flags(self):
        """Fast-path disclaimer is invariant — review kwargs must be ignored."""
        from app.agent.agent.boundaries import FAST_PATH_DISCLAIMER
        block = build_boundary_block(
            "fast",
            review_required=True,
            review_reason="should be ignored",
        )
        assert block == FAST_PATH_DISCLAIMER
        assert REVIEW_PENDING_PREFIX not in block

    def test_review_reason_included_in_notice(self):
        reason = "Demo-Daten im Scope — governe Materialdaten nicht vorhanden."
        block = build_boundary_block("structured", review_required=True, review_reason=reason)
        assert reason in block


# ---------------------------------------------------------------------------
# 8. build_final_reply forwards review kwargs
# ---------------------------------------------------------------------------

def _make_minimal_selection_state(
    *, selection_status: str = "blocked_no_candidates"
) -> dict:
    return {
        "selection_status": selection_status,
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "output_blocked": True,
        "candidates": [],
        "viable_candidate_ids": [],
        "blocked_candidates": [],
        "winner_candidate_id": None,
        "recommendation_artifact": {
            "selection_status": selection_status,
            "winner_candidate_id": None,
            "candidate_ids": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "evidence_basis": [],
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
            "trace_provenance_refs": [],
        },
    }


class TestBuildFinalReplyReview:
    def test_review_notice_in_reply_when_required(self):
        state = _make_minimal_selection_state()
        reply = build_final_reply(
            state,
            review_required=True,
            review_reason="Hersteller-Validierung erforderlich.",
        )
        assert REVIEW_PENDING_PREFIX in reply
        assert "Hersteller-Validierung erforderlich." in reply

    def test_no_review_notice_by_default(self):
        state = _make_minimal_selection_state()
        reply = build_final_reply(state)
        assert REVIEW_PENDING_PREFIX not in reply

    def test_review_notice_absent_when_not_required(self):
        state = _make_minimal_selection_state()
        reply = build_final_reply(state, review_required=False, review_reason="")
        assert REVIEW_PENDING_PREFIX not in reply

    def test_core_reply_precedes_review_notice(self):
        """Governance text must appear before the review notice."""
        state = _make_minimal_selection_state(selection_status="blocked_no_candidates")
        reply = build_final_reply(
            state,
            review_required=True,
            review_reason="Demo-Daten.",
        )
        core_pos = reply.index(NO_CANDIDATES_REPLY)
        notice_pos = reply.index(REVIEW_PENDING_PREFIX)
        assert core_pos < notice_pos

    def test_manufacturer_validation_reply_with_review_pending(self):
        """Combination: manufacturer_validation reply text + review notice both present."""
        state = _make_minimal_selection_state()
        state["release_status"] = "manufacturer_validation_required"
        state["rfq_admissibility"] = "provisional"
        state["recommendation_artifact"]["release_status"] = "manufacturer_validation_required"
        state["recommendation_artifact"]["rfq_admissibility"] = "provisional"
        reply = build_final_reply(
            state,
            review_required=True,
            review_reason=REASON_MANUFACTURER_VALIDATION,
        )
        from app.agent.agent.selection import MANUFACTURER_VALIDATION_REPLY
        assert MANUFACTURER_VALIDATION_REPLY in reply
        assert REVIEW_PENDING_PREFIX in reply
