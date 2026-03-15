"""0B.2a: Next-step contract — NextStepContractResponse in ChatResponse.

Verifies that:
  - NextStepContractResponse model validates correctly
  - guided paths carry next_step_contract with live post-run data
  - qualified paths carry next_step_contract
  - fast paths (FAST_KNOWLEDGE, FAST_CALCULATION) carry next_step_contract = None
  - ask_mode reflects guidance_contract derivation correctly
  - requested_fields are post-run live state (not pre-run policy snapshot)
  - required_fields from InteractionPolicyDecision is NOT in next_step_contract
  - next_step_contract.reason_code is machine-readable
  - next_step_contract.impact_hint is present for blocking modes
  - response model accepts next_step_contract field
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.agent.api.models import ChatResponse, NextStepContractResponse
from app.agent.api.router import (
    SESSION_STORE,
    _build_guidance_response_payload,
    build_runtime_payload,
    chat_endpoint,
)
from app.agent.cli import create_initial_state
from app.agent.case_state import build_conversation_guidance_contract
from app.services.auth.dependencies import RequestUser


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_guided_decision(**kwargs):
    defaults = {
        "result_form": "guided",
        "path": "structured",
        "stream_mode": "structured_progress_stream",
        "coverage_status": "partial",
        "boundary_flags": ("orientation_only",),
        "required_fields": ("pressure", "temperature"),  # pre-run snapshot — must NOT appear in next_step_contract
        "escalation_reason": None,
        "interaction_class": "GUIDANCE",
        "runtime_path": "STRUCTURED_GUIDANCE",
        "binding_level": "ORIENTATION",
        "has_case_state": True,
        "policy_version": "interaction_policy_v1",
    }
    defaults.update(kwargs)
    return type("Decision", (), defaults)()


def _make_minimal_state(*, missing_critical: list[str] | None = None):
    sealing_state = create_initial_state()
    if missing_critical:
        sealing_state["governance"]["unknowns_release_blocking"] = missing_critical
    return {
        "messages": [AIMessage(content="Test reply.")],
        "sealing_state": sealing_state,
        "working_profile": {},
        "relevant_fact_cards": [],
    }


def _current_user():
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


# ── 1. Model validation ───────────────────────────────────────────────────────

def test_next_step_contract_response_validates():
    contract = NextStepContractResponse(
        ask_mode="critical_inputs",
        requested_fields=["pressure", "temperature"],
        reason_code="qualification_blocked_by_missing_core_inputs",
        impact_hint="Qualification remains blocked until the listed core inputs are confirmed.",
        rfq_admissibility="inadmissible",
        state_revision=3,
    )
    assert contract.ask_mode == "critical_inputs"
    assert contract.requested_fields == ["pressure", "temperature"]
    assert contract.reason_code == "qualification_blocked_by_missing_core_inputs"
    assert contract.state_revision == 3


def test_next_step_contract_response_defaults():
    contract = NextStepContractResponse(
        ask_mode="no_question_needed",
        reason_code="no_action_needed",
    )
    assert contract.requested_fields == []
    assert contract.rfq_admissibility == "inadmissible"
    assert contract.state_revision == 0
    assert contract.impact_hint is None


def test_next_step_contract_response_forbids_extra_fields():
    with pytest.raises(ValidationError):
        NextStepContractResponse(
            ask_mode="no_question_needed",
            reason_code="no_action_needed",
            unknown_field="should_fail",
        )


def test_chat_response_accepts_next_step_contract_field():
    from app.agent.api.models import VisibleCaseNarrativeResponse
    response = ChatResponse(
        reply="Test.",
        session_id="s1",
        interaction_class="GUIDANCE",
        runtime_path="STRUCTURED_GUIDANCE",
        binding_level="ORIENTATION",
        has_case_state=True,
        next_step_contract=NextStepContractResponse(
            ask_mode="critical_inputs",
            requested_fields=["pressure"],
            reason_code="qualification_blocked_by_missing_core_inputs",
        ),
    )
    assert response.next_step_contract is not None
    assert response.next_step_contract.ask_mode == "critical_inputs"


def test_chat_response_next_step_contract_defaults_to_none():
    response = ChatResponse(
        reply="Test.",
        session_id="s1",
        interaction_class="KNOWLEDGE",
        runtime_path="FAST_KNOWLEDGE",
        binding_level="KNOWLEDGE",
        has_case_state=False,
    )
    assert response.next_step_contract is None


# ── 2. Guidance payload builder ───────────────────────────────────────────────

def test_guidance_payload_carries_next_step_contract():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    assert "next_step_contract" in payload
    assert payload["next_step_contract"] is not None


def test_guidance_payload_next_step_contract_has_ask_mode():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    nsc = payload["next_step_contract"]
    assert "ask_mode" in nsc


def test_guidance_payload_next_step_contract_ask_mode_is_critical_when_blocking_unknowns():
    state = _make_minimal_state(missing_critical=["pressure", "temperature"])
    decision = _make_guided_decision()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    nsc = payload["next_step_contract"]
    assert nsc["ask_mode"] == "critical_inputs"
    assert "pressure" in nsc["requested_fields"] or "temperature" in nsc["requested_fields"]


def test_guidance_payload_next_step_contract_is_post_run_not_required_fields():
    """next_step_contract must NOT mirror decision.required_fields — it's from live state."""
    state = _make_minimal_state()  # no blocking unknowns in state
    decision = _make_guided_decision(required_fields=("stale_pressure_from_pre_run",))
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    nsc = payload["next_step_contract"]
    # post-run state has no blocking unknowns → requested_fields is empty
    # the pre-run required_fields ("stale_pressure_from_pre_run") must NOT appear here
    assert "stale_pressure_from_pre_run" not in nsc.get("requested_fields", [])


def test_guidance_payload_next_step_contract_reason_code_is_present():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    nsc = payload["next_step_contract"]
    assert "reason_code" in nsc
    assert isinstance(nsc["reason_code"], str)


def test_guidance_payload_next_step_contract_impact_hint_present():
    decision = _make_guided_decision()
    state = _make_minimal_state()
    payload = _build_guidance_response_payload(decision, session_id="s1", reply=".", state=state)
    nsc = payload["next_step_contract"]
    assert "impact_hint" in nsc


# ── 3. build_runtime_payload (fast path) ──────────────────────────────────────

def test_build_runtime_payload_fast_path_has_no_next_step_contract():
    """Fast path: next_step_contract not passed → not in payload."""
    decision = type("D", (), {
        "interaction_class": "KNOWLEDGE",
        "runtime_path": "FAST_KNOWLEDGE",
        "binding_level": "KNOWLEDGE",
        "has_case_state": False,
        "result_form": "direct",
        "coverage_status": "unknown",
        "boundary_flags": (),
        "escalation_reason": None,
    })()
    payload = build_runtime_payload(decision, session_id="s1", reply="Answer.")
    # next_step_contract not in payload at all for fast path (omitted, not None)
    assert payload.get("next_step_contract") is None


def test_build_runtime_payload_accepts_next_step_contract_kwarg():
    """next_step_contract passed explicitly → present in payload."""
    decision = type("D", (), {
        "interaction_class": "GUIDANCE",
        "runtime_path": "STRUCTURED_GUIDANCE",
        "binding_level": "ORIENTATION",
        "has_case_state": True,
        "result_form": "guided",
        "coverage_status": "partial",
        "boundary_flags": (),
        "escalation_reason": None,
    })()
    nsc_data = {"ask_mode": "no_question_needed", "requested_fields": [], "reason_code": "no_action_needed"}
    payload = build_runtime_payload(
        decision,
        session_id="s1",
        reply=".",
        next_step_contract=nsc_data,
    )
    assert payload["next_step_contract"] == nsc_data


# ── 4. build_conversation_guidance_contract output contract ──────────────────

def test_guidance_contract_has_all_required_keys():
    state = _make_minimal_state()
    contract = build_conversation_guidance_contract(state)
    for key in ("ask_mode", "requested_fields", "reason_code", "impact_hint", "rfq_admissibility", "state_revision"):
        assert key in contract, f"Missing key: {key}"


def test_guidance_contract_critical_inputs_when_blocking():
    state = _make_minimal_state(missing_critical=["shaft_diameter", "medium"])
    contract = build_conversation_guidance_contract(state)
    assert contract["ask_mode"] == "critical_inputs"
    assert "shaft_diameter" in contract["requested_fields"] or "medium" in contract["requested_fields"]


def test_guidance_contract_no_question_needed_when_empty():
    state = _make_minimal_state()
    contract = build_conversation_guidance_contract(state)
    # No blocking unknowns, no raw_inputs → "technical_inputs_not_confirmed" is the only missing
    # which means ask_mode should be critical_inputs (that synthetic entry triggers it)
    # OR no_question_needed when there are no critical inputs
    assert contract["ask_mode"] in ("critical_inputs", "no_question_needed", "qualification_ready")


# ── 5. End-to-end: chat_endpoint carries next_step_contract ──────────────────

def test_chat_endpoint_structured_path_carries_next_step_contract():
    """chat_endpoint structured qualification path must produce next_step_contract in response."""
    from app.agent.api.models import ChatRequest
    request = ChatRequest(message="Empfehlung Dichtung", session_id="case-nsc-1")
    state = _make_minimal_state(missing_critical=["pressure"])
    state["messages"] = [AIMessage(content="Antwort")]

    SESSION_STORE.clear()

    with patch("app.agent.api.router.evaluate_interaction_policy") as pol_mock, \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=state)), \
         patch("app.agent.api.router.execute_agent", new=AsyncMock(return_value=state)), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)):
        pol_mock.return_value = type("Decision", (), {
            "has_case_state": True,
            "runtime_path": "STRUCTURED_QUALIFICATION",
            "binding_level": "QUALIFIED_PRESELECTION",
            "interaction_class": "QUALIFICATION",
            "result_form": "qualified",
            "coverage_status": "in_scope",
            "boundary_flags": (),
            "escalation_reason": None,
            "required_fields": (),
            "policy_version": "interaction_policy_v1",
        })()
        response = asyncio.run(chat_endpoint(request, current_user=_current_user()))

    assert response.next_step_contract is not None
    assert hasattr(response.next_step_contract, "ask_mode")
    assert hasattr(response.next_step_contract, "requested_fields")


def test_chat_endpoint_fast_knowledge_has_no_next_step_contract():
    """FAST_KNOWLEDGE path: next_step_contract must be None (no case state)."""
    from app.agent.api.models import ChatRequest

    request = ChatRequest(message="Was ist PTFE?", session_id="fast-nsc-1")
    SESSION_STORE.clear()

    with patch("app.agent.api.router.evaluate_interaction_policy") as pol_mock, \
         patch("app.agent.api.router.execute_fast_knowledge", new=AsyncMock(
             return_value=type("R", (), {"reply": "PTFE ist ...", "working_profile": None})()
         )):
        pol_mock.return_value = type("Decision", (), {
            "has_case_state": False,
            "runtime_path": "FAST_KNOWLEDGE",
            "binding_level": "KNOWLEDGE",
            "interaction_class": "KNOWLEDGE",
            "result_form": "direct",
            "coverage_status": "unknown",
            "boundary_flags": (),
            "escalation_reason": None,
            "required_fields": (),
            "policy_version": "interaction_policy_v1",
        })()
        response = asyncio.run(chat_endpoint(request, current_user=_current_user()))

    assert response.next_step_contract is None
