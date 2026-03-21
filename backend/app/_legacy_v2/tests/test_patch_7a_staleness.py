from __future__ import annotations

import pytest
from app._legacy_v2.state.sealai_state import SealAIState, AnswerContract, RequirementSpec, RFQDraft
from app._legacy_v2.utils.assertion_cycle import build_assertion_cycle_update, is_artifact_stale
from app._legacy_v2.utils.completeness import compute_risk_driven_completeness
from app._legacy_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app._legacy_v2.nodes.answer_subgraph.node_finalize import node_finalize

def test_cycle_increment_marks_artifacts_stale():
    state = SealAIState(
        reasoning={
            "current_assertion_cycle_id": 1,
            "asserted_profile_revision": 1,
        },
        system={
            "derived_artifacts_stale": False,
            "answer_contract": AnswerContract(contract_id="contract-c1-r1")
        }
    )
    
    update = build_assertion_cycle_update(state, applied_fields=["pressure_bar"])
    
    assert update["reasoning"]["current_assertion_cycle_id"] == 2
    assert update["reasoning"]["derived_artifacts_stale"] is True
    assert update["system"]["derived_artifacts_stale"] is True
    assert update["working_profile"]["derived_artifacts_stale"] is True
    assert update["system"]["answer_contract"]["obsolete"] is True

def test_completeness_blocked_by_staleness():
    # Ready profile but stale artifacts
    state = SealAIState(
        medium="Wasser",
        pressure_bar=10.0,
        temperature_c=80.0,
        shaft_diameter=50.0,
        speed_rpm=1500.0,
        reasoning={"derived_artifacts_stale": True}
    )
    
    completeness = compute_risk_driven_completeness(state)
    
    assert completeness["coverage_score"] == 1.0
    # Even though coverage is 1.0, staleness blocks readiness
    assert completeness["recommendation_ready"] is False
    assert completeness["artifacts_stale"] is True

def test_finalize_aborts_on_staleness():
    state = SealAIState(
        system={
            "derived_artifacts_stale": True,
            "draft_text": "Old verified answer"
        },
        reasoning={"phase": "final"}
    )
    
    patch = node_finalize(state)
    
    assert patch["system"]["error"] == "finalize_aborted_stale"
    assert "messages" not in patch # No AIMessage added

def test_prepare_contract_refreshes_staleness():
    state = SealAIState(
        reasoning={
            "current_assertion_cycle_id": 2,
            "asserted_profile_revision": 2,
            "derived_artifacts_stale": True,
            "phase": "final"
        },
        system={"derived_artifacts_stale": True},
        working_profile={"derived_artifacts_stale": True, "medium": "Wasser"}
    )
    
    patch = node_prepare_contract(state)
    
    # Contract should be fresh for c2-r2
    assert patch["system"]["answer_contract"].contract_id == "contract-c2-r2"
    
    # stamp_patch_with_assertion_binding should have cleared staleness
    assert patch["reasoning"]["derived_artifacts_stale"] is False
    assert patch["system"]["derived_artifacts_stale"] is False
    assert patch["working_profile"]["derived_artifacts_stale"] is False

def test_system_state_has_confirmed_rfq_id():
    state = SealAIState()
    assert hasattr(state.system, "confirmed_rfq_id")
