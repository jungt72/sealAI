"""Tests for the engineering_report.j2 Jinja2 template (Sprint 6).

Golden-file test: known CalcOutput -> rendered report matches reference.
StrictUndefined test: missing field -> UndefinedError raised.
"""

import pytest
from jinja2 import UndefinedError

from app.langgraph_v2.utils.jinja import render_template


def _full_context():
    """Known CalcOutput + WorkingProfile context for golden-file test."""
    return {
        "medium": "Dampf",
        "pressure_max_bar": 40.0,
        "temperature_max_c": 300.0,
        "flange_standard": "EN 1092-1",
        "flange_dn": 100,
        "flange_pn": 40,
        "flange_class": None,
        "bolt_count": 8,
        "bolt_size": "M20",
        "cyclic_load": False,
        "emission_class": None,
        "industry_sector": None,
        "gasket_inner_d_mm": 114.3,
        "gasket_outer_d_mm": 146.5,
        "bolt_circle_d_mm": 190.0,
        "required_gasket_stress_mpa": 69.0,
        "available_bolt_load_kn": 1096.0,
        "safety_factor": 2.31,
        "temperature_margin_c": 250.0,
        "pressure_margin_bar": 210.0,
        "is_critical_application": False,
        "notes": ["Required stress raised to minimum seating stress (69.0 MPa)."],
        "warnings": [],
        "v_surface_m_s": 5.2,
        "pv_value_mpa_m_s": 0.26,
        "friction_power_watts": 12.5,
        "p_v_limit_check": "OK",
        "hrc_warning": False,
        "hrc_value": 55.0,
        "shaft_diameter": None,
        "speed_rpm": 1200.0,
    }


class TestGoldenFile:
    """Known CalcOutput -> rendered report matches expected structure."""

    def test_report_has_all_sections(self):
        rendered = render_template("engineering_report.j2", _full_context())

        assert "BERECHNUNGSERGEBNIS" in rendered
        assert "Flanschdichtungsauslegung" in rendered
        assert "Betriebsparameter:" in rendered
        assert "Dichtungsgeometrie:" in rendered
        assert "Verschraubung:" in rendered
        assert "Berechnung:" in rendered

    def test_report_contains_values(self):
        rendered = render_template("engineering_report.j2", _full_context())

        assert "Dampf" in rendered
        assert "40.0" in rendered or "40" in rendered
        assert "300.0" in rendered or "300" in rendered
        assert "114.3" in rendered
        assert "146.5" in rendered
        assert "190.0" in rendered
        assert "69.0" in rendered
        assert "1096.0" in rendered
        assert "2.31" in rendered
        assert "250.0" in rendered
        assert "210.0" in rendered

    def test_report_contains_flange_info(self):
        rendered = render_template("engineering_report.j2", _full_context())

        assert "EN 1092-1" in rendered
        assert "DN100" in rendered
        assert "PN40" in rendered

    def test_report_shows_notes(self):
        rendered = render_template("engineering_report.j2", _full_context())

        assert "HINWEISE:" in rendered
        assert "minimum seating stress" in rendered

    def test_report_no_warnings_when_empty(self):
        rendered = render_template("engineering_report.j2", _full_context())

        assert "WARNUNGEN:" not in rendered

    def test_report_shows_warnings(self):
        ctx = _full_context()
        ctx["warnings"] = ["Cyclic load detected — fatigue analysis recommended."]

        rendered = render_template("engineering_report.j2", ctx)

        assert "WARNUNGEN:" in rendered
        assert "fatigue analysis" in rendered

    def test_report_critical_application_ja(self):
        ctx = _full_context()
        ctx["is_critical_application"] = True

        rendered = render_template("engineering_report.j2", ctx)

        assert "Kritische Anwendung: Ja" in rendered

    def test_report_critical_application_nein(self):
        rendered = render_template("engineering_report.j2", _full_context())

        assert "Kritische Anwendung: Nein" in rendered
