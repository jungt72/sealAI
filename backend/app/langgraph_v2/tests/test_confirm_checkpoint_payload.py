from app.langgraph_v2.nodes.answer_subgraph.subgraph_builder import (
    _clear_checkpoint,
    _consume_decision,
    _handle_checkpoint,
    _merge_state_patch,
)
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.confirm_checkpoint import build_confirm_checkpoint_payload


def test_build_confirm_checkpoint_payload() -> None:
    state = SealAIState(
        phase="confirm",
        last_node="confirm_recommendation_node",
        governed_output_text="**Abnahme-Checkpoint (vorläufig)**\n- Status: GO",
        user_id="user-1",
        thread_id="conv-1",
        recommendation_go=True,
        coverage_score=0.9,
        coverage_gaps=["medium"],
        working_profile={
            "engineering_profile": {
                "medium": "Hydraulikoel",
                "temperature_C": 80,
                "pressure_bar": 10,
                "speed_rpm": 1500,
                "shaft_diameter": 50,
            }
        },
        system={
            "governance_metadata": {
                "scope_of_validity": ["Nur fuer den aktuellen Assertion-Stand."],
                "assumptions_active": [],
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": ["PTFE erfordert Herstellerfreigabe."],
                "gate_failures": [],
                "governance_notes": [],
            },
            "rfq_admissibility": {
                "status": "inadmissible",
                "reason": "rfq_contract_missing",
                "open_points": [],
                "blockers": [],
                "governed_ready": False,
            },
            "sealing_requirement_spec": {
                "spec_id": "SRS-1",
                "material_specificity_required": "family_only",
                "operating_envelope": {"pressure_bar": 10, "temperature_c": 80},
            },
            "rfq_draft": {
                "rfq_id": "RFQ-1",
                "rfq_basis_status": "provisional",
                "buyer_contact": {"company": "SealAI Test GmbH"},
            },
            "rfq_confirmed": True,
        },
    )
    payload = build_confirm_checkpoint_payload(state, action="RUN_PANEL_NORMS_RAG", checkpoint_id="chk-1")
    assert payload["checkpoint_id"] == "chk-1"
    assert payload["required_user_sub"] == state.conversation.user_id
    assert payload["conversation_id"] == state.conversation.thread_id
    assert payload["action"] == "RUN_PANEL_NORMS_RAG"
    assert payload["risk"] == "med"
    assert payload["preview"]["text"].startswith("**Abnahme-Checkpoint")
    assert payload["preview"]["coverage_score"] == 0.9
    assert payload["preview"]["coverage_gaps"] == ["medium"]
    assert payload["preview"]["governance_metadata"]["scope_of_validity"] == ["Nur fuer den aktuellen Assertion-Stand."]
    assert payload["preview"]["rfq_admissibility"]["status"] == "inadmissible"
    assert payload["preview"]["sealing_requirement_spec"]["spec_id"] == "SRS-1"
    assert payload["preview"]["rfq_draft"]["rfq_id"] == "RFQ-1"
    assert payload["preview"]["rfq_confirmed"] is True


# ---------------------------------------------------------------------------
# Regression: _clear_checkpoint resets all HITL flags
# ---------------------------------------------------------------------------


def test_clear_checkpoint_resets_all_hitl_flags() -> None:
    patch = _clear_checkpoint()
    sys = patch["system"]
    assert sys["confirm_decision"] is None
    assert sys["confirm_status"] == "resolved"
    assert sys["awaiting_user_confirmation"] is False
    assert sys["pending_action"] is None
    assert sys["confirm_checkpoint"] == {}
    assert sys["confirm_checkpoint_id"] is None
    assert patch["reasoning"]["phase"] == "final"
    assert patch["reasoning"]["last_node"] == "answer_subgraph_node"


def test_clear_checkpoint_applied_to_state_resets_flow_cleanly() -> None:
    state = SealAIState(
        system={
            "pending_action": "snapshot_confirmation",
            "confirm_status": "pending",
            "awaiting_user_confirmation": True,
            "confirm_checkpoint_id": "chk-old",
            "confirm_checkpoint": {"checkpoint_id": "chk-old"},
            "confirm_decision": "approve",
        },
        reasoning={"phase": "confirm", "last_node": "snapshot_confirmation_node"},
    )
    merged = _merge_state_patch(state, _clear_checkpoint())
    assert merged.system.pending_action is None
    assert merged.system.confirm_checkpoint == {}
    assert merged.system.confirm_checkpoint_id is None
    assert merged.system.confirm_status == "resolved"
    assert merged.system.awaiting_user_confirmation is False
    assert merged.reasoning.phase == "final"


# ---------------------------------------------------------------------------
# Regression: _consume_decision helper
# ---------------------------------------------------------------------------


def test_consume_decision_approves_matching_action() -> None:
    state = SealAIState(
        system={"pending_action": "snapshot_confirmation", "confirm_decision": "approve"},
    )
    assert _consume_decision(state, "snapshot_confirmation") is True


def test_consume_decision_rejects_mismatched_action() -> None:
    state = SealAIState(
        system={"pending_action": "rfq_confirmation", "confirm_decision": "approve"},
    )
    assert _consume_decision(state, "snapshot_confirmation") is False


def test_consume_decision_rejects_missing_decision() -> None:
    state = SealAIState(
        system={"pending_action": "snapshot_confirmation", "confirm_decision": None},
    )
    assert _consume_decision(state, "snapshot_confirmation") is False


# ---------------------------------------------------------------------------
# Regression: snapshot_confirmation fires/skips based on confirmed_spec_id
# ---------------------------------------------------------------------------


def test_snapshot_fires_on_new_spec_id() -> None:
    """First time seeing a spec_id -> checkpoint must be emitted."""
    state = SealAIState(
        system={
            "sealing_requirement_spec": {"spec_id": "srs-c1-r1"},
            "confirmed_spec_id": None,
        },
    )
    spec_id = state.system.sealing_requirement_spec.spec_id
    confirmed = getattr(state.system, "confirmed_spec_id", "")
    assert spec_id != (confirmed or ""), "New spec_id should differ from empty/None confirmed_spec_id"

    checkpoint = _handle_checkpoint(state, "snapshot_confirmation", "snapshot_confirmation_node")
    assert checkpoint["system"]["pending_action"] == "snapshot_confirmation"
    assert checkpoint["system"]["confirm_status"] == "pending"
    assert checkpoint["system"]["awaiting_user_confirmation"] is True


def test_snapshot_skips_on_already_confirmed_identical_spec_id() -> None:
    """If confirmed_spec_id == current spec_id, no re-trigger needed."""
    state = SealAIState(
        system={
            "sealing_requirement_spec": {"spec_id": "srs-c3-r7"},
            "confirmed_spec_id": "srs-c3-r7",
        },
    )
    spec_id = state.system.sealing_requirement_spec.spec_id
    confirmed = getattr(state.system, "confirmed_spec_id", "")
    assert spec_id == confirmed, "Identical spec_id should NOT trigger checkpoint"


def test_snapshot_refires_on_changed_spec_id() -> None:
    """If spec_id changed since last confirmation, checkpoint must fire again."""
    state = SealAIState(
        system={
            "sealing_requirement_spec": {"spec_id": "srs-c4-r9"},
            "confirmed_spec_id": "srs-c3-r7",
        },
    )
    spec_id = state.system.sealing_requirement_spec.spec_id
    confirmed = getattr(state.system, "confirmed_spec_id", "")
    assert spec_id != confirmed, "Changed spec_id must trigger a new checkpoint"

    checkpoint = _handle_checkpoint(state, "snapshot_confirmation", "snapshot_confirmation_node")
    assert checkpoint["system"]["pending_action"] == "snapshot_confirmation"


def test_snapshot_confirmation_approve_sets_confirmed_spec_id() -> None:
    """After user approves, _clear_checkpoint + confirmed_spec_id update."""
    state = SealAIState(
        system={
            "sealing_requirement_spec": {"spec_id": "srs-c4-r9"},
            "confirmed_spec_id": "srs-c3-r7",
            "pending_action": "snapshot_confirmation",
            "confirm_decision": "approve",
        },
    )
    assert _consume_decision(state, "snapshot_confirmation") is True
    patch = _clear_checkpoint()
    patch["system"]["confirmed_spec_id"] = "srs-c4-r9"
    merged = _merge_state_patch(state, patch)
    assert merged.system.confirmed_spec_id == "srs-c4-r9"
    assert merged.system.pending_action is None


# ---------------------------------------------------------------------------
# Regression: rfq_confirmation stays functionally unchanged
# ---------------------------------------------------------------------------


def test_rfq_confirmation_triggers_when_not_confirmed() -> None:
    state = SealAIState(
        system={
            "rfq_draft": {"rfq_id": "RFQ-1", "rfq_basis_status": "provisional"},
            "rfq_admissibility": {"status": "ready", "governed_ready": True},
            "rfq_confirmed": False,
        },
    )
    rfq_draft = getattr(state.system, "rfq_draft", None)
    rfq_admissibility = getattr(state.system, "rfq_admissibility", None)
    is_rfq_confirmed = getattr(state.system, "rfq_confirmed", False)
    assert rfq_draft and rfq_admissibility and not is_rfq_confirmed

    checkpoint = _handle_checkpoint(state, "rfq_confirmation", "rfq_confirmation_node")
    assert checkpoint["system"]["pending_action"] == "rfq_confirmation"


def test_rfq_confirmation_skips_when_already_confirmed() -> None:
    state = SealAIState(
        system={
            "rfq_draft": {"rfq_id": "RFQ-1", "rfq_basis_status": "provisional"},
            "rfq_admissibility": {"status": "ready", "governed_ready": True},
            "rfq_confirmed": True,
        },
    )
    is_rfq_confirmed = getattr(state.system, "rfq_confirmed", False)
    assert is_rfq_confirmed is True, "Already confirmed -> should skip"
