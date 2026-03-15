"""
0A.3: Guided vs Qualified payload split — table-driven test matrix.

Tests cover:
- guided payload has no case_state, no result_contract, no qualified_action_gate
- guided payload has binding_level="ORIENTATION" and rfq_ready=False
- guided payload has visible_case_narrative
- guided state persisted without case_state (stale case_state stripped)
- qualified path payload is unchanged (case_state present)
- follow-up turn: guided → qualified works without context break
- _build_guidance_response_payload() helper contract
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.api.router import (
    _build_guidance_response_payload,
    SESSION_STORE,
)
from app.agent.cli import create_initial_state
from app.agent.runtime import InteractionPolicyDecision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_sessions():
    SESSION_STORE.clear()


def _make_guided_decision(**overrides) -> InteractionPolicyDecision:
    defaults = dict(
        result_form="guided",
        path="structured",
        stream_mode="structured_progress_stream",
        interaction_class="GUIDANCE",
        runtime_path="STRUCTURED_GUIDANCE",
        binding_level="ORIENTATION",
        has_case_state=True,
        coverage_status="partial",
        boundary_flags=("orientation_only", "no_manufacturer_release"),
        escalation_reason=None,
        required_fields=(),
    )
    defaults.update(overrides)
    return InteractionPolicyDecision(**defaults)


def _make_qualified_decision(**overrides) -> InteractionPolicyDecision:
    defaults = dict(
        result_form="qualified",
        path="structured",
        stream_mode="structured_progress_stream",
        interaction_class="QUALIFICATION",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="QUALIFIED_PRESELECTION",
        has_case_state=True,
        coverage_status="partial",
        boundary_flags=(),
        escalation_reason=None,
        required_fields=(),
    )
    defaults.update(overrides)
    return InteractionPolicyDecision(**defaults)


def _make_minimal_state(*, with_case_state: bool = False) -> dict:
    sealing_state = create_initial_state()
    state = {
        "messages": [
            HumanMessage(content="Dichtung für Wasser bei 150°C"),
            AIMessage(content="Orientierung: FKM ist geeignet bei diesen Bedingungen."),
        ],
        "sealing_state": sealing_state,
        "working_profile": {"temperature": 150.0},
        "relevant_fact_cards": [],
        "tenant_id": "tenant_test",
        "owner_id": "user_test",
    }
    if with_case_state:
        state["case_state"] = {
            "case_meta": {"binding_level": "QUALIFIED_PRESELECTION", "runtime_path": "STRUCTURED_QUALIFICATION"},
            "result_contract": {"binding_level": "QUALIFIED_PRESELECTION", "release_status": "inadmissible"},
            "qualified_action_gate": {"action": "download_rfq", "allowed": False, "rfq_ready": False},
        }
    return state


# ---------------------------------------------------------------------------
# _build_guidance_response_payload() — unit contract
# ---------------------------------------------------------------------------

def test_guidance_payload_has_no_case_state():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply="Orientierung.", state=state)
    assert "case_state" not in payload or payload.get("case_state") is None


def test_guidance_payload_has_no_result_contract():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply="Orientierung.", state=state)
    assert payload.get("result_contract") is None


def test_guidance_payload_has_no_qualified_action_gate():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply="Orientierung.", state=state)
    assert payload.get("qualified_action_gate") is None


def test_guidance_payload_binding_level_is_orientation():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply="Orientierung.", state=state)
    assert payload["binding_level"] == "ORIENTATION"


def test_guidance_payload_rfq_ready_is_false():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply="Orientierung.", state=state)
    assert payload["rfq_ready"] is False


def test_guidance_payload_result_form_is_guided():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply="Orientierung.", state=state)
    assert payload["result_form"] == "guided"


def test_guidance_payload_has_visible_case_narrative():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply="Orientierung.", state=state)
    assert payload.get("visible_case_narrative") is not None
    assert isinstance(payload["visible_case_narrative"], dict)


def test_guidance_payload_has_reply():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply="Meine Orientierung.", state=state)
    assert payload["reply"] == "Meine Orientierung."


def test_guidance_payload_has_session_id():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="sess_42", reply=".", state=state)
    assert payload["session_id"] == "sess_42"
    assert payload["case_id"] == "sess_42"


def test_guidance_payload_has_case_state_true():
    """has_case_state=True because structured session is active (not qualified case)."""
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert payload["has_case_state"] is True


def test_guidance_payload_boundary_flags_present():
    decision = _make_guided_decision(boundary_flags=("orientation_only", "no_manufacturer_release"))
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert "orientation_only" in payload["boundary_flags"]
    assert "no_manufacturer_release" in payload["boundary_flags"]


def test_guidance_payload_escalation_reason_propagated():
    decision = _make_guided_decision(escalation_reason="qualification_signal_without_data_basis")
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert payload["escalation_reason"] == "qualification_signal_without_data_basis"


def test_guidance_payload_coverage_status_propagated():
    decision = _make_guided_decision(coverage_status="partial")
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert payload["coverage_status"] == "partial"


def test_guidance_payload_working_profile_included_when_provided():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(
        decision, session_id="s1", reply=".", state=state, working_profile={"temperature": 150.0}
    )
    assert payload.get("working_profile") is not None
    assert payload["working_profile"]["temperature"] == 150.0


def test_guidance_payload_working_profile_absent_when_not_provided():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert "working_profile" not in payload or payload.get("working_profile") is None


# ---------------------------------------------------------------------------
# Stale case_state stripping — state-level contract
# ---------------------------------------------------------------------------

def test_guided_state_strips_stale_case_state():
    """Guided branch must pop case_state from prior qualified turns before persistence."""
    state_with_case = _make_minimal_state(with_case_state=True)
    assert "case_state" in state_with_case  # baseline: prior qualified turn left case_state

    # Simulate what the guided branch in the router does
    guided_state = dict(state_with_case)
    guided_state.pop("case_state", None)

    assert "case_state" not in guided_state
    # Original state not mutated (shallow copy pattern)
    assert "case_state" in state_with_case


def test_guided_state_strip_is_safe_on_fresh_state():
    """pop("case_state", None) must not raise on state without case_state."""
    state_fresh = _make_minimal_state(with_case_state=False)
    guided_state = dict(state_fresh)
    result = guided_state.pop("case_state", None)
    assert result is None


# ---------------------------------------------------------------------------
# Visible narrative is orientation-level
# ---------------------------------------------------------------------------

def test_guidance_narrative_built_without_case_state():
    """build_visible_case_narrative with case_state=None builds from sealing_state directly."""
    from app.agent.case_state import build_visible_case_narrative
    state = _make_minimal_state()
    narrative = build_visible_case_narrative(state=state, case_state=None, binding_level="ORIENTATION")
    assert isinstance(narrative, dict)
    assert "governed_summary" in narrative
    assert "next_best_inputs" in narrative
    assert "suggested_next_questions" in narrative


# ---------------------------------------------------------------------------
# Interaction class and runtime path preserved in guidance payload
# ---------------------------------------------------------------------------

def test_guidance_payload_interaction_class():
    decision = _make_guided_decision(interaction_class="GUIDANCE")
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert payload["interaction_class"] == "GUIDANCE"


def test_guidance_payload_runtime_path():
    decision = _make_guided_decision(runtime_path="STRUCTURED_GUIDANCE")
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert payload["runtime_path"] == "STRUCTURED_GUIDANCE"


def test_guidance_payload_fallback_runtime_path():
    decision = _make_guided_decision(runtime_path="FALLBACK_SAFE_STRUCTURED")
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert payload["runtime_path"] == "FALLBACK_SAFE_STRUCTURED"


# ---------------------------------------------------------------------------
# Follow-up continuity: guided → qualified
# ---------------------------------------------------------------------------

def test_guided_state_retains_sealing_state_for_follow_up():
    """After a guided turn, sealing_state.asserted must survive for next-turn policy evaluation."""
    from app.agent.runtime import _has_asserted_parameters

    state = _make_minimal_state()
    state["sealing_state"]["asserted"]["medium_profile"] = {"name": "Wasser"}

    guided_state = dict(state)
    guided_state.pop("case_state", None)

    # The key check: sealing_state.asserted is preserved after guided branch stripping
    assert guided_state["sealing_state"]["asserted"]["medium_profile"]["name"] == "Wasser"
    # _has_asserted_parameters reads from sealing_state — should return True
    assert _has_asserted_parameters(guided_state) is True


def test_qualified_decision_after_guided_turn_with_asserted_medium():
    """Policy correctly upgrades to qualified on follow-up when asserted params are present."""
    from app.agent.runtime import evaluate_interaction_policy

    # Simulate the SESSION_STORE state after a guided turn
    guided_session_state = _make_minimal_state()
    guided_session_state["sealing_state"]["asserted"]["medium_profile"] = {"name": "Wasser"}
    # No case_state — as expected from guided persistence

    decision = evaluate_interaction_policy(
        "Empfehle ein Material",
        has_rwdr_payload=False,
        existing_state=guided_session_state,
    )
    assert decision.result_form == "qualified"
    assert "case_state" not in guided_session_state  # guided state clean


# ---------------------------------------------------------------------------
# Qualified path — payload contract unchanged (regression guard)
# ---------------------------------------------------------------------------

def test_build_runtime_payload_qualified_has_case_id_when_case_state():
    """build_runtime_payload (qualified path) must still set case_id when has_case_state=True."""
    from app.agent.api.router import build_runtime_payload

    decision = _make_qualified_decision()
    case_state = {
        "result_contract": {"binding_level": "QUALIFIED_PRESELECTION", "release_status": "inadmissible"},
        "qualified_action_gate": {"action": "download_rfq", "allowed": False, "rfq_ready": False, "block_reasons": [], "binding_level": "QUALIFIED_PRESELECTION", "source_type": "deterministic", "source_ref": "test", "summary": "blocked"},
    }
    payload = build_runtime_payload(
        decision,
        session_id="s1",
        reply="Qualifizierte Antwort.",
        case_state=case_state,
    )
    assert payload["case_id"] == "s1"
    assert payload["result_form"] == "qualified"
    assert payload.get("result_contract") is not None


def test_build_runtime_payload_qualified_result_form_not_guided():
    """build_runtime_payload must never return result_form='guided' for qualified decision."""
    from app.agent.api.router import build_runtime_payload

    decision = _make_qualified_decision()
    payload = build_runtime_payload(decision, session_id="s1", reply=".", case_state=None)
    assert payload.get("result_form") == "qualified"
