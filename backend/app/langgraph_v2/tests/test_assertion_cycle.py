from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState
from app.langgraph_v2.utils.assertion_cycle import build_assertion_cycle_update


def test_build_assertion_cycle_update_tracks_revision_parent() -> None:
    """Test that bumping the cycle tracks the snapshot_parent_revision correctly."""
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
    
    # Verify obsolescence markers
    assert reasoning["derived_artifacts_stale"] is True
    assert "pressure_bar" in reasoning["derived_artifacts_stale_reason"]
    
    # In the current implementation, answer_contract is reset to None on bump 
    # to prevent stale authority from being used.
    assert patch["system"]["answer_contract"] is None


def test_build_assertion_cycle_update_no_contract() -> None:
    """Test that bumping the cycle safely handles missing AnswerContract."""
    state = SealAIState(
        conversation={"session_id": "test_sess_123"},
        reasoning={"current_assertion_cycle_id": 1, "asserted_profile_revision": 1},
        system={"answer_contract": None}
    )

    patch = build_assertion_cycle_update(state, applied_fields=["pressure_bar"])
    
    assert patch["system"]["answer_contract"] is None
