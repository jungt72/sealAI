from app._legacy_v2.state.sealai_state import AnswerContract, SealAIState
from app._legacy_v2.utils.assertion_cycle import build_assertion_cycle_update


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
    assert patch["system"]["sealing_requirement_spec"] is None
    assert patch["system"]["rfq_draft"] is None
    assert patch["system"]["rfq_confirmed"] is False


def test_build_assertion_cycle_update_no_contract() -> None:
    """Test that bumping the cycle safely handles missing AnswerContract."""
    state = SealAIState(
        conversation={"session_id": "test_sess_123"},
        reasoning={"current_assertion_cycle_id": 1, "asserted_profile_revision": 1},
        system={"answer_contract": None}
    )

    patch = build_assertion_cycle_update(state, applied_fields=["pressure_bar"])

    assert patch["system"]["answer_contract"] is None


def test_root_state_flat_payload_routes_assertion_and_rfq_fields_into_pillars() -> None:
    state = SealAIState(
        current_assertion_cycle_id=3,
        asserted_profile_revision=8,
        state_revision=8,
        snapshot_parent_revision=7,
        governance_metadata={"scope_of_validity": ["Nur fuer den aktuellen Assertion-Stand."]},
        derived_from_assertion_cycle_id=3,
        derived_from_assertion_revision=8,
        sealing_requirement_spec={"spec_id": "SRS-1"},
        rfq_draft={"rfq_id": "RFQ-1"},
        rfq_confirmed=True,
    )

    assert state.reasoning.current_assertion_cycle_id == 3
    assert state.reasoning.asserted_profile_revision == 8
    assert state.reasoning.state_revision == 8
    assert state.reasoning.snapshot_parent_revision == 7
    assert state.system.governance_metadata.scope_of_validity == ["Nur fuer den aktuellen Assertion-Stand."]
    assert state.system.derived_from_assertion_cycle_id == 3
    assert state.system.derived_from_assertion_revision == 8
    assert state.system.sealing_requirement_spec is not None
    assert state.system.sealing_requirement_spec.spec_id == "SRS-1"
    assert state.system.rfq_draft is not None
    assert state.system.rfq_draft.rfq_id == "RFQ-1"
    assert state.system.rfq_confirmed is True
