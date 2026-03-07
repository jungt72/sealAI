"""Tests for P4a Parameter-Extraction Node (Sprint 6).

Verifies deterministic mapping from WorkingProfile to CalcInput fields,
skip logic for incomplete profiles, and graceful error handling.
"""

import pytest

from app.langgraph_v2.state import SealAIState
from app.services.rag.state import WorkingProfile
from app.services.rag.nodes.p4a_extract import node_p4a_extract


def _make_state(**overrides) -> SealAIState:
    """Create a minimal SealAIState for testing."""
    defaults = {
        "messages": [],
        "run_id": "test-run",
        "thread_id": "test-thread",
    }
    defaults.update(overrides)
    return SealAIState(**defaults)


class TestP4aFullProfile:
    """Full profile -> valid extracted_params with all CalcInput fields."""

    def test_full_profile_extracts_all_fields(self):
        wp = WorkingProfile(
            medium="Dampf",
            pressure_max_bar=40.0,
            temperature_max_c=300.0,
            flange_standard="EN 1092-1",
            flange_dn=100,
            flange_pn=40,
            bolt_count=8,
            bolt_size="M20",
            cyclic_load=True,
        )
        state = _make_state(
            working_profile=wp,
            recommendation_ready=True,
            gap_report={"recommendation_ready": True},
        )

        result = node_p4a_extract(state)

        assert result["working_profile"]["extracted_params"]["pressure_max_bar"] == 40.0
        assert result["working_profile"]["extracted_params"]["temperature_max_c"] == 300.0
        assert result["working_profile"]["extracted_params"]["flange_standard"] == "EN 1092-1"
        assert result["working_profile"]["extracted_params"]["flange_dn"] == 100
        assert result["working_profile"]["extracted_params"]["bolt_count"] == 8
        assert result["working_profile"]["extracted_params"]["bolt_size"] == "M20"
        assert result["working_profile"]["extracted_params"]["medium"] == "Dampf"
        assert result["working_profile"]["extracted_params"]["cyclic_load"] is True
        assert result["phase"] == "extraction"
        assert result["last_node"] == "node_p4a_extract"

    def test_minimal_profile_extracts_required_fields(self):
        wp = WorkingProfile(
            pressure_max_bar=10.0,
            temperature_max_c=100.0,
        )
        state = _make_state(
            working_profile=wp,
            recommendation_ready=True,
            gap_report={"recommendation_ready": True},
        )

        result = node_p4a_extract(state)

        assert result["working_profile"]["extracted_params"]["pressure_max_bar"] == 10.0
        assert result["working_profile"]["extracted_params"]["temperature_max_c"] == 100.0
        assert "error" not in result


class TestP4aSparseProfile:
    """Sparse profile (recommendation_ready=False) -> empty extracted_params."""

    def test_recommendation_not_ready_skips(self):
        wp = WorkingProfile(medium="Dampf")
        state = _make_state(
            working_profile=wp,
            recommendation_ready=False,
            gap_report={"recommendation_ready": False},
        )

        result = node_p4a_extract(state)

        assert result["working_profile"]["extracted_params"] == {}
        assert result["phase"] == "extraction"

    def test_gap_report_overrides_state_flag(self):
        """gap_report.recommendation_ready takes precedence."""
        wp = WorkingProfile(pressure_max_bar=10.0, temperature_max_c=100.0)
        state = _make_state(
            working_profile=wp,
            recommendation_ready=True,  # state says ready
            gap_report={"recommendation_ready": False},  # gap_report says not ready
        )

        result = node_p4a_extract(state)

        assert result["working_profile"]["extracted_params"] == {}

    def test_no_working_profile_skips(self):
        state = _make_state(
            recommendation_ready=True,
            gap_report={"recommendation_ready": True},
        )

        result = node_p4a_extract(state)

        # No working_profile -> no pressure/temp -> returns empty with error
        assert result["working_profile"]["extracted_params"] == {}

    def test_missing_pressure_returns_empty(self):
        wp = WorkingProfile(temperature_max_c=100.0)
        state = _make_state(
            working_profile=wp,
            recommendation_ready=True,
            gap_report={"recommendation_ready": True},
        )

        result = node_p4a_extract(state)

        assert result["working_profile"]["extracted_params"] == {}
        assert "error" in result

    def test_missing_temperature_returns_empty(self):
        wp = WorkingProfile(pressure_max_bar=10.0)
        state = _make_state(
            working_profile=wp,
            recommendation_ready=True,
            gap_report={"recommendation_ready": True},
        )

        result = node_p4a_extract(state)

        assert result["working_profile"]["extracted_params"] == {}
        assert "error" in result


class TestP4aValidationError:
    """Profile with invalid values -> Pydantic validation error handled gracefully."""

    def test_valid_flange_class_passes_through(self):
        """Valid flange_class passes through CalcInput validation."""
        wp = WorkingProfile(
            pressure_max_bar=10.0,
            temperature_max_c=100.0,
            flange_class=300,
        )
        state = _make_state(
            working_profile=wp,
            recommendation_ready=True,
            gap_report={"recommendation_ready": True},
        )

        result = node_p4a_extract(state)

        assert result["working_profile"]["extracted_params"]["flange_class"] == 300
        assert "error" not in result

    def test_invalid_flange_class_rejected_at_working_profile(self):
        """WorkingProfile itself rejects invalid flange_class values."""
        with pytest.raises(Exception):
            WorkingProfile(
                pressure_max_bar=10.0,
                temperature_max_c=100.0,
                flange_class=999,
            )
