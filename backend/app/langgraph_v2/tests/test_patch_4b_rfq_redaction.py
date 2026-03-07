from __future__ import annotations

import pytest
from app.langgraph_v2.nodes.answer_subgraph.node_finalize import _build_rfq_draft
from app.langgraph_v2.utils.redaction import redact_operating_context
from app.langgraph_v2.state.sealai_state import SealAIState, SealingRequirementSpec, AnswerContract, RFQDraft

def test_operating_context_redaction_filters_keys():
    raw_context = {
        "medium": "Wasser",
        "pressure_bar": 10.0,
        "internal_project_id": "PRJ-123", # Should be redacted
        "unnecessary_precision": 0.12345
    }
    redacted = redact_operating_context(raw_context)
    
    assert "medium" in redacted
    assert "pressure_bar" in redacted
    assert "internal_project_id" not in redacted
    assert "unnecessary_precision" not in redacted

def test_operating_context_redaction_rounds_floats():
    raw_context = {
        "shaft_diameter": 55.1234567,
        "speed_rpm": 1450.0
    }
    redacted = redact_operating_context(raw_context)
    
    assert redacted["shaft_diameter"] == 55.1
    assert redacted["speed_rpm"] == 1450.0

def test_build_rfq_draft_includes_buyer_id():
    state = SealAIState(
        conversation={"user_id": "user-456"},
        system={
            "sealing_requirement_spec": SealingRequirementSpec(
                operating_envelope={"medium": "Oil"}
            ),
            "answer_contract": AnswerContract(release_status="rfq_ready")
        }
    )
    
    draft = _build_rfq_draft(state)
    assert draft.buyer_contact == {"buyer_id": "user-456"}

def test_build_rfq_draft_handles_anonymous_user():
    state = SealAIState(
        conversation={"user_id": None},
        system={
            "sealing_requirement_spec": SealingRequirementSpec(),
            "answer_contract": AnswerContract(release_status="rfq_ready")
        }
    )
    draft = _build_rfq_draft(state)
    assert draft.buyer_contact == {"buyer_id": "anonymous"}

def test_redaction_allowlist_completeness():
    # Verify all expected keys are in the allowlist
    from app.langgraph_v2.utils.redaction import _RFQ_REDACTION_ALLOWLIST
    
    expected_keys = {
        "medium", "pressure_bar", "temperature_C", "shaft_diameter", 
        "speed_rpm", "dynamic_type", "shaft_runout", "shaft_hardness",
        "seal_material", "normative_references"
    }
    assert expected_keys.issubset(_RFQ_REDACTION_ALLOWLIST)
