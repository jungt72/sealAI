"""
Tests for graph/nodes/governance_node.py — Phase F-C.1

Key invariants under test:
    1. Purely deterministic — no LLM call under any input.
    2. GovernanceState is written exclusively via reduce_asserted_to_governance().
    3. AssertedState is read-only — not modified.
    4. ObservedState, NormalizedState, compute_results unchanged.

Coverage:
    1.  All three core fields confirmed → Class A, rfq_admissible=True
    2.  Two core fields confirmed, one missing → Class B
    3.  blocking_unknowns with cycle < max → Class B
    4.  blocking_unknowns after max_cycles → Class C
    5.  Blocking conflict flag → Class C
    6.  No core fields asserted → Class D
    7.  Class A → rfq_admissible=True
    8.  Class B → rfq_admissible=False
    9.  Class C → rfq_admissible=False
    10. Class D → rfq_admissible=False
    11. Estimated field → validity_limits contains that field
    12. Inferred field → validity_limits contains that field
    13. Blocking unknown → open_validation_points contains that field
    14. analysis_cycle forwarded to reducer
    15. max_cycles forwarded to reducer
    16. ObservedState unchanged
    17. NormalizedState unchanged
    18. compute_results unchanged
    19. analysis_cycle unchanged on state
    20. No LLM call (openai never invoked)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.governance_node import governance_node
from app.agent.state.models import AssertedClaim, AssertedState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _state(
    *,
    analysis_cycle: int = 0,
    max_cycles: int = 3,
    blocking_unknowns: list[str] | None = None,
    conflict_flags: list[str] | None = None,
    **fields,
) -> GraphState:
    """Build GraphState with AssertedState from field→(value, confidence) pairs."""
    assertions = {
        field: _claim(field, val, conf)
        for field, (val, conf) in fields.items()
    }
    asserted = AssertedState(
        assertions=assertions,
        blocking_unknowns=blocking_unknowns or [],
        conflict_flags=conflict_flags or [],
    )
    return GraphState(
        asserted=asserted,
        analysis_cycle=analysis_cycle,
        max_cycles=max_cycles,
    )


def _full_class_a() -> GraphState:
    return _state(
        medium=("Dampf", "confirmed"),
        pressure_bar=(12.0, "confirmed"),
        temperature_c=(180.0, "confirmed"),
        sealing_type=("general_seal", "confirmed"),
        material=("PTFE", "confirmed"),
    )


# ---------------------------------------------------------------------------
# 1–2. Class A and B via field presence
# ---------------------------------------------------------------------------

class TestGovClassAB:
    @pytest.mark.asyncio
    async def test_all_core_confirmed_class_a(self):
        state = _full_class_a()
        result = await governance_node(state)
        assert result.governance.gov_class == "A"

    @pytest.mark.asyncio
    async def test_missing_one_core_field_class_b(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            # temperature_c missing → blocking_unknowns set by assert_node upstream
            blocking_unknowns=["temperature_c"],
        )
        result = await governance_node(state)
        assert result.governance.gov_class == "B"

    @pytest.mark.asyncio
    async def test_blocking_unknown_within_cycle_limit_class_b(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            blocking_unknowns=["material"],
            analysis_cycle=1,
            max_cycles=3,
        )
        result = await governance_node(state)
        assert result.governance.gov_class == "B"


# ---------------------------------------------------------------------------
# 3–5. Class C: cycle exceeded or blocking conflict
# ---------------------------------------------------------------------------

class TestGovClassC:
    @pytest.mark.asyncio
    async def test_blocking_unknowns_after_max_cycles_class_c(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            blocking_unknowns=["material"],
            analysis_cycle=3,   # == max_cycles → exceeded
            max_cycles=3,
        )
        result = await governance_node(state)
        assert result.governance.gov_class == "C"

    @pytest.mark.asyncio
    async def test_blocking_conflict_flag_class_c(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            conflict_flags=["medium"],
        )
        result = await governance_node(state)
        assert result.governance.gov_class == "C"


# ---------------------------------------------------------------------------
# 6. Class D: no core fields asserted
# ---------------------------------------------------------------------------

class TestGovClassD:
    @pytest.mark.asyncio
    async def test_no_core_fields_class_d(self):
        state = GraphState()  # empty AssertedState
        result = await governance_node(state)
        assert result.governance.gov_class == "D"

    @pytest.mark.asyncio
    async def test_non_core_fields_only_class_d(self):
        state = _state(material=("FKM", "confirmed"))
        result = await governance_node(state)
        assert result.governance.gov_class == "D"


# ---------------------------------------------------------------------------
# 7–10. rfq_admissible
# ---------------------------------------------------------------------------

class TestRfqAdmissible:
    @pytest.mark.asyncio
    async def test_class_a_rfq_admissible_true(self):
        state = _full_class_a()
        result = await governance_node(state)
        assert result.governance.rfq_admissible is True

    @pytest.mark.asyncio
    async def test_class_b_rfq_admissible_false(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            blocking_unknowns=["temperature_c"],
        )
        result = await governance_node(state)
        assert result.governance.rfq_admissible is False

    @pytest.mark.asyncio
    async def test_class_c_rfq_admissible_false(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            blocking_unknowns=["material"],
            analysis_cycle=3,
            max_cycles=3,
        )
        result = await governance_node(state)
        assert result.governance.rfq_admissible is False

    @pytest.mark.asyncio
    async def test_class_d_rfq_admissible_false(self):
        state = GraphState()
        result = await governance_node(state)
        assert result.governance.rfq_admissible is False


# ---------------------------------------------------------------------------
# 11–13. validity_limits and open_validation_points
# ---------------------------------------------------------------------------

class TestValidityAndValidationPoints:
    @pytest.mark.asyncio
    async def test_estimated_field_in_validity_limits(self):
        state = _state(
            medium=("Dampf", "estimated"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        result = await governance_node(state)
        assert any("medium" in note for note in result.governance.validity_limits)

    @pytest.mark.asyncio
    async def test_inferred_field_in_validity_limits(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "inferred"),
        )
        result = await governance_node(state)
        assert any("temperature_c" in note for note in result.governance.validity_limits)

    @pytest.mark.asyncio
    async def test_confirmed_fields_no_validity_limits(self):
        state = _full_class_a()
        result = await governance_node(state)
        assert result.governance.validity_limits == []

    @pytest.mark.asyncio
    async def test_blocking_unknown_in_open_validation_points(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            blocking_unknowns=["temperature_c"],
        )
        result = await governance_node(state)
        assert "temperature_c" in result.governance.open_validation_points


# ---------------------------------------------------------------------------
# 14–15. Cycle forwarding
# ---------------------------------------------------------------------------

class TestCycleForwarding:
    @pytest.mark.asyncio
    async def test_analysis_cycle_1_still_class_b_not_c(self):
        """cycle=1 < max=3 → B despite blocking unknown."""
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            blocking_unknowns=["material"],
            analysis_cycle=1,
            max_cycles=3,
        )
        result = await governance_node(state)
        assert result.governance.gov_class == "B"

    @pytest.mark.asyncio
    async def test_analysis_cycle_equals_max_cycles_class_c(self):
        """cycle >= max → C despite only one blocking unknown."""
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            blocking_unknowns=["material"],
            analysis_cycle=2,
            max_cycles=2,
        )
        result = await governance_node(state)
        assert result.governance.gov_class == "C"


# ---------------------------------------------------------------------------
# 16–19. Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    @pytest.mark.asyncio
    async def test_observed_unchanged(self):
        state = _full_class_a()
        original = list(state.observed.raw_extractions)
        result = await governance_node(state)
        assert list(result.observed.raw_extractions) == original

    @pytest.mark.asyncio
    async def test_normalized_unchanged(self):
        state = _full_class_a()
        original_params = dict(state.normalized.parameters)
        result = await governance_node(state)
        assert dict(result.normalized.parameters) == original_params

    @pytest.mark.asyncio
    async def test_compute_results_unchanged(self):
        state = _full_class_a()
        state = state.model_copy(update={"compute_results": [{"calc_type": "rwdr"}]})
        result = await governance_node(state)
        assert result.compute_results == [{"calc_type": "rwdr"}]

    @pytest.mark.asyncio
    async def test_asserted_unchanged(self):
        state = _full_class_a()
        original_keys = set(state.asserted.assertions.keys())
        result = await governance_node(state)
        assert set(result.asserted.assertions.keys()) == original_keys

    @pytest.mark.asyncio
    async def test_analysis_cycle_on_state_unchanged(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            analysis_cycle=2,
        )
        result = await governance_node(state)
        assert result.analysis_cycle == 2


class TestCaseLifecyclePhase:
    @pytest.mark.asyncio
    async def test_explicit_authority_phase_sets_case_lifecycle_phase(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            phase=("matching", "confirmed"),
        )

        result = await governance_node(state)

        assert result.case_lifecycle.phase == "matching"

    @pytest.mark.asyncio
    async def test_unknown_phase_does_not_set_case_lifecycle_phase(self):
        state = _state(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
            phase=("final", "confirmed"),
        )

        result = await governance_node(state)

        assert result.case_lifecycle.phase is None

    @pytest.mark.asyncio
    async def test_neighbouring_state_does_not_set_case_lifecycle_phase(self):
        state = _full_class_a().model_copy(
            update={
                "analysis_cycle": 3,
                "rfq": _full_class_a().rfq.model_copy(update={"rfq_ready": True}),
                "matching": _full_class_a().matching.model_copy(update={"status": "matched_primary_candidate"}),
                "exploration_progress": _full_class_a().exploration_progress.model_copy(update={"last_route": "GOVERNED"}),
            }
        )

        result = await governance_node(state)

        assert result.case_lifecycle.phase is None


# ---------------------------------------------------------------------------
# 20. No LLM call
# ---------------------------------------------------------------------------

class TestNoLLM:
    @pytest.mark.asyncio
    async def test_openai_never_called(self):
        state = _full_class_a()
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(
                side_effect=AssertionError("LLM must not be called in governance_node")
            )
            result = await governance_node(state)
        mock_cls.assert_not_called()
        assert result.governance.gov_class == "A"
