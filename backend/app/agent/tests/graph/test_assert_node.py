"""
Tests for graph/nodes/assert_node.py — Phase F-C.1

Key invariants under test:
    1. Purely deterministic — no LLM call under any input.
    2. AssertedState is written exclusively via reduce_normalized_to_asserted().
    3. NormalizedState is read-only — not modified.
    4. ObservedState unchanged after this node.
    5. GovernanceState unchanged after this node.

Coverage:
    1.  All three core fields confirmed → assertions complete, no blocking
    2.  requires_confirmation field → blocking_unknowns, absent from assertions
    3.  inferred field → AssertedClaim present (caveat carried by confidence)
    4.  Missing core field → blocking_unknowns includes that field
    5.  All core fields missing → all three in blocking_unknowns
    6.  Blocking conflict → conflict_flags populated
    7.  Non-blocking (warning) conflict → conflict_flags empty
    8.  ObservedState not mutated
    9.  NormalizedState not mutated
    10. GovernanceState unchanged
    11. analysis_cycle, max_cycles unchanged
    12. No LLM call (openai never invoked)
    13. Empty NormalizedState → all core fields in blocking_unknowns
    14. User override field (confirmed) → AssertedClaim present
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.state.models import (
    ConflictRef,
    NormalizedParameter,
    NormalizedState,
    ObservedState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CORE_FIELDS = ("medium", "pressure_bar", "temperature_c")


def _param(
    field: str,
    value,
    confidence: str = "confirmed",
    source: str = "llm",
    source_turn: int = 0,
) -> NormalizedParameter:
    return NormalizedParameter(
        field_name=field,
        value=value,
        confidence=confidence,
        source=source,
        source_turn=source_turn,
    )


def _state_with_params(**kwargs) -> GraphState:
    """Build a GraphState with a NormalizedState whose parameters match kwargs.

    kwargs maps field_name → (value, confidence) tuple.
    """
    params = {
        field: _param(field, val, conf)
        for field, (val, conf) in kwargs.items()
    }
    normalized = NormalizedState(parameters=params)
    return GraphState(normalized=normalized)


def _state_with_conflict(field: str, severity: str = "blocking") -> GraphState:
    """Build a state with a single blocking or warning conflict for field."""
    params = {
        "medium":        _param("medium",        "Dampf", "confirmed"),
        "pressure_bar":  _param("pressure_bar",  12.0,    "confirmed"),
        "temperature_c": _param("temperature_c", 180.0,   "confirmed"),
        field:           _param(field,            "X",     "confirmed"),
    }
    conflict = ConflictRef(
        field_name=field,
        description=f"Conflicting values for '{field}'",
        severity=severity,
    )
    normalized = NormalizedState(parameters=params, conflicts=[conflict])
    return GraphState(normalized=normalized)


# ---------------------------------------------------------------------------
# 1. All three core fields confirmed
# ---------------------------------------------------------------------------

class TestCoreFieldsConfirmed:
    @pytest.mark.asyncio
    async def test_all_three_asserted(self):
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert "medium" in result.asserted.assertions
        assert "pressure_bar" in result.asserted.assertions
        assert "temperature_c" in result.asserted.assertions

    @pytest.mark.asyncio
    async def test_no_blocking_unknowns_when_all_core_confirmed(self):
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert result.asserted.blocking_unknowns == []

    @pytest.mark.asyncio
    async def test_asserted_value_correct(self):
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert result.asserted.assertions["medium"].asserted_value == "Dampf"
        assert result.asserted.assertions["pressure_bar"].asserted_value == 12.0
        assert result.asserted.assertions["temperature_c"].asserted_value == 180.0


# ---------------------------------------------------------------------------
# 2. requires_confirmation → blocking_unknowns
# ---------------------------------------------------------------------------

class TestRequiresConfirmation:
    @pytest.mark.asyncio
    async def test_field_not_in_assertions(self):
        state = _state_with_params(
            medium=("Unbekannt", "requires_confirmation"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert "medium" not in result.asserted.assertions

    @pytest.mark.asyncio
    async def test_field_in_blocking_unknowns(self):
        state = _state_with_params(
            medium=("Unbekannt", "requires_confirmation"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert "medium" in result.asserted.blocking_unknowns


# ---------------------------------------------------------------------------
# 3. inferred → AssertedClaim present
# ---------------------------------------------------------------------------

class TestInferred:
    @pytest.mark.asyncio
    async def test_inferred_field_in_assertions(self):
        state = _state_with_params(
            medium=("Dampf", "inferred"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert "medium" in result.asserted.assertions

    @pytest.mark.asyncio
    async def test_inferred_confidence_preserved(self):
        state = _state_with_params(
            medium=("Dampf", "inferred"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert result.asserted.assertions["medium"].confidence == "inferred"

    @pytest.mark.asyncio
    async def test_inferred_not_in_blocking_unknowns(self):
        state = _state_with_params(
            medium=("Dampf", "inferred"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert "medium" not in result.asserted.blocking_unknowns


# ---------------------------------------------------------------------------
# 4. Missing core field → blocking_unknowns
# ---------------------------------------------------------------------------

class TestMissingCoreField:
    @pytest.mark.asyncio
    async def test_missing_medium_in_blocking(self):
        state = _state_with_params(
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert "medium" in result.asserted.blocking_unknowns

    @pytest.mark.asyncio
    async def test_missing_pressure_in_blocking(self):
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert "pressure_bar" in result.asserted.blocking_unknowns

    @pytest.mark.asyncio
    async def test_missing_temperature_in_blocking(self):
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
        )
        result = await assert_node(state)
        assert "temperature_c" in result.asserted.blocking_unknowns


# ---------------------------------------------------------------------------
# 5. All core fields missing
# ---------------------------------------------------------------------------

class TestAllCoreFieldsMissing:
    @pytest.mark.asyncio
    async def test_empty_normalized_all_core_in_blocking(self):
        state = GraphState()
        result = await assert_node(state)
        for field in _CORE_FIELDS:
            assert field in result.asserted.blocking_unknowns

    @pytest.mark.asyncio
    async def test_empty_normalized_no_assertions(self):
        state = GraphState()
        result = await assert_node(state)
        assert result.asserted.assertions == {}


# ---------------------------------------------------------------------------
# 6. Blocking conflict → conflict_flags
# ---------------------------------------------------------------------------

class TestBlockingConflict:
    @pytest.mark.asyncio
    async def test_blocking_conflict_in_conflict_flags(self):
        state = _state_with_conflict("material", severity="blocking")
        result = await assert_node(state)
        assert "material" in result.asserted.conflict_flags


# ---------------------------------------------------------------------------
# 7. Warning conflict → conflict_flags empty
# ---------------------------------------------------------------------------

class TestWarningConflict:
    @pytest.mark.asyncio
    async def test_warning_conflict_not_in_conflict_flags(self):
        state = _state_with_conflict("material", severity="warning")
        result = await assert_node(state)
        assert "material" not in result.asserted.conflict_flags


# ---------------------------------------------------------------------------
# 8 & 9. Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    @pytest.mark.asyncio
    async def test_observed_unchanged(self):
        state = GraphState(observed=ObservedState())
        original_extractions = list(state.observed.raw_extractions)
        result = await assert_node(state)
        assert list(result.observed.raw_extractions) == original_extractions

    @pytest.mark.asyncio
    async def test_normalized_not_mutated(self):
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        original_keys = set(state.normalized.parameters.keys())
        result = await assert_node(state)
        assert set(result.normalized.parameters.keys()) == original_keys

    @pytest.mark.asyncio
    async def test_governance_unchanged(self):
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await assert_node(state)
        assert result.governance.gov_class is None
        assert result.governance.rfq_admissible is False

    @pytest.mark.asyncio
    async def test_analysis_cycle_unchanged(self):
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
        )
        state = state.model_copy(update={"analysis_cycle": 2})
        result = await assert_node(state)
        assert result.analysis_cycle == 2


# ---------------------------------------------------------------------------
# 10. No LLM call
# ---------------------------------------------------------------------------

class TestNoLLM:
    @pytest.mark.asyncio
    async def test_openai_never_called(self):
        """assert_node must never call OpenAI under any input."""
        state = _state_with_params(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(
                side_effect=AssertionError("LLM must not be called in assert_node")
            )
            result = await assert_node(state)

        mock_cls.assert_not_called()
        assert len(result.asserted.assertions) == 3


# ---------------------------------------------------------------------------
# 11. User override field (confirmed via normalize → assert)
# ---------------------------------------------------------------------------

class TestUserOverrideField:
    @pytest.mark.asyncio
    async def test_user_override_asserted_at_confirmed(self):
        """Fields normalized from user_override source are confirmed → AssertedClaim."""
        params = {
            "medium":        _param("medium",        "Dampf", "confirmed", source="user_override"),
            "pressure_bar":  _param("pressure_bar",  12.0,    "confirmed"),
            "temperature_c": _param("temperature_c", 180.0,   "confirmed"),
        }
        normalized = NormalizedState(parameters=params)
        state = GraphState(normalized=normalized)
        result = await assert_node(state)
        assert result.asserted.assertions["medium"].asserted_value == "Dampf"
        assert result.asserted.assertions["medium"].confidence == "confirmed"
