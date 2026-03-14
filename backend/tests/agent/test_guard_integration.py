"""
Integration tests for hardening guard wired into graph.py and runtime.py — G01–G06.

These tests verify that:
- Guard passes allowed fields through to the state reducer (G01)
- Guard strips forbidden keys and logs CRITICAL (G02)
- assert_deterministic_unchanged causes no false positives on a normal run (G03)
- assert_deterministic_unchanged raises RuntimeError when governance is mutated (G04)
- reasoning_node does not mutate deterministic layers during extract_parameters (G05)
- execute_fast_calculation appends a [PLAUSIBILITY] warning for out-of-range results (G06)
"""
import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.agent.graph import evidence_tool_node, reasoning_node, reasoning_node_sync
from app.agent.agent.state import AgentState, SealingAIState
from app.agent.case_state import build_default_sealing_requirement_spec
from app.agent.evidence.models import ClaimType
from app.agent.hardening.guard import (
    assert_deterministic_unchanged,
    snapshot_deterministic_layers,
)
from app.agent.runtime import execute_fast_calculation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_full_sealing_state(state_revision: int = 1) -> SealingAIState:
    """Minimal but complete SealingAIState suitable for all 5 deterministic layers."""
    return {
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "asserted": {
            "medium_profile": {},
            "machine_profile": {},
            "installation_profile": {},
            "operating_conditions": {},
            "sealing_requirement_spec": build_default_sealing_requirement_spec(
                analysis_cycle_id="guard_test_1",
                state_revision=state_revision,
            ),
        },
        "governance": {
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "scope_of_validity": [],
            "assumptions_active": [],
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        },
        "cycle": {
            "analysis_cycle_id": "guard_test_1",
            "snapshot_parent_revision": 0,
            "superseded_by_cycle": None,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
            "state_revision": state_revision,
        },
        "selection": {
            "selection_status": "not_started",
            "candidates": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "winner_candidate_id": None,
            "recommendation_artifact": None,
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
        },
    }


def _tool_call_message(statement: str, claim_type: str = "fact_observed") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "submit_claim",
                "args": {
                    "claim_type": claim_type,
                    "statement": statement,
                    "confidence": 1.0,
                    "source_fact_ids": [],
                },
                "id": "call_guard_test",
            }
        ],
    )


def _stream_once(message):
    yield message


# ---------------------------------------------------------------------------
# G01: allowed claim target passes guard and reaches state
# ---------------------------------------------------------------------------


def test_G01_temperature_claim_passes_guard_and_reaches_state():
    """
    G01: A claim with an explicit temperature value passes claim_whitelist_check
    and the temperature ends up in the normalized layer of the new sealing state.
    The state revision increments, proving process_cycle_update ran.
    """
    state: AgentState = {
        "messages": [_tool_call_message("Die Betriebstemperatur beträgt 150 C.")],
        "sealing_state": _make_full_sealing_state(state_revision=1),
        "relevant_fact_cards": [],
        "working_profile": {},
        "tenant_id": None,
    }

    result = evidence_tool_node(state)

    new_sealing_state = result["sealing_state"]
    # Revision advanced — process_cycle_update ran successfully
    assert new_sealing_state["cycle"]["state_revision"] == 2
    # Temperature extracted and stored in normalized layer
    normalized_params = new_sealing_state["normalized"].get("normalized_parameters", {})
    assert "temperature_c" in normalized_params
    assert normalized_params["temperature_c"] == 150.0


# ---------------------------------------------------------------------------
# G02: forbidden key in validated_params is stripped with CRITICAL log
# ---------------------------------------------------------------------------


def test_G02_forbidden_key_stripped_and_logged(caplog):
    """
    G02: When evaluate_claim_conflicts (mocked) returns a validated_params dict
    containing a forbidden key ("hard_stops"), claim_whitelist_check strips it
    and emits a CRITICAL log before process_cycle_update is called.
    """
    state: AgentState = {
        "messages": [_tool_call_message("Die Temperatur ist 80 C.")],
        "sealing_state": _make_full_sealing_state(state_revision=1),
        "relevant_fact_cards": [],
        "working_profile": {},
        "tenant_id": None,
    }

    # Mock evaluate_claim_conflicts to inject a forbidden key
    with caplog.at_level(logging.CRITICAL, logger="app.agent.hardening.guard"), \
         patch(
             "app.agent.agent.graph.evaluate_claim_conflicts",
             return_value=([], {"temperature": 80.0, "hard_stops": ["nbr_blocked"]}),
         ):
        result = evidence_tool_node(state)

    new_sealing_state = result["sealing_state"]
    # State update still succeeded — allowed key passed through
    assert new_sealing_state["cycle"]["state_revision"] == 2

    # CRITICAL log emitted for the forbidden key
    violations = [r for r in caplog.records if "GUARD VIOLATION" in r.message]
    assert len(violations) >= 1
    assert "hard_stops" in violations[0].message

    # The forbidden key never reached any part of the sealing state
    state_str = str(new_sealing_state)
    assert "hard_stops" not in state_str


# ---------------------------------------------------------------------------
# G03: normal graph run — assert_deterministic_unchanged produces no false positives
# ---------------------------------------------------------------------------


def test_G03_no_false_positive_invariant_on_normal_run():
    """
    G03: A full evidence_tool_node run with a valid claim must NOT raise
    RuntimeError from assert_deterministic_unchanged.

    The guard is placed BEFORE process_cycle_update and checks that
    evaluate_claim_conflicts did not mutate the deterministic layers.
    process_cycle_update itself is ALLOWED to change governance/cycle/selection
    (that is its purpose), so the assert is intentionally checked before it runs.
    """
    state: AgentState = {
        "messages": [_tool_call_message("Druck beträgt 10 bar.")],
        "sealing_state": _make_full_sealing_state(state_revision=1),
        "relevant_fact_cards": [],
        "working_profile": {},
        "tenant_id": None,
    }

    # Must not raise — evaluate_claim_conflicts does not mutate sealing_state
    result = evidence_tool_node(state)
    assert "sealing_state" in result
    assert result["sealing_state"]["cycle"]["state_revision"] == 2


# ---------------------------------------------------------------------------
# G04: manually injected governance mutation → RuntimeError
# ---------------------------------------------------------------------------


def test_G04_injected_governance_mutation_raises_runtime_error():
    """
    G04: If governance is modified between snapshot and assert,
    assert_deterministic_unchanged raises RuntimeError with a CRITICAL message.

    Simulates what would happen if evaluate_claim_conflicts (or any code before the
    deterministic reducer) unexpectedly mutated the sealing_state's governance layer.
    """
    sealing_state = {
        "governance": {"release_status": "inadmissible", "conflicts": []},
        "cycle": {"state_revision": 1, "contract_obsolete": False},
        "selection": {"selection_status": "not_started", "output_blocked": True},
    }

    before_hash = snapshot_deterministic_layers(sealing_state)

    # Simulate unexpected mutation of governance (e.g., a bug in evaluate_claim_conflicts)
    sealing_state["governance"]["release_status"] = "rfq_ready"

    with pytest.raises(RuntimeError, match="CRITICAL INVARIANT VIOLATION"):
        assert_deterministic_unchanged(
            before_hash, sealing_state, node_name="evidence_tool_node"
        )


# ---------------------------------------------------------------------------
# G05: reasoning_node does not mutate deterministic layers during extract_parameters
# ---------------------------------------------------------------------------


def test_G05_reasoning_node_extract_parameters_leaves_deterministic_layers_unchanged():
    """
    G05: Running reasoning_node_sync with a query containing numeric parameters
    (temperature, pressure, shaft dimensions) must not mutate the deterministic
    layers (governance/cycle/selection) in sealing_state.
    The assert_deterministic_unchanged call inside reasoning_node_sync must not raise.
    """
    sealing_state = _make_full_sealing_state(state_revision=1)
    state: AgentState = {
        "messages": [HumanMessage(content="Welle 50mm, 3000 rpm, 10 bar, 80 C")],
        "sealing_state": sealing_state,
        "relevant_fact_cards": [],
        "working_profile": {},
        "tenant_id": None,
    }

    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value.stream = MagicMock(
        side_effect=lambda messages, config=None: _stream_once(
            AIMessage(content="Acknowledged.", tool_calls=[])
        )
    )

    with patch("app.agent.agent.graph.get_llm", return_value=mock_llm), \
         patch("app.agent.agent.graph._retrieve_relevant_cards_sync", return_value=[]):
        # Must not raise RuntimeError from assert_deterministic_unchanged
        result = reasoning_node_sync(state)

    assert "working_profile" in result
    # extract_parameters extracted at least one numeric field
    profile = result["working_profile"]
    assert profile.get("speed") == 3000.0 or profile.get("diameter") == 50.0


# ---------------------------------------------------------------------------
# G06: execute_fast_calculation with extreme speed → PLAUSIBILITY warning in reply
# ---------------------------------------------------------------------------


def test_G06_fast_calculation_appends_plausibility_warning_for_out_of_range_speed():
    """
    G06: execute_fast_calculation with d=80mm, n=40000 rpm produces
    v ≈ 167.6 m/s > 150 m/s threshold.
    The reply must contain a [PLAUSIBILITY] warning string.
    """
    # "80mm 40000 rpm" → v ≈ 167.6 m/s
    message = "Berechne Umfangsgeschwindigkeit: Durchmesser 80mm, Drehzahl 40000 rpm"

    result = asyncio.run(execute_fast_calculation(message))

    assert "[PLAUSIBILITY]" in result.reply
    assert "150" in result.reply or "m/s" in result.reply
    # The numeric result is still present — plausibility warns but does not block
    assert "167" in result.reply or "Umfangsgeschwindigkeit" in result.reply
