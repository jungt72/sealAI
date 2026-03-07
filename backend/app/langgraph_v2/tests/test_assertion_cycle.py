from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState
from app.langgraph_v2.utils.assertion_cycle import build_assertion_cycle_update


def test_build_assertion_cycle_update_marks_obsolete_instead_of_none() -> None:
    """Test that bumping the cycle marks an existing AnswerContract as obsolete but retains it."""
    state = SealAIState(
        conversation={"session_id": "test_sess_123"},
        reasoning={
            "current_assertion_cycle_id": 1, 
            "asserted_profile_revision": 5,
            "state_revision": 5
        },
        system={
            "answer_contract": AnswerContract(
                analysis_cycle_id="cycle_test_sess_123_1"
            )
        }
    )

    patch = build_assertion_cycle_update(state, applied_fields=["pressure_bar"])
    
    # Verify the cycle and revision are bumped
    reasoning = patch["reasoning"]
    assert reasoning["current_assertion_cycle_id"] == 2
    assert reasoning["asserted_profile_revision"] == 6
    assert reasoning["state_revision"] == 6
    
    # Verify the snapshot_parent_revision is correctly set to the previous revision
    assert reasoning["snapshot_parent_revision"] == 5
    
    # Verify obsolescence markers in the retained contract
    updated_contract = patch["system"]["answer_contract"]
    assert updated_contract is not None
    assert updated_contract["obsolete"] is True
    assert "pressure_bar" in updated_contract["obsolete_reason"]
    assert updated_contract["superseded_by_cycle"] == "cycle_test_sess_123_2"


def test_build_assertion_cycle_update_no_contract() -> None:
    """Test that bumping the cycle safely handles missing AnswerContract."""
    state = SealAIState(
        conversation={"session_id": "test_sess_123"},
        reasoning={"current_assertion_cycle_id": 1, "asserted_profile_revision": 1},
        system={"answer_contract": None}
    )

    patch = build_assertion_cycle_update(state, applied_fields=["pressure_bar"])
    
    assert patch["system"]["answer_contract"] is None
