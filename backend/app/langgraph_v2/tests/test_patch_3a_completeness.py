from __future__ import annotations

import pytest
from app.langgraph_v2.nodes.nodes_supervisor import (
    _derive_open_questions,
    _get_dynamic_priority
)
from app.langgraph_v2.utils.completeness import compute_risk_driven_completeness
from app.langgraph_v2.state.sealai_state import SealAIState, WorkingMemory, RequirementSpec
from app.langgraph_v2.state.governance_types import CompletenessCategory, CompletenessDepth

def test_risk_driven_completeness_derivation():
    # Case 1: Empty state -> precheck
    state = SealAIState()
    completeness = compute_risk_driven_completeness(state)
    assert completeness["completeness_depth"] == "precheck"
    assert "medium" in completeness["missing_technical"]
    assert completeness["recommendation_ready"] is False

    # Case 2: Technical core fields present -> prequalification
    state = SealAIState(
        medium="Wasser",
        pressure_bar=10.0,
        temperature_c=80.0
    )
    completeness = compute_risk_driven_completeness(state)
    assert completeness["completeness_depth"] == "prequalification"
    assert completeness["coverage_score"] >= 0.6
    # missing qualification fields (diameter, rpm) still make it not ready (threshold 0.8)
    assert completeness["recommendation_ready"] is False

    # Case 3: All core fields present -> critical_review
    state = SealAIState(
        medium="Wasser",
        pressure_bar=10.0,
        temperature_c=80.0,
        shaft_diameter=50.0,
        speed_rpm=1500.0
    )
    completeness = compute_risk_driven_completeness(state)
    assert completeness["completeness_depth"] == "critical_review"
    assert completeness["coverage_score"] == 1.0
    assert completeness["recommendation_ready"] is True

def test_question_prioritization_by_category():
    state = SealAIState(
        pressure_bar=10.0,
        temperature_c=80.0,
        # missing medium (highest risk)
        # missing diameter (medium risk)
        missing_params=["medium", "shaft_diameter"],
        discovery_missing=["some_info"] # low risk
    )
    
    questions = _derive_open_questions(state)
    
    # 1. technical blocker
    assert questions[0].id == "medium"
    assert questions[0].category == "release_blocking_technical_unknown"
    
    # 2. qualification gap
    assert questions[1].id == "shaft_diameter"
    assert questions[1].category == "qualification_gap"
    
    # 3. clarification
    assert questions[2].id == "some_info"
    assert questions[2].category == "clarification_gap"

def test_dynamic_priority_escalation():
    # Normal case
    state = SealAIState()
    priority, category = _get_dynamic_priority("shaft_runout", state)
    assert priority == "medium"
    assert category == "clarification_gap"
    
    # High pressure escalation
    state = SealAIState(pressure_bar=40.0)
    priority, category = _get_dynamic_priority("shaft_runout", state)
    assert priority == "high"
    assert category == "qualification_gap"
