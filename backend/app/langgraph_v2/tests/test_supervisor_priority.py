from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node, ACTION_RUN_PANEL_NORMS_RAG, ACTION_RUN_PANEL_CALC, ACTION_REQUIRE_CONFIRM
from app.langgraph_v2.state import SealAIState, Intent, WorkingMemory
from app.langgraph_v2.phase import PHASE
import pytest

def test_priority_rag_over_calc():
    """
    Test A: requires_rag=True + goal/design_recommendation + missing calc params
    => Should prioritize ACTION_RUN_PANEL_NORMS_RAG (via ACTION_REQUIRE_CONFIRM)
    """
    state = SealAIState(
        intent=Intent(goal="design_recommendation", key="knowledge_norms"),
        requires_rag=True, 
        phase=PHASE.SUPERVISOR,
        # missing_calc = True by default since calc_results is None
    )
    
    patch = supervisor_policy_node(state)
    
    # In HITL flow, action is REQUIRE_CONFIRM and pending is the target
    assert patch["next_action"] == ACTION_REQUIRE_CONFIRM
    assert patch["pending_action"] == ACTION_RUN_PANEL_NORMS_RAG
    assert patch["next_action_reason"] == "rag_sources_required"

def test_priority_calc_when_no_rag():
    """
    Test B: requires_rag=False + same scenario
    => Should fallback to existing ACTION_RUN_PANEL_CALC
    """
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        requires_rag=False,
        phase=PHASE.SUPERVISOR,
    )
    
    patch = supervisor_policy_node(state)
    
    # Without RAG, it should ask for missing calc params
    assert patch["next_action"] == ACTION_RUN_PANEL_CALC
    assert patch["next_action_reason"] == "missing_calc_facts"

def test_priority_needs_sources_flag():
    """
    Verify that needs_sources also triggers the priority.
    """
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        needs_sources=True,
        requires_rag=False,
        phase=PHASE.SUPERVISOR,
    )
    
    patch = supervisor_policy_node(state)
    assert patch["next_action"] == ACTION_REQUIRE_CONFIRM
    assert patch["pending_action"] == ACTION_RUN_PANEL_NORMS_RAG
    assert patch["next_action_reason"] == "rag_sources_required"
