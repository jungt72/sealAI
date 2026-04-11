"""
Tests for Phase 0D.4 — Evidence governance: structured path has an explicit
evidence-availability state and it appears in the output boundary.

Covers:
1. boundaries.py: evidence_available=False adds a note to the structured block
2. boundaries.py: evidence_available=True (default) does not add the note
3. selection.py: build_final_reply forwards evidence_available to boundary
4. No-evidence note is deterministic and never LLM-generated
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agent.agent.boundaries import build_boundary_block, _NO_EVIDENCE_NOTE, STRUCTURED_PATH_SUFFIX
from app.agent.agent.selection import build_final_reply


# ---------------------------------------------------------------------------
# 1 & 2: boundaries.py evidence flag
# ---------------------------------------------------------------------------

class TestBoundaryEvidenceFlag:
    def test_no_evidence_note_absent_by_default(self):
        block = build_boundary_block("structured")
        assert _NO_EVIDENCE_NOTE not in block

    def test_no_evidence_note_present_when_flagged(self):
        block = build_boundary_block("structured", evidence_available=False)
        assert _NO_EVIDENCE_NOTE in block

    def test_no_evidence_note_absent_when_evidence_available(self):
        block = build_boundary_block("structured", evidence_available=True)
        assert _NO_EVIDENCE_NOTE not in block

    def test_structured_suffix_still_present_with_no_evidence(self):
        """Core suffix must always be present regardless of evidence flag."""
        block = build_boundary_block("structured", evidence_available=False)
        assert STRUCTURED_PATH_SUFFIX in block

    def test_fast_path_ignores_evidence_flag(self):
        """Fast path boundary is invariant — evidence_available has no effect."""
        from app.agent.agent.boundaries import FAST_PATH_DISCLAIMER
        block_with = build_boundary_block("fast", evidence_available=False)
        block_without = build_boundary_block("fast", evidence_available=True)
        assert block_with == FAST_PATH_DISCLAIMER
        assert block_without == FAST_PATH_DISCLAIMER

    def test_no_evidence_note_content_is_deterministic(self):
        """Two calls with same args must produce identical output."""
        b1 = build_boundary_block("structured", evidence_available=False)
        b2 = build_boundary_block("structured", evidence_available=False)
        assert b1 == b2

    def test_no_evidence_combined_with_other_flags(self):
        """evidence_available=False must combine correctly with other flags."""
        block = build_boundary_block(
            "structured",
            coverage_status="limited",
            evidence_available=False,
            demo_data_present=True,
        )
        assert _NO_EVIDENCE_NOTE in block
        assert STRUCTURED_PATH_SUFFIX in block
        assert "Eingeschränkte Datenbasis" in block


# ---------------------------------------------------------------------------
# 3: build_final_reply forwards evidence_available
# ---------------------------------------------------------------------------

def _minimal_selection_state() -> dict:
    return {
        "selection_status": "blocked_no_candidates",
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "output_blocked": True,
        "candidates": [],
        "viable_candidate_ids": [],
        "blocked_candidates": [],
        "winner_candidate_id": None,
        "recommendation_artifact": {
            "selection_status": "blocked_no_candidates",
            "winner_candidate_id": None,
            "candidate_projection": None,
            "candidate_ids": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "evidence_basis": [],
            "evidence_status": "no_evidence",
            "provenance_refs": [],
            "rationale_basis": ["blocked_no_candidates", "insufficient_inputs", "no_evidence", "non_binding_projection"],
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
            "binding_level": "non_binding",
            "readiness_status": "insufficient_inputs",
            "blocking_reason": "Required core params not yet confirmed.",
            "rationale_summary": "No governed recommendation can be released from the current evidence.",
            "trace_provenance_refs": [],
        },
        "evidence_provenance_projection": {
            "status": "no_evidence",
            "provenance_refs": [],
            "evidence_basis": [],
        },
        "review_escalation_projection": {
            "status": "withheld_missing_core_inputs",
            "reason": "Required core params not yet confirmed.",
            "missing_items": ["medium", "pressure", "temperature"],
            "ambiguous_candidate_ids": [],
            "evidence_status": "no_evidence",
            "provenance_refs": [],
            "review_meaningful": False,
            "handover_possible": False,
            "human_validation_ready": False,
        },
        "user_facing_output_projection": {
            "status": "clarification_needed",
        },
        "output_contract_projection": {
            "output_status": "clarification_needed",
            "allowed_surface_claims": ["missing_inputs", "single_next_question"],
            "next_user_action": "answer_next_question",
            "visible_warning_flags": [],
            "suppress_recommendation_details": True,
        },
    }


def _delta_selection_state(
    *,
    case_status: str,
    output_status: str,
    next_step: str,
    actionability_status: str,
    primary_allowed_action: str,
    next_expected_user_action: str | None = None,
    active_blockers: list[str] | None = None,
    blocked_actions: list[str] | None = None,
    domain_status: str = "in_domain_scope",
    threshold_status: str = "threshold_free",
    integrity_status: str = "normalized_ok",
    conflict_status: str = "no_conflict",
    invariant_ok: bool = True,
) -> dict:
    state = _minimal_selection_state()
    active_blockers = list(active_blockers or [])
    blocked_actions = list(blocked_actions or [])
    state["output_contract_projection"] = {
        "output_status": output_status,
        "allowed_surface_claims": [],
        "next_user_action": next_step,
        "visible_warning_flags": [],
        "suppress_recommendation_details": output_status != "governed_non_binding_result",
    }
    state["case_summary_projection"] = {
        "current_case_status": case_status,
        "confirmed_core_fields": ["medium", "pressure", "temperature"],
        "missing_core_fields": [],
        "active_blockers": active_blockers,
        "next_step": next_step,
    }
    state["actionability_projection"] = {
        "actionability_status": actionability_status,
        "primary_allowed_action": primary_allowed_action,
        "blocked_actions": blocked_actions,
        "next_expected_user_action": next_expected_user_action or next_step,
    }
    state["domain_scope_projection"] = {
        "status": domain_status,
        "triggered_thresholds": [],
        "warning_thresholds": [],
        "blocking_thresholds": [],
        "threshold_status": threshold_status,
        "usable_for_governed_step": domain_status not in {"out_of_domain_scope", "escalation_required"},
    }
    state["threshold_projection"] = {
        "triggered_thresholds": [],
        "warning_thresholds": [],
        "blocking_thresholds": [],
        "threshold_status": threshold_status,
        "usable_for_governed_step": threshold_status != "threshold_blocking",
    }
    state["parameter_integrity_projection"] = {
        "affected_keys": [],
        "integrity_status": integrity_status,
        "warning_keys": [],
        "blocking_keys": [],
        "usable_for_structured_step": integrity_status != "unusable_until_clarified",
    }
    state["conflict_status_projection"] = {
        "status": conflict_status,
        "affected_keys": ["pressure"] if conflict_status == "unresolved_conflict" else [],
        "previous_value_summary": "pressure=5.0" if conflict_status == "unresolved_conflict" else "",
        "current_value_summary": "pressure=10.0" if conflict_status == "unresolved_conflict" else "",
        "correction_applied": conflict_status == "corrected_conflict",
        "conflict_still_open": conflict_status == "unresolved_conflict",
    }
    state["projection_invariant_projection"] = {
        "invariant_ok": invariant_ok,
        "invariant_violations": [] if invariant_ok else ["governed_result_suppressed_details"],
    }
    return state


class TestBuildFinalReplyEvidenceFlag:
    def test_no_evidence_note_in_reply_when_no_evidence(self):
        state = _minimal_selection_state()
        reply = build_final_reply(state, evidence_available=False)
        assert _NO_EVIDENCE_NOTE in reply

    def test_no_evidence_note_absent_by_default(self):
        state = _minimal_selection_state()
        reply = build_final_reply(state)
        assert _NO_EVIDENCE_NOTE not in reply

    def test_structured_suffix_always_present_regardless_of_evidence(self):
        state = _minimal_selection_state()
        for ev in (True, False):
            reply = build_final_reply(state, evidence_available=ev)
            assert STRUCTURED_PATH_SUFFIX in reply, f"Suffix missing for evidence_available={ev}"


# ---------------------------------------------------------------------------
# Phase 1A — PATCH 2: Named engineering gates
# ---------------------------------------------------------------------------

def _make_empty_sealing_state():
    """Minimal SealingAIState with fully empty asserted layer — no core params."""
    from app.agent.agent.logic import _ensure_state_shape
    state = {}
    _ensure_state_shape(state)
    return state


def _make_partial_sealing_state(*, medium=None, pressure=None, temperature=None):
    """SealingAIState with selectively populated asserted core params."""
    from app.agent.agent.logic import _ensure_state_shape
    state = {}
    _ensure_state_shape(state)
    asserted = state["asserted"]
    if medium is not None:
        asserted["medium_profile"]["name"] = medium
    oc = asserted.setdefault("operating_conditions", {})
    if pressure is not None:
        oc["pressure"] = pressure
    if temperature is not None:
        oc["temperature"] = temperature
    return state


class TestNamedGateConstants:
    """Gate constants exist and have the canonical string values."""

    def test_gate_insufficient_required_inputs_constant(self):
        from app.agent.agent.logic import GATE_INSUFFICIENT_REQUIRED_INPUTS
        assert GATE_INSUFFICIENT_REQUIRED_INPUTS == "insufficient_required_inputs"

    def test_gate_demo_data_in_scope_constant(self):
        from app.agent.agent.logic import GATE_DEMO_DATA_IN_SCOPE
        assert GATE_DEMO_DATA_IN_SCOPE == "demo_data_in_scope"

    def test_gate_review_required_constant(self):
        from app.agent.agent.logic import GATE_REVIEW_REQUIRED
        assert GATE_REVIEW_REQUIRED == "review_required"

    def test_gate_evidence_missing_constant(self):
        from app.agent.agent.logic import GATE_EVIDENCE_MISSING
        assert GATE_EVIDENCE_MISSING == "evidence_missing"

    def test_gate_evidence_insufficient_constant(self):
        from app.agent.agent.logic import GATE_EVIDENCE_INSUFFICIENT
        assert GATE_EVIDENCE_INSUFFICIENT == "evidence_insufficient"

    def test_gate_out_of_scope_constant(self):
        from app.agent.agent.logic import GATE_OUT_OF_SCOPE
        assert GATE_OUT_OF_SCOPE == "out_of_scope"

    def test_gate_blocked_by_boundary_constant(self):
        from app.agent.agent.logic import GATE_BLOCKED_BY_BOUNDARY
        assert GATE_BLOCKED_BY_BOUNDARY == "blocked_by_boundary"


class TestInsufficientRequiredInputsGate:
    """GATE_INSUFFICIENT_REQUIRED_INPUTS fires when no core param is in asserted."""

    def test_empty_asserted_produces_insufficient_required_inputs_gate(self):
        from app.agent.agent.logic import _derive_governance_from_state, GATE_INSUFFICIENT_REQUIRED_INPUTS
        state = _make_empty_sealing_state()
        _derive_governance_from_state(state)
        assert GATE_INSUFFICIENT_REQUIRED_INPUTS in state["governance"]["unknowns_release_blocking"], (
            "Empty asserted_state must produce GATE_INSUFFICIENT_REQUIRED_INPUTS in unknowns_release_blocking"
        )

    def test_empty_asserted_results_in_inadmissible(self):
        from app.agent.agent.logic import _derive_governance_from_state
        state = _make_empty_sealing_state()
        _derive_governance_from_state(state)
        assert state["governance"]["release_status"] == "inadmissible"

    def test_medium_only_does_not_fire_insufficient_gate(self):
        """Medium confirmed but pressure/temperature missing → gate must NOT fire
        (we have something to work with; the issue is incompleteness, not total absence)."""
        from app.agent.agent.logic import _derive_governance_from_state, GATE_INSUFFICIENT_REQUIRED_INPUTS
        state = _make_partial_sealing_state(medium="Hydrauliköl")
        _derive_governance_from_state(state)
        assert GATE_INSUFFICIENT_REQUIRED_INPUTS not in state["governance"]["unknowns_release_blocking"], (
            "Gate must NOT fire when at least one core param is asserted"
        )

    def test_pressure_only_does_not_fire_insufficient_gate(self):
        from app.agent.agent.logic import _derive_governance_from_state, GATE_INSUFFICIENT_REQUIRED_INPUTS
        state = _make_partial_sealing_state(pressure=10.0)
        _derive_governance_from_state(state)
        assert GATE_INSUFFICIENT_REQUIRED_INPUTS not in state["governance"]["unknowns_release_blocking"]

    def test_all_three_core_params_no_insufficient_gate(self):
        from app.agent.agent.logic import _derive_governance_from_state, GATE_INSUFFICIENT_REQUIRED_INPUTS
        state = _make_partial_sealing_state(medium="Wasser", pressure=5.0, temperature=80.0)
        _derive_governance_from_state(state)
        assert GATE_INSUFFICIENT_REQUIRED_INPUTS not in state["governance"]["unknowns_release_blocking"]

    def test_gate_not_duplicated_on_second_call(self):
        """Running _derive_governance_from_state twice must not duplicate gate entries."""
        from app.agent.agent.logic import _derive_governance_from_state, GATE_INSUFFICIENT_REQUIRED_INPUTS
        state = _make_empty_sealing_state()
        _derive_governance_from_state(state)
        _derive_governance_from_state(state)
        count = state["governance"]["unknowns_release_blocking"].count(GATE_INSUFFICIENT_REQUIRED_INPUTS)
        assert count == 1, f"Gate must appear exactly once, got {count}"


# ---------------------------------------------------------------------------
# Phase 1B — PATCH 1: Central OutputReadinessDecision
# ---------------------------------------------------------------------------

def _full_asserted() -> dict:
    return {
        "medium_profile": {"name": "Hydrauliköl"},
        "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
    }


def _green_governance() -> dict:
    return {
        "release_status": "inquiry_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "unknowns_release_blocking": [],
        "gate_failures": [],
        "conflicts": [],
    }


def _blocking_governance() -> dict:
    return {
        "release_status": "inadmissible",
        "rfq_admissibility": "inadmissible",
        "specificity_level": "family_only",
        "unknowns_release_blocking": ["evidence_missing"],
        "gate_failures": [],
        "conflicts": [],
    }


def _pending_review() -> dict:
    return {
        "review_required": True,
        "review_state": "pending",
        "review_reason": "Hersteller-Validierung erforderlich.",
    }


class TestOutputReadinessDecision:
    """Phase 1B PATCH 1: evaluate_output_readiness() is the single source of truth."""

    def test_releasable_when_all_conditions_met(self):
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(
            _full_asserted(), _green_governance(),
            review_state=None, evidence_available=True, demo_data_present=False,
        )
        assert decision.releasable is True
        assert decision.status == "releasable"
        assert decision.blocking_reason == ""

    def test_insufficient_inputs_when_no_params(self):
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(None, _green_governance())
        assert decision.releasable is False
        assert decision.status == "insufficient_inputs"

    def test_insufficient_inputs_takes_priority_over_governance_blocked(self):
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(None, _blocking_governance())
        assert decision.status == "insufficient_inputs"

    def test_demo_data_quarantine_when_demo_data_present(self):
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(
            _full_asserted(), _green_governance(), demo_data_present=True,
        )
        assert decision.releasable is False
        assert decision.status == "demo_data_quarantine"

    def test_demo_data_takes_priority_over_evidence_missing(self):
        """demo_data_quarantine fires before evidence_missing when both apply."""
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(
            _full_asserted(), _green_governance(),
            demo_data_present=True, evidence_available=False,
        )
        assert decision.status == "demo_data_quarantine"

    def test_evidence_missing_when_not_available(self):
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(
            _full_asserted(), _green_governance(), evidence_available=False,
        )
        assert decision.releasable is False
        assert decision.status == "evidence_missing"

    def test_review_pending_when_review_required(self):
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(
            _full_asserted(), _green_governance(), review_state=_pending_review(),
        )
        assert decision.releasable is False
        assert decision.status == "review_pending"

    def test_review_pending_includes_reason_in_blocking_reason(self):
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(
            _full_asserted(), _green_governance(), review_state=_pending_review(),
        )
        assert "Hersteller-Validierung" in decision.blocking_reason

    def test_governance_blocked_when_governance_not_ready(self):
        from app.agent.agent.selection import evaluate_output_readiness
        decision = evaluate_output_readiness(
            _full_asserted(), _blocking_governance(),
            review_state=None, evidence_available=True, demo_data_present=False,
        )
        assert decision.releasable is False
        assert decision.status == "governance_blocked"

    def test_governance_blocked_when_gate_failures_present(self):
        from app.agent.agent.selection import evaluate_output_readiness
        gov = {**_green_governance(), "gate_failures": ["evidence_insufficient"]}
        decision = evaluate_output_readiness(_full_asserted(), gov)
        assert decision.status == "governance_blocked"

    def test_governance_blocked_when_blocking_unknowns_present(self):
        from app.agent.agent.selection import evaluate_output_readiness
        gov = {**_green_governance(), "unknowns_release_blocking": ["review_required"]}
        decision = evaluate_output_readiness(_full_asserted(), gov)
        assert decision.status == "governance_blocked"

    def test_decision_is_deterministic(self):
        """Same inputs must always return identical decision."""
        from app.agent.agent.selection import evaluate_output_readiness
        d1 = evaluate_output_readiness(_full_asserted(), _green_governance())
        d2 = evaluate_output_readiness(_full_asserted(), _green_governance())
        assert d1 == d2

    def test_blocking_reason_non_empty_when_not_releasable(self):
        """Every non-releasable decision must have an explanatory blocking_reason."""
        from app.agent.agent.selection import evaluate_output_readiness
        for scenario in [
            (None, _green_governance(), {}),
            (_full_asserted(), _green_governance(), {"demo": True}),
            (_full_asserted(), _green_governance(), {"ev": False}),
            (_full_asserted(), _blocking_governance(), {}),
        ]:
            asserted, gov, extras = scenario
            decision = evaluate_output_readiness(
                asserted, gov,
                demo_data_present=extras.get("demo", False),
                evidence_available=extras.get("ev", True),
            )
            if not decision.releasable:
                assert decision.blocking_reason, (
                    f"blocking_reason must be non-empty for status={decision.status!r}"
                )


class TestEvidenceProvenanceProjection:
    def test_no_source_refs_project_no_evidence(self):
        from app.agent.agent.selection import project_evidence_provenance_state

        projection = project_evidence_provenance_state([], [])
        assert projection["status"] == "no_evidence"
        assert projection["provenance_refs"] == []

    def test_single_provenance_ref_projects_thin_evidence(self):
        from app.agent.agent.selection import project_evidence_provenance_state

        projection = project_evidence_provenance_state(
            [_qualified_fact_card("fc_1", grade_name="F1")],
            ["fc_1"],
        )
        assert projection["status"] == "thin_evidence"
        assert projection["provenance_refs"] == ["source::fc_1"]

    def test_multiple_provenance_refs_project_grounded_evidence(self):
        from app.agent.agent.selection import project_evidence_provenance_state

        projection = project_evidence_provenance_state(
            [
                _qualified_fact_card("fc_1", grade_name="F1"),
                _qualified_fact_card("fc_2", grade_name="F2"),
            ],
            ["fc_1", "fc_2"],
        )
        assert projection["status"] == "grounded_evidence"
        assert projection["provenance_refs"] == ["source::fc_1", "source::fc_2"]

    def test_projection_ignores_cards_outside_evidence_basis(self):
        from app.agent.agent.selection import project_evidence_provenance_state

        projection = project_evidence_provenance_state(
            [
                _qualified_fact_card("fc_1", grade_name="F1"),
                _qualified_fact_card("fc_2", grade_name="F2"),
            ],
            ["fc_2"],
        )
        assert projection["status"] == "thin_evidence"
        assert projection["provenance_refs"] == ["source::fc_2"]


def _qualified_fact_card(
    evidence_id: str,
    *,
    family: str = "FKM",
    grade_name: str | None = None,
    manufacturer_name: str | None = None,
    temp_max: float = 120.0,
    pressure_max: float = 16.0,
) -> dict:
    normalized = {
        "material_family": family,
        "grade_name": grade_name,
        "manufacturer_name": manufacturer_name,
        "normalized_temp_min": -20.0,
        "normalized_temp_max": temp_max,
        "normalized_pressure_max": pressure_max,
    }
    return {
        "id": evidence_id,
        "evidence_id": evidence_id,
        "source_ref": f"source::{evidence_id}",
        "retrieval_rank": 1,
        "topic": family,
        "content": f"{family} technical evidence",
        "metadata": {
            "material_family": family,
            "grade_name": grade_name,
            "manufacturer_name": manufacturer_name,
        },
        "normalized_evidence": normalized,
    }


class TestGovernedRecommendationArtifact:
    def test_releasable_artifact_projects_single_candidate_non_binding(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"]["candidate_id"] == "fkm::f1"
        assert artifact["binding_level"] == "non_binding"
        assert artifact["readiness_status"] == "releasable"
        assert artifact["output_blocked"] is False
        assert artifact["evidence_status"] == "thin_evidence"
        assert artifact["provenance_refs"] == ["source::fc_1"]
        assert "thin_evidence" in artifact["rationale_basis"]
        assert "Freigabeschluss" in artifact["rationale_summary"]
        assert "eingeschränkt" in artifact["rationale_summary"]

    def test_insufficient_inputs_produce_no_candidate_projection(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={"medium_profile": {"name": "Hydrauliköl"}, "operating_conditions": {"pressure": 10.0}},
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"] is None
        assert artifact["readiness_status"] == "insufficient_inputs"
        assert artifact["output_blocked"] is True
        assert artifact["provenance_refs"] == ["source::fc_1"]

    def test_review_required_withholds_normal_candidate_projection(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"] is None
        assert artifact["readiness_status"] == "review_pending"
        assert artifact["winner_candidate_id"] == "fkm::f1"
        assert artifact["evidence_status"] == "thin_evidence"

    def test_missing_evidence_produces_restricted_artifact_state(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            evidence_available=False,
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"] is None
        assert artifact["readiness_status"] == "evidence_missing"
        assert artifact["evidence_status"] == "thin_evidence"
        assert artifact["provenance_refs"] == ["source::fc_1"]
        assert "Referenzdaten" in artifact["rationale_summary"]

    def test_demo_data_quarantine_has_no_normal_candidate_projection(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            demo_data_present=True,
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"] is None
        assert artifact["readiness_status"] == "demo_data_quarantine"
        assert artifact["evidence_status"] == "thin_evidence"

    def test_multiple_viable_candidates_do_not_claim_single_best_candidate(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[
                _qualified_fact_card("fc_1", grade_name="F1"),
                _qualified_fact_card("fc_2", grade_name="F2"),
            ],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )

        artifact = state["recommendation_artifact"]
        assert state["selection_status"] == "multiple_viable_candidates"
        assert artifact["candidate_projection"] is None
        assert artifact["winner_candidate_id"] is None
        assert artifact["readiness_status"] == "candidate_ambiguity"
        assert artifact["evidence_status"] == "grounded_evidence"
        assert artifact["provenance_refs"] == ["source::fc_1", "source::fc_2"]

    def test_rationale_summary_avoids_soft_recommendation_claims(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )

        summary = state["recommendation_artifact"]["rationale_summary"].lower()
        assert "passt gut" not in summary
        assert "ideal" not in summary
        assert "empfohlen" not in summary

    def test_artifact_with_no_provenance_stays_no_evidence(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )

        artifact = state["recommendation_artifact"]
        assert artifact["evidence_status"] == "no_evidence"
        assert artifact["provenance_refs"] == []
        assert artifact["candidate_projection"] is None

    def test_unresolved_conflict_withholds_normal_candidate_projection(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state={**_green_governance(), "conflicts": [{"field": "pressure", "type": "parameter_conflict", "severity": "CRITICAL"}]},
            asserted_state=_full_asserted(),
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 10 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 10.0}, "identity_records": {}},
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"] is None
        assert artifact["readiness_status"] == "conflict_unresolved"
        assert artifact["conflict_status"] == "unresolved_conflict"
        assert state["correction_projection"]["conflict_still_open"] is True

    def test_corrected_value_keeps_projection_consistent(self):
        from app.agent.agent.selection import build_selection_state, CORRECTION_APPLIED_PREFIX

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 10 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 10.0}, "identity_records": {}},
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"]["candidate_id"] == "fkm::f1"
        assert artifact["conflict_status"] == "corrected_value"
        assert state["correction_projection"]["correction_applied"] is True
        assert CORRECTION_APPLIED_PREFIX in artifact["rationale_summary"]

    def test_integrity_warning_keeps_releasable_projection_but_marks_warning(self):
        from app.agent.agent.selection import build_selection_state, INTEGRITY_WARNING_PREFIX

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 6.8948, "temperature": 80.0},
            },
            normalized_state={
                "normalized_parameters": {"pressure_bar": 6.8948, "temperature_c": 80.0},
                "identity_records": {
                    "pressure": {
                        "raw_value": "100 psi",
                        "normalized_value": 6.8948,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "Umgerechnet von 100 PSI -> 6.8948 bar",
                    },
                    "temperature": {
                        "raw_value": "80°C",
                        "normalized_value": 80.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_temperature_c",
                    },
                    "medium": {
                        "raw_value": "Hydrauliköl",
                        "normalized_value": "Öl",
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_medium",
                    },
                },
            },
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"]["candidate_id"] == "fkm::f1"
        assert artifact["integrity_status"] == "usable_with_warning"
        assert state["parameter_integrity_projection"]["warning_keys"] == ["pressure"]
        assert INTEGRITY_WARNING_PREFIX in artifact["rationale_summary"]

    def test_unit_ambiguous_integrity_withholds_normal_candidate_projection(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
            },
            normalized_state={
                "normalized_parameters": {"pressure_bar": 10.0, "temperature_c": 80.0},
                "identity_records": {
                    "pressure": {
                        "raw_value": "10 bar",
                        "normalized_value": 10.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_pressure_bar",
                    },
                    "temperature": {
                        "raw_value": "80 grad",
                        "normalized_value": 80.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_temperature_c",
                    },
                    "medium": {
                        "raw_value": "Hydrauliköl",
                        "normalized_value": "Öl",
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_medium",
                    },
                },
            },
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"] is None
        assert artifact["readiness_status"] == "integrity_unusable"
        assert artifact["integrity_status"] == "unusable_until_clarified"
        assert state["parameter_integrity_projection"]["blocking_keys"] == ["temperature"]

    def test_domain_warning_keeps_candidate_projection_but_marks_scope_warning(self):
        from app.agent.agent.selection import build_selection_state, DOMAIN_WARNING_PREFIX

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"]["candidate_id"] == "fkm::f1"
        assert artifact["domain_scope_status"] == "in_domain_with_warning"
        assert artifact["threshold_status"] == "warning_thresholds"
        assert DOMAIN_WARNING_PREFIX in artifact["rationale_summary"]

    def test_out_of_domain_withholds_normal_candidate_projection(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 220.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"] is None
        assert artifact["readiness_status"] == "domain_scope_blocked"
        assert artifact["domain_scope_status"] == "out_of_domain_scope"

    def test_threshold_escalation_withholds_normal_candidate_projection(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 300.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )

        artifact = state["recommendation_artifact"]
        assert artifact["candidate_projection"] is None
        assert artifact["domain_scope_status"] == "escalation_required"
        assert artifact["readiness_status"] == "domain_scope_blocked"


class TestReviewEscalationProjection:
    def test_review_required_projects_review_pending(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "review_pending"
        assert projection["evidence_status"] == "thin_evidence"
        assert projection["provenance_refs"] == ["source::fc_1"]
        assert projection["review_meaningful"] is True
        assert projection["handover_possible"] is True

    def test_no_evidence_projects_withheld_no_evidence(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            evidence_available=False,
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "withheld_no_evidence"
        assert projection["evidence_status"] == "thin_evidence"
        assert projection["provenance_refs"] == ["source::fc_1"]
        assert projection["review_meaningful"] is False

    def test_demo_data_projects_withheld_demo_data(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            demo_data_present=True,
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "withheld_demo_data"
        assert projection["evidence_status"] == "thin_evidence"
        assert projection["handover_possible"] is False

    def test_missing_core_inputs_project_withheld_missing_core_inputs(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={"medium_profile": {"name": "Hydrauliköl"}, "operating_conditions": {"pressure": 10.0}},
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "withheld_missing_core_inputs"
        assert projection["evidence_status"] == "thin_evidence"
        assert "temperature" in projection["missing_items"]

    def test_multiple_viable_candidates_project_ambiguous_but_reviewable(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[
                _qualified_fact_card("fc_1", grade_name="F1"),
                _qualified_fact_card("fc_2", grade_name="F2"),
            ],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "ambiguous_but_reviewable"
        assert projection["review_meaningful"] is True
        assert projection["ambiguous_candidate_ids"] == ["fkm::f1", "fkm::f2"]
        assert projection["evidence_status"] == "grounded_evidence"
        assert projection["provenance_refs"] == ["source::fc_1", "source::fc_2"]

    def test_blocked_no_viable_candidates_project_escalation_needed(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1", temp_max=60.0)],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "escalation_needed"
        assert projection["evidence_status"] == "thin_evidence"
        assert projection["handover_possible"] is True

    def test_open_conflict_projects_escalation_needed_without_handover(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state={**_green_governance(), "conflicts": [{"field": "pressure", "type": "parameter_conflict", "severity": "CRITICAL"}]},
            asserted_state=_full_asserted(),
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 10 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 10.0}, "identity_records": {}},
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "escalation_needed"
        assert projection["conflict_status"] == "unresolved_conflict"
        assert projection["affected_keys"] == ["pressure"]
        assert projection["handover_possible"] is False

    def test_integrity_unusable_projects_escalation_needed(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
            },
            normalized_state={
                "normalized_parameters": {"pressure_bar": 10.0, "temperature_c": 80.0},
                "identity_records": {
                    "pressure": {
                        "raw_value": "10 bar",
                        "normalized_value": 10.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_pressure_bar",
                    },
                    "temperature": {
                        "raw_value": "80 grad",
                        "normalized_value": 80.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_temperature_c",
                    },
                },
            },
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "escalation_needed"
        assert projection["integrity_status"] == "unusable_until_clarified"
        assert "temperature" in projection["affected_keys"]

    def test_domain_scope_block_projects_escalation_needed(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 300.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        projection = state["review_escalation_projection"]
        assert projection["status"] == "escalation_needed"
        assert "Betriebsbedingungen" in projection["reason"] or "Anwendungsbereich" in projection["reason"]


class TestClarificationEvidenceBinding:
    def test_clarification_keeps_missing_inputs_separate_from_evidence_absence(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={"medium_profile": {"name": "Hydrauliköl"}, "operating_conditions": {}},
        )
        projection = state["clarification_projection"]
        assert projection["clarification_still_meaningful"] is True
        assert projection["next_question_key"] == "pressure"
        assert projection["evidence_status"] == "thin_evidence"
        assert projection["provenance_refs"] == ["source::fc_1"]

    def test_clarification_pauses_when_no_evidence_is_canonical_blocker(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            evidence_available=False,
        )
        projection = state["clarification_projection"]
        assert projection["clarification_still_meaningful"] is False
        assert projection["evidence_status"] == "thin_evidence"
        assert projection["reason_if_not"]

    def test_conflict_and_no_evidence_prefer_no_evidence_over_clarification(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state={**_green_governance(), "conflicts": [{"field": "pressure", "type": "parameter_conflict", "severity": "CRITICAL"}]},
            asserted_state=_full_asserted(),
            evidence_available=False,
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 10 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 10.0}, "identity_records": {}},
        )
        assert state["review_escalation_projection"]["status"] == "withheld_no_evidence"
        assert state["clarification_projection"]["clarification_still_meaningful"] is False

    def test_integrity_unusable_drives_targeted_clarification(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
            },
            normalized_state={
                "normalized_parameters": {"pressure_bar": 10.0, "temperature_c": 80.0},
                "identity_records": {
                    "pressure": {
                        "raw_value": "10 bar",
                        "normalized_value": 10.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_pressure_bar",
                    },
                    "temperature": {
                        "raw_value": "80 grad",
                        "normalized_value": 80.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_temperature_c",
                    },
                },
            },
        )
        projection = state["clarification_projection"]
        assert projection["integrity_status"] == "unusable_until_clarified"
        assert projection["next_question_key"] == "temperature"

    def test_domain_scope_block_pauses_clarification(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 300.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        projection = state["clarification_projection"]
        assert projection["clarification_still_meaningful"] is False
        assert "Betriebsbedingungen" in projection["reason_if_not"] or "Anwendungsbereich" in projection["reason_if_not"]


class TestUserFacingOutputContract:
    def test_clarification_case_projects_clarification_needed(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={"medium_profile": {"name": "Hydrauliköl"}, "operating_conditions": {}},
        )
        assert state["user_facing_output_projection"]["status"] == "clarification_needed"
        contract = state["output_contract_projection"]
        assert contract["output_status"] == "clarification_needed"
        assert contract["next_user_action"] == "answer_next_question"
        assert contract["suppress_recommendation_details"] is True

    def test_review_case_projects_withheld_review(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )
        assert state["user_facing_output_projection"]["status"] == "withheld_review"
        contract = state["output_contract_projection"]
        assert contract["output_status"] == "withheld_review"
        assert contract["next_user_action"] == "human_review"
        assert contract["suppress_recommendation_details"] is True

    def test_no_evidence_case_projects_withheld_no_evidence(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            evidence_available=False,
        )
        assert state["user_facing_output_projection"]["status"] == "withheld_no_evidence"
        contract = state["output_contract_projection"]
        assert contract["output_status"] == "withheld_no_evidence"
        assert contract["next_user_action"] == "obtain_qualified_evidence"
        assert contract["suppress_recommendation_details"] is True

    def test_out_of_domain_case_projects_withheld_domain_block(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 220.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        assert state["user_facing_output_projection"]["status"] == "withheld_domain_block"
        contract = state["output_contract_projection"]
        assert contract["output_status"] == "withheld_domain_block"
        assert contract["next_user_action"] == "engineering_escalation"
        assert contract["suppress_recommendation_details"] is True

    def test_releasable_case_projects_governed_non_binding_result(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        assert state["user_facing_output_projection"]["status"] == "governed_non_binding_result"
        contract = state["output_contract_projection"]
        assert contract["output_status"] == "governed_non_binding_result"
        assert contract["next_user_action"] == "confirmed_result_review"
        assert contract["suppress_recommendation_details"] is False


class TestProjectionInvariants:
    def test_consistent_releasable_state_has_no_invariant_violations(self):
        from app.agent.agent.selection import build_selection_state, project_projection_invariants

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )

        projection = project_projection_invariants(
            recommendation_artifact=state["recommendation_artifact"],
            review_escalation_projection=state["review_escalation_projection"],
            clarification_projection=state["clarification_projection"],
            evidence_provenance_projection=state["evidence_provenance_projection"],
            conflict_status_projection=state["conflict_status_projection"],
            parameter_integrity_projection=state["parameter_integrity_projection"],
            domain_scope_projection=state["domain_scope_projection"],
            output_contract_projection=state["output_contract_projection"],
        )

        assert projection == {"invariant_ok": True, "invariant_violations": []}

    def test_projection_invariants_report_deterministic_violations_for_impossible_combo(self):
        from app.agent.agent.selection import project_projection_invariants

        projection = project_projection_invariants(
            recommendation_artifact={
                "candidate_projection": {"candidate_id": "ptfe::f1"},
                "readiness_status": "releasable",
            },
            review_escalation_projection={"status": "review_pending"},
            clarification_projection={"clarification_still_meaningful": True},
            evidence_provenance_projection={"status": "no_evidence"},
            conflict_status_projection={"conflict_still_open": True},
            parameter_integrity_projection={"integrity_status": "unusable_until_clarified"},
            domain_scope_projection={"status": "out_of_domain_scope"},
            output_contract_projection={
                "output_status": "governed_non_binding_result",
                "suppress_recommendation_details": True,
            },
        )

        assert projection["invariant_ok"] is False
        assert projection["invariant_violations"] == [
            "governed_result_cannot_suppress_recommendation_details",
            "governed_result_conflicts_with_blocking_projection",
            "unresolved_conflict_cannot_surface_technical_preselection",
            "releasable_readiness_conflicts_with_blocking_projection",
        ]

    def test_build_selection_state_downgrades_when_invariant_violation_is_introduced(self):
        from app.agent.agent.selection import build_selection_state

        def _contradictory_contract(**_: object) -> dict:
            return {
                "output_status": "governed_non_binding_result",
                "allowed_surface_claims": ["non_binding_result"],
                "next_user_action": "confirmed_result_review",
                "visible_warning_flags": [],
                "suppress_recommendation_details": True,
            }

        with patch(
            "app.agent.runtime.selection.build_output_contract_projection",
            side_effect=_contradictory_contract,
        ):
            state = build_selection_state(
                relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
                cycle_state={"analysis_cycle_id": "cycle-1"},
                governance_state=_green_governance(),
                asserted_state=_full_asserted(),
            )

        assert state["projection_invariant_projection"]["invariant_ok"] is False
        assert state["projection_invariant_projection"]["invariant_violations"] == [
            "governed_result_cannot_suppress_recommendation_details",
        ]
        assert state["output_contract_projection"]["output_status"] == "withheld_escalation"
        assert state["output_contract_projection"]["suppress_recommendation_details"] is True
        assert state["output_contract_projection"]["allowed_surface_claims"] == [
            "withheld",
            "state_invariant_violation",
        ]
        assert "invariant_violation" in state["output_contract_projection"]["visible_warning_flags"]
        assert state["recommendation_artifact"]["candidate_projection"] is None
        assert state["recommendation_artifact"]["readiness_status"] == "invariant_blocked"
        assert state["output_blocked"] is True


class TestStateTraceAuditProjection:
    def test_clarification_case_projects_trace_reason(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={"medium_profile": {"name": "Hydrauliköl"}, "operating_conditions": {}},
        )
        trace = state["state_trace_audit_projection"]
        assert trace["primary_status_reason"] == "clarification_missing_inputs"
        assert trace["contributing_reasons"] == ["missing_inputs"]
        assert trace["blocking_reasons"] == []

    def test_review_case_projects_trace_reason(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )
        trace = state["state_trace_audit_projection"]
        assert trace["primary_status_reason"] == "review_pending"
        assert "review_pending" in trace["blocking_reasons"]
        assert "review_pending" in trace["contributing_reasons"]

    def test_escalation_case_projects_trace_reason(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1", temp_max=60.0)],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        trace = state["state_trace_audit_projection"]
        assert trace["primary_status_reason"] == "escalation_no_viable_candidates"
        assert trace["blocking_reasons"] == ["no_viable_candidates"]

    def test_invariant_blocked_case_projects_trace_reason(self):
        from app.agent.agent.selection import build_selection_state

        def _contradictory_contract(**_: object) -> dict:
            return {
                "output_status": "governed_non_binding_result",
                "allowed_surface_claims": ["non_binding_result"],
                "next_user_action": "confirmed_result_review",
                "visible_warning_flags": [],
                "suppress_recommendation_details": True,
            }

        with patch(
            "app.agent.runtime.selection.build_output_contract_projection",
            side_effect=_contradictory_contract,
        ):
            state = build_selection_state(
                relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
                cycle_state={"analysis_cycle_id": "cycle-1"},
                governance_state=_green_governance(),
                asserted_state=_full_asserted(),
            )

        trace = state["state_trace_audit_projection"]
        assert trace["primary_status_reason"] == "invariant_blocked"
        assert trace["blocking_reasons"] == ["invariant_blocked"]
        assert "governed_result_cannot_suppress_recommendation_details" in trace["contributing_reasons"]
        assert "invariant_violation" in trace["trace_flags"]

    def test_releasable_governed_case_projects_trace_reason(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        trace = state["state_trace_audit_projection"]
        assert trace["primary_status_reason"] == "governed_releasable_result"
        assert trace["blocking_reasons"] == []
        assert "thin_evidence" in trace["trace_flags"]

    def test_trace_helpers_expose_primary_reason_and_blockers(self):
        from app.agent.agent.selection import get_primary_trace_reason, is_blocked_by_trace

        trace = {
            "primary_status_reason": "review_pending",
            "contributing_reasons": ["review_pending"],
            "blocking_reasons": ["review_pending"],
            "trace_flags": [],
        }
        assert get_primary_trace_reason(trace) == "review_pending"
        assert is_blocked_by_trace(trace) is True
        assert is_blocked_by_trace(trace, "review_pending") is True
        assert is_blocked_by_trace(trace, "no_evidence") is False


class TestCaseSummaryProjection:
    def test_releasable_case_projects_summary(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        summary = state["case_summary_projection"]
        assert summary["current_case_status"] == "governed_non_binding_result"
        assert summary["confirmed_core_fields"] == ["medium", "pressure", "temperature"]
        assert summary["missing_core_fields"] == []
        assert summary["active_blockers"] == []
        assert summary["next_step"] == "confirmed_result_review"

    def test_clarification_case_projects_summary(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={"medium_profile": {"name": "Hydrauliköl"}, "operating_conditions": {}},
        )
        summary = state["case_summary_projection"]
        assert summary["current_case_status"] == "clarification_needed"
        assert summary["confirmed_core_fields"] == ["medium"]
        assert summary["missing_core_fields"] == ["pressure", "temperature"]
        assert summary["active_blockers"] == []
        assert summary["next_step"] == "answer_next_question"

    def test_review_case_projects_summary(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )
        summary = state["case_summary_projection"]
        assert summary["current_case_status"] == "withheld_review"
        assert summary["active_blockers"] == ["review_pending"]
        assert summary["next_step"] == "human_review"

    def test_escalation_case_projects_summary(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1", temp_max=60.0)],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        summary = state["case_summary_projection"]
        assert summary["current_case_status"] == "withheld_escalation"
        assert summary["active_blockers"] == ["no_viable_candidates"]
        assert summary["next_step"] == "engineering_escalation"

    def test_invariant_blocked_case_projects_summary(self):
        from app.agent.agent.selection import build_selection_state

        def _contradictory_contract(**_: object) -> dict:
            return {
                "output_status": "governed_non_binding_result",
                "allowed_surface_claims": ["non_binding_result"],
                "next_user_action": "confirmed_result_review",
                "visible_warning_flags": [],
                "suppress_recommendation_details": True,
            }

        with patch(
            "app.agent.runtime.selection.build_output_contract_projection",
            side_effect=_contradictory_contract,
        ):
            state = build_selection_state(
                relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
                cycle_state={"analysis_cycle_id": "cycle-1"},
                governance_state=_green_governance(),
                asserted_state=_full_asserted(),
            )

        summary = state["case_summary_projection"]
        assert summary["current_case_status"] == "withheld_escalation"
        assert summary["active_blockers"] == ["invariant_blocked"]
        assert summary["next_step"] == "engineering_escalation"

    def test_summary_helpers_expose_status_step_and_blockers(self):
        from app.agent.agent.selection import get_case_status, get_next_case_step, has_active_blockers

        summary = {
            "current_case_status": "withheld_review",
            "confirmed_core_fields": ["medium", "pressure", "temperature"],
            "missing_core_fields": [],
            "active_blockers": ["review_pending"],
            "next_step": "human_review",
        }
        assert get_case_status(summary) == "withheld_review"
        assert get_next_case_step(summary) == "human_review"
        assert has_active_blockers(summary) is True


class TestActionabilityProjection:
    def test_clarification_case_projects_actionability(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={"medium_profile": {"name": "Hydrauliköl"}, "operating_conditions": {}},
        )
        projection = state["actionability_projection"]
        assert projection["actionability_status"] == "input_required"
        assert projection["primary_allowed_action"] == "provide_missing_input"
        assert projection["next_expected_user_action"] == "answer_next_question"
        assert "consume_governed_result" in projection["blocked_actions"]

    def test_review_case_projects_actionability(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )
        projection = state["actionability_projection"]
        assert projection["actionability_status"] == "review_pending"
        assert projection["primary_allowed_action"] == "await_review"
        assert projection["next_expected_user_action"] == "human_review"

    def test_escalation_case_projects_actionability(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1", temp_max=60.0)],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        projection = state["actionability_projection"]
        assert projection["actionability_status"] == "escalation_required"
        assert projection["primary_allowed_action"] == "escalate_engineering"
        assert projection["next_expected_user_action"] == "engineering_escalation"

    def test_releasable_governed_case_projects_actionability(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        projection = state["actionability_projection"]
        assert projection["actionability_status"] == "result_available"
        assert projection["primary_allowed_action"] == "consume_governed_result"
        assert projection["next_expected_user_action"] == "confirmed_result_review"

    def test_handoverable_but_not_releasable_projects_actionability(self):
        from app.agent.agent.selection import build_actionability_projection

        projection = build_actionability_projection(
            case_summary_projection={
                "current_case_status": "withheld_review",
                "confirmed_core_fields": ["medium", "pressure", "temperature"],
                "missing_core_fields": [],
                "active_blockers": ["candidate_ambiguity"],
                "next_step": "human_review",
            },
            output_contract_projection={
                "output_status": "withheld_review",
                "allowed_surface_claims": ["withheld", "review_required"],
                "next_user_action": "human_review",
                "visible_warning_flags": [],
                "suppress_recommendation_details": True,
            },
            review_escalation_projection={
                "status": "ambiguous_but_reviewable",
                "handover_possible": True,
            },
            clarification_projection={"clarification_still_meaningful": False},
            projection_invariant_projection={"invariant_ok": True, "invariant_violations": []},
        )
        assert projection["actionability_status"] == "handoverable_restricted"
        assert projection["primary_allowed_action"] == "prepare_handover"
        assert projection["next_expected_user_action"] == "human_review"

    def test_invariant_blocked_case_projects_actionability(self):
        from app.agent.agent.selection import build_selection_state

        def _contradictory_contract(**_: object) -> dict:
            return {
                "output_status": "governed_non_binding_result",
                "allowed_surface_claims": ["non_binding_result"],
                "next_user_action": "confirmed_result_review",
                "visible_warning_flags": [],
                "suppress_recommendation_details": True,
            }

        with patch(
            "app.agent.runtime.selection.build_output_contract_projection",
            side_effect=_contradictory_contract,
        ):
            state = build_selection_state(
                relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
                cycle_state={"analysis_cycle_id": "cycle-1"},
                governance_state=_green_governance(),
                asserted_state=_full_asserted(),
            )

        projection = state["actionability_projection"]
        assert projection["actionability_status"] == "blocked"
        assert projection["primary_allowed_action"] == "no_action_until_clarified"
        assert projection["next_expected_user_action"] == "engineering_escalation"

    def test_actionability_helpers_expose_primary_action_and_blockers(self):
        from app.agent.agent.selection import (
            get_primary_allowed_action,
            get_next_expected_user_action,
            is_action_blocked,
        )

        projection = {
            "actionability_status": "review_pending",
            "primary_allowed_action": "await_review",
            "blocked_actions": ["provide_missing_input", "consume_governed_result"],
            "next_expected_user_action": "human_review",
        }
        assert get_primary_allowed_action(projection) == "await_review"
        assert get_next_expected_user_action(projection) == "human_review"
        assert is_action_blocked(projection, "consume_governed_result") is True
        assert is_action_blocked(projection, "await_review") is False


class TestStateDeltaProjection:
    def test_single_parameter_flip_projects_neutral_to_warning(self):
        from app.agent.agent.selection import build_state_delta_projection

        previous_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
        )
        current_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
            domain_status="in_domain_with_warning",
            threshold_status="threshold_warning",
        )

        projection = build_state_delta_projection(
            previous_selection_state=previous_state,
            current_selection_state=current_state,
        )
        assert projection["changed_keys"] == ["domain_scope_status", "threshold_status"]
        assert projection["primary_delta_reason"] == "threshold_scope_changed"
        assert projection["delta_direction"] == "degraded"
        assert projection["changed_statuses"]["domain_scope_status"]["delta"] == "neutral_to_warning"

    def test_single_parameter_flip_projects_warning_to_blocked(self):
        from app.agent.agent.selection import build_state_delta_projection

        previous_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
            domain_status="in_domain_with_warning",
            threshold_status="threshold_warning",
        )
        current_state = _delta_selection_state(
            case_status="withheld_escalation",
            output_status="withheld_escalation",
            next_step="engineering_escalation",
            actionability_status="escalation_required",
            primary_allowed_action="escalate_engineering",
            blocked_actions=["consume_governed_result", "await_review"],
            active_blockers=["domain_threshold_blocked"],
            domain_status="escalation_required",
            threshold_status="threshold_blocking",
        )

        projection = build_state_delta_projection(
            previous_selection_state=previous_state,
            current_selection_state=current_state,
        )
        assert projection["primary_delta_reason"] == "threshold_scope_changed"
        assert projection["delta_direction"] == "more_blocked"
        assert projection["changed_statuses"]["domain_scope_status"]["delta"] == "warning_to_blocked"
        assert projection["changed_statuses"]["output_status"]["to"] == "withheld_escalation"
        assert "blocked_actions" in projection["changed_keys"]

    def test_conflict_correction_projects_improved_delta(self):
        from app.agent.agent.selection import build_state_delta_projection

        previous_state = _delta_selection_state(
            case_status="withheld_escalation",
            output_status="withheld_escalation",
            next_step="engineering_escalation",
            actionability_status="escalation_required",
            primary_allowed_action="escalate_engineering",
            blocked_actions=["consume_governed_result", "await_review"],
            active_blockers=["conflict_open"],
            conflict_status="unresolved_conflict",
        )
        current_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
            conflict_status="no_conflict",
        )

        projection = build_state_delta_projection(
            previous_selection_state=previous_state,
            current_selection_state=current_state,
        )
        assert projection["primary_delta_reason"] == "conflict_status_changed"
        assert projection["delta_direction"] == "improved"
        assert projection["changed_statuses"]["conflict_status"]["delta"] == "unresolved_conflict_to_no_conflict"
        assert projection["changed_statuses"]["output_status"]["delta"] == "withheld_escalation_to_governed_non_binding_result"

    def test_summary_and_actionability_changes_are_tracked_without_noise(self):
        from app.agent.agent.selection import build_state_delta_projection

        previous_state = _delta_selection_state(
            case_status="clarification_needed",
            output_status="clarification_needed",
            next_step="answer_next_question",
            actionability_status="input_required",
            primary_allowed_action="provide_missing_input",
            blocked_actions=["await_review", "consume_governed_result"],
        )
        current_state = _delta_selection_state(
            case_status="withheld_review",
            output_status="withheld_review",
            next_step="human_review",
            actionability_status="review_pending",
            primary_allowed_action="await_review",
            blocked_actions=["provide_missing_input", "consume_governed_result"],
            active_blockers=["review_pending"],
        )
        current_state["recommendation_artifact"]["rationale_summary"] = "Internal note that must not affect the delta."

        projection = build_state_delta_projection(
            previous_selection_state=previous_state,
            current_selection_state=current_state,
        )
        assert "output_status" in projection["changed_keys"]
        assert "next_step" in projection["changed_keys"]
        assert "blocked_actions" in projection["changed_keys"]
        assert "rationale_summary" not in projection["changed_keys"]
        assert projection["changed_statuses"]["next_step"]["delta"] == "answer_next_question_to_human_review"

    def test_irrelevant_internal_change_projects_no_delta(self):
        from app.agent.agent.selection import build_state_delta_projection

        previous_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
        )
        current_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
        )
        current_state["recommendation_artifact"]["rationale_summary"] = "Different internal rationale."

        projection = build_state_delta_projection(
            previous_selection_state=previous_state,
            current_selection_state=current_state,
        )
        assert projection["changed_keys"] == []
        assert projection["primary_delta_reason"] == "no_relevant_change"
        assert projection["delta_direction"] == "unchanged"

    def test_delta_helpers_expose_case_actionability_and_threshold_transitions(self):
        from app.agent.agent.selection import compare_actionability, compare_case_status, compare_threshold_scope

        previous_summary = {"current_case_status": "withheld_review"}
        current_summary = {"current_case_status": "governed_non_binding_result"}
        previous_actionability = {"actionability_status": "review_pending"}
        current_actionability = {"actionability_status": "result_available"}

        assert compare_case_status(previous_summary, current_summary) == "withheld_review_to_governed_non_binding_result"
        assert compare_actionability(previous_actionability, current_actionability) == "review_pending_to_result_available"
        assert compare_threshold_scope(
            previous_threshold_projection={"threshold_status": "threshold_warning"},
            current_threshold_projection={"threshold_status": "threshold_blocking"},
            previous_domain_scope_projection={"status": "in_domain_with_warning"},
            current_domain_scope_projection={"status": "escalation_required"},
        ) == "warning_to_blocked"


class TestStructuredSnapshotContract:
    def test_releasable_case_projects_snapshot_contract(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        snapshot = state["structured_snapshot_contract"]
        assert snapshot == {
            "case_status": "governed_non_binding_result",
            "output_status": "governed_non_binding_result",
            "primary_reason": "governed_releasable_result",
            "next_step": "confirmed_result_review",
            "primary_allowed_action": "consume_governed_result",
            "active_blockers": [],
        }

    def test_review_case_projects_snapshot_contract(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )
        snapshot = state["structured_snapshot_contract"]
        assert snapshot["case_status"] == "withheld_review"
        assert snapshot["output_status"] == "withheld_review"
        assert snapshot["primary_reason"] == "review_pending"
        assert snapshot["next_step"] == "human_review"
        assert snapshot["primary_allowed_action"] == "await_review"
        assert snapshot["active_blockers"] == ["review_pending"]

    def test_clarification_case_projects_snapshot_contract(self):
        from app.agent.agent.selection import build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={"medium_profile": {"name": "Hydrauliköl"}, "operating_conditions": {}},
        )
        snapshot = state["structured_snapshot_contract"]
        assert snapshot["case_status"] == "clarification_needed"
        assert snapshot["output_status"] == "clarification_needed"
        assert snapshot["primary_reason"] == "clarification_missing_inputs"
        assert snapshot["next_step"] == "answer_next_question"
        assert snapshot["primary_allowed_action"] == "provide_missing_input"

    def test_domain_block_case_projects_snapshot_contract(self):
        from app.agent.agent.selection import build_structured_snapshot

        state = _delta_selection_state(
            case_status="withheld_domain_block",
            output_status="withheld_domain_block",
            next_step="engineering_escalation",
            actionability_status="escalation_required",
            primary_allowed_action="escalate_engineering",
            blocked_actions=["consume_governed_result", "await_review"],
            active_blockers=["domain_blocked"],
            domain_status="out_of_domain_scope",
        )
        state["state_trace_audit_projection"] = {
            "primary_status_reason": "domain_scope_blocked",
            "contributing_reasons": ["domain_blocked"],
            "blocking_reasons": ["domain_blocked"],
            "trace_flags": [],
        }

        snapshot = build_structured_snapshot(state)
        assert snapshot == {
            "case_status": "withheld_domain_block",
            "output_status": "withheld_domain_block",
            "primary_reason": "domain_scope_blocked",
            "next_step": "engineering_escalation",
            "primary_allowed_action": "escalate_engineering",
            "active_blockers": ["domain_blocked"],
        }


class TestStructuredSnapshotComparisonContract:
    def test_review_to_releasable_projects_comparison_contract(self):
        from app.agent.agent.selection import (
            build_state_delta_projection,
            build_structured_snapshot,
            compare_structured_snapshots,
        )

        previous_state = _delta_selection_state(
            case_status="withheld_review",
            output_status="withheld_review",
            next_step="human_review",
            actionability_status="review_pending",
            primary_allowed_action="await_review",
            blocked_actions=["consume_governed_result", "provide_missing_input"],
            active_blockers=["review_pending"],
        )
        previous_state["state_trace_audit_projection"] = {
            "primary_status_reason": "review_pending",
            "contributing_reasons": ["review_pending"],
            "blocking_reasons": ["review_pending"],
            "trace_flags": [],
        }
        current_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "provide_missing_input"],
        )
        current_state["state_trace_audit_projection"] = {
            "primary_status_reason": "governed_releasable_result",
            "contributing_reasons": [],
            "blocking_reasons": [],
            "trace_flags": [],
        }

        comparison = compare_structured_snapshots(
            build_structured_snapshot(previous_state),
            build_structured_snapshot(current_state),
            delta_projection=build_state_delta_projection(
                previous_selection_state=previous_state,
                current_selection_state=current_state,
            ),
        )
        assert comparison["from_status"] == "withheld_review"
        assert comparison["to_status"] == "governed_non_binding_result"
        assert comparison["changed_actions"]["from_primary_allowed_action"] == "await_review"
        assert comparison["changed_actions"]["to_primary_allowed_action"] == "consume_governed_result"
        assert comparison["changed_blockers"] == {"added": [], "removed": ["review_pending"]}
        assert comparison["primary_delta_reason"] == "output_status_changed"
        assert comparison["delta_direction"] == "improved"

    def test_warning_to_blocked_projects_comparison_contract(self):
        from app.agent.agent.selection import (
            build_state_delta_projection,
            build_structured_snapshot,
            compare_structured_snapshots,
        )

        previous_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
            domain_status="in_domain_with_warning",
            threshold_status="threshold_warning",
        )
        previous_state["state_trace_audit_projection"] = {
            "primary_status_reason": "governed_releasable_result",
            "contributing_reasons": [],
            "blocking_reasons": [],
            "trace_flags": ["domain_warning"],
        }
        current_state = _delta_selection_state(
            case_status="withheld_escalation",
            output_status="withheld_escalation",
            next_step="engineering_escalation",
            actionability_status="escalation_required",
            primary_allowed_action="escalate_engineering",
            blocked_actions=["consume_governed_result", "await_review"],
            active_blockers=["domain_threshold_blocked"],
            domain_status="escalation_required",
            threshold_status="threshold_blocking",
        )
        current_state["state_trace_audit_projection"] = {
            "primary_status_reason": "escalation_domain_threshold",
            "contributing_reasons": ["domain_threshold_blocked"],
            "blocking_reasons": ["domain_threshold_blocked"],
            "trace_flags": [],
        }

        comparison = compare_structured_snapshots(
            build_structured_snapshot(previous_state),
            build_structured_snapshot(current_state),
            delta_projection=build_state_delta_projection(
                previous_selection_state=previous_state,
                current_selection_state=current_state,
            ),
        )
        assert comparison["from_status"] == "governed_non_binding_result"
        assert comparison["to_status"] == "withheld_escalation"
        assert comparison["changed_actions"]["action_changed"] is True
        assert comparison["changed_blockers"] == {"added": ["domain_threshold_blocked"], "removed": []}
        assert comparison["primary_delta_reason"] == "threshold_scope_changed"
        assert comparison["delta_direction"] == "more_blocked"

    def test_clarification_to_review_projects_comparison_contract(self):
        from app.agent.agent.selection import (
            build_state_delta_projection,
            build_structured_snapshot,
            compare_structured_snapshots,
        )

        previous_state = _delta_selection_state(
            case_status="clarification_needed",
            output_status="clarification_needed",
            next_step="answer_next_question",
            actionability_status="input_required",
            primary_allowed_action="provide_missing_input",
            blocked_actions=["await_review", "consume_governed_result"],
        )
        previous_state["state_trace_audit_projection"] = {
            "primary_status_reason": "clarification_missing_inputs",
            "contributing_reasons": ["missing_inputs"],
            "blocking_reasons": [],
            "trace_flags": [],
        }
        current_state = _delta_selection_state(
            case_status="withheld_review",
            output_status="withheld_review",
            next_step="human_review",
            actionability_status="review_pending",
            primary_allowed_action="await_review",
            blocked_actions=["provide_missing_input", "consume_governed_result"],
            active_blockers=["review_pending"],
        )
        current_state["state_trace_audit_projection"] = {
            "primary_status_reason": "review_pending",
            "contributing_reasons": ["review_pending"],
            "blocking_reasons": ["review_pending"],
            "trace_flags": [],
        }

        comparison = compare_structured_snapshots(
            build_structured_snapshot(previous_state),
            build_structured_snapshot(current_state),
            delta_projection=build_state_delta_projection(
                previous_selection_state=previous_state,
                current_selection_state=current_state,
            ),
        )
        assert comparison["from_status"] == "clarification_needed"
        assert comparison["to_status"] == "withheld_review"
        assert comparison["changed_actions"]["from_primary_allowed_action"] == "provide_missing_input"
        assert comparison["changed_actions"]["to_primary_allowed_action"] == "await_review"
        assert comparison["changed_blockers"] == {"added": ["review_pending"], "removed": []}
        assert comparison["primary_delta_reason"] == "output_status_changed"
        assert comparison["delta_direction"] == "degraded"

    def test_unchanged_core_status_projects_stable_comparison_contract(self):
        from app.agent.agent.selection import (
            build_state_delta_projection,
            build_structured_snapshot,
            compare_structured_snapshots,
        )

        previous_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
        )
        previous_state["state_trace_audit_projection"] = {
            "primary_status_reason": "governed_releasable_result",
            "contributing_reasons": [],
            "blocking_reasons": [],
            "trace_flags": [],
        }
        current_state = _delta_selection_state(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            actionability_status="result_available",
            primary_allowed_action="consume_governed_result",
            blocked_actions=["await_review", "escalate_engineering"],
        )
        current_state["state_trace_audit_projection"] = {
            "primary_status_reason": "governed_releasable_result",
            "contributing_reasons": [],
            "blocking_reasons": [],
            "trace_flags": ["internal_warning_ignored"],
        }

        comparison = compare_structured_snapshots(
            build_structured_snapshot(previous_state),
            build_structured_snapshot(current_state),
            delta_projection=build_state_delta_projection(
                previous_selection_state=previous_state,
                current_selection_state=current_state,
            ),
        )
        assert comparison["from_status"] == "governed_non_binding_result"
        assert comparison["to_status"] == "governed_non_binding_result"
        assert comparison["changed_actions"]["action_changed"] is False
        assert comparison["changed_blockers"] == {"added": [], "removed": []}
        assert comparison["primary_delta_reason"] == "no_relevant_change"
        assert comparison["delta_direction"] == "unchanged"


class TestFinalReplyRecommendationCoupling:
    def test_artifact_absent_returns_safeguarded_reply(self):
        from app.agent.agent.selection import build_final_reply, SAFEGUARDED_WITHHELD_REPLY

        state = _minimal_selection_state()
        state["recommendation_artifact"] = None
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert SAFEGUARDED_WITHHELD_REPLY in reply

    def test_invariant_violation_returns_safe_reply_without_recommendation_details(self):
        from app.agent.agent.selection import build_final_reply, INVARIANT_BLOCKED_REPLY

        state = _minimal_selection_state()
        state["selection_status"] = "winner_selected"
        state["winner_candidate_id"] = "ptfe::f1"
        state["output_blocked"] = False
        state["recommendation_artifact"] = {
            **state["recommendation_artifact"],
            "selection_status": "winner_selected",
            "winner_candidate_id": "ptfe::f1",
            "candidate_projection": {"candidate_id": "ptfe::f1"},
            "readiness_status": "releasable",
            "rationale_summary": "Deterministische Candidate-Projektion: PTFE F1.",
            "output_blocked": False,
        }
        state["review_escalation_projection"] = {
            **state["review_escalation_projection"],
            "status": "review_pending",
        }
        state["output_contract_projection"] = {
            "output_status": "governed_non_binding_result",
            "allowed_surface_claims": ["non_binding_result"],
            "next_user_action": "confirmed_result_review",
            "visible_warning_flags": [],
            "suppress_recommendation_details": True,
        }
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert INVARIANT_BLOCKED_REPLY in reply
        assert "Deterministische Candidate-Projektion" not in reply

    def test_review_reply_stays_consistent_with_trace_reason(self):
        from app.agent.agent.selection import build_final_reply, REVIEW_PENDING_REPLY

        state = _minimal_selection_state()
        state["state_trace_audit_projection"] = {
            "primary_status_reason": "review_pending",
            "contributing_reasons": ["review_pending"],
            "blocking_reasons": ["review_pending"],
            "trace_flags": [],
        }
        state["output_contract_projection"] = {
            "output_status": "withheld_review",
            "allowed_surface_claims": ["withheld", "review_required"],
            "next_user_action": "human_review",
            "visible_warning_flags": [],
            "suppress_recommendation_details": True,
        }
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert REVIEW_PENDING_REPLY in reply

    def test_escalation_reply_stays_consistent_with_trace_reason(self):
        from app.agent.agent.selection import build_final_reply, UNRESOLVED_CONFLICT_REPLY

        state = _minimal_selection_state()
        state["projection_invariant_projection"] = {"invariant_ok": True, "invariant_violations": []}
        state["output_contract_projection"] = {
            "output_status": "withheld_escalation",
            "allowed_surface_claims": ["withheld", "escalation_required"],
            "next_user_action": "engineering_escalation",
            "visible_warning_flags": ["conflict_open"],
            "suppress_recommendation_details": True,
        }
        state["conflict_status_projection"] = {
            "status": "unresolved_conflict",
            "affected_keys": ["pressure"],
            "previous_value_summary": "pressure=5.0",
            "current_value_summary": "pressure=10.0",
            "correction_applied": False,
            "conflict_still_open": True,
        }
        state["state_trace_audit_projection"] = {
            "primary_status_reason": "escalation_conflict_open",
            "contributing_reasons": ["conflict_open"],
            "blocking_reasons": ["conflict_open"],
            "trace_flags": ["conflict_open"],
        }
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert UNRESOLVED_CONFLICT_REPLY in reply

    def test_clarification_reply_stays_consistent_with_trace_reason(self):
        from app.agent.agent.selection import build_final_reply

        state = _minimal_selection_state()
        state["projection_invariant_projection"] = {"invariant_ok": True, "invariant_violations": []}
        state["state_trace_audit_projection"] = {
            "primary_status_reason": "clarification_missing_inputs",
            "contributing_reasons": ["missing_inputs"],
            "blocking_reasons": [],
            "trace_flags": [],
        }
        state["clarification_projection"] = {
            "missing_items": ["medium", "pressure", "temperature"],
            "next_question_key": "medium",
            "next_question_label": "Dichtungsmedium",
            "clarification_still_meaningful": True,
            "reason_if_not": "",
        }
        state["case_summary_projection"] = {
            "current_case_status": "clarification_needed",
            "confirmed_core_fields": [],
            "missing_core_fields": ["medium", "pressure", "temperature"],
            "active_blockers": [],
            "next_step": "answer_next_question",
        }
        reply = build_final_reply(state, asserted_state=None, working_profile=None)
        assert "Welches Medium soll abgedichtet werden?" in reply

    def test_releasable_reply_stays_consistent_with_trace_reason(self):
        from app.agent.agent.selection import build_final_reply, build_selection_state

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        assert state["state_trace_audit_projection"]["primary_status_reason"] == "governed_releasable_result"
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert "Orientierungsrahmen" in reply

    def test_review_reply_stays_consistent_with_case_summary_blocker(self):
        from app.agent.agent.selection import build_final_reply, REVIEW_PENDING_REPLY

        state = _minimal_selection_state()
        state["projection_invariant_projection"] = {"invariant_ok": True, "invariant_violations": []}
        state["case_summary_projection"] = {
            "current_case_status": "withheld_review",
            "confirmed_core_fields": ["medium", "pressure", "temperature"],
            "missing_core_fields": [],
            "active_blockers": ["review_pending"],
            "next_step": "human_review",
        }
        state["output_contract_projection"] = {
            "output_status": "withheld_review",
            "allowed_surface_claims": ["withheld", "review_required"],
            "next_user_action": "human_review",
            "visible_warning_flags": [],
            "suppress_recommendation_details": True,
        }
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert REVIEW_PENDING_REPLY in reply

    def test_escalation_reply_stays_consistent_with_case_summary_blocker(self):
        from app.agent.agent.selection import build_final_reply, ESCALATION_NEEDED_REPLY

        state = _minimal_selection_state()
        state["projection_invariant_projection"] = {"invariant_ok": True, "invariant_violations": []}
        state["case_summary_projection"] = {
            "current_case_status": "withheld_escalation",
            "confirmed_core_fields": ["medium", "pressure", "temperature"],
            "missing_core_fields": [],
            "active_blockers": ["no_viable_candidates"],
            "next_step": "engineering_escalation",
        }
        state["output_contract_projection"] = {
            "output_status": "withheld_escalation",
            "allowed_surface_claims": ["withheld", "escalation_required"],
            "next_user_action": "engineering_escalation",
            "visible_warning_flags": [],
            "suppress_recommendation_details": True,
        }
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert ESCALATION_NEEDED_REPLY in reply

    def test_clarification_reply_stays_consistent_with_allowed_action(self):
        from app.agent.agent.selection import build_final_reply

        state = _minimal_selection_state()
        state["projection_invariant_projection"] = {"invariant_ok": True, "invariant_violations": []}
        state["clarification_projection"] = {
            "missing_items": ["medium"],
            "next_question_key": "medium",
            "next_question_label": "Dichtungsmedium",
            "clarification_still_meaningful": True,
            "reason_if_not": "",
        }
        state["case_summary_projection"] = {
            "current_case_status": "clarification_needed",
            "confirmed_core_fields": [],
            "missing_core_fields": ["medium"],
            "active_blockers": [],
            "next_step": "answer_next_question",
        }
        state["actionability_projection"] = {
            "actionability_status": "input_required",
            "primary_allowed_action": "provide_missing_input",
            "blocked_actions": ["await_review", "consume_governed_result"],
            "next_expected_user_action": "answer_next_question",
        }
        reply = build_final_reply(state, asserted_state=None, working_profile=None)
        assert "Welches Medium soll abgedichtet werden?" in reply

    def test_review_reply_stays_consistent_with_await_review(self):
        from app.agent.agent.selection import build_final_reply, REVIEW_PENDING_REPLY

        state = _minimal_selection_state()
        state["projection_invariant_projection"] = {"invariant_ok": True, "invariant_violations": []}
        state["actionability_projection"] = {
            "actionability_status": "review_pending",
            "primary_allowed_action": "await_review",
            "blocked_actions": ["provide_missing_input", "consume_governed_result"],
            "next_expected_user_action": "human_review",
        }
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert REVIEW_PENDING_REPLY in reply

    def test_governed_result_reply_stays_consistent_with_consume_action(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        assert state["actionability_projection"]["primary_allowed_action"] == "consume_governed_result"
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert "Orientierungsrahmen" in reply

    def test_handoverable_case_reply_stays_consistent_with_prepare_handover(self):
        from app.agent.agent.selection import build_final_reply, AMBIGUOUS_CANDIDATE_REPLY

        state = _minimal_selection_state()
        state["projection_invariant_projection"] = {"invariant_ok": True, "invariant_violations": []}
        state["case_summary_projection"] = {
            "current_case_status": "withheld_review",
            "confirmed_core_fields": ["medium", "pressure", "temperature"],
            "missing_core_fields": [],
            "active_blockers": ["candidate_ambiguity"],
            "next_step": "human_review",
        }
        state["actionability_projection"] = {
            "actionability_status": "handoverable_restricted",
            "primary_allowed_action": "prepare_handover",
            "blocked_actions": ["consume_governed_result", "provide_missing_input"],
            "next_expected_user_action": "human_review",
        }
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert AMBIGUOUS_CANDIDATE_REPLY in reply

    def test_delta_projection_remains_read_only_for_releasable_reply_surface(self):
        from app.agent.agent.selection import build_final_reply, build_selection_state, build_state_delta_projection

        previous_state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        current_state = {
            **previous_state,
            "recommendation_artifact": {
                **previous_state["recommendation_artifact"],
                "rationale_summary": "Internal delta note only.",
            },
        }

        projection = build_state_delta_projection(
            previous_selection_state=previous_state,
            current_selection_state=current_state,
        )
        assert projection["changed_keys"] == []

        reply = build_final_reply(previous_state, asserted_state=_full_asserted())
        assert "Orientierungsrahmen" in reply

    def test_blocked_artifact_reply_matches_artifact_rationale(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )

        reply = build_final_reply(
            state,
            asserted_state=_full_asserted(),
            review_state=_pending_review(),
        )
        assert state["output_contract_projection"]["output_status"] == "withheld_review"
        assert state["recommendation_artifact"]["rationale_summary"] not in reply
        assert "Deterministische Candidate-Projektion" not in reply

    def test_releasable_artifact_reply_matches_artifact_rationale(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )

        reply = build_final_reply(state, asserted_state=_full_asserted())
        artifact = state["recommendation_artifact"]
        assert state["output_contract_projection"]["output_status"] == "governed_non_binding_result"
        assert artifact["rationale_summary"] in reply
        assert artifact["candidate_projection"]["candidate_id"] not in reply
        assert "eingeschränkt" in reply

    def test_ambiguous_projection_reply_matches_ambiguity_class(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, AMBIGUOUS_CANDIDATE_REPLY

        state = build_selection_state(
            relevant_fact_cards=[
                _qualified_fact_card("fc_1", grade_name="F1"),
                _qualified_fact_card("fc_2", grade_name="F2"),
            ],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert state["output_contract_projection"]["output_status"] == "withheld_review"
        assert AMBIGUOUS_CANDIDATE_REPLY in reply
        assert "Deterministische Candidate-Projektion" not in reply

    def test_escalation_projection_reply_matches_escalation_class(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, ESCALATION_NEEDED_REPLY

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1", temp_max=60.0)],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
        )
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert state["output_contract_projection"]["output_status"] == "withheld_escalation"
        assert ESCALATION_NEEDED_REPLY in reply
        assert "Deterministische Candidate-Projektion" not in reply

    def test_corrected_value_reply_mentions_update_without_losing_governed_projection(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, CORRECTION_APPLIED_PREFIX

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state=_full_asserted(),
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 10 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 10.0}, "identity_records": {}},
        )
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert CORRECTION_APPLIED_PREFIX in reply
        assert state["recommendation_artifact"]["candidate_projection"]["candidate_id"] not in reply

    def test_unresolved_conflict_reply_has_no_normal_governed_projection(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, UNRESOLVED_CONFLICT_REPLY

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state={**_green_governance(), "conflicts": [{"field": "pressure", "type": "parameter_conflict", "severity": "CRITICAL"}]},
            asserted_state=_full_asserted(),
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 10 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 10.0}, "identity_records": {}},
        )
        reply = build_final_reply(state, asserted_state=_full_asserted())
        assert UNRESOLVED_CONFLICT_REPLY in reply
        assert "Deterministische Candidate-Projektion" not in reply

    def test_integrity_warning_reply_mentions_warning_but_keeps_projection(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, INTEGRITY_WARNING_PREFIX

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 6.8948, "temperature": 80.0},
            },
            normalized_state={
                "normalized_parameters": {"pressure_bar": 6.8948, "temperature_c": 80.0},
                "identity_records": {
                    "pressure": {
                        "raw_value": "100 psi",
                        "normalized_value": 6.8948,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "Umgerechnet von 100 PSI -> 6.8948 bar",
                    }
                },
            },
        )
        reply = build_final_reply(state, asserted_state=state["recommendation_artifact"]["candidate_projection"] and {
            "medium_profile": {"name": "Hydrauliköl"},
            "operating_conditions": {"pressure": 6.8948, "temperature": 80.0},
        })
        assert INTEGRITY_WARNING_PREFIX in reply
        assert "Orientierungsrahmen" in reply

    def test_integrity_unusable_reply_has_no_normal_governed_projection(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, INTEGRITY_UNUSABLE_REPLY

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
            },
            normalized_state={
                "normalized_parameters": {"pressure_bar": 10.0, "temperature_c": 80.0},
                "identity_records": {
                    "temperature": {
                        "raw_value": "80 grad",
                        "normalized_value": 80.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_temperature_c",
                    }
                },
            },
        )
        reply = build_final_reply(state, asserted_state={
            "medium_profile": {"name": "Hydrauliköl"},
            "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
        })
        assert INTEGRITY_UNUSABLE_REPLY in reply
        assert "Deterministische Candidate-Projektion" not in reply

    def test_domain_warning_reply_mentions_scope_warning_but_keeps_projection(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, DOMAIN_WARNING_PREFIX

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        reply = build_final_reply(state, asserted_state=state["recommendation_artifact"] and {
            "medium_profile": {"name": "Hydrauliköl"},
            "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
            "machine_profile": {"material": "FKM"},
        })
        assert DOMAIN_WARNING_PREFIX in reply
        assert "Orientierungsrahmen" in reply

    def test_out_of_domain_reply_has_no_normal_governed_projection(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, OUT_OF_DOMAIN_REPLY

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 220.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        reply = build_final_reply(state, asserted_state={
            "medium_profile": {"name": "Hydrauliköl"},
            "operating_conditions": {"pressure": 10.0, "temperature": 220.0},
            "machine_profile": {"material": "FKM"},
        })
        assert OUT_OF_DOMAIN_REPLY in reply
        assert "Deterministische Candidate-Projektion" not in reply

    def test_threshold_escalation_reply_has_no_normal_governed_projection(self):
        from app.agent.agent.selection import build_selection_state, build_final_reply, THRESHOLD_ESCALATION_REPLY

        state = build_selection_state(
            relevant_fact_cards=[_qualified_fact_card("fc_1", grade_name="F1")],
            cycle_state={"analysis_cycle_id": "cycle-1"},
            governance_state=_green_governance(),
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 300.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        reply = build_final_reply(state, asserted_state={
            "medium_profile": {"name": "Hydrauliköl"},
            "operating_conditions": {"pressure": 300.0, "temperature": 80.0},
            "machine_profile": {"material": "FKM"},
        })
        assert THRESHOLD_ESCALATION_REPLY in reply
        assert "Deterministische Candidate-Projektion" not in reply
