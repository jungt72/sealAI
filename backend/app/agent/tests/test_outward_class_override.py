"""
Tests for knowledge/comparison question override in GOVERNED sessions.

Verifies that:
  - Knowledge questions in a GOVERNED session → conversational_answer
  - Comparison questions in a GOVERNED session → exploration_answer
  - Parameter corrections ("statt", "korrigiere") → governed_state_update (no override)
  - Sealing type changes → governed_state_update (no override)
  - classify_message_as_knowledge_override returns None for normal messages
"""
from __future__ import annotations

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.output_contract_node import (
    _determine_response_class,
    classify_message_as_knowledge_override,
)
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernanceState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _full_a_state(pending: str = "") -> GraphState:
    """GraphState with gov_class A — would normally yield governed_state_update."""
    assertions = {
        "medium":        _claim("medium",        "Salzwasser", "confirmed"),
        "pressure_bar":  _claim("pressure_bar",  10.0,         "confirmed"),
        "temperature_c": _claim("temperature_c", 80.0,         "confirmed"),
        "shaft_diameter_mm": _claim("shaft_diameter_mm", 50.0, "confirmed"),
        "sealing_type":  _claim("sealing_type",  "mechanical_seal", "confirmed"),
    }
    governance = GovernanceState(gov_class="A", rfq_admissible=False)
    return GraphState(
        asserted=AssertedState(assertions=assertions),
        governance=governance,
        pending_message=pending,
    )


# ---------------------------------------------------------------------------
# Unit tests: classify_message_as_knowledge_override
# ---------------------------------------------------------------------------

class TestClassifyMessageAsKnowledgeOverride:
    """Unit tests for the standalone classifier (no graph state needed)."""

    # Knowledge patterns → conversational_answer
    def test_was_ist_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("was ist ein O-Ring?") == "conversational_answer"

    def test_was_sind_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("Was sind Gleitringdichtungen?") == "conversational_answer"

    def test_erklaere_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("Erkläre mir PTFE") == "conversational_answer"

    def test_wie_funktioniert_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("Wie funktioniert eine Stopfbuchse?") == "conversational_answer"

    def test_was_bedeutet_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("Was bedeutet PV-Wert?") == "conversational_answer"

    # Comparison patterns → exploration_answer
    def test_vergleiche_returns_exploration_answer(self):
        assert classify_message_as_knowledge_override("vergleiche NBR und PTFE") == "exploration_answer"

    def test_unterschied_returns_exploration_answer(self):
        assert classify_message_as_knowledge_override("Unterschied zwischen FKM und EPDM?") == "exploration_answer"

    def test_versus_returns_exploration_answer(self):
        assert classify_message_as_knowledge_override("NBR versus PTFE") == "exploration_answer"

    def test_vs_returns_exploration_answer(self):
        assert classify_message_as_knowledge_override("FKM vs. EPDM — was ist besser?") == "exploration_answer"

    def test_besser_oder_returns_exploration_answer(self):
        assert classify_message_as_knowledge_override("Was ist besser: Gleitring oder RWDR?") == "exploration_answer"

    # Parameter update markers → None (no override)
    def test_statt_marker_suppresses_override(self):
        assert classify_message_as_knowledge_override("80°C statt 90°C") is None

    def test_statt_sealing_type_suppresses_override(self):
        assert classify_message_as_knowledge_override("statt Gleitring RWDR") is None

    def test_korrigiere_suppresses_override(self):
        assert classify_message_as_knowledge_override("Korrigiere den Druck auf 15 bar") is None

    def test_sondern_suppresses_override(self):
        assert classify_message_as_knowledge_override("nicht 80°C sondern 120°C") is None

    # Normal governed messages → None
    def test_parameter_message_returns_none(self):
        assert classify_message_as_knowledge_override("Salzwasser 80°C 50mm 6000rpm 10bar") is None

    def test_empty_message_returns_none(self):
        assert classify_message_as_knowledge_override("") is None

    def test_greeting_returns_none(self):
        # Greetings don't match knowledge/comparison patterns
        assert classify_message_as_knowledge_override("Hallo") is None

    def test_thanks_returns_none(self):
        assert classify_message_as_knowledge_override("vielen Dank") is None

    # New patterns (Phase H)
    def test_was_versteht_man_unter_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("Was versteht man unter einem RWDR?") == "conversational_answer"

    def test_kannst_du_erklaeren_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("Kannst du mir erklären was ein RWDR ist?") == "conversational_answer"

    def test_erklaere_mir_rwdr_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("erkläre mir was ein RWDR ist") == "conversational_answer"

    def test_erklaer_rwdr_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("erkläre RWDR") == "conversational_answer"

    # Case-insensitive
    def test_was_ist_uppercase_returns_conversational_answer(self):
        assert classify_message_as_knowledge_override("WAS IST ein O-Ring?") == "conversational_answer"

    def test_vergleiche_uppercase_returns_exploration_answer(self):
        assert classify_message_as_knowledge_override("VERGLEICHE NBR und PTFE") == "exploration_answer"


# ---------------------------------------------------------------------------
# Integration tests: _determine_response_class with pending_message
# ---------------------------------------------------------------------------

class TestDetermineResponseClassWithOverride:
    """Tests that _determine_response_class respects knowledge/comparison overrides."""

    def test_knowledge_question_in_governed_returns_conversational_answer(self):
        state = _full_a_state(pending="was ist ein O-Ring?")
        result = _determine_response_class(state)
        assert result == "conversational_answer"

    def test_comparison_question_in_governed_returns_exploration_answer(self):
        state = _full_a_state(pending="vergleiche NBR und PTFE")
        result = _determine_response_class(state)
        assert result == "exploration_answer"

    def test_param_update_statt_remains_governed_state_update(self):
        state = _full_a_state(pending="80°C statt 90°C")
        result = _determine_response_class(state)
        # Gov class A without compute → governed_state_update
        assert result == "governed_state_update"

    def test_sealing_type_change_statt_remains_governed_state_update(self):
        state = _full_a_state(pending="statt Gleitring RWDR")
        result = _determine_response_class(state)
        assert result == "governed_state_update"

    def test_normal_technical_message_remains_governed_state_update(self):
        state = _full_a_state(pending="Salzwasser, 80°C, 10bar, 50mm Welle")
        result = _determine_response_class(state)
        assert result == "governed_state_update"

    def test_empty_pending_message_falls_through_to_gov_class_logic(self):
        state = _full_a_state(pending="")
        result = _determine_response_class(state)
        # Without override: gov_class A, no compute → governed_state_update
        assert result == "governed_state_update"

    def test_was_sind_gleitringdichtungen_returns_conversational_answer(self):
        state = _full_a_state(pending="Was sind Gleitringdichtungen?")
        result = _determine_response_class(state)
        assert result == "conversational_answer"

    def test_erklaere_ptfe_returns_conversational_answer(self):
        state = _full_a_state(pending="Erkläre mir PTFE kurz")
        result = _determine_response_class(state)
        assert result == "conversational_answer"
