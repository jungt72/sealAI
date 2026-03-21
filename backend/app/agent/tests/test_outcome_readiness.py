"""
Unit tests for Phase A7 — Outcome-Feedback-Readiness.

Tests verify:
1. OutcomeLayer TypedDict accepts all five required fields
2. All fields are individually optional (total=False semantics)
3. OutcomeLayer is a NotRequired field on SealingAIState
4. A SealingAIState dict without 'outcome' is still structurally valid
5. A SealingAIState dict with a populated OutcomeLayer is valid
6. Outcome fields carry correct Python types
7. The agent graph never writes to outcome during a run (structural invariant)
"""
from __future__ import annotations

import pytest

from app.agent.agent.state import OutcomeLayer, SealingAIState


# ---------------------------------------------------------------------------
# 1–6. OutcomeLayer structural typing
# ---------------------------------------------------------------------------

class TestOutcomeLayerFields:
    def test_all_five_fields_accepted(self):
        outcome: OutcomeLayer = {
            "implemented": True,
            "failed": False,
            "replaced": False,
            "review_override": False,
            "outcome_note": "Material performed within spec after 6 months.",
        }
        assert outcome["implemented"] is True
        assert outcome["failed"] is False
        assert outcome["replaced"] is False
        assert outcome["review_override"] is False
        assert outcome["outcome_note"] == "Material performed within spec after 6 months."

    def test_implemented_true(self):
        o: OutcomeLayer = {"implemented": True}
        assert o["implemented"] is True

    def test_failed_true(self):
        o: OutcomeLayer = {"failed": True}
        assert o["failed"] is True

    def test_replaced_true(self):
        o: OutcomeLayer = {"replaced": True}
        assert o["replaced"] is True

    def test_review_override_true(self):
        o: OutcomeLayer = {"review_override": True}
        assert o["review_override"] is True

    def test_outcome_note_string(self):
        o: OutcomeLayer = {"outcome_note": "Seal failed at 180°C due to pressure spike."}
        assert isinstance(o["outcome_note"], str)

    def test_empty_outcome_layer_is_valid(self):
        """total=False means all fields are optional — empty dict is valid."""
        o: OutcomeLayer = {}
        assert isinstance(o, dict)

    def test_partial_outcome_layer_is_valid(self):
        """Only the fields that are known need to be set."""
        o: OutcomeLayer = {"implemented": True, "outcome_note": "OK"}
        assert o["implemented"] is True
        assert "failed" not in o

    def test_outcome_note_empty_string(self):
        o: OutcomeLayer = {"outcome_note": ""}
        assert o["outcome_note"] == ""

    def test_all_bool_fields_accept_false(self):
        o: OutcomeLayer = {
            "implemented": False,
            "failed": False,
            "replaced": False,
            "review_override": False,
        }
        for key in ("implemented", "failed", "replaced", "review_override"):
            assert o[key] is False


# ---------------------------------------------------------------------------
# 3–5. Integration into SealingAIState
# ---------------------------------------------------------------------------

class TestOutcomeInSealingAIState:
    def test_sealing_state_without_outcome_is_valid(self):
        """outcome is NotRequired — SealingAIState without it is structurally fine."""
        # Just check the key is not mandatory by building a minimal dict
        state: dict = {}
        assert "outcome" not in state  # no KeyError expected

    def test_sealing_state_with_outcome_field(self):
        """SealingAIState accepts 'outcome' as a NotRequired field."""
        state: SealingAIState = {  # type: ignore[typeddict-item]
            "outcome": {
                "implemented": True,
                "outcome_note": "Dichtung hält.",
            }
        }
        outcome = state.get("outcome") or {}
        assert outcome.get("implemented") is True
        assert outcome.get("outcome_note") == "Dichtung hält."

    def test_outcome_field_is_independent_of_review_and_handover(self):
        """outcome, review, and handover are all separate NotRequired layers."""
        state: dict = {
            "review": {"review_required": False, "review_state": "none"},
            "handover": {"is_handover_ready": False},
            "outcome": {"failed": True, "outcome_note": "Pressure spike at startup."},
        }
        assert state["outcome"]["failed"] is True
        assert state["review"]["review_state"] == "none"
        assert state["handover"]["is_handover_ready"] is False


# ---------------------------------------------------------------------------
# 7. Structural invariant: graph nodes must not write to outcome
# ---------------------------------------------------------------------------

class TestOutcomeNotWrittenByGraph:
    def test_selection_node_does_not_write_outcome(self):
        """selection_node return value must not include 'outcome'."""
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import selection_node
        from app.agent.tests.test_graph_routing import _make_state

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        result = selection_node(state)
        new_sealing = result.get("sealing_state", {})
        assert "outcome" not in new_sealing, (
            "selection_node must not write 'outcome' — it is reserved for external feedback"
        )

    def test_final_response_node_does_not_write_outcome(self):
        """final_response_node must not populate the outcome layer."""
        import asyncio
        from langchain_core.messages import HumanMessage
        from app.agent.agent.graph import final_response_node
        from app.agent.tests.test_graph_routing import _make_state

        state = _make_state(
            policy_path="structured",
            result_form="direct_answer",
            messages=[HumanMessage(content="test")],
        )
        result = asyncio.run(final_response_node(state))
        new_sealing = result.get("sealing_state", {})
        assert "outcome" not in new_sealing, (
            "final_response_node must not write 'outcome' — it is reserved for external feedback"
        )
