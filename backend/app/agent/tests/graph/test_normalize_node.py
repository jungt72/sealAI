"""
Tests for graph/nodes/normalize_node.py — Phase F-C.1

Key invariants under test:
    1. Purely deterministic — no LLM call under any input.
    2. NormalizedState is written exclusively via reduce_observed_to_normalized().
    3. ObservedState is read-only — not modified.
    4. AssertedState unchanged after this node.
    5. GovernanceState unchanged after this node.

Coverage:
    1.  Empty ObservedState → empty NormalizedState
    2.  Single extraction → correct NormalizedParameter (field, value, confidence)
    3.  Multiple extractions same field → highest confidence wins
    4.  User override wins over LLM extraction for same field
    5.  User override source = 'user_override' in NormalizedState
    6.  Conflicting values for same field → ConflictRef produced
    7.  requires_confirmation extraction → AssumptionRef (not in parameters)
    8.  turn_index preserved in NormalizedParameter.source_turn
    9.  ObservedState not mutated
    10. AssertedState unchanged
    11. GovernanceState unchanged
    12. No LLM call (openai never invoked)
    13. All three core fields present → parameters has all three
    14. analysis_cycle, max_cycles unchanged
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.state.models import (
    ContextHintState,
    ObservedExtraction,
    ObservedState,
    UserOverride,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_extractions(*extractions: ObservedExtraction, **kwargs) -> GraphState:
    observed = ObservedState()
    for e in extractions:
        observed = observed.with_extraction(e)
    return GraphState(observed=observed, **kwargs)


def _state_with_override(override: UserOverride, *extras: ObservedExtraction) -> GraphState:
    observed = ObservedState()
    for e in extras:
        observed = observed.with_extraction(e)
    observed = observed.with_override(override)
    return GraphState(observed=observed)


def _ext(field: str, value, confidence: float = 0.92, turn: int = 0) -> ObservedExtraction:
    return ObservedExtraction(
        field_name=field, raw_value=value, source="llm",
        confidence=confidence, turn_index=turn,
    )


# ---------------------------------------------------------------------------
# 1. Empty ObservedState
# ---------------------------------------------------------------------------

class TestEmptyObserved:
    @pytest.mark.asyncio
    async def test_empty_observed_produces_empty_normalized(self):
        state = GraphState()
        result = await normalize_node(state)
        assert result.normalized.parameters == {}
        assert result.normalized.conflicts == []
        assert result.normalized.assumptions == []

    @pytest.mark.asyncio
    async def test_empty_observed_unit_system_si(self):
        state = GraphState()
        result = await normalize_node(state)
        assert result.normalized.unit_system == "SI"

    @pytest.mark.asyncio
    async def test_empty_observed_keeps_medium_classification_unavailable(self):
        state = GraphState()
        result = await normalize_node(state)
        assert result.medium_capture.primary_raw_text is None
        assert result.medium_classification.status == "unavailable"


# ---------------------------------------------------------------------------
# 2. Single extraction → correct NormalizedParameter
# ---------------------------------------------------------------------------

class TestSingleExtraction:
    @pytest.mark.asyncio
    async def test_pressure_bar_in_parameters(self):
        state = _state_with_extractions(_ext("pressure_bar", 12.0))
        result = await normalize_node(state)
        assert "pressure_bar" in result.normalized.parameters

    @pytest.mark.asyncio
    async def test_pressure_value_preserved(self):
        state = _state_with_extractions(_ext("pressure_bar", 12.0))
        result = await normalize_node(state)
        assert result.normalized.parameters["pressure_bar"].value == 12.0

    @pytest.mark.asyncio
    async def test_high_confidence_extraction_is_confirmed(self):
        state = _state_with_extractions(_ext("pressure_bar", 12.0, confidence=0.95))
        result = await normalize_node(state)
        assert result.normalized.parameters["pressure_bar"].confidence == "confirmed"

    @pytest.mark.asyncio
    async def test_medium_confidence_extraction_is_estimated(self):
        # 0.75 → estimated (threshold: ≥0.70)
        state = _state_with_extractions(_ext("medium", "Dampf", confidence=0.75))
        result = await normalize_node(state)
        assert result.normalized.parameters["medium"].confidence == "estimated"

    @pytest.mark.asyncio
    async def test_pending_message_builds_medium_capture_and_classification(self):
        state = _state_with_extractions(_ext("medium", "Salzwasser")).model_copy(
            update={"pending_message": "ich muss salzwasser trennen"}
        )
        result = await normalize_node(state)
        assert result.medium_capture.primary_raw_text == "salzwasser"
        assert result.medium_classification.status == "recognized"
        assert result.medium_classification.canonical_label == "Salzwasser"
        assert result.medium_classification.family == "waessrig_salzhaltig"

    @pytest.mark.asyncio
    async def test_pending_message_preserves_unclassified_medium_capture(self):
        state = GraphState(pending_message="medium ist XY-Compound 4711")
        result = await normalize_node(state)
        assert result.medium_capture.primary_raw_text == "XY-Compound 4711"
        assert result.medium_classification.status == "mentioned_unclassified"

    @pytest.mark.asyncio
    async def test_pending_message_derives_rotary_and_application_hints(self):
        state = GraphState(pending_message="es ist eine rotierende welle")
        result = await normalize_node(state)
        assert result.motion_hint.label == "rotary"
        assert result.motion_hint.source_type == "deterministic_text_inference"
        assert result.application_hint.label == "shaft_sealing"

    @pytest.mark.asyncio
    async def test_pending_message_derives_external_sealing_hint(self):
        state = GraphState(pending_message="ich muss salzwasser draussen halten")
        result = await normalize_node(state)
        assert result.application_hint.label == "external_sealing"

    @pytest.mark.asyncio
    async def test_linear_correction_replaces_rotary_hints(self):
        state = GraphState(
            pending_message="Korrektur: keine rotierende Welle, sondern lineare Bewegung.",
            motion_hint=ContextHintState(
                label="rotary",
                confidence="high",
                source_turn_ref="turn:1",
                source_turn_index=1,
                source_type="deterministic_text_inference",
            ),
            application_hint=ContextHintState(
                label="shaft_sealing",
                confidence="medium",
                source_turn_ref="turn:1",
                source_turn_index=1,
                source_type="deterministic_text_inference",
            ),
        )

        result = await normalize_node(state)

        assert result.motion_hint.label == "linear"
        assert result.application_hint.label == "linear_sealing"

    @pytest.mark.asyncio
    async def test_existing_hint_is_preserved_when_followup_turn_contains_no_new_hint(self):
        state = GraphState(
            pending_message="welchen druck brauchen sie noch?",
            application_hint=ContextHintState(
                label="shaft_sealing",
                confidence="medium",
                source_turn_ref="turn:1",
                source_turn_index=1,
                source_type="deterministic_text_inference",
            ),
        )
        result = await normalize_node(state)
        assert result.application_hint.label == "shaft_sealing"
        assert result.application_hint.source_turn_ref == "turn:1"

    @pytest.mark.asyncio
    async def test_low_confidence_extraction_is_inferred(self):
        # 0.55 → inferred (threshold: ≥0.50)
        state = _state_with_extractions(_ext("medium", "Öl", confidence=0.55))
        result = await normalize_node(state)
        assert result.normalized.parameters["medium"].confidence == "inferred"

    @pytest.mark.asyncio
    async def test_very_low_confidence_is_requires_confirmation(self):
        # 0.40 → requires_confirmation — appears in parameters with that confidence level
        # AND in assumptions (both — reducer invariant)
        state = _state_with_extractions(_ext("medium", "Unbekannt", confidence=0.40))
        result = await normalize_node(state)
        assert result.normalized.parameters["medium"].confidence == "requires_confirmation"
        assert any(a.field_name == "medium" for a in result.normalized.assumptions)


# ---------------------------------------------------------------------------
# 3. Multiple extractions same field → highest confidence wins
# ---------------------------------------------------------------------------

class TestMultipleExtractionsConflict:
    @pytest.mark.asyncio
    async def test_highest_confidence_wins(self):
        state = _state_with_extractions(
            _ext("pressure_bar", 10.0, confidence=0.75),
            _ext("pressure_bar", 12.0, confidence=0.95),
        )
        result = await normalize_node(state)
        assert result.normalized.parameters["pressure_bar"].value == 12.0

    @pytest.mark.asyncio
    async def test_latest_turn_wins_on_confidence_tie(self):
        state = _state_with_extractions(
            _ext("pressure_bar", 10.0, confidence=0.92, turn=0),
            _ext("pressure_bar", 12.0, confidence=0.92, turn=1),
        )
        result = await normalize_node(state)
        # Same confidence → latest turn wins
        assert result.normalized.parameters["pressure_bar"].value == 12.0

    @pytest.mark.asyncio
    async def test_same_field_different_values_produces_conflict(self):
        state = _state_with_extractions(
            _ext("medium", "Wasser",  confidence=0.92),
            _ext("medium", "Dampf",   confidence=0.85),
        )
        result = await normalize_node(state)
        assert any(c.field_name == "medium" for c in result.normalized.conflicts)

    @pytest.mark.asyncio
    async def test_same_field_same_value_no_conflict(self):
        state = _state_with_extractions(
            _ext("medium", "Wasser", confidence=0.92),
            _ext("medium", "Wasser", confidence=0.85),
        )
        result = await normalize_node(state)
        assert result.normalized.conflicts == []


# ---------------------------------------------------------------------------
# 4 & 5. User override
# ---------------------------------------------------------------------------

class TestUserOverride:
    @pytest.mark.asyncio
    async def test_user_override_wins_over_llm(self):
        override = UserOverride(field_name="medium", override_value="Dampf", turn_index=2)
        state = _state_with_override(
            override,
            _ext("medium", "Wasser", confidence=0.99),  # high-confidence LLM extraction
        )
        result = await normalize_node(state)
        assert result.normalized.parameters["medium"].value == "Dampf"

    @pytest.mark.asyncio
    async def test_user_override_source_is_user_override(self):
        override = UserOverride(field_name="medium", override_value="Dampf", turn_index=1)
        state = _state_with_override(override)
        result = await normalize_node(state)
        assert result.normalized.parameters["medium"].source == "user_override"

    @pytest.mark.asyncio
    async def test_user_override_confidence_is_confirmed(self):
        override = UserOverride(field_name="pressure_bar", override_value=8.0, turn_index=0)
        state = _state_with_override(override)
        result = await normalize_node(state)
        assert result.normalized.parameters["pressure_bar"].confidence == "confirmed"


# ---------------------------------------------------------------------------
# 6. requires_confirmation → AssumptionRef
# ---------------------------------------------------------------------------

class TestRequiresConfirmation:
    @pytest.mark.asyncio
    async def test_assumption_ref_created(self):
        state = _state_with_extractions(_ext("medium", "Viton-ähnlich", confidence=0.35))
        result = await normalize_node(state)
        assert len(result.normalized.assumptions) >= 1

    @pytest.mark.asyncio
    async def test_assumption_field_name_correct(self):
        state = _state_with_extractions(_ext("medium", "Unbekannt", confidence=0.30))
        result = await normalize_node(state)
        fields = {a.field_name for a in result.normalized.assumptions}
        assert "medium" in fields


# ---------------------------------------------------------------------------
# 7. turn_index propagated
# ---------------------------------------------------------------------------

class TestTurnIndex:
    @pytest.mark.asyncio
    async def test_source_turn_preserved(self):
        state = _state_with_extractions(_ext("temperature_c", 180.0, turn=3))
        result = await normalize_node(state)
        assert result.normalized.parameters["temperature_c"].source_turn == 3


# ---------------------------------------------------------------------------
# 8. Immutability — ObservedState not mutated
# ---------------------------------------------------------------------------

class TestImmutability:
    @pytest.mark.asyncio
    async def test_observed_not_mutated(self):
        ext = _ext("pressure_bar", 12.0)
        state = _state_with_extractions(ext)
        original_extractions = list(state.observed.raw_extractions)

        result = await normalize_node(state)

        # Original observed is unchanged
        assert list(state.observed.raw_extractions) == original_extractions
        # Result's observed is also the same object (model_copy does not touch observed)
        assert result.observed.raw_extractions == original_extractions

    @pytest.mark.asyncio
    async def test_asserted_unchanged(self):
        state = _state_with_extractions(_ext("pressure_bar", 12.0))
        result = await normalize_node(state)
        # AssertedState not populated by this node
        assert result.asserted.assertions == {}
        assert result.asserted.blocking_unknowns == []

    @pytest.mark.asyncio
    async def test_governance_unchanged(self):
        state = _state_with_extractions(_ext("medium", "Wasser"))
        result = await normalize_node(state)
        assert result.governance.gov_class is None
        assert result.governance.rfq_admissible is False

    @pytest.mark.asyncio
    async def test_analysis_cycle_unchanged(self):
        state = _state_with_extractions(_ext("pressure_bar", 5.0), analysis_cycle=2)
        result = await normalize_node(state)
        assert result.analysis_cycle == 2


# ---------------------------------------------------------------------------
# 9. No LLM call
# ---------------------------------------------------------------------------

class TestNoLLM:
    @pytest.mark.asyncio
    async def test_openai_never_called(self):
        """normalize_node must never call OpenAI under any input."""
        state = _state_with_extractions(
            _ext("medium", "Dampf"),
            _ext("pressure_bar", 12.0),
            _ext("temperature_c", 180.0),
        )
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(
                side_effect=AssertionError("LLM must not be called in normalize_node")
            )
            result = await normalize_node(state)

        mock_cls.assert_not_called()
        # Normalisation still succeeded
        assert len(result.normalized.parameters) == 3


# ---------------------------------------------------------------------------
# 10. All three core fields → parameters complete
# ---------------------------------------------------------------------------

class TestCoreFields:
    @pytest.mark.asyncio
    async def test_all_three_core_fields_normalized(self):
        state = _state_with_extractions(
            _ext("medium",        "Dampf",  confidence=0.92),
            _ext("pressure_bar",  12.0,     confidence=0.92),
            _ext("temperature_c", 180.0,    confidence=0.92),
        )
        result = await normalize_node(state)
        params = result.normalized.parameters
        assert "medium" in params
        assert "pressure_bar" in params
        assert "temperature_c" in params

    @pytest.mark.asyncio
    async def test_missing_core_field_absent_from_parameters(self):
        """Missing medium → 'medium' not in parameters (will become blocking_unknown downstream)."""
        state = _state_with_extractions(
            _ext("pressure_bar",  12.0,  confidence=0.92),
            _ext("temperature_c", 180.0, confidence=0.92),
        )
        result = await normalize_node(state)
        assert "medium" not in result.normalized.parameters
