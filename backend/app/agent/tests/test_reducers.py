"""
Tests for deterministic state reducers — Phase F-B.2

Covers:
  - reduce_observed_to_normalized: basic extraction, user override priority,
    conflict detection, requires_confirmation → AssumptionRef
  - reduce_normalized_to_asserted: evidence upgrade, blocking unknowns,
    missing core fields
  - reduce_asserted_to_governance: Class A/B/C/D classification
  - Architecture invariants: no direct construction of Normalized/Governance
    from call-site code (grep-based integration checks)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agent.domain.requirement_class import RequirementClassSpecialistResult
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernanceState,
    NormalizedParameter,
    NormalizedState,
    ObservedExtraction,
    ObservedState,
    RequirementClass,
    UserOverride,
)
from app.agent.state.reducers import (
    SimpleClaim,
    _CORE_REQUIRED_FIELDS,
    reduce_asserted_to_governance,
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _observed(*extractions: ObservedExtraction, overrides=()) -> ObservedState:
    obs = ObservedState()
    for e in extractions:
        obs = obs.with_extraction(e)
    for o in overrides:
        obs = obs.with_override(o)
    return obs


# Float confidence values mapping to each ConfidenceLevel bucket
_CONF_CONFIRMED = 1.0        # ≥ 0.90 → "confirmed"
_CONF_ESTIMATED = 0.80       # ≥ 0.70 → "estimated"
_CONF_INFERRED = 0.60        # ≥ 0.50 → "inferred"
_CONF_REQUIRES = 0.30        # < 0.50 → "requires_confirmation"


def _ext(field, value, confidence=_CONF_CONFIRMED, turn=0, unit=None):
    """Build an ObservedExtraction.

    confidence must be a float (0.0–1.0) — use the _CONF_* constants above
    or pass a raw float value.
    """
    return ObservedExtraction(
        field_name=field,
        raw_value=value,
        raw_unit=unit,
        confidence=confidence,
        turn_index=turn,
    )


def _full_asserted(
    medium="Wasser",
    pressure=6.0,
    temperature=80.0,
    confidence="confirmed",
) -> AssertedState:
    """Build a fully-asserted state with all three core fields."""
    return AssertedState(
        assertions={
            "medium": AssertedClaim(
                field_name="medium",
                asserted_value=medium,
                confidence=confidence,
            ),
            "pressure_bar": AssertedClaim(
                field_name="pressure_bar",
                asserted_value=pressure,
                confidence=confidence,
            ),
            "temperature_c": AssertedClaim(
                field_name="temperature_c",
                asserted_value=temperature,
                confidence=confidence,
            ),
            "sealing_type": AssertedClaim(
                field_name="sealing_type",
                asserted_value="general_seal",
                confidence=confidence,
            ),
            "pressure_direction": AssertedClaim(
                field_name="pressure_direction",
                asserted_value="bidirectional",
                confidence=confidence,
            ),
            "contamination": AssertedClaim(
                field_name="contamination",
                asserted_value="none_reported",
                confidence=confidence,
            ),
            "counterface_surface": AssertedClaim(
                field_name="counterface_surface",
                asserted_value="not_critical_for_test",
                confidence=confidence,
            ),
            "tolerances": AssertedClaim(
                field_name="tolerances",
                asserted_value="not_critical_for_test",
                confidence=confidence,
            ),
            "medium_qualifiers": AssertedClaim(
                field_name="medium_qualifiers",
                asserted_value=["not_critical_for_test"],
                confidence=confidence,
            ),
        },
        blocking_unknowns=[],
        conflict_flags=[],
    )


# ---------------------------------------------------------------------------
# F-B.2.1 — reduce_observed_to_normalized
# ---------------------------------------------------------------------------

class TestReducerObservedToNormalized:

    def test_basic_single_extraction(self):
        obs = _observed(_ext("medium", "Dampf"))
        result = reduce_observed_to_normalized(obs)

        assert "medium" in result.parameters
        param = result.parameters["medium"]
        assert param.value == "Dampf"
        assert param.confidence == "confirmed"
        assert param.source == "llm"

    def test_empty_observed_gives_empty_normalized(self):
        result = reduce_observed_to_normalized(ObservedState())
        assert result.parameters == {}
        assert result.conflicts == []
        assert result.assumptions == []

    def test_user_override_wins_over_llm(self):
        obs = _observed(
            _ext("medium", "Wasser"),
            overrides=[UserOverride(field_name="medium", override_value="Öl", turn_index=1)],
        )
        result = reduce_observed_to_normalized(obs)

        param = result.parameters["medium"]
        assert param.value == "Öl"
        assert param.source == "user_override"
        assert param.confidence == "confirmed"

    def test_user_override_wins_even_with_lower_llm_confidence(self):
        obs = _observed(
            _ext("pressure_bar", 10.0, confidence=_CONF_CONFIRMED),
            overrides=[UserOverride(field_name="pressure_bar", override_value=5.0, turn_index=2)],
        )
        result = reduce_observed_to_normalized(obs)

        assert result.parameters["pressure_bar"].value == 5.0
        assert result.parameters["pressure_bar"].source == "user_override"

    def test_highest_confidence_wins_among_llm(self):
        obs = _observed(
            _ext("temperature_c", 100, confidence=_CONF_INFERRED, turn=0),
            _ext("temperature_c", 120, confidence=_CONF_CONFIRMED, turn=1),
        )
        result = reduce_observed_to_normalized(obs)

        assert result.parameters["temperature_c"].value == 120
        assert result.parameters["temperature_c"].confidence == "confirmed"

    def test_most_recent_wins_on_equal_confidence(self):
        obs = _observed(
            _ext("temperature_c", 100, confidence=_CONF_ESTIMATED, turn=0),
            _ext("temperature_c", 120, confidence=_CONF_ESTIMATED, turn=2),
        )
        result = reduce_observed_to_normalized(obs)
        assert result.parameters["temperature_c"].value == 120

    def test_conflicting_values_creates_conflict_ref(self):
        obs = _observed(
            _ext("medium", "Wasser", turn=0),
            _ext("medium", "Dampf", turn=1),
        )
        result = reduce_observed_to_normalized(obs)

        assert len(result.conflicts) == 1
        assert result.conflicts[0].field_name == "medium"
        assert result.conflicts[0].severity == "warning"

    def test_identical_values_no_conflict(self):
        obs = _observed(
            _ext("medium", "Wasser", turn=0),
            _ext("medium", "Wasser", turn=1),
        )
        result = reduce_observed_to_normalized(obs)
        assert result.conflicts == []

    def test_requires_confirmation_creates_assumption_ref(self):
        obs = _observed(_ext("medium", "Unbekannt", confidence=_CONF_REQUIRES))
        result = reduce_observed_to_normalized(obs)

        assert len(result.assumptions) == 1
        assert result.assumptions[0].field_name == "medium"
        assert result.parameters["medium"].confidence == "requires_confirmation"

    def test_unit_preserved(self):
        obs = _observed(_ext("pressure_bar", 6.0, unit="bar"))
        result = reduce_observed_to_normalized(obs)
        assert result.parameters["pressure_bar"].unit == "bar"

    def test_multiple_fields_independent(self):
        obs = _observed(
            _ext("medium", "Wasser"),
            _ext("pressure_bar", 6.0),
            _ext("temperature_c", 80.0),
        )
        result = reduce_observed_to_normalized(obs)
        assert len(result.parameters) == 3

    def test_returns_new_state_does_not_mutate(self):
        obs = _observed(_ext("medium", "Wasser"))
        obs_before_len = len(obs.raw_extractions)
        result = reduce_observed_to_normalized(obs)
        assert len(obs.raw_extractions) == obs_before_len
        assert result is not obs

    def test_salzwasser_medium_flows_without_medium_assumption(self):
        obs = _observed(_ext("medium", "Salzwasser", confidence=_CONF_CONFIRMED))
        result = reduce_observed_to_normalized(obs)

        assert result.parameters["medium"].value == "Salzwasser"
        assert result.parameters["medium"].confidence == "confirmed"
        assert [assumption.field_name for assumption in result.assumptions] == []


# ---------------------------------------------------------------------------
# F-B.2.2 — reduce_normalized_to_asserted
# ---------------------------------------------------------------------------

class TestReducerNormalizedToAsserted:

    def _normalized_with(self, **fields) -> NormalizedState:
        """Build NormalizedState with given field→(value, confidence) pairs."""
        params = {}
        for fname, (val, conf) in fields.items():
            params[fname] = NormalizedParameter(
                field_name=fname,
                value=val,
                confidence=conf,
                source="llm",
            )
        return NormalizedState(parameters=params)

    def test_confirmed_field_is_asserted(self):
        norm = self._normalized_with(medium=("Wasser", "confirmed"))
        result = reduce_normalized_to_asserted(norm)
        assert "medium" in result.assertions
        assert result.assertions["medium"].asserted_value == "Wasser"
        assert result.assertions["medium"].confidence == "confirmed"

    def test_estimated_field_is_asserted_with_caveat(self):
        norm = self._normalized_with(temperature_c=(80.0, "estimated"))
        result = reduce_normalized_to_asserted(norm)
        assert "temperature_c" in result.assertions
        assert result.assertions["temperature_c"].confidence == "estimated"

    def test_inferred_field_is_asserted(self):
        norm = self._normalized_with(pressure_bar=(6.0, "inferred"))
        result = reduce_normalized_to_asserted(norm)
        assert "pressure_bar" in result.assertions
        assert result.assertions["pressure_bar"].confidence == "inferred"

    def test_requires_confirmation_goes_to_blocking_unknowns(self):
        norm = self._normalized_with(medium=("?", "requires_confirmation"))
        result = reduce_normalized_to_asserted(norm)
        assert "medium" not in result.assertions
        assert "medium" in result.blocking_unknowns

    def test_missing_core_fields_become_blocking_unknowns(self):
        # Only provide one core field
        norm = self._normalized_with(medium=("Wasser", "confirmed"))
        result = reduce_normalized_to_asserted(norm)
        assert "pressure_bar" in result.blocking_unknowns
        assert "temperature_c" in result.blocking_unknowns
        assert "medium" not in result.blocking_unknowns

    def test_all_core_fields_present_no_blocking_unknowns(self):
        norm = self._normalized_with(
            medium=("Wasser", "confirmed"),
            pressure_bar=(6.0, "confirmed"),
            temperature_c=(80.0, "confirmed"),
        )
        result = reduce_normalized_to_asserted(norm)
        assert "sealing_type" in result.blocking_unknowns

    def test_evidence_upgrades_inferred_to_confirmed(self):
        norm = self._normalized_with(pressure_bar=(6.0, "inferred"))
        evidence = [SimpleClaim(
            claim_id="C1",
            field_name="pressure_bar",
            value=6.0,
            confidence="confirmed",
        )]
        result = reduce_normalized_to_asserted(norm, evidence=evidence)
        assert result.assertions["pressure_bar"].confidence == "confirmed"
        assert "C1" in result.assertions["pressure_bar"].evidence_refs

    def test_evidence_does_not_upgrade_requires_confirmation(self):
        norm = self._normalized_with(medium=("?", "requires_confirmation"))
        evidence = [SimpleClaim(
            claim_id="C2",
            field_name="medium",
            value="Wasser",
            confidence="confirmed",
        )]
        result = reduce_normalized_to_asserted(norm, evidence=evidence)
        # requires_confirmation is never asserted, even with evidence
        assert "medium" not in result.assertions
        assert "medium" in result.blocking_unknowns

    def test_no_evidence_is_fine(self):
        norm = self._normalized_with(medium=("Wasser", "confirmed"))
        result = reduce_normalized_to_asserted(norm, evidence=None)
        assert "medium" in result.assertions

    def test_blocking_conflict_goes_to_conflict_flags(self):
        from app.agent.state.models import ConflictRef
        norm = NormalizedState(
            parameters={
                "medium": NormalizedParameter(
                    field_name="medium", value="Wasser", confidence="confirmed", source="llm"
                )
            },
            conflicts=[
                ConflictRef(field_name="medium", description="Conflict!", severity="blocking")
            ],
        )
        result = reduce_normalized_to_asserted(norm)
        assert "medium" in result.conflict_flags

    def test_warning_conflict_does_not_go_to_conflict_flags(self):
        from app.agent.state.models import ConflictRef
        norm = NormalizedState(
            parameters={
                "medium": NormalizedParameter(
                    field_name="medium", value="Wasser", confidence="confirmed", source="llm"
                )
            },
            conflicts=[
                ConflictRef(field_name="medium", description="Soft conflict", severity="warning")
            ],
        )
        result = reduce_normalized_to_asserted(norm)
        assert result.conflict_flags == []

    def test_returns_new_state(self):
        norm = self._normalized_with(medium=("Wasser", "confirmed"))
        result = reduce_normalized_to_asserted(norm)
        assert result is not norm

    def test_recognized_medium_does_not_remain_blocking_unknown(self):
        norm = self._normalized_with(
            medium=("Salzwasser", "confirmed"),
            pressure_bar=(6.0, "confirmed"),
            temperature_c=(40.0, "confirmed"),
        )
        result = reduce_normalized_to_asserted(norm)

        assert result.assertions["medium"].asserted_value == "Salzwasser"
        assert "medium" not in result.blocking_unknowns


# ---------------------------------------------------------------------------
# F-B.2.3 — reduce_asserted_to_governance
# ---------------------------------------------------------------------------

class TestReducerAssertedToGovernanceClassA:

    def test_class_a_all_core_fields_no_blockers(self):
        asserted = _full_asserted()
        result = reduce_asserted_to_governance(asserted)
        assert result.gov_class == "A"
        assert result.rfq_admissible is True

    def test_class_a_with_estimated_fields(self):
        asserted = _full_asserted(confidence="estimated")
        result = reduce_asserted_to_governance(asserted)
        assert result.gov_class == "A"
        assert result.rfq_admissible is True

    def test_class_a_has_no_open_validation_points(self):
        asserted = _full_asserted()
        result = reduce_asserted_to_governance(asserted)
        assert result.open_validation_points == []

    def test_class_a_estimated_produces_validity_limits(self):
        asserted = _full_asserted(confidence="estimated")
        result = reduce_asserted_to_governance(asserted)
        assert any("estimated" in s for s in result.validity_limits)


class TestReducerAssertedToGovernanceClassB:

    def test_class_b_some_core_fields_within_cycle_limit(self):
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(
                    field_name="medium", asserted_value="Wasser", confidence="confirmed"
                ),
            },
            blocking_unknowns=["pressure_bar", "temperature_c"],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted, analysis_cycle=0, max_cycles=3)
        assert result.gov_class == "B"
        assert result.rfq_admissible is False

    def test_class_b_has_open_validation_points(self):
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(
                    field_name="medium", asserted_value="Wasser", confidence="confirmed"
                ),
            },
            blocking_unknowns=["pressure_bar"],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted)
        assert "pressure_bar" in result.open_validation_points
        assert "medium" not in result.open_validation_points

    def test_recognized_medium_is_not_in_open_validation_points(self):
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(
                    field_name="medium", asserted_value="Salzwasser", confidence="confirmed"
                ),
                "pressure_bar": AssertedClaim(
                    field_name="pressure_bar", asserted_value=6.0, confidence="confirmed"
                ),
                "temperature_c": AssertedClaim(
                    field_name="temperature_c", asserted_value=40.0, confidence="confirmed"
                ),
            },
            blocking_unknowns=[],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted)

        assert result.gov_class == "B"
        assert "sealing_type" in result.preselection_blockers
        assert "medium" not in result.open_validation_points

    def test_mechanical_seal_requires_duty_and_installation_before_preselection(self):
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(field_name="medium", asserted_value="Salzwasser", confidence="confirmed"),
                "pressure_bar": AssertedClaim(field_name="pressure_bar", asserted_value=10.0, confidence="confirmed"),
                "temperature_c": AssertedClaim(field_name="temperature_c", asserted_value=80.0, confidence="confirmed"),
                "sealing_type": AssertedClaim(field_name="sealing_type", asserted_value="mechanical_seal", confidence="confirmed"),
            },
            blocking_unknowns=[],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted)

        assert result.gov_class == "B"
        assert result.rfq_admissible is False
        assert result.type_sensitive_required == ["duty_profile", "installation"]
        assert "duty_profile" in result.preselection_blockers
        assert "installation" in result.preselection_blockers

    def test_regulated_industry_requires_compliance_qualifier(self):
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(field_name="medium", asserted_value="Wasser", confidence="confirmed"),
                "pressure_bar": AssertedClaim(field_name="pressure_bar", asserted_value=3.0, confidence="confirmed"),
                "temperature_c": AssertedClaim(field_name="temperature_c", asserted_value=120.0, confidence="confirmed"),
                "sealing_type": AssertedClaim(field_name="sealing_type", asserted_value="general_seal", confidence="confirmed"),
                "industry": AssertedClaim(field_name="industry", asserted_value="food_pharma", confidence="confirmed"),
            },
            blocking_unknowns=[],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted)

        assert result.gov_class == "B"
        assert result.compliance_blockers == ["compliance"]
        assert "compliance" in result.preselection_blockers


class TestReducerAssertedToGovernanceClassC:

    def test_class_c_cycle_exceeded_with_blockers(self):
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(
                    field_name="medium", asserted_value="Wasser", confidence="confirmed"
                ),
            },
            blocking_unknowns=["pressure_bar"],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted, analysis_cycle=3, max_cycles=3)
        assert result.gov_class == "C"
        assert result.rfq_admissible is False

    def test_class_c_conflict_flags(self):
        asserted = AssertedState(
            assertions={"medium": AssertedClaim(
                field_name="medium", asserted_value="Wasser", confidence="confirmed"
            )},
            blocking_unknowns=[],
            conflict_flags=["medium"],
        )
        result = reduce_asserted_to_governance(asserted)
        assert result.gov_class == "C"
        assert result.rfq_admissible is False

    def test_class_c_no_cycle_exceeded_but_all_core_present(self):
        """Cycle exceeded has no effect when there are no blocking unknowns."""
        asserted = _full_asserted()
        result = reduce_asserted_to_governance(asserted, analysis_cycle=99, max_cycles=3)
        assert result.gov_class == "A"  # cycle_exceeded only matters when blockers exist


class TestReducerAssertedToGovernanceClassD:

    def test_class_d_no_core_fields_at_all(self):
        asserted = AssertedState(
            assertions={
                "shaft_diameter_mm": AssertedClaim(
                    field_name="shaft_diameter_mm", asserted_value=50, confidence="confirmed"
                ),
            },
            blocking_unknowns=[],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted)
        assert result.gov_class == "D"
        assert result.rfq_admissible is False

    def test_class_d_empty_assertions(self):
        asserted = AssertedState()
        result = reduce_asserted_to_governance(asserted)
        assert result.gov_class == "D"

    def test_class_d_inferred_core_fields_not_enough(self):
        """Inferred confidence does not count toward core_asserted for governance."""
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(
                    field_name="medium", asserted_value="?", confidence="inferred"
                ),
                "pressure_bar": AssertedClaim(
                    field_name="pressure_bar", asserted_value=6.0, confidence="inferred"
                ),
                "temperature_c": AssertedClaim(
                    field_name="temperature_c", asserted_value=80.0, confidence="inferred"
                ),
            },
            blocking_unknowns=[],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted)
        # All inferred, none confirmed/estimated → governance treats as no core → Class D
        assert result.gov_class == "D"


class TestGovernanceReturnContract:

    def test_returns_governance_state(self):
        asserted = _full_asserted()
        result = reduce_asserted_to_governance(asserted)
        assert isinstance(result, GovernanceState)

    def test_does_not_mutate_input(self):
        asserted = _full_asserted()
        blocking_before = list(asserted.blocking_unknowns)
        reduce_asserted_to_governance(asserted)
        assert asserted.blocking_unknowns == blocking_before

    def test_validity_limits_for_inferred(self):
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(
                    field_name="medium", asserted_value="Wasser", confidence="confirmed"
                ),
                "pressure_bar": AssertedClaim(
                    field_name="pressure_bar", asserted_value=6.0, confidence="inferred"
                ),
                "temperature_c": AssertedClaim(
                    field_name="temperature_c", asserted_value=80.0, confidence="confirmed"
                ),
            },
            blocking_unknowns=[],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted)
        assert any("inferred" in s for s in result.validity_limits)

    def test_requirement_class_prefers_asserted_material_family(self):
        asserted = AssertedState(
            assertions={
                "medium": AssertedClaim(
                    field_name="medium", asserted_value="Wasser", confidence="confirmed"
                ),
                "pressure_bar": AssertedClaim(
                    field_name="pressure_bar", asserted_value=6.0, confidence="confirmed"
                ),
                "temperature_c": AssertedClaim(
                    field_name="temperature_c", asserted_value=80.0, confidence="confirmed"
                ),
                "material": AssertedClaim(
                    field_name="material", asserted_value="FKM", confidence="confirmed"
                ),
            },
            blocking_unknowns=[],
            conflict_flags=[],
        )
        result = reduce_asserted_to_governance(asserted)

        assert result.requirement_class is not None
        assert result.requirement_class.class_id == "FKM-GEN-1"
        assert result.requirement_class.seal_type == "radial_shaft_seal"

    def test_requirement_class_retains_ptfe_steam_class_without_material(self):
        asserted = _full_asserted(medium="Dampf", pressure=12.0, temperature=180.0)
        result = reduce_asserted_to_governance(asserted)

        assert result.requirement_class is not None
        assert result.requirement_class.class_id == "PTFE10"
        assert result.requirement_class.seal_type == "gasket"

    def test_requirement_class_derivation_runs_through_specialist(self, monkeypatch):
        def _specialist(_payload):
            return RequirementClassSpecialistResult(
                requirement_class_candidates=(
                    RequirementClass(
                        class_id="RC-SPECIALIST",
                        description="bounded specialist output",
                        seal_type="gasket",
                    ),
                ),
                preferred_requirement_class=RequirementClass(
                    class_id="RC-SPECIALIST",
                    description="bounded specialist output",
                    seal_type="gasket",
                ),
                open_points=("material",),
                scope_of_validity=("specialist_scope",),
            )

        monkeypatch.setattr("app.agent.state.reducers.run_requirement_class_specialist", _specialist)

        result = reduce_asserted_to_governance(_full_asserted())

        assert result.requirement_class is not None
        assert result.requirement_class.class_id == "RC-SPECIALIST"


# ---------------------------------------------------------------------------
# Architecture invariants — grep-based integration checks (F-B.2 spec)
# ---------------------------------------------------------------------------

class TestNoDirectWriteToNormalized:
    """
    NormalizedState may only be constructed by reduce_observed_to_normalized().
    No other call site may instantiate NormalizedState directly.
    """

    _ALLOWED_FILES = {
        "reducers.py",
        "test_reducers.py",
        "models.py",
        # graph/tests — test helpers that build NormalizedState for assertion setup
        "test_assert_node.py",
        "test_turn_context.py",
        # H1.1 — admissibility test builds NormalizedState fixtures
        "test_inquiry_admissibility.py",
    }

    def _collect_violations(self) -> list[Path]:
        root = Path(__file__).parents[3]  # backend/
        violations = []
        pattern = re.compile(r"\bNormalizedState\s*\(")
        for py_file in root.rglob("*.py"):
            if py_file.name in self._ALLOWED_FILES:
                continue
            text = py_file.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                violations.append(py_file)
        return violations

    def test_no_direct_write_to_normalized(self):
        violations = self._collect_violations()
        assert violations == [], (
            "Direct NormalizedState() construction outside allowed files:\n"
            + "\n".join(str(v) for v in violations)
        )


class TestNoDirectWriteToGovernance:
    """
    GovernanceState may only be constructed by reduce_asserted_to_governance().
    No other call site may instantiate GovernanceState directly.
    """

    _ALLOWED_FILES = {
        "reducers.py",
        "test_reducers.py",
        "models.py",
        # graph/tests — test helpers that build GovernanceState for assertion setup
        "test_output_contract_node.py",
        "test_cycle_control.py",
        "test_turn_context.py",
        "test_case_workspace_projection.py",
        "test_projections.py",
        "test_api_router.py",
    }

    def _collect_violations(self) -> list[Path]:
        root = Path(__file__).parents[3]  # backend/
        violations = []
        pattern = re.compile(r"\bGovernanceState\s*\(")
        for py_file in root.rglob("*.py"):
            if py_file.name in self._ALLOWED_FILES:
                continue
            text = py_file.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                violations.append(py_file)
        return violations

    def test_no_direct_write_to_governance(self):
        violations = self._collect_violations()
        assert violations == [], (
            "Direct GovernanceState() construction outside allowed files:\n"
            + "\n".join(str(v) for v in violations)
        )


# ---------------------------------------------------------------------------
# Full pipeline integration
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_pipeline_class_b_from_legacy_three_field_observations(self):
        obs = ObservedState()
        for field, value in [("medium", "Wasser"), ("pressure_bar", 6.0), ("temperature_c", 80.0)]:
            obs = obs.with_extraction(ObservedExtraction(
                field_name=field, raw_value=value, confidence=1.0, turn_index=0
            ))

        normalized = reduce_observed_to_normalized(obs)
        asserted = reduce_normalized_to_asserted(normalized)
        governance = reduce_asserted_to_governance(asserted)

        assert governance.gov_class == "B"
        assert governance.rfq_admissible is False
        assert "sealing_type" in governance.preselection_blockers

    def test_pipeline_class_b_missing_two_core_fields(self):
        obs = ObservedState().with_extraction(
            ObservedExtraction(field_name="medium", raw_value="Dampf", confidence=1.0, turn_index=0)
        )
        normalized = reduce_observed_to_normalized(obs)
        asserted = reduce_normalized_to_asserted(normalized)
        governance = reduce_asserted_to_governance(asserted)

        assert governance.gov_class == "B"
        assert governance.rfq_admissible is False

    def test_pipeline_class_d_no_technical_content(self):
        obs = ObservedState().with_extraction(
            ObservedExtraction(
                field_name="greeting", raw_value="Hallo", confidence=1.0, turn_index=0
            )
        )
        normalized = reduce_observed_to_normalized(obs)
        asserted = reduce_normalized_to_asserted(normalized)
        governance = reduce_asserted_to_governance(asserted)

        assert governance.gov_class == "D"
