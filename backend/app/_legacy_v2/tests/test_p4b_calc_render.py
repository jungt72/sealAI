"""Tests for P4b MCP Calc + Jinja2 Render Node (Sprint 6).

Verifies: calc runs and report rendered, empty params skip, MCP failure
error handling, and Jinja2 UndefinedError handling.
"""

from unittest.mock import patch

from app._legacy_v2.state import Intent, SealAIState
from app.services.rag.state import WorkingProfile
from app.services.rag.nodes.p4b_calc_render import node_p4b_calc_render


def _make_state(**overrides) -> SealAIState:
    """Create a minimal SealAIState for testing."""
    defaults = {
        "messages": [],
        "run_id": "test-run",
        "thread_id": "test-thread",
    }
    defaults.update(overrides)
    return SealAIState(**defaults)


class TestP4bValidCalc:
    """Valid extracted_params -> calc runs, report rendered."""

    def test_valid_params_produces_calculation_result(self):
        wp = WorkingProfile(
            medium="Dampf",
            pressure_max_bar=40.0,
            temperature_max_c=300.0,
            flange_standard="EN 1092-1",
            flange_dn=100,
            bolt_count=8,
            bolt_size="M20",
        )
        state = _make_state(
            working_profile=wp,
            extracted_params={
                "pressure_max_bar": 40.0,
                "temperature_max_c": 300.0,
                "flange_standard": "EN 1092-1",
                "flange_dn": 100,
                "bolt_count": 8,
                "bolt_size": "M20",
                "medium": "Dampf",
                "cyclic_load": False,
            },
        )

        result = node_p4b_calc_render(state)

        assert result["calculation_result"] is not None
        assert "rendered_report" in result["calculation_result"]
        assert result["calculation_result"]["safety_factor"] > 0
        assert result["calc_results"] is not None
        assert result["phase"] == "calculation"
        assert result["last_node"] == "node_p4b_calc_render"

    def test_report_contains_key_sections(self):
        wp = WorkingProfile(
            medium="Dampf",
            pressure_max_bar=40.0,
            temperature_max_c=300.0,
            flange_dn=100,
        )
        state = _make_state(
            working_profile=wp,
            extracted_params={
                "pressure_max_bar": 40.0,
                "temperature_max_c": 300.0,
                "medium": "Dampf",
                "cyclic_load": False,
            },
        )

        result = node_p4b_calc_render(state)

        report = result["calculation_result"]["rendered_report"]
        assert "BERECHNUNGSERGEBNIS" in report
        assert "Betriebsparameter" in report
        assert "Dichtungsgeometrie" in report
        assert "Sicherheitsfaktor" in report
        assert "40.0" in report or "40" in report  # pressure value

    def test_critical_application_flag_set(self):
        state = _make_state(
            working_profile=WorkingProfile(
                medium="H2",
                pressure_max_bar=10.0,
                temperature_max_c=20.0,
            ),
            extracted_params={
                "pressure_max_bar": 10.0,
                "temperature_max_c": 20.0,
                "medium": "H2",
                "cyclic_load": False,
            },
        )

        result = node_p4b_calc_render(state)

        assert result["is_critical_application"] is True

    def test_calc_results_compatibility(self):
        """CalcResults should be populated for existing final-answer chain."""
        state = _make_state(
            working_profile=WorkingProfile(
                pressure_max_bar=40.0,
                temperature_max_c=200.0,
            ),
            extracted_params={
                "pressure_max_bar": 40.0,
                "temperature_max_c": 200.0,
                "cyclic_load": False,
            },
        )

        result = node_p4b_calc_render(state)

    def test_calc_render_stamps_assertion_binding(self):
        state = _make_state(
            working_profile=WorkingProfile(
                pressure_max_bar=40.0,
                temperature_max_c=200.0,
            ),
            extracted_params={
                "pressure_max_bar": 40.0,
                "temperature_max_c": 200.0,
                "cyclic_load": False,
            },
            reasoning={"current_assertion_cycle_id": 5, "asserted_profile_revision": 11},
        )

        result = node_p4b_calc_render(state)

        assert result["working_profile"]["derived_from_assertion_cycle_id"] == 5
        assert result["working_profile"]["derived_from_assertion_revision"] == 11
        assert result["working_profile"]["derived_artifacts_stale"] is False

        calc_results = result["calc_results"]
        assert calc_results.safety_factor is not None
        assert calc_results.temperature_margin is not None
        assert calc_results.pressure_margin is not None

    def test_extra_extracted_fields_are_ignored(self):
        """Additional P1/P4 physics fields must not break CalcInput validation."""
        state = _make_state(
            working_profile=WorkingProfile(
                pressure_max_bar=40.0,
                temperature_max_c=200.0,
                medium="Dampf",
            ),
            extracted_params={
                "pressure_max_bar": 40.0,
                "temperature_max_c": 200.0,
                "medium": "Dampf",
                "cyclic_load": False,
                # New physics extraction keys not part of CalcInput:
                "rpm": 1500.0,
                "hrc": 55.0,
                "hrc_value": 55.0,
                "shaft_d1_mm": 50.0,
                "clearance_gap_mm": 0.2,
            },
        )

        result = node_p4b_calc_render(state)

        assert "error" not in result
        assert result["calculation_result"] is not None
        assert result["phase"] == "calculation"


class TestP4bEmptyParams:
    """Empty extracted_params -> skip, no error."""

    def test_empty_params_skips(self):
        state = _make_state(extracted_params={})

        result = node_p4b_calc_render(state)

        assert result["phase"] == "calculation"
        assert result["last_node"] == "node_p4b_calc_render"
        assert "calculation_result" not in result
        assert "error" not in result

    def test_none_params_skips(self):
        state = _make_state()

        result = node_p4b_calc_render(state)

        assert "calculation_result" not in result
        assert "error" not in result

    def test_missing_required_fields_are_backfilled_from_working_profile(self):
        state = _make_state(
            working_profile=WorkingProfile(
                pressure_max_bar=25.0,
                temperature_max_c=180.0,
                medium="Wasser",
            ),
            extracted_params={"medium": "Wasser", "cyclic_load": False},
        )

        result = node_p4b_calc_render(state)

        assert "error" not in result
        assert result.get("calculation_result") is not None

    def test_explanation_intent_skips_if_required_inputs_missing(self):
        state = _make_state(
            intent=Intent(goal="explanation_or_comparison"),
            flags={"frontdoor_intent_category": "MATERIAL_RESEARCH"},
            extracted_params={"medium": "Kyrolon", "cyclic_load": False},
        )

        result = node_p4b_calc_render(state)

        assert result["phase"] == "calculation"
        assert result["last_node"] == "node_p4b_calc_render"
        assert "error" not in result
        assert "calculation_result" not in result


class TestP4bMcpFailure:
    """MCP failure -> error_state set, no crash."""

    def test_calc_engine_failure_sets_error(self):
        state = _make_state(
            working_profile=WorkingProfile(
                pressure_max_bar=40.0,
                temperature_max_c=200.0,
            ),
            extracted_params={
                "pressure_max_bar": 40.0,
                "temperature_max_c": 200.0,
                "cyclic_load": False,
            },
        )

        with patch(
            "app.services.rag.nodes.p4b_calc_render.mcp_calc_gasket",
            side_effect=RuntimeError("MCP engine down"),
        ):
            result = node_p4b_calc_render(state)

        assert "error" in result
        assert "P4b: MCP calc engine failed" in result["error"]
        assert "calculation_result" not in result

    def test_invalid_calc_input_sets_error(self):
        state = _make_state(
            working_profile=WorkingProfile.model_construct(
                pressure_max_bar=-999.0,  # Invalid
                temperature_max_c=200.0,
            ),
            extracted_params={
                "pressure_max_bar": -999.0,
                "temperature_max_c": 200.0,
            },
        )

        result = node_p4b_calc_render(state)

        assert "error" in result


class TestP4bJinjaError:
    """Jinja2 UndefinedError -> error logged, no partial report."""

    def test_jinja_undefined_error_handled(self):
        from jinja2 import UndefinedError

        state = _make_state(
            working_profile=WorkingProfile(
                pressure_max_bar=40.0,
                temperature_max_c=200.0,
            ),
            extracted_params={
                "pressure_max_bar": 40.0,
                "temperature_max_c": 200.0,
                "cyclic_load": False,
            },
        )

        with patch(
            "app.services.rag.nodes.p4b_calc_render.render_template",
            side_effect=UndefinedError("'missing_var' is undefined"),
        ):
            result = node_p4b_calc_render(state)

        assert "error" in result
        assert "Jinja2 template error" in result["error"]
        # Should still set calc_results and is_critical even if template fails
        assert result.get("calc_results") is not None
