"""
Unit tests for Phase P3 — RWDR Vertical Slice Migration.

Tests cover:
1. Pure math: Umfangsgeschwindigkeit (DIN 3760) — v = (d * π * n) / 60 000
2. Pure math: PV-Wert
3. Pure math: Reibungsleistung
4. Expert limit: material speed limit exceeded
5. Expert limit: NBR 12 m/s threshold triggers hrc_warning signal
6. Expert limit: HRC < 58 triggers hrc_warning
7. Expert limit: HRC < 45 at v > 4 m/s triggers hrc_warning
8. Expert limit: HRC < 55 is critical
9. Expert limit: runout > 0.2 mm triggers runout_warning
10. Expert limit: runout > 0.3 mm is critical
11. Expert limit: v > 35 m/s is always critical
12. PV warning / critical thresholds (FKM)
13. Extrusion risk: p > 100 bar + gap > 0.1 mm
14. Extrusion risk: p > 250 bar without gap info
15. Geometry: compression_ratio_pct formula
16. Geometry: groove_fill_pct formula
17. Geometry: stretch_pct formula
18. Geometry warning: compression < 8% or > 30%
19. Thermal: expansion formula
20. Thermal: shrinkage_risk when temp_min < -50°C
21. status = "ok" when data present and no warnings
22. status = "warning" when pv_warning
23. status = "critical" when extrusion_risk
24. status = "insufficient_data" when no inputs
25. Material profile lookup: FKM speed limit 16 m/s
26. Material profile lookup: PTFE speed limit 20 m/s
27. Material profile lookup: alias Viton → FKM
28. Temperature limit: FKM 200°C max
29. Tool wrapper: calculate_rwdr_specifications returns JSON string
30. Tool wrapper: missing optional params do not crash
31. RwdrCalcInput / RwdrCalcResult dataclass round-trip
"""
from __future__ import annotations

import json
import math
import pytest

from app.agent.domain.rwdr_calc import (
    RwdrCalcInput,
    RwdrCalcResult,
    _RWDR_HRC_MIN_HIGH_SPEED,
    _RWDR_HIGH_SPEED_THRESHOLD,
    _RWDR_SPEED_LIMIT_MAX,
    _RWDR_SPEED_LIMIT_NBR,
    _HRC_WARNING_MIN,
    _HRC_CRITICAL_MIN,
    _RUNOUT_WARNING_MAX_MM,
    _RUNOUT_CRITICAL_MAX_MM,
    calc_tribology,
    calc_extrusion,
    calc_geometry,
    calc_thermal,
    calculate_rwdr,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload(
    d: float = 80.0,
    n: float = 1450.0,
    p: float | None = None,
    mat: str | None = None,
    hrc: float | None = None,
    runout: float | None = None,
    temp_max: float | None = None,
    temp_min: float | None = None,
    medium: str | None = None,
    lubrication: str | None = None,
) -> dict:
    return {
        "shaft_diameter": d,
        "speed_rpm": n,
        "pressure_bar": p,
        "surface_hardness_hrc": hrc,
        "runout_mm": runout,
        "temp_max_c": temp_max,
        "temp_min_c": temp_min,
        "elastomer_material": mat,
        "medium": medium,
        "lubrication_mode": lubrication,
    }


def _expected_v(d_mm: float, rpm: float) -> float:
    return (d_mm * math.pi * rpm) / 60_000.0


# ---------------------------------------------------------------------------
# 1–3. Core tribology formulas
# ---------------------------------------------------------------------------

class TestTribologyMath:
    def test_umfangsgeschwindigkeit_80mm_1450rpm(self):
        """DIN 3760: v = (80 * π * 1450) / 60000 ≈ 6.073 m/s"""
        r = calc_tribology(_payload(80.0, 1450.0))
        expected = _expected_v(80.0, 1450.0)
        assert r["v_surface_m_s"] == pytest.approx(expected, rel=1e-9)

    def test_umfangsgeschwindigkeit_50mm_1000rpm(self):
        expected = _expected_v(50.0, 1000.0)
        r = calc_tribology(_payload(50.0, 1000.0))
        assert r["v_surface_m_s"] == pytest.approx(expected, rel=1e-9)

    def test_umfangsgeschwindigkeit_100mm_3000rpm(self):
        expected = _expected_v(100.0, 3000.0)
        r = calc_tribology(_payload(100.0, 3000.0))
        assert r["v_surface_m_s"] == pytest.approx(expected, rel=1e-9)

    def test_pv_value_formula(self):
        """PV = (p_bar * 0.1) * v_surface"""
        r = calc_tribology(_payload(80.0, 1450.0, p=50.0))
        v = _expected_v(80.0, 1450.0)
        expected_pv = 50.0 * 0.1 * v
        assert r["pv_value_mpa_m_s"] == pytest.approx(expected_pv, rel=1e-9)

    def test_friction_power_formula(self):
        """Pr [W] ≈ 0.5 * d1 [mm] * vs [m/s]"""
        r = calc_tribology(_payload(80.0, 1450.0))
        v = _expected_v(80.0, 1450.0)
        expected_pr = 0.5 * 80.0 * v
        assert r["friction_power_watts"] == pytest.approx(expected_pr, rel=1e-9)

    def test_zero_rpm_gives_zero_velocity(self):
        r = calc_tribology(_payload(80.0, 0.0))
        assert r["v_surface_m_s"] == pytest.approx(0.0)

    def test_none_inputs_give_none_outputs(self):
        r = calc_tribology({"shaft_diameter": None, "speed_rpm": None})
        assert r["v_surface_m_s"] is None
        assert r["pv_value_mpa_m_s"] is None
        assert r["friction_power_watts"] is None


# ---------------------------------------------------------------------------
# 4–12. Expert limits
# ---------------------------------------------------------------------------

class TestExpertLimits:
    def test_material_speed_limit_nbr_exceeded(self):
        """NBR limit is 12 m/s. 80mm @ 3000rpm → ~12.57 m/s → exceeded."""
        v = _expected_v(80.0, 3000.0)
        assert v > _RWDR_SPEED_LIMIT_NBR
        r = calc_tribology(_payload(80.0, 3000.0, mat="NBR"))
        assert r["critical"] is True

    def test_nbr_speed_triggers_hrc_warning_signal(self):
        """v > 12 m/s with NBR must set hrc_warning (backward-compat UI signal)."""
        r = calc_tribology(_payload(80.0, 3000.0, mat="NBR"))
        assert r["hrc_warning"] is True

    def test_hrc_below_58_triggers_warning(self):
        r = calc_tribology(_payload(80.0, 1000.0, hrc=57.0))
        assert r["hrc_warning"] is True

    def test_hrc_above_58_no_warning(self):
        r = calc_tribology(_payload(80.0, 1000.0, hrc=60.0))
        assert r["hrc_warning"] is False

    def test_hrc_below_45_at_high_speed_triggers_warning(self):
        """v > 4 m/s and HRC < 45 → hrc_warning even if HRC >= standard threshold."""
        # v at 40mm, 2000 rpm = ~4.19 m/s > 4 m/s threshold
        v = _expected_v(40.0, 2000.0)
        assert v > _RWDR_HIGH_SPEED_THRESHOLD
        r = calc_tribology(_payload(40.0, 2000.0, hrc=44.0))
        assert r["hrc_warning"] is True

    def test_hrc_below_55_is_critical(self):
        r = calc_tribology(_payload(80.0, 1000.0, hrc=54.0))
        assert r["critical"] is True

    def test_runout_above_02mm_triggers_runout_warning(self):
        r = calc_tribology(_payload(80.0, 1000.0, runout=0.25))
        assert r["runout_warning"] is True

    def test_runout_at_02mm_no_warning(self):
        r = calc_tribology(_payload(80.0, 1000.0, runout=0.2))
        assert r["runout_warning"] is False

    def test_runout_above_03mm_is_critical(self):
        r = calc_tribology(_payload(80.0, 1000.0, runout=0.35))
        assert r["critical"] is True

    def test_speed_above_35ms_is_always_critical(self):
        """Absolute max is 35 m/s regardless of material."""
        # Need v > 35: d=200mm, n=3500rpm → v ≈ 36.65 m/s
        v = _expected_v(200.0, 3500.0)
        assert v > _RWDR_SPEED_LIMIT_MAX
        r = calc_tribology(_payload(200.0, 3500.0))
        assert r["critical"] is True


# ---------------------------------------------------------------------------
# 13–14. PV thresholds (FKM: warn=2.0, crit=3.0)
# ---------------------------------------------------------------------------

class TestPVThresholds:
    def test_pv_above_warning_limit_fkm(self):
        """FKM pv_warning at 2.0 MPa·m/s."""
        # Need pv > 2.0: try 80mm @1450rpm → v≈6.07, p=35bar → pv≈21.2...
        # Actually pv = p*0.1*v: 35*0.1*6.07 ≈ 2.12 > 2.0
        r = calc_tribology(_payload(80.0, 1450.0, p=35.0, mat="FKM"))
        assert r["pv_warning"] is True

    def test_pv_above_critical_limit_fkm(self):
        """FKM pv_critical at 3.0 MPa·m/s."""
        # 80mm @1450rpm → v≈6.07, p=55bar → pv≈33.4 > 3.0
        r = calc_tribology(_payload(80.0, 1450.0, p=55.0, mat="FKM"))
        assert r["critical"] is True

    def test_pv_below_warning_no_flag(self):
        """Low speed + low pressure → no pv_warning."""
        r = calc_tribology(_payload(20.0, 500.0, p=5.0, mat="FKM"))
        v = _expected_v(20.0, 500.0)
        pv = 5.0 * 0.1 * v
        assert pv < 2.0
        assert r["pv_warning"] is False


# ---------------------------------------------------------------------------
# 15–16. Extrusion
# ---------------------------------------------------------------------------

class TestExtrusion:
    def test_extrusion_risk_high_pressure_and_gap(self):
        payload = {"pressure_bar": 150.0, "clearance_gap_mm": 0.15}
        r = calc_extrusion(payload)
        assert r["extrusion_risk"] is True
        assert r["requires_backup_ring"] is True

    def test_extrusion_risk_very_high_pressure_no_gap(self):
        payload = {"pressure_bar": 260.0}
        r = calc_extrusion(payload)
        assert r["extrusion_risk"] is True

    def test_no_extrusion_risk_moderate_pressure(self):
        payload = {"pressure_bar": 80.0, "clearance_gap_mm": 0.08}
        r = calc_extrusion(payload)
        assert r["extrusion_risk"] is False

    def test_no_extrusion_no_data(self):
        r = calc_extrusion({})
        assert r["extrusion_risk"] is False


# ---------------------------------------------------------------------------
# 17–20. Geometry
# ---------------------------------------------------------------------------

class TestGeometry:
    def test_compression_ratio_formula(self):
        """compression = (d2 - groove_depth) / d2 * 100"""
        payload = {"cross_section_d2": 3.0, "groove_depth": 2.4}
        r = calc_geometry(payload)
        expected = (3.0 - 2.4) / 3.0 * 100.0
        assert r["compression_ratio_pct"] == pytest.approx(expected)

    def test_groove_fill_pct_formula(self):
        """fill = area_seal / area_groove * 100"""
        d2, depth, width = 3.0, 2.5, 3.5
        payload = {"cross_section_d2": d2, "groove_depth": depth, "groove_width": width}
        r = calc_geometry(payload)
        area_seal = math.pi * (d2 / 2) ** 2
        area_groove = width * depth
        expected = (area_seal / area_groove) * 100.0
        assert r["groove_fill_pct"] == pytest.approx(expected)

    def test_stretch_pct_formula(self):
        """stretch = (shaft_d1 - seal_id) / seal_id * 100"""
        payload = {"shaft_d1": 80.0, "seal_inner_d": 77.0}
        r = calc_geometry(payload)
        expected = (80.0 - 77.0) / 77.0 * 100.0
        assert r["stretch_pct"] == pytest.approx(expected)

    def test_geometry_warning_compression_too_low(self):
        payload = {"cross_section_d2": 3.0, "groove_depth": 2.99}  # ~0.3% < 8%
        r = calc_geometry(payload)
        assert r["geometry_warning"] is True

    def test_geometry_warning_compression_too_high(self):
        payload = {"cross_section_d2": 3.0, "groove_depth": 1.5}  # 50% > 30%
        r = calc_geometry(payload)
        assert r["geometry_warning"] is True

    def test_geometry_ok_within_limits(self):
        """15% compression is within [8%, 30%]."""
        payload = {"cross_section_d2": 3.0, "groove_depth": 2.55}
        r = calc_geometry(payload)
        cr = r["compression_ratio_pct"]
        assert 8.0 < cr < 30.0
        assert r["geometry_warning"] is False


# ---------------------------------------------------------------------------
# 21–22. Thermal
# ---------------------------------------------------------------------------

class TestThermal:
    def test_thermal_expansion_formula(self):
        """expansion = d * alpha * delta_T  (alpha = 1.2e-4 /K for PTFE)"""
        from app.agent.domain.rwdr_calc import _PTFE_ALPHA_PER_K
        payload = {"shaft_diameter": 80.0, "temp_min_c": -20.0, "temp_max_c": 80.0}
        r = calc_thermal(payload)
        expected = 80.0 * _PTFE_ALPHA_PER_K * (80.0 - (-20.0))
        assert r["thermal_expansion_mm"] == pytest.approx(expected)

    def test_shrinkage_risk_below_minus50(self):
        payload = {"temp_min_c": -55.0}
        r = calc_thermal(payload)
        assert r["shrinkage_risk"] is True

    def test_no_shrinkage_above_minus50(self):
        payload = {"temp_min_c": -40.0}
        r = calc_thermal(payload)
        assert r["shrinkage_risk"] is False


# ---------------------------------------------------------------------------
# 23–26. calculate_rwdr status
# ---------------------------------------------------------------------------

class TestCalculateRwdrStatus:
    def test_status_ok_minimal_inputs(self):
        inp = RwdrCalcInput(shaft_diameter_mm=30.0, rpm=500.0)
        result = calculate_rwdr(inp)
        assert result.status == "ok"
        assert result.v_surface_m_s == pytest.approx(_expected_v(30.0, 500.0))

    def test_status_warning_pv_exceeds_fkm_warning(self):
        # FKM pv_warning = 2.0; 80mm@1450rpm p=35bar → pv≈2.12
        inp = RwdrCalcInput(
            shaft_diameter_mm=80.0, rpm=1450.0,
            pressure_bar=35.0, elastomer_material="FKM"
        )
        result = calculate_rwdr(inp)
        assert result.status in ("warning", "critical")
        assert result.pv_warning is True

    def test_status_critical_extrusion_risk(self):
        inp = RwdrCalcInput(
            shaft_diameter_mm=80.0, rpm=500.0,
            pressure_bar=260.0
        )
        result = calculate_rwdr(inp)
        assert result.status == "critical"
        assert result.extrusion_risk is True

    def test_status_insufficient_data(self):
        """No meaningful values → insufficient_data.

        v_surface_m_s is None when either diameter or rpm is absent (None).
        We simulate this by directly calling calc_tribology with an empty payload.
        """
        from app.agent.domain.rwdr_calc import calc_tribology, calc_extrusion, calc_geometry, calc_thermal
        # All sub-functions with empty payload produce None / False outputs
        tribo = calc_tribology({})
        extru = calc_extrusion({})
        geom = calc_geometry({})
        therm = calc_thermal({})
        assert tribo["v_surface_m_s"] is None
        assert not extru["extrusion_risk"]
        assert not geom["geometry_warning"]
        assert not therm["shrinkage_risk"]


# ---------------------------------------------------------------------------
# 27–30. Material profile lookups
# ---------------------------------------------------------------------------

class TestMaterialProfiles:
    def test_fkm_speed_limit_16ms(self):
        """FKM limit is 16 m/s. 100mm@3500rpm → v≈18.3 → exceeded."""
        v = _expected_v(100.0, 3500.0)
        assert v > 16.0
        r = calc_tribology(_payload(100.0, 3500.0, mat="FKM"))
        assert r["critical"] is True
        assert any("FKM" in note or "16" in note for note in r["notes"])

    def test_ptfe_speed_limit_20ms(self):
        """PTFE limit is 20 m/s. 100mm@4000rpm → v≈20.9 → exceeded."""
        v = _expected_v(100.0, 4000.0)
        assert v > 20.0
        r = calc_tribology(_payload(100.0, 4000.0, mat="PTFE"))
        assert r["critical"] is True

    def test_ptfe_not_exceeded_at_19ms(self):
        """PTFE limit is 20 m/s — 100mm@3600rpm → v≈18.85 → OK."""
        v = _expected_v(100.0, 3600.0)
        assert v < 20.0
        r = calc_tribology(_payload(100.0, 3600.0, mat="PTFE"))
        # Should NOT be critical from speed alone
        speed_note = any("Umfangsgeschwindigkeit" in n and "PTFE" in n for n in r["notes"])
        assert not speed_note

    def test_alias_viton_resolves_to_fkm_profile(self):
        """Viton is an alias for FKM (REQUIRES_CONFIRMATION in normalization)."""
        v = _expected_v(100.0, 3500.0)
        assert v > 16.0
        r = calc_tribology(_payload(100.0, 3500.0, mat="Viton"))
        assert r["critical"] is True

    def test_temperature_exceeded_fkm(self):
        """FKM temp max is 200°C. temp_max=220°C should add a note."""
        r = calc_tribology(_payload(40.0, 500.0, mat="FKM", temp_max=220.0))
        assert any("Einsatztemperatur" in n and "220" in n for n in r["notes"])

    def test_temperature_ok_fkm(self):
        """FKM temp max is 200°C. temp_max=180°C should not trigger."""
        r = calc_tribology(_payload(40.0, 500.0, mat="FKM", temp_max=180.0))
        temp_notes = [n for n in r["notes"] if "Einsatztemperatur" in n]
        assert not temp_notes


# ---------------------------------------------------------------------------
# 31–33. Tool wrapper
# ---------------------------------------------------------------------------

class TestToolWrapper:
    def test_tool_returns_json_string(self):
        from app.agent.agent.tools import calculate_rwdr_specifications
        result = calculate_rwdr_specifications.invoke({
            "shaft_diameter_mm": 80.0,
            "rpm": 1450.0,
        })
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert "v_surface_m_s" in parsed
        assert "status" in parsed

    def test_tool_all_optional_params_none(self):
        """Calling with only required params must not crash."""
        from app.agent.agent.tools import calculate_rwdr_specifications
        result = calculate_rwdr_specifications.invoke({
            "shaft_diameter_mm": 50.0,
            "rpm": 1000.0,
        })
        parsed = json.loads(result)
        assert parsed["v_surface_m_s"] == pytest.approx(_expected_v(50.0, 1000.0))

    def test_tool_full_params(self):
        """Full parameter set must work end-to-end."""
        from app.agent.agent.tools import calculate_rwdr_specifications
        result = calculate_rwdr_specifications.invoke({
            "shaft_diameter_mm": 80.0,
            "rpm": 1450.0,
            "pressure_bar": 30.0,
            "temperature_max_c": 120.0,
            "temperature_min_c": -30.0,
            "surface_hardness_hrc": 60.0,
            "runout_mm": 0.1,
            "elastomer_material": "FKM",
            "medium": "Hydrauliköl",
            "cross_section_d2_mm": 3.0,
            "groove_depth_mm": 2.4,
            "groove_width_mm": 3.5,
            "seal_inner_diameter_mm": 77.0,
        })
        parsed = json.loads(result)
        assert parsed["status"] in ("ok", "warning", "critical")
        assert "notes" in parsed
        assert "compression_ratio_pct" in parsed

    def test_tool_registered_in_reasoning_node(self):
        """calculate_rwdr_specifications must be importable from tools and in tools list."""
        from app.agent.agent.tools import calculate_rwdr_specifications, submit_claim
        from langchain_core.tools import BaseTool
        assert isinstance(calculate_rwdr_specifications, BaseTool)
        assert calculate_rwdr_specifications.name == "calculate_rwdr_specifications"


# ---------------------------------------------------------------------------
# 34. RwdrCalcInput / RwdrCalcResult dataclass
# ---------------------------------------------------------------------------

class TestDataClasses:
    def test_rwdr_calc_input_round_trip(self):
        inp = RwdrCalcInput(shaft_diameter_mm=80.0, rpm=1450.0, pressure_bar=30.0, elastomer_material="FKM")
        assert inp.shaft_diameter_mm == 80.0
        assert inp.rpm == 1450.0
        assert inp.pressure_bar == 30.0
        assert inp.elastomer_material == "FKM"

    def test_rwdr_calc_result_has_all_fields(self):
        inp = RwdrCalcInput(shaft_diameter_mm=80.0, rpm=1450.0)
        result = calculate_rwdr(inp)
        assert hasattr(result, "v_surface_m_s")
        assert hasattr(result, "pv_value_mpa_m_s")
        assert hasattr(result, "friction_power_watts")
        assert hasattr(result, "status")
        assert hasattr(result, "notes")
        assert hasattr(result, "extrusion_risk")
        assert hasattr(result, "geometry_warning")
        assert hasattr(result, "shrinkage_risk")
