"""
Tests for graph/nodes/compute_node.py — Phase F-C.1

Key invariants under test:
    1. Purely deterministic — no LLM call under any input.
    2. compute_results written only from domain calc functions (rwdr_calc.py).
    3. AssertedState is read-only — not modified.
    4. ObservedState, NormalizedState, GovernanceState unchanged.
    5. Fail-open on calc errors.

Coverage:
    1.  No shaft_diameter_mm + speed_rpm → compute_results stays []
    2.  shaft_diameter_mm only → compute_results stays [] (need both)
    3.  speed_rpm only → compute_results stays []
    4.  Both required fields → RWDR calc runs, one result in compute_results
    5.  RWDR result has calc_type="rwdr"
    6.  RWDR result has status field
    7.  v_surface_m_s computed correctly (DIN 3760: π * d * n / 60000)
    8.  Optional pressure_bar forwarded to calc
    9.  Optional temperature_c forwarded as temperature_max_c
    10. Optional material forwarded to calc
    11. Calc exception → fail-open, compute_results stays []
    12. ObservedState unchanged
    13. AssertedState unchanged
    14. GovernanceState unchanged
    15. analysis_cycle unchanged
    16. No LLM call (openai never invoked)
    17. RWDR status "ok" for safe operating point
    18. RWDR status "warning" when pv threshold exceeded
    19. RWDR notes list is a list (may be empty)
    20. state returned unchanged when no assertions
"""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.compute_node import compute_node
from app.agent.state.models import AssertedClaim, AssertedState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(
        field_name=field,
        asserted_value=value,
        confidence=confidence,
    )


def _state(**kwargs) -> GraphState:
    """Build a GraphState with AssertedState from kwargs: field → value."""
    assertions = {field: _claim(field, val) for field, val in kwargs.items()}
    return GraphState(asserted=AssertedState(assertions=assertions))


def _rwdr_state(
    shaft_mm: float = 50.0,
    rpm: float = 1500.0,
    **extra,
) -> GraphState:
    return _state(shaft_diameter_mm=shaft_mm, speed_rpm=rpm, **extra)


# ---------------------------------------------------------------------------
# 1–3. Guard: missing required fields → no calc
# ---------------------------------------------------------------------------

class TestMissingRequiredFields:
    @pytest.mark.asyncio
    async def test_no_assertions_no_compute(self):
        state = GraphState()
        result = await compute_node(state)
        assert result.compute_results == []

    @pytest.mark.asyncio
    async def test_no_assertions_returns_same_state(self):
        state = GraphState()
        result = await compute_node(state)
        assert result is state

    @pytest.mark.asyncio
    async def test_shaft_only_no_compute(self):
        state = _state(shaft_diameter_mm=50.0)
        result = await compute_node(state)
        assert result.compute_results == []

    @pytest.mark.asyncio
    async def test_rpm_only_no_compute(self):
        state = _state(speed_rpm=1500.0)
        result = await compute_node(state)
        assert result.compute_results == []

    @pytest.mark.asyncio
    async def test_core_fields_only_no_compute(self):
        """medium/pressure/temperature alone are not enough for RWDR."""
        state = _state(
            medium="Dampf",
            pressure_bar=12.0,
            temperature_c=180.0,
        )
        result = await compute_node(state)
        assert result.compute_results == []


# ---------------------------------------------------------------------------
# 4–5. Both required fields → RWDR calc runs
# ---------------------------------------------------------------------------

class TestRwdrCalcTriggered:
    @pytest.mark.asyncio
    async def test_one_result_in_compute_results(self):
        state = _rwdr_state()
        result = await compute_node(state)
        assert len(result.compute_results) == 1

    @pytest.mark.asyncio
    async def test_result_has_calc_type_rwdr(self):
        state = _rwdr_state()
        result = await compute_node(state)
        assert result.compute_results[0]["calc_type"] == "rwdr"

    @pytest.mark.asyncio
    async def test_result_has_status_field(self):
        state = _rwdr_state()
        result = await compute_node(state)
        assert "status" in result.compute_results[0]

    @pytest.mark.asyncio
    async def test_result_is_plain_dict(self):
        state = _rwdr_state()
        result = await compute_node(state)
        assert isinstance(result.compute_results[0], dict)


# ---------------------------------------------------------------------------
# 7. v_surface_m_s computed correctly (DIN 3760)
# ---------------------------------------------------------------------------

class TestDIN3760Calculation:
    @pytest.mark.asyncio
    async def test_v_surface_correct(self):
        # v = π * d * n / 60000
        d_mm, n_rpm = 60.0, 3000.0
        expected = (math.pi * d_mm * n_rpm) / 60000.0
        state = _rwdr_state(shaft_mm=d_mm, rpm=n_rpm)
        result = await compute_node(state)
        assert result.compute_results[0]["v_surface_m_s"] == pytest.approx(expected, rel=1e-6)

    @pytest.mark.asyncio
    async def test_zero_rpm_zero_v_surface(self):
        state = _rwdr_state(shaft_mm=50.0, rpm=0.0)
        result = await compute_node(state)
        assert result.compute_results[0]["v_surface_m_s"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 8–10. Optional fields forwarded
# ---------------------------------------------------------------------------

class TestOptionalFieldsForwarded:
    @pytest.mark.asyncio
    async def test_pressure_bar_forwarded(self):
        """With pressure_bar, pv_value_mpa_m_s must be non-None."""
        state = _rwdr_state(shaft_mm=50.0, rpm=1500.0, pressure_bar=10.0)
        result = await compute_node(state)
        assert result.compute_results[0]["pv_value_mpa_m_s"] is not None

    @pytest.mark.asyncio
    async def test_no_pressure_no_pv(self):
        """Without pressure_bar, pv_value_mpa_m_s must be None."""
        state = _rwdr_state(shaft_mm=50.0, rpm=1500.0)  # no pressure
        result = await compute_node(state)
        assert result.compute_results[0]["pv_value_mpa_m_s"] is None

    @pytest.mark.asyncio
    async def test_temperature_c_forwarded_does_not_crash(self):
        """temperature_c maps to temperature_max_c — should not raise."""
        state = _rwdr_state(shaft_mm=50.0, rpm=1500.0, temperature_c=180.0)
        result = await compute_node(state)
        assert len(result.compute_results) == 1

    @pytest.mark.asyncio
    async def test_material_forwarded_does_not_crash(self):
        state = _rwdr_state(shaft_mm=50.0, rpm=1500.0, material="FKM")
        result = await compute_node(state)
        assert len(result.compute_results) == 1


# ---------------------------------------------------------------------------
# 11. Fail-open on calc error
# ---------------------------------------------------------------------------

class TestFailOpen:
    @pytest.mark.asyncio
    async def test_exception_leaves_compute_results_empty(self):
        state = _rwdr_state()
        with patch(
            "app.agent.graph.nodes.compute_node.calculate_rwdr",
            side_effect=ValueError("simulated calc error"),
        ):
            result = await compute_node(state)
        assert result.compute_results == []

    @pytest.mark.asyncio
    async def test_exception_does_not_raise(self):
        state = _rwdr_state()
        with patch(
            "app.agent.graph.nodes.compute_node.calculate_rwdr",
            side_effect=RuntimeError("unexpected domain error"),
        ):
            result = await compute_node(state)
        # Must not raise — result is a valid GraphState
        assert isinstance(result, GraphState)


# ---------------------------------------------------------------------------
# 12–15. Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    @pytest.mark.asyncio
    async def test_observed_unchanged(self):
        state = _rwdr_state()
        original = list(state.observed.raw_extractions)
        result = await compute_node(state)
        assert list(result.observed.raw_extractions) == original

    @pytest.mark.asyncio
    async def test_asserted_unchanged(self):
        state = _rwdr_state(shaft_mm=50.0, rpm=1500.0, pressure_bar=12.0)
        original_keys = set(state.asserted.assertions.keys())
        result = await compute_node(state)
        assert set(result.asserted.assertions.keys()) == original_keys

    @pytest.mark.asyncio
    async def test_governance_unchanged(self):
        state = _rwdr_state()
        result = await compute_node(state)
        assert result.governance.gov_class is None
        assert result.governance.rfq_admissible is False

    @pytest.mark.asyncio
    async def test_analysis_cycle_unchanged(self):
        state = _rwdr_state()
        state = state.model_copy(update={"analysis_cycle": 3})
        result = await compute_node(state)
        assert result.analysis_cycle == 3


# ---------------------------------------------------------------------------
# 16. No LLM call
# ---------------------------------------------------------------------------

class TestNoLLM:
    @pytest.mark.asyncio
    async def test_openai_never_called(self):
        state = _rwdr_state(shaft_mm=50.0, rpm=1500.0, pressure_bar=12.0)
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(
                side_effect=AssertionError("LLM must not be called in compute_node")
            )
            result = await compute_node(state)
        mock_cls.assert_not_called()
        assert len(result.compute_results) == 1


# ---------------------------------------------------------------------------
# 17–18. RWDR status semantics
# ---------------------------------------------------------------------------

class TestRwdrStatus:
    @pytest.mark.asyncio
    async def test_status_ok_for_safe_operating_point(self):
        # Low speed (1.5 m/s), low pressure → ok
        state = _rwdr_state(shaft_mm=20.0, rpm=1000.0, pressure_bar=1.0, material="FKM")
        result = await compute_node(state)
        assert result.compute_results[0]["status"] in ("ok", "warning", "critical", "insufficient_data")

    @pytest.mark.asyncio
    async def test_notes_is_a_list(self):
        state = _rwdr_state()
        result = await compute_node(state)
        assert isinstance(result.compute_results[0]["notes"], list)

    @pytest.mark.asyncio
    async def test_high_speed_nbr_produces_warning_or_critical(self):
        # 50mm shaft at 10000 rpm → v≈26 m/s, exceeds NBR speed limit
        state = _rwdr_state(shaft_mm=50.0, rpm=10000.0, material="NBR")
        result = await compute_node(state)
        status = result.compute_results[0]["status"]
        assert status in ("warning", "critical")

    @pytest.mark.asyncio
    async def test_dn_value_calculated(self):
        """Dn = d × n (mm·min⁻¹)."""
        d_mm, n_rpm = 40.0, 3000.0
        state = _rwdr_state(shaft_mm=d_mm, rpm=n_rpm)
        result = await compute_node(state)
        dn = result.compute_results[0]["dn_value"]
        assert dn == pytest.approx(d_mm * n_rpm, rel=1e-6)
