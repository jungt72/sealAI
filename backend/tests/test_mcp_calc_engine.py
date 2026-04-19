"""Tests for the MCP gasket calculation engine (Sprint 6).

Verifies deterministic calculations: reference values, gasket dimensions,
bolt loads, safety factors, critical application detection, and edge cases.
"""

import math

import pytest

from app.mcp.calc_schemas import CalcInput, CalcOutput
from app.mcp.calc_engine import (
    mcp_calc_gasket,
    _lookup_gasket_dims,
    _bolt_capacity,
    _gasket_area,
    _EN_GASKET_DIMENSIONS,
    _BOLT_CAPACITY_KN,
)
from app.mcp.calculations.compliance import is_critical_application as _is_critical_medium


# ---------------------------------------------------------------------------
# Reference value tests
# ---------------------------------------------------------------------------


class TestGasketDimensionLookup:
    """DN -> gasket dimensions via lookup table."""

    def test_dn50_en_dimensions(self):
        inner, outer, bolt_circle = _lookup_gasket_dims(50, "EN 1092-1")
        assert inner == 60.3
        assert outer == 82.5
        assert bolt_circle == 125.0

    def test_dn100_en_dimensions(self):
        inner, outer, bolt_circle = _lookup_gasket_dims(100, "EN 1092-1")
        assert inner == 114.3
        assert outer == 146.5
        assert bolt_circle == 190.0

    def test_dn50_asme_dimensions(self):
        inner, outer, bolt_circle = _lookup_gasket_dims(50, "ASME B16.5")
        assert inner == 60.3
        assert outer == 82.6
        assert bolt_circle == 127.0

    def test_dn_none_returns_none(self):
        inner, outer, bolt_circle = _lookup_gasket_dims(None, "EN 1092-1")
        assert inner is None
        assert outer is None
        assert bolt_circle is None

    def test_dn_not_in_table_uses_closest(self):
        """DN45 is not in table — should use closest (DN50 or DN40)."""
        inner, outer, bolt_circle = _lookup_gasket_dims(45, "EN 1092-1")
        assert inner is not None
        assert outer is not None


class TestBoltCapacity:
    """Bolt M-size -> capacity in kN."""

    def test_m20_capacity(self):
        assert _bolt_capacity("M20") == 137.0

    def test_m24_capacity(self):
        assert _bolt_capacity("M24") == 198.0

    def test_m16_capacity(self):
        assert _bolt_capacity("M16") == 88.0

    def test_none_bolt_size(self):
        assert _bolt_capacity(None) is None

    def test_unknown_bolt_size(self):
        assert _bolt_capacity("M99") is None

    def test_case_insensitive(self):
        # _bolt_capacity uppercases the input, so "m20" matches "M20"
        assert _bolt_capacity("m20") == 137.0


class TestBoltLoadCalculation:
    """Bolt load = bolt_count * bolt_capacity_per_bolt."""

    def test_m20_x_8_bolts(self):
        """M20 x 8 bolts -> 8 * 137 = 1096 kN."""
        params = CalcInput(
            pressure_max_bar=40.0,
            temperature_max_c=200.0,
            flange_dn=100,
            flange_standard="EN 1092-1",
            bolt_count=8,
            bolt_size="M20",
        )
        result = mcp_calc_gasket(params)
        assert result.available_bolt_load_kn == pytest.approx(1096.0, abs=0.1)

    def test_m24_x_12_bolts(self):
        """M24 x 12 bolts -> 12 * 198 = 2376 kN."""
        params = CalcInput(
            pressure_max_bar=40.0,
            temperature_max_c=200.0,
            flange_dn=200,
            flange_standard="EN 1092-1",
            bolt_count=12,
            bolt_size="M24",
        )
        result = mcp_calc_gasket(params)
        assert result.available_bolt_load_kn == pytest.approx(2376.0, abs=0.1)


class TestSafetyFactor:
    """Safety factor = available / required."""

    def test_safety_factor_with_full_bolt_data(self):
        params = CalcInput(
            pressure_max_bar=40.0,
            temperature_max_c=200.0,
            flange_dn=100,
            flange_standard="EN 1092-1",
            bolt_count=8,
            bolt_size="M20",
        )
        result = mcp_calc_gasket(params)
        assert result.safety_factor > 0
        # Safety factor should be available_stress / required_stress
        # With 8xM20 on DN100, we should have a reasonable safety factor
        assert result.safety_factor > 1.0

    def test_safety_factor_without_bolt_data(self):
        params = CalcInput(
            pressure_max_bar=40.0,
            temperature_max_c=200.0,
            flange_dn=100,
        )
        result = mcp_calc_gasket(params)
        assert result.safety_factor == 1.0
        assert any("Bolt data incomplete" in n for n in result.notes)


class TestCriticalApplication:
    """is_critical_application detection."""

    def test_h2_is_critical(self):
        params = CalcInput(pressure_max_bar=10.0, temperature_max_c=20.0, medium="H2")
        result = mcp_calc_gasket(params)
        assert result.is_critical_application is True

    def test_hydrogen_is_critical(self):
        params = CalcInput(pressure_max_bar=10.0, temperature_max_c=20.0, medium="Hydrogen")
        result = mcp_calc_gasket(params)
        assert result.is_critical_application is True

    def test_wasserstoff_is_critical(self):
        params = CalcInput(pressure_max_bar=10.0, temperature_max_c=20.0, medium="Wasserstoff")
        result = mcp_calc_gasket(params)
        assert result.is_critical_application is True

    def test_o2_is_critical(self):
        params = CalcInput(pressure_max_bar=10.0, temperature_max_c=20.0, medium="O2")
        result = mcp_calc_gasket(params)
        assert result.is_critical_application is True

    def test_steam_50bar_is_not_critical(self):
        params = CalcInput(pressure_max_bar=50.0, temperature_max_c=200.0, medium="Dampf")
        result = mcp_calc_gasket(params)
        assert result.is_critical_application is False

    def test_high_pressure_is_critical(self):
        params = CalcInput(pressure_max_bar=120.0, temperature_max_c=200.0, medium="Wasser")
        result = mcp_calc_gasket(params)
        assert result.is_critical_application is True

    def test_high_temperature_is_critical(self):
        params = CalcInput(pressure_max_bar=10.0, temperature_max_c=450.0, medium="Dampf")
        result = mcp_calc_gasket(params)
        assert result.is_critical_application is True

    def test_cryo_temperature_is_critical(self):
        params = CalcInput(pressure_max_bar=10.0, temperature_max_c=-50.0, medium="LNG")
        result = mcp_calc_gasket(params)
        assert result.is_critical_application is True


class TestEdgeCases:
    """Edge cases: zero pressure, extreme temperatures."""

    def test_zero_pressure(self):
        params = CalcInput(pressure_max_bar=0.0, temperature_max_c=20.0)
        result = mcp_calc_gasket(params)
        assert result.required_gasket_stress_mpa >= 0
        # At zero pressure, should still have minimum seating stress
        assert result.required_gasket_stress_mpa > 0

    def test_negative_temperature_cryo(self):
        params = CalcInput(pressure_max_bar=10.0, temperature_max_c=-196.0)
        result = mcp_calc_gasket(params)
        assert result.temperature_margin_c > 0  # 550 - (-196) = 746
        assert result.is_critical_application is True

    def test_output_is_calc_output(self):
        params = CalcInput(pressure_max_bar=40.0, temperature_max_c=200.0)
        result = mcp_calc_gasket(params)
        assert isinstance(result, CalcOutput)

    def test_margins_calculated_correctly(self):
        params = CalcInput(pressure_max_bar=100.0, temperature_max_c=300.0)
        result = mcp_calc_gasket(params)
        assert result.temperature_margin_c == pytest.approx(250.0, abs=0.1)
        assert result.pressure_margin_bar == pytest.approx(150.0, abs=0.1)


class TestCalcInputValidation:
    """CalcInput Pydantic validation."""

    def test_negative_pressure_rejected(self):
        with pytest.raises(Exception):
            CalcInput(pressure_max_bar=-1.0, temperature_max_c=20.0)

    def test_below_absolute_zero_rejected(self):
        with pytest.raises(Exception):
            CalcInput(pressure_max_bar=10.0, temperature_max_c=-300.0)

    def test_invalid_flange_class_rejected(self):
        with pytest.raises(Exception):
            CalcInput(pressure_max_bar=10.0, temperature_max_c=20.0, flange_class=999)

    def test_odd_bolt_count_rejected(self):
        with pytest.raises(Exception):
            CalcInput(pressure_max_bar=10.0, temperature_max_c=20.0, bolt_count=7)
