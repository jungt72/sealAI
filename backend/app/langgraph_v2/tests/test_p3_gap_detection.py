"""Tests for P3 Gap-Detection Node (Sprint 5)."""

from __future__ import annotations

import pytest

from app.services.rag.nodes.p3_gap_detection import (
    CRITICAL_FIELDS,
    _compute_gap_report,
    node_p3_gap_detection,
)
from app.services.rag.state import WorkingProfile


def _make_state(**overrides):
    from app.langgraph_v2.state import SealAIState

    defaults = {
        "messages": [],
        "user_id": "test-user",
        "thread_id": "test-thread",
        "run_id": "test-run",
    }
    defaults.update(overrides)
    return SealAIState(**defaults)


class TestComputeGapReport:
    def test_none_profile(self):
        report = _compute_gap_report(None)
        assert set(report["missing_critical"]) == CRITICAL_FIELDS
        assert report["coverage_ratio"] == 0.0
        assert report["recommendation_ready"] is False

    def test_empty_profile(self):
        report = _compute_gap_report(WorkingProfile())
        assert set(report["missing_critical"]) == CRITICAL_FIELDS
        assert report["coverage_ratio"] == 0.0
        assert report["recommendation_ready"] is False

    def test_fully_filled_profile(self):
        profile = WorkingProfile(
            medium="Dampf",
            medium_detail="gesättigt",
            pressure_max_bar=150.0,
            pressure_min_bar=1.0,
            temperature_max_c=400.0,
            temperature_min_c=20.0,
            flange_standard="EN 1092-1",
            flange_dn=100,
            flange_pn=40,
            bolt_count=8,
            bolt_size="M20",
            cyclic_load=True,
            emission_class="TA-Luft",
            industry_sector="Petrochemie",
        )
        report = _compute_gap_report(profile)
        assert report["missing_critical"] == []
        assert report["recommendation_ready"] is True
        assert report["coverage_ratio"] > 0.9

    def test_partial_profile(self):
        profile = WorkingProfile(
            medium="Dampf",
            pressure_max_bar=10.0,
        )
        report = _compute_gap_report(profile)
        assert "medium" not in report["missing_critical"]
        assert "pressure_max_bar" not in report["missing_critical"]
        assert "temperature_max_c" in report["missing_critical"]
        assert "flange_standard" in report["missing_critical"]
        assert "flange_dn" in report["missing_critical"]
        assert report["recommendation_ready"] is False
        assert report["coverage_ratio"] > 0.0

    def test_all_critical_filled(self):
        profile = WorkingProfile(
            medium="H2SO4",
            pressure_max_bar=5.0,
            temperature_max_c=80.0,
            flange_standard="ASME B16.5",
            flange_dn=50,
        )
        report = _compute_gap_report(profile)
        assert report["missing_critical"] == []
        assert report["recommendation_ready"] is True
        assert len(report["missing_optional"]) > 0  # optional fields still missing

    def test_high_impact_gaps_equals_missing_critical(self):
        report = _compute_gap_report(WorkingProfile(medium="Dampf"))
        assert report["high_impact_gaps"] == report["missing_critical"]


class TestNodeP3GapDetection:
    def test_returns_gap_report_in_state(self):
        state = _make_state(working_profile=WorkingProfile(medium="Dampf"))
        result = node_p3_gap_detection(state)
        assert result["last_node"] == "node_p3_gap_detection"
        assert "gap_report" in result
        assert isinstance(result["gap_report"], dict)
        assert "missing_critical" in result["gap_report"]

    def test_no_profile(self):
        state = _make_state(working_profile=None)
        result = node_p3_gap_detection(state)
        assert result["gap_report"]["recommendation_ready"] is False
        assert len(result["gap_report"]["missing_critical"]) == len(CRITICAL_FIELDS)
