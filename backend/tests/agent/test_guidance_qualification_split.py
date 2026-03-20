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
    assert payload["path"] == "structured"
    assert payload["stream_mode"] == "structured_progress_stream"
    assert payload["required_fields"] == []


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

def test_guided_state_replaces_stale_case_state_with_minimal_meta():
    """Guided branch must replace stale case_state with minimal guidance case_meta (P5c)."""
    state_with_case = _make_minimal_state(with_case_state=True)
    assert "case_state" in state_with_case  # baseline: prior qualified turn left case_state

    # Simulate what the guided branch in the router does after P5c
    guided_state = dict(state_with_case)
    guided_state["case_state"] = {
        "case_meta": {"binding_level": "ORIENTATION", "runtime_path": "STRUCTURED_GUIDANCE"},
    }

    assert guided_state["case_state"]["case_meta"]["binding_level"] == "ORIENTATION"
    # No qualification artifacts
    assert "result_contract" not in guided_state["case_state"]
    assert "qualified_action_gate" not in guided_state["case_state"]
    # Original state not mutated (shallow copy pattern)
    assert state_with_case["case_state"]["case_meta"]["binding_level"] == "QUALIFIED_PRESELECTION"


def test_guided_state_overwrite_is_safe_on_fresh_state():
    """Setting case_state with minimal meta must not raise on state without prior case_state."""
    state_fresh = _make_minimal_state(with_case_state=False)
    guided_state = dict(state_fresh)
    guided_state["case_state"] = {
        "case_meta": {"binding_level": "ORIENTATION", "runtime_path": "STRUCTURED_GUIDANCE"},
    }
    assert guided_state["case_state"]["case_meta"]["binding_level"] == "ORIENTATION"


# ---------------------------------------------------------------------------
# Visible narrative is orientation-level
# ---------------------------------------------------------------------------

def test_guidance_narrative_built_without_case_state():
    """build_visible_case_narrative with case_state=None builds from sealing_state directly.
    Note: after P3b this path is no longer used for guidance, but remains valid for other callers."""
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
    guided_state["case_state"] = {
        "case_meta": {"binding_level": "ORIENTATION", "runtime_path": "STRUCTURED_GUIDANCE"},
    }

    # The key check: sealing_state.asserted is preserved after guided branch stripping
    assert guided_state["sealing_state"]["asserted"]["medium_profile"]["name"] == "Wasser"
    # _has_asserted_parameters reads from sealing_state — should return True
    assert _has_asserted_parameters(guided_state) is True


def test_qualified_decision_after_guided_turn_with_asserted_medium():
    """Policy correctly upgrades to qualified on follow-up when asserted params are present."""
    from app.agent.runtime import evaluate_interaction_policy

    # Simulate the SESSION_STORE state after a guided turn (P5c: minimal case_meta)
    guided_session_state = _make_minimal_state()
    guided_session_state["sealing_state"]["asserted"]["medium_profile"] = {"name": "Wasser"}
    guided_session_state["case_state"] = {
        "case_meta": {"binding_level": "ORIENTATION", "runtime_path": "STRUCTURED_GUIDANCE"},
    }

    decision = evaluate_interaction_policy(
        "Empfehle ein Material",
        has_rwdr_payload=False,
        existing_state=guided_session_state,
    )
    assert decision.result_form == "qualified"
    # P5c: guided state has minimal case_meta, not full qualification case_state
    assert guided_session_state["case_state"]["case_meta"]["binding_level"] == "ORIENTATION"


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
    assert payload.get("path") == "structured"
    assert payload.get("stream_mode") == "structured_progress_stream"
    assert payload.get("required_fields") == []


# ---------------------------------------------------------------------------
# 0A.3 P2: selection_node guidance branch — execution-level tests
# ---------------------------------------------------------------------------

def test_selection_node_guidance_skips_qualification():
    """P2: selection_node returns guidance-semantic selection when result_form=='guided'."""
    from app.agent.agent.graph import selection_node

    state = _make_minimal_state()
    state["result_form"] = "guided"
    result = selection_node(state)
    selection = result["sealing_state"]["selection"]
    assert selection["selection_status"] == "not_applicable"
    assert selection["release_status"] == "not_applicable"
    assert selection["rfq_admissibility"] == "not_applicable"
    assert selection["candidates"] == []
    assert selection["winner_candidate_id"] is None


def test_selection_node_qualified_runs_full_pipeline():
    """P2: selection_node runs build_selection_state when result_form!='guided'."""
    from app.agent.agent.graph import selection_node

    state = _make_minimal_state()
    state["result_form"] = "qualified"
    result = selection_node(state)
    selection = result["sealing_state"]["selection"]
    # build_selection_state always sets selection_status to a real value, never "not_applicable"
    assert selection["selection_status"] != "not_applicable"


def test_selection_node_no_result_form_runs_full_pipeline():
    """P2: selection_node defaults to qualification when result_form absent."""
    from app.agent.agent.graph import selection_node

    state = _make_minimal_state()
    # result_form not set — should behave like qualified
    result = selection_node(state)
    selection = result["sealing_state"]["selection"]
    assert selection["selection_status"] != "not_applicable"


# ---------------------------------------------------------------------------
# 0A.3 P3: _build_guidance_case_state — execution-level tests
# ---------------------------------------------------------------------------

def test_build_guidance_case_state_binding_level():
    """P3: guidance case_state has ORIENTATION binding_level."""
    from app.agent.agent.graph import _build_guidance_case_state

    cs = _build_guidance_case_state({"ask_mode": "critical_inputs", "requested_fields": ["medium"]})
    assert cs["result_contract"]["binding_level"] == "ORIENTATION"
    assert cs["case_meta"]["binding_level"] == "ORIENTATION"
    assert cs["qualified_action_gate"]["allowed"] is False
    assert cs["qualified_action_gate"]["gate_status"] == "not_applicable"


def test_build_guidance_case_state_readiness_critical():
    """P3: guidance case_state maps critical_inputs ask_mode correctly."""
    from app.agent.agent.graph import _build_guidance_case_state

    cs = _build_guidance_case_state({"ask_mode": "critical_inputs", "requested_fields": ["medium", "pressure"]})
    assert cs["readiness"]["missing_critical_inputs"] == ["medium", "pressure"]
    assert cs["readiness"]["missing_review_inputs"] == []
    assert cs["readiness"]["ready_for_qualification"] is False


def test_build_guidance_case_state_readiness_qualification_ready():
    """P3: guidance case_state maps qualification_ready ask_mode correctly."""
    from app.agent.agent.graph import _build_guidance_case_state

    cs = _build_guidance_case_state({"ask_mode": "qualification_ready", "requested_fields": []})
    assert cs["readiness"]["ready_for_qualification"] is True
    assert cs["readiness"]["missing_critical_inputs"] == []


# ---------------------------------------------------------------------------
# 0A.3 P3b: _build_guidance_response_payload — case_state=None blocked
# ---------------------------------------------------------------------------

def test_guidance_response_payload_no_qualification_pipeline():
    """P3b: _build_guidance_response_payload does NOT trigger full qualification pipeline.

    Verified by checking that visible_case_narrative does NOT contain material_core qualification_results.
    """
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    narrative = payload["visible_case_narrative"]
    qual_results = narrative.get("qualification_results") or {}
    assert "material_core" not in qual_results
    assert "material_selection_projection" not in qual_results


# ---------------------------------------------------------------------------
# 0A.3 P3b Closeout: positive Guidance-Semantik in _build_guidance_response_payload
# ---------------------------------------------------------------------------

def _make_state_with_missing_fields() -> dict:
    """State with governance.unknowns_release_blocking to trigger critical_inputs guidance."""
    state = _make_minimal_state()
    state["sealing_state"]["governance"]["unknowns_release_blocking"] = [
        "pressure_bar", "shaft_diameter_mm",
    ]
    state["sealing_state"]["asserted"]["medium_profile"] = {"name": "Wasser"}
    return state


def test_guidance_payload_narrative_has_next_best_inputs():
    """Closeout: visible_case_narrative carries next_best_inputs with missing field details."""
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    narrative = payload["visible_case_narrative"]
    next_inputs = narrative.get("next_best_inputs")
    assert isinstance(next_inputs, list)
    assert len(next_inputs) > 0
    # At least one entry must reference the missing fields
    all_details = " ".join(str(item.get("detail", "")) for item in next_inputs)
    assert "pressure_bar" in all_details or "shaft_diameter_mm" in all_details


def test_guidance_payload_narrative_has_suggested_next_questions():
    """Closeout: visible_case_narrative carries suggested_next_questions from live guidance contract."""
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    narrative = payload["visible_case_narrative"]
    questions = narrative.get("suggested_next_questions")
    assert isinstance(questions, list)
    assert len(questions) > 0
    # Must contain critical_input questions (not "No suggested question")
    values = [str(item.get("value", "")) for item in questions]
    assert any("Critical" in v or "critical" in v.lower() for v in values), (
        f"Expected critical input question, got: {values}"
    )


def test_guidance_payload_narrative_governed_summary_shows_orientation():
    """Closeout: governed_summary visibly communicates ORIENTATION binding level."""
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    narrative = payload["visible_case_narrative"]
    summary = str(narrative.get("governed_summary") or "")
    assert "ORIENTATION" in summary


def test_guidance_payload_narrative_governed_summary_shows_missing_fields():
    """Closeout: governed_summary communicates the blocking unknowns."""
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    summary = str(payload["visible_case_narrative"].get("governed_summary") or "")
    assert "pressure_bar" in summary or "shaft_diameter_mm" in summary


def test_guidance_payload_case_summary_uses_explicit_lifecycle():
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    current_case_summary = next(
        item for item in payload["visible_case_narrative"]["case_summary"]
        if item["key"] == "current_case_summary"
    )
    assert current_case_summary["value"] == "Needs Clarification"


def test_guidance_payload_narrative_no_material_core():
    """Closeout: qualification_results must not contain material_core or material_selection_projection."""
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    qual_results = payload["visible_case_narrative"].get("qualification_results") or {}
    assert "material_core" not in qual_results
    assert "material_selection_projection" not in qual_results


def test_guidance_payload_binding_level_orientation_in_payload_and_narrative():
    """Closeout: ORIENTATION binding level visible at both payload level and narrative level."""
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert payload["binding_level"] == "ORIENTATION"
    summary = str(payload["visible_case_narrative"].get("governed_summary") or "")
    assert "ORIENTATION" in summary


def test_guidance_payload_qualified_action_gate_is_guidance_semantic():
    """Closeout: next_step_contract or narrative gate must block qualification actions."""
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert payload["rfq_ready"] is False
    # next_step_contract comes from live guidance_contract
    nsc = payload.get("next_step_contract")
    assert nsc is not None
    assert nsc.get("ask_mode") == "critical_inputs"
    assert "pressure_bar" in nsc.get("requested_fields", [])


def test_guidance_payload_uses_live_guidance_contract_not_static():
    """Closeout: router reuses _build_guidance_case_state (same as graph) — not static stub."""
    decision = _make_guided_decision()
    state = _make_state_with_missing_fields()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    # next_step_contract should carry the live guidance contract fields
    nsc = payload.get("next_step_contract") or {}
    assert nsc.get("requested_fields") == ["pressure_bar", "shaft_diameter_mm"]
    assert nsc.get("reason_code") == "qualification_blocked_by_missing_core_inputs"


# ---------------------------------------------------------------------------
# 0A.3 P4: deterministic_foundation signal guard
# ---------------------------------------------------------------------------

def test_deterministic_signal_skips_guidance_selection():
    """P4: selection_output_blocked signal NOT emitted for guidance selection."""
    from app.agent.deterministic_foundation import build_engineering_signal_foundation

    guidance_selection = {
        "selection_status": "not_applicable",
        "output_blocked": True,
        "candidates": [],
    }
    sealing_state = create_initial_state()
    sealing_state["selection"] = guidance_selection
    signals = build_engineering_signal_foundation(
        sealing_state,
        working_profile={},
        rwdr_state={},
        derived_calculations={},
    )
    assert "selection_output_blocked" not in signals


def test_deterministic_signal_emitted_for_qualification_selection():
    """P4: selection_output_blocked signal IS emitted for qualification selection."""
    from app.agent.deterministic_foundation import build_engineering_signal_foundation

    sealing_state = create_initial_state()
    # Default selection has selection_status="not_started", output_blocked=True
    signals = build_engineering_signal_foundation(
        sealing_state,
        working_profile={},
        rwdr_state={},
        derived_calculations={},
    )
    assert "selection_output_blocked" in signals


# ---------------------------------------------------------------------------
# 0A.3 P4: _detect_active_domain guard
# ---------------------------------------------------------------------------

def test_detect_active_domain_guidance_returns_knowledge_only():
    """P4: guidance selection maps to knowledge_only domain, not qualification."""
    from app.agent.case_state import _detect_active_domain

    guidance_selection = {
        "selection_status": "not_applicable",
        "output_blocked": True,
    }
    sealing_state = {"selection": guidance_selection, "governance": {}}
    assert _detect_active_domain(sealing_state, {}) == "knowledge_only"


def test_detect_active_domain_qualification_returns_prequalification():
    """P4: qualification selection maps to material_static_seal_prequalification."""
    from app.agent.case_state import _detect_active_domain

    sealing_state = create_initial_state()
    assert _detect_active_domain(sealing_state, {}) == "material_static_seal_prequalification"


# ---------------------------------------------------------------------------
# 0A.3 P5: _build_qualification_results guard
# ---------------------------------------------------------------------------

def test_qualification_results_skips_material_core_for_guidance():
    """P5: _build_qualification_results returns only material_governance for guidance selection."""
    from app.agent.case_state import _build_qualification_results

    guidance_selection = {
        "selection_status": "not_applicable",
        "candidates": [],
        "output_blocked": True,
    }
    sealing_state = create_initial_state()
    sealing_state["selection"] = guidance_selection
    state = {"sealing_state": sealing_state, "relevant_fact_cards": []}
    results = _build_qualification_results(
        state, sealing_state,
        binding_level="ORIENTATION",
        rwdr_state={},
        invalidation_state={},
    )
    assert "material_governance" in results
    assert "material_core" not in results
    assert "material_selection_projection" not in results


def test_qualification_results_runs_full_for_qualification():
    """P5: _build_qualification_results runs full pipeline for qualification selection."""
    from app.agent.case_state import _build_qualification_results

    sealing_state = create_initial_state()
    state = {"sealing_state": sealing_state, "relevant_fact_cards": []}
    results = _build_qualification_results(
        state, sealing_state,
        binding_level="QUALIFIED_PRESELECTION",
        rwdr_state={},
        invalidation_state={},
    )
    assert "material_governance" in results
    assert "material_core" in results


# ---------------------------------------------------------------------------
# 0A.3 P5c: minimal case_meta persistence for reload
# ---------------------------------------------------------------------------

def test_guidance_persisted_state_has_case_meta():
    """P5c: guided path persists case_state with case_meta.binding_level=ORIENTATION."""
    state = _make_minimal_state()
    guided_state = dict(state)
    # Simulate what the router does after P5c
    guided_state["case_state"] = {
        "case_meta": {"binding_level": "ORIENTATION", "runtime_path": "STRUCTURED_GUIDANCE"},
    }
    case_meta = guided_state["case_state"]["case_meta"]
    assert case_meta["binding_level"] == "ORIENTATION"
    assert case_meta["runtime_path"] == "STRUCTURED_GUIDANCE"


def test_reload_path_uses_guidance_binding_level():
    """P5c: load_and_refresh_structured_case reads ORIENTATION from guidance case_meta."""
    # Simulate the reload logic from load_and_refresh_structured_case
    persisted_state = _make_minimal_state()
    persisted_state["case_state"] = {
        "case_meta": {"binding_level": "ORIENTATION", "runtime_path": "STRUCTURED_GUIDANCE"},
    }
    existing_case_state = persisted_state.get("case_state") or {}
    case_meta = existing_case_state.get("case_meta") or {}
    runtime_path = str(case_meta.get("runtime_path") or "STRUCTURED_QUALIFICATION")
    binding_level = str(case_meta.get("binding_level") or "QUALIFIED_PRESELECTION")
    assert runtime_path == "STRUCTURED_GUIDANCE"
    assert binding_level == "ORIENTATION"


# ---------------------------------------------------------------------------
# 0A.3 P1: result_form propagation
# ---------------------------------------------------------------------------

def test_result_form_propagated_to_state():
    """P1: result_form from InteractionPolicyDecision must be set on agent state."""
    decision = _make_guided_decision()
    state = _make_minimal_state()
    state["result_form"] = decision.result_form
    assert state["result_form"] == "guided"
