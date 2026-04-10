"""
Tests for Phase 0D.5 — working_profile vs asserted_state semantics.

Verifies that _build_missing_inputs_text() correctly distinguishes:
- asserted values (confirmed/binding — not listed as missing or pending)
- working_profile-only values (pending — listed as "not yet confirmed")
- absent in both (missing — listed as required)
"""
from __future__ import annotations

import pytest
from app.agent.agent.selection import _build_missing_inputs_text


class TestMissingInputsThreeTier:
    """Phase 0D.5: three-tier parameter status in the missing-inputs reply."""

    def test_fully_empty_shows_all_as_missing(self):
        text = _build_missing_inputs_text(None, None)
        assert "Medium" in text
        assert "Betriebsdruck" in text
        assert "Betriebstemperatur" in text
        # Nothing should be "pending" when both sources are empty
        assert "noch nicht bestätigt" not in text

    def test_all_asserted_shows_nothing(self):
        """When all three are in asserted, nothing should be listed."""
        asserted = {
            "medium_profile": {"name": "Wasser"},
            "operating_conditions": {"pressure": 5.0, "temperature": 80.0},
        }
        text = _build_missing_inputs_text(asserted)
        assert "Medium" not in text
        assert "Betriebsdruck" not in text
        assert "Betriebstemperatur" not in text

    def test_wp_only_medium_shown_as_pending(self):
        """Medium in working_profile but NOT in asserted → pending, not missing."""
        wp = {"medium": "Öl"}
        text = _build_missing_inputs_text(None, wp)
        # Must appear as pending, not as missing
        assert "noch nicht bestätigt" in text
        assert "Öl" in text
        # Must NOT appear in the "benötige ich noch" section as if it were missing
        lines_before_pending = text.split("noch nicht bestätigt")[0]
        assert "Öl" not in lines_before_pending or "Ausstehend" in lines_before_pending

    def test_wp_only_pressure_shown_as_pending(self):
        wp = {"pressure_bar": 5.0}
        text = _build_missing_inputs_text(None, wp)
        assert "noch nicht bestätigt" in text
        assert "5.0" in text

    def test_wp_only_temperature_shown_as_pending(self):
        wp = {"temperature_max_c": 80.0}
        text = _build_missing_inputs_text(None, wp)
        assert "noch nicht bestätigt" in text
        assert "80.0" in text

    def test_asserted_overrides_wp(self):
        """Asserted value takes precedence — wp value for same param is irrelevant."""
        asserted = {"medium_profile": {"name": "Wasser"}}
        wp = {"medium": "Öl"}  # contradicts asserted, but asserted wins
        text = _build_missing_inputs_text(asserted, wp)
        # Wasser is confirmed → not in text at all as missing or pending
        assert "Medium" not in text

    def test_mixed_state_partial_asserted_partial_wp(self):
        """Pressure asserted, medium in wp only, temperature missing → three categories."""
        asserted = {"operating_conditions": {"pressure": 10.0}}
        wp = {"medium": "Kraftstoff"}
        text = _build_missing_inputs_text(asserted, wp)
        # Pressure confirmed → not listed
        assert "Betriebsdruck" not in text
        # Medium pending
        assert "Kraftstoff" in text
        assert "noch nicht bestätigt" in text
        # Temperature missing
        assert "Betriebstemperatur" in text

    def test_pending_label_not_in_missing_section(self):
        """pending values must appear in their own section, not mixed into 'missing'."""
        wp = {"medium": "Öl", "pressure_bar": 3.0}
        text = _build_missing_inputs_text(None, wp)
        # The text should contain both "benötige ich noch" (for temperature)
        # and "Ausstehende Bestätigung" (for medium and pressure)
        assert "Betriebstemperatur" in text  # still missing
        assert "Ausstehende Bestätigung" in text  # pending section


class TestMissingInputsNoPendingRegression:
    """Regression: when asserted has all values, no spurious output."""

    def test_all_three_asserted_empty_reply(self):
        asserted = {
            "medium_profile": {"name": "Druckluft"},
            "operating_conditions": {"pressure": 8.0, "temperature": 40.0},
        }
        text = _build_missing_inputs_text(asserted, working_profile=None)
        assert "Betriebstemperatur" not in text
        assert "Betriebsdruck" not in text
        assert "Medium" not in text

    def test_pressure_key_variants_in_wp(self):
        """Both 'pressure' and 'pressure_bar' WP keys must be treated as pending."""
        for key in ("pressure", "pressure_bar"):
            wp = {key: 7.0}
            text = _build_missing_inputs_text(None, wp)
            assert "7.0" in text, f"Expected '7.0' in pending output for wp key={key!r}"
            assert "noch nicht bestätigt" in text


class TestClarificationPriority:
    def test_priority_empty_case_is_stable_and_explicit(self):
        from app.agent.agent.selection import prioritize_missing_inputs

        result = prioritize_missing_inputs(None, None)
        assert result[:3] == ["medium", "pressure", "temperature"]
        assert result[3:] == ["shaft_diameter", "shaft_speed", "dynamic_type"]

    def test_priority_skips_pending_wp_values(self):
        from app.agent.agent.selection import prioritize_missing_inputs

        wp = {"medium": "Wasser", "pressure_bar": 8.0}
        result = prioritize_missing_inputs(None, wp)
        assert "medium" not in result
        assert "pressure" not in result
        assert result[0] == "temperature"

    def test_priority_partial_case_keeps_core_before_supplementary(self):
        from app.agent.agent.selection import prioritize_missing_inputs

        asserted = {"medium_profile": {"name": "Wasser"}}
        result = prioritize_missing_inputs(asserted, None)
        assert result[:2] == ["pressure", "temperature"]

    def test_priority_stable_for_multiple_missing_core_params(self):
        from app.agent.agent.selection import prioritize_missing_inputs

        asserted = {"operating_conditions": {"temperature": 80.0}}
        result = prioritize_missing_inputs(asserted, None)
        assert result[0:2] == ["medium", "pressure"]


class TestDeterministicNextQuestion:
    def test_next_question_targets_top_missing_core_param(self):
        from app.agent.agent.selection import build_clarification_projection, build_next_clarification_question

        projection = build_clarification_projection(
            asserted_state=None,
            working_profile=None,
            review_escalation_projection={"status": "withheld_missing_core_inputs"},
        )
        question = build_next_clarification_question(projection)
        assert projection["next_question_key"] == "medium"
        assert question == "Welches Medium soll abgedichtet werden?"

    def test_no_question_when_clarification_not_meaningful(self):
        from app.agent.agent.selection import build_clarification_projection, build_next_clarification_question

        projection = build_clarification_projection(
            asserted_state=None,
            working_profile=None,
            review_escalation_projection={"status": "review_pending"},
        )
        assert build_next_clarification_question(projection) is None

    def test_next_question_is_single_topic_only(self):
        from app.agent.agent.selection import build_clarification_projection, build_next_clarification_question

        projection = build_clarification_projection(
            asserted_state={"medium_profile": {"name": "Wasser"}},
            working_profile=None,
            review_escalation_projection={"status": "withheld_missing_core_inputs"},
        )
        question = build_next_clarification_question(projection)
        assert question == "Wie hoch ist der Betriebsdruck in bar?"
        assert " und " not in question


class TestConflictCorrectionProjection:
    def test_same_value_repeated_projects_no_conflict(self):
        from app.agent.agent.selection import project_conflict_status

        projection = project_conflict_status(
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 5 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 5.0}, "identity_records": {}},
            governance_state={"conflicts": []},
            asserted_state={"operating_conditions": {"pressure": 5.0}},
        )
        assert projection["status"] == "no_conflict"
        assert projection["correction_applied"] is False
        assert projection["conflict_still_open"] is False

    def test_new_value_projects_corrected_value(self):
        from app.agent.agent.selection import project_conflict_status

        projection = project_conflict_status(
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 8 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 8.0}, "identity_records": {}},
            governance_state={"conflicts": []},
            asserted_state={"operating_conditions": {"pressure": 8.0}},
        )
        assert projection["status"] == "corrected_value"
        assert projection["affected_keys"] == ["pressure"]
        assert projection["correction_applied"] is True
        assert projection["conflict_still_open"] is False

    def test_conflicting_values_with_open_conflict_project_unresolved(self):
        from app.agent.agent.selection import project_conflict_status

        projection = project_conflict_status(
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 8 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {"pressure_bar": 5.0}, "identity_records": {}},
            governance_state={"conflicts": [{"field": "pressure", "type": "parameter_conflict"}]},
            asserted_state={"operating_conditions": {"pressure": 5.0}},
        )
        assert projection["status"] == "unresolved_conflict"
        assert projection["affected_keys"] == ["pressure"]
        assert projection["correction_applied"] is False
        assert projection["conflict_still_open"] is True

    def test_conflicting_values_without_resolved_current_value_stay_conflicting(self):
        from app.agent.agent.selection import project_conflict_status

        projection = project_conflict_status(
            observed_state={
                "observed_inputs": [
                    {"raw_text": "Betriebsdruck 5 bar"},
                    {"raw_text": "Betriebsdruck 8 bar"},
                ]
            },
            normalized_state={"normalized_parameters": {}, "identity_records": {}},
            governance_state={"conflicts": []},
            asserted_state={"operating_conditions": {}},
        )
        assert projection["status"] == "conflicting_values"
        assert projection["conflict_still_open"] is True

    def test_conflict_projection_drives_targeted_clarification_question(self):
        from app.agent.agent.selection import build_clarification_projection, build_next_clarification_question

        conflict_projection = {
            "status": "unresolved_conflict",
            "affected_keys": ["pressure"],
            "previous_value_summary": "pressure=5.0",
            "current_value_summary": "pressure=8.0",
            "correction_applied": False,
            "conflict_still_open": True,
        }
        projection = build_clarification_projection(
            asserted_state={"medium_profile": {"name": "Wasser"}, "operating_conditions": {"temperature": 80.0}},
            working_profile=None,
            review_escalation_projection={"status": "withheld_missing_core_inputs"},
            conflict_status_projection=conflict_projection,
        )
        question = build_next_clarification_question(projection)
        assert projection["conflict_status"] == "unresolved_conflict"
        assert projection["next_question_key"] == "pressure"
        assert question == "Welcher Betriebsdruck ist korrekt?"


class TestParameterIntegrityProjection:
    def test_clean_pressure_projects_normalized_ok(self):
        from app.agent.agent.selection import project_unit_normalization_status, build_parameter_integrity_projection

        unit_projection = project_unit_normalization_status(
            normalized_state={
                "normalized_parameters": {"pressure_bar": 10.0},
                "identity_records": {
                    "pressure": {
                        "raw_value": "10 bar",
                        "normalized_value": 10.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_pressure_bar",
                    }
                },
            },
            asserted_state={"operating_conditions": {"pressure": 10.0}},
        )
        integrity = build_parameter_integrity_projection(unit_projection)
        assert unit_projection["statuses"]["pressure"] == "normalized_ok"
        assert integrity["integrity_status"] == "normalized_ok"
        assert integrity["usable_for_structured_step"] is True

    def test_unit_conversion_projects_usable_with_warning(self):
        from app.agent.agent.selection import project_unit_normalization_status, build_parameter_integrity_projection

        unit_projection = project_unit_normalization_status(
            normalized_state={
                "normalized_parameters": {"pressure_bar": 6.8948},
                "identity_records": {
                    "pressure": {
                        "raw_value": "100 psi",
                        "normalized_value": 6.8948,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "Umgerechnet von 100 PSI -> 6.8948 bar",
                    }
                },
            },
            asserted_state={"operating_conditions": {"pressure": 6.8948}},
        )
        integrity = build_parameter_integrity_projection(unit_projection)
        assert unit_projection["statuses"]["pressure"] == "usable_with_warning"
        assert integrity["integrity_status"] == "usable_with_warning"
        assert integrity["warning_keys"] == ["pressure"]
        assert integrity["usable_for_structured_step"] is True

    def test_temperature_grad_projects_unit_ambiguous_and_unusable(self):
        from app.agent.agent.selection import project_unit_normalization_status, build_parameter_integrity_projection

        unit_projection = project_unit_normalization_status(
            normalized_state={
                "normalized_parameters": {"temperature_c": 80.0},
                "identity_records": {
                    "temperature": {
                        "raw_value": "80 grad",
                        "normalized_value": 80.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_temperature_c",
                    }
                },
            },
            asserted_state={"operating_conditions": {"temperature": 80.0}},
        )
        integrity = build_parameter_integrity_projection(unit_projection)
        assert unit_projection["statuses"]["temperature"] == "unit_ambiguous"
        assert integrity["integrity_status"] == "unusable_until_clarified"
        assert integrity["blocking_keys"] == ["temperature"]
        assert integrity["usable_for_structured_step"] is False

    def test_negative_pressure_projects_implausible_value(self):
        from app.agent.agent.selection import project_unit_normalization_status, build_parameter_integrity_projection

        unit_projection = project_unit_normalization_status(
            normalized_state={
                "normalized_parameters": {"pressure_bar": -2.0},
                "identity_records": {
                    "pressure": {
                        "raw_value": "-2 bar",
                        "normalized_value": -2.0,
                        "identity_class": "identity_confirmed",
                        "normalization_certainty": "explicit_value",
                        "mapping_reason": "normalized_pressure_bar",
                    }
                },
            },
            asserted_state={"operating_conditions": {"pressure": -2.0}},
        )
        integrity = build_parameter_integrity_projection(unit_projection)
        assert unit_projection["statuses"]["pressure"] == "implausible_value"
        assert integrity["integrity_status"] == "unusable_until_clarified"


class TestDomainThresholdProjection:
    def test_in_scope_case_projects_in_domain_scope(self):
        from app.agent.agent.selection import project_threshold_status, project_domain_scope_status

        threshold = project_threshold_status(
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 5.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        domain = project_domain_scope_status(threshold)
        assert threshold["threshold_status"] == "threshold_free"
        assert domain["status"] == "in_domain_scope"
        assert domain["usable_for_governed_step"] is True

    def test_warning_case_projects_in_domain_with_warning(self):
        from app.agent.agent.selection import project_threshold_status, project_domain_scope_status

        threshold = project_threshold_status(
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        domain = project_domain_scope_status(threshold)
        assert "pv_warning" in threshold["warning_thresholds"]
        assert threshold["threshold_status"] == "warning_thresholds"
        assert domain["status"] == "in_domain_with_warning"

    def test_material_limit_projects_out_of_domain_scope(self):
        from app.agent.agent.selection import project_threshold_status, project_domain_scope_status

        threshold = project_threshold_status(
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 10.0, "temperature": 220.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        domain = project_domain_scope_status(threshold)
        assert "material_limit_exceeded" in threshold["blocking_thresholds"]
        assert domain["status"] == "out_of_domain_scope"
        assert domain["usable_for_governed_step"] is False

    def test_extrusion_risk_projects_escalation_required(self):
        from app.agent.agent.selection import project_threshold_status, project_domain_scope_status

        threshold = project_threshold_status(
            asserted_state={
                "medium_profile": {"name": "Hydrauliköl"},
                "operating_conditions": {"pressure": 300.0, "temperature": 80.0},
                "machine_profile": {"material": "FKM"},
            },
            working_profile={"shaft_diameter_mm": 50.0, "speed_rpm": 1000.0},
        )
        domain = project_domain_scope_status(threshold)
        assert "extrusion_risk" in threshold["blocking_thresholds"] or "rwdr_critical_status" in threshold["blocking_thresholds"]
        assert domain["status"] == "escalation_required"


# ---------------------------------------------------------------------------
# Phase 1A — PATCH 1: Central required-parameter regime
# ---------------------------------------------------------------------------

class TestRequiredParamsRegime:
    """Phase 1A PATCH 1: STRUCTURED_REQUIRED_CORE_PARAMS is the single source of truth
    for which parameters are needed before governed output can proceed."""

    def test_required_core_params_constant_exists(self):
        from app.agent.agent.selection import STRUCTURED_REQUIRED_CORE_PARAMS
        assert isinstance(STRUCTURED_REQUIRED_CORE_PARAMS, tuple)
        assert len(STRUCTURED_REQUIRED_CORE_PARAMS) > 0

    def test_required_core_params_has_canonical_three(self):
        from app.agent.agent.selection import STRUCTURED_REQUIRED_CORE_PARAMS
        assert "medium" in STRUCTURED_REQUIRED_CORE_PARAMS
        assert "pressure" in STRUCTURED_REQUIRED_CORE_PARAMS
        assert "temperature" in STRUCTURED_REQUIRED_CORE_PARAMS

    def test_supplementary_params_constant_exists(self):
        from app.agent.agent.selection import STRUCTURED_SUPPLEMENTARY_PARAMS
        assert isinstance(STRUCTURED_SUPPLEMENTARY_PARAMS, tuple)
        assert "shaft_diameter" in STRUCTURED_SUPPLEMENTARY_PARAMS
        assert "shaft_speed" in STRUCTURED_SUPPLEMENTARY_PARAMS

    def test_missing_critical_params_returns_all_when_no_state(self):
        """Without state, all STRUCTURED_REQUIRED_CORE_PARAMS are reported missing."""
        from app.agent.agent.interaction_policy import _missing_critical_params
        from app.agent.agent.selection import STRUCTURED_REQUIRED_CORE_PARAMS
        result = _missing_critical_params(None)
        assert set(result) == set(STRUCTURED_REQUIRED_CORE_PARAMS)

    def test_missing_critical_params_returns_empty_when_all_asserted(self):
        state = {"sealing_state": {"asserted": {
            "medium_profile": {"name": "Hydrauliköl"},
            "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
        }}}
        from app.agent.agent.interaction_policy import _missing_critical_params
        assert _missing_critical_params(state) == ()

    def test_missing_critical_params_reports_partial_gap(self):
        """Only medium confirmed → pressure and temperature reported as missing."""
        state = {"sealing_state": {"asserted": {
            "medium_profile": {"name": "Wasser"},
            "operating_conditions": {},
        }}}
        from app.agent.agent.interaction_policy import _missing_critical_params
        result = _missing_critical_params(state)
        assert "pressure" in result
        assert "temperature" in result
        assert "medium" not in result

    def test_policy_decision_required_fields_mirrors_missing_params(self):
        """evaluate_policy() required_fields must mirror _missing_critical_params() output."""
        from app.agent.agent.interaction_policy import evaluate_policy, _missing_critical_params
        # State with no params → all required
        state_empty = None
        decision = evaluate_policy("Berechne RWDR für 50mm Welle 3000rpm", state_empty)
        missing = _missing_critical_params(state_empty)
        # All missing params must appear in the decision's required_fields
        for param in missing:
            assert param in decision.required_fields, (
                f"Missing param {param!r} must be in decision.required_fields"
            )


# ---------------------------------------------------------------------------
# Phase 1A — PATCH 4: confirmed / sufficient / releasable three-level predicates
# ---------------------------------------------------------------------------

def _full_asserted() -> dict:
    """Asserted state with all three core params confirmed."""
    return {
        "medium_profile": {"name": "Hydrauliköl"},
        "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
    }


def _releasable_governance() -> dict:
    """Governance state that does NOT block output (all gates green)."""
    return {
        "release_status": "inquiry_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "unknowns_release_blocking": [],
        "gate_failures": [],
        "conflicts": [],
    }


def _blocking_governance(reason: str = "review_required") -> dict:
    """Governance state that blocks output via unknowns_release_blocking."""
    return {
        "release_status": "inquiry_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "unknowns_release_blocking": [reason],
        "gate_failures": [],
        "conflicts": [],
    }


class TestConfirmedSufficientReleasable:
    """Phase 1A PATCH 4: three semantic levels are explicitly named and independently testable."""

    # ---- has_confirmed_core_params ----------------------------------------

    def test_confirmed_true_when_all_three_in_asserted(self):
        from app.agent.agent.selection import has_confirmed_core_params
        assert has_confirmed_core_params(_full_asserted()) is True

    def test_confirmed_false_when_asserted_is_none(self):
        from app.agent.agent.selection import has_confirmed_core_params
        assert has_confirmed_core_params(None) is False

    def test_confirmed_false_when_medium_missing(self):
        from app.agent.agent.selection import has_confirmed_core_params
        asserted = {"operating_conditions": {"pressure": 5.0, "temperature": 60.0}}
        assert has_confirmed_core_params(asserted) is False

    def test_confirmed_false_when_pressure_missing(self):
        from app.agent.agent.selection import has_confirmed_core_params
        asserted = {
            "medium_profile": {"name": "Wasser"},
            "operating_conditions": {"temperature": 60.0},
        }
        assert has_confirmed_core_params(asserted) is False

    def test_confirmed_false_when_temperature_missing(self):
        from app.agent.agent.selection import has_confirmed_core_params
        asserted = {
            "medium_profile": {"name": "Wasser"},
            "operating_conditions": {"pressure": 5.0},
        }
        assert has_confirmed_core_params(asserted) is False

    def test_confirmed_false_when_two_of_three_present(self):
        """Two confirmed params are NOT sufficient — all three required."""
        from app.agent.agent.selection import has_confirmed_core_params
        asserted = {
            "medium_profile": {"name": "Öl"},
            "operating_conditions": {"pressure": 3.0},  # temperature absent
        }
        assert has_confirmed_core_params(asserted) is False

    def test_wp_only_value_does_not_count_as_confirmed(self):
        """working_profile values must NOT influence has_confirmed_core_params."""
        from app.agent.agent.selection import has_confirmed_core_params
        # asserted has no medium; a wp medium must not make it True
        asserted = {"operating_conditions": {"pressure": 5.0, "temperature": 60.0}}
        # caller passes only asserted — wp is invisible here by design
        assert has_confirmed_core_params(asserted) is False

    # ---- is_sufficient_for_structured -------------------------------------

    def test_sufficient_true_when_all_three_asserted(self):
        from app.agent.agent.selection import is_sufficient_for_structured
        assert is_sufficient_for_structured(_full_asserted()) is True

    def test_sufficient_false_when_partial_asserted(self):
        from app.agent.agent.selection import is_sufficient_for_structured
        partial = {"medium_profile": {"name": "Öl"}}  # missing pressure + temperature
        assert is_sufficient_for_structured(partial) is False

    def test_sufficient_false_when_none(self):
        from app.agent.agent.selection import is_sufficient_for_structured
        assert is_sufficient_for_structured(None) is False

    def test_sufficient_mirrors_confirmed(self):
        """is_sufficient_for_structured must agree with has_confirmed_core_params."""
        from app.agent.agent.selection import has_confirmed_core_params, is_sufficient_for_structured
        for asserted in [_full_asserted(), None, {"medium_profile": {"name": "X"}}]:
            assert is_sufficient_for_structured(asserted) == has_confirmed_core_params(asserted), (
                f"Mismatch for asserted={asserted!r}"
            )

    # ---- is_releasable ---------------------------------------------------

    def test_releasable_true_when_sufficient_and_governance_green(self):
        from app.agent.agent.selection import is_releasable
        assert is_releasable(_full_asserted(), _releasable_governance()) is True

    def test_releasable_false_when_not_sufficient(self):
        """Confirmed params missing → not releasable even if governance is green."""
        from app.agent.agent.selection import is_releasable
        partial = {"medium_profile": {"name": "Öl"}}
        assert is_releasable(partial, _releasable_governance()) is False

    def test_releasable_false_when_governance_blocks(self):
        """All params confirmed but governance blocks → not releasable."""
        from app.agent.agent.selection import is_releasable
        assert is_releasable(_full_asserted(), _blocking_governance()) is False

    def test_releasable_false_when_release_status_not_rfq_ready(self):
        from app.agent.agent.selection import is_releasable
        gov = {**_releasable_governance(), "release_status": "inadmissible"}
        assert is_releasable(_full_asserted(), gov) is False

    def test_releasable_false_when_gate_failures_present(self):
        from app.agent.agent.selection import is_releasable
        gov = {**_releasable_governance(), "gate_failures": ["evidence_missing"]}
        assert is_releasable(_full_asserted(), gov) is False

    def test_releasable_false_when_critical_conflict_present(self):
        from app.agent.agent.selection import is_releasable
        gov = {**_releasable_governance(), "conflicts": [{"severity": "CRITICAL"}]}
        assert is_releasable(_full_asserted(), gov) is False

    def test_releasable_false_when_neither_sufficient_nor_governance_green(self):
        """Worst case: both layers block."""
        from app.agent.agent.selection import is_releasable
        assert is_releasable(None, _blocking_governance()) is False

    def test_releasable_false_when_governance_is_none(self):
        """None governance defaults to inadmissible — not releasable."""
        from app.agent.agent.selection import is_releasable
        assert is_releasable(_full_asserted(), None) is False


# ---------------------------------------------------------------------------
# Phase 1B — PATCH 2: project_case_readiness() four-level projection
# ---------------------------------------------------------------------------

def _approved_review() -> dict:
    return {
        "review_required": True,
        "review_state": "approved",
        "review_reason": "Hersteller-Validierung abgeschlossen.",
    }


def _pending_review() -> dict:
    return {
        "review_required": True,
        "review_state": "pending",
        "review_reason": "Hersteller-Validierung erforderlich.",
    }


def _no_review() -> dict:
    return {"review_required": False, "review_state": "none", "review_reason": ""}


class TestCaseReadinessProjection:
    """Phase 1B PATCH 2: four-level case closure status is deterministic and testable."""

    def test_incomplete_when_no_params(self):
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(None, _releasable_governance()) == "incomplete"

    def test_incomplete_when_partial_params(self):
        from app.agent.agent.selection import project_case_readiness
        partial = {"medium_profile": {"name": "Öl"}}  # pressure + temperature missing
        assert project_case_readiness(partial, _releasable_governance()) == "incomplete"

    def test_sufficient_but_blocked_when_governance_blocks(self):
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(
            _full_asserted(), _blocking_governance()
        ) == "sufficient_but_blocked"

    def test_sufficient_but_blocked_when_review_pending(self):
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(
            _full_asserted(), _releasable_governance(), review_state=_pending_review()
        ) == "sufficient_but_blocked"

    def test_sufficient_but_blocked_when_evidence_missing(self):
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(
            _full_asserted(), _releasable_governance(), evidence_available=False
        ) == "sufficient_but_blocked"

    def test_sufficient_but_blocked_when_demo_data(self):
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(
            _full_asserted(), _releasable_governance(), demo_data_present=True
        ) == "sufficient_but_blocked"

    def test_handover_ready_when_all_clear_and_no_review(self):
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(
            _full_asserted(), _releasable_governance(), review_state=_no_review()
        ) == "handover_ready"

    def test_handover_ready_when_review_approved(self):
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(
            _full_asserted(), _releasable_governance(), review_state=_approved_review()
        ) == "handover_ready"

    def test_handover_ready_when_review_state_is_none(self):
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(
            _full_asserted(), _releasable_governance(), review_state=None
        ) == "handover_ready"

    def test_four_levels_are_ordered(self):
        """Demonstrate progression through all four levels."""
        from app.agent.agent.selection import project_case_readiness

        # Level 1: incomplete
        assert project_case_readiness(None, _blocking_governance()) == "incomplete"

        # Level 2: sufficient but blocked
        assert project_case_readiness(
            _full_asserted(), _blocking_governance()
        ) == "sufficient_but_blocked"

        # Level 4: handover_ready (skipping level 3 since review not required)
        assert project_case_readiness(
            _full_asserted(), _releasable_governance()
        ) == "handover_ready"

    def test_incomplete_takes_priority_over_governance_status(self):
        """incomplete must fire even when governance is green — inputs are the first gate."""
        from app.agent.agent.selection import project_case_readiness
        assert project_case_readiness(None, _releasable_governance()) == "incomplete"

    def test_deterministic_on_repeated_calls(self):
        from app.agent.agent.selection import project_case_readiness
        r1 = project_case_readiness(_full_asserted(), _releasable_governance())
        r2 = project_case_readiness(_full_asserted(), _releasable_governance())
        assert r1 == r2
