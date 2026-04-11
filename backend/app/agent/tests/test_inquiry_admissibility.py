"""
Tests for check_inquiry_admissibility — Phase H.1.1

Coverage:
  ✓ full state → admissible=True
  ✓ missing mandatory field → admissible=False
  ✓ "assumed" status for critical field → admissible=False
  ✓ critical_review blocking_findings → admissible=False
  ✓ blocking_reasons never empty when admissible=False
  ✓ basis_hash is non-empty string
  ✓ multiple violations → all reasons reported
"""
from __future__ import annotations

import pytest

from app.agent.domain.admissibility import (
    MANDATORY_FIELDS,
    AdmissibilityResult,
    check_inquiry_admissibility,
)
from app.agent.state.models import (
    GovernedSessionState,
    NormalizedParameter,
    NormalizedState,
    RfqState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_normalized_state() -> NormalizedState:
    """NormalizedState with all 5 mandatory fields present and confirmed."""
    params = {
        "medium": NormalizedParameter(
            field_name="medium",
            value="Salzwasser",
            confidence="confirmed",
        ),
        "temperature_max_c": NormalizedParameter(
            field_name="temperature_max_c",
            value=80.0,
            unit="°C",
            confidence="confirmed",
        ),
        "pressure_max_bar": NormalizedParameter(
            field_name="pressure_max_bar",
            value=6.0,
            unit="bar",
            confidence="confirmed",
        ),
        "shaft_diameter_mm": NormalizedParameter(
            field_name="shaft_diameter_mm",
            value=50.0,
            unit="mm",
            confidence="confirmed",
        ),
        "sealing_type": NormalizedParameter(
            field_name="sealing_type",
            value="STS-TYPE-GS-S",
            confidence="confirmed",
        ),
    }
    status = {name: "observed" for name in params}
    return NormalizedState(parameters=params, parameter_status=status)


def _full_state() -> GovernedSessionState:
    """GovernedSessionState with all mandatory fields confirmed, no blocking findings."""
    return GovernedSessionState(normalized=_full_normalized_state())


# ---------------------------------------------------------------------------
# 1. Full state → admissible=True
# ---------------------------------------------------------------------------

class TestFullStateAdmissible:
    def test_full_state_is_admissible(self) -> None:
        state = _full_state()
        result = check_inquiry_admissibility(state)
        assert result.admissible is True

    def test_full_state_no_blocking_reasons(self) -> None:
        state = _full_state()
        result = check_inquiry_admissibility(state)
        assert result.blocking_reasons == ()

    def test_full_state_basis_hash_non_empty(self) -> None:
        state = _full_state()
        result = check_inquiry_admissibility(state)
        assert isinstance(result.basis_hash, str)
        assert len(result.basis_hash) > 0

    def test_full_state_result_type(self) -> None:
        state = _full_state()
        result = check_inquiry_admissibility(state)
        assert isinstance(result, AdmissibilityResult)


# ---------------------------------------------------------------------------
# 2. Missing mandatory fields → admissible=False
# ---------------------------------------------------------------------------

class TestMissingMandatoryField:
    @pytest.mark.parametrize("missing_field", MANDATORY_FIELDS)
    def test_missing_field_blocks(self, missing_field: str) -> None:
        normalized = _full_normalized_state()
        params = dict(normalized.parameters)
        params.pop(missing_field, None)
        # Also remove any alias keys
        for alias in ("temperature_c", "pressure_bar", "shaft_diameter",
                       "medium_canonical", "medium_classification"):
            params.pop(alias, None)
        status = {k: v for k, v in normalized.parameter_status.items() if k != missing_field}
        ns = NormalizedState(parameters=params, parameter_status=status)
        state = GovernedSessionState(normalized=ns)

        result = check_inquiry_admissibility(state)
        assert result.admissible is False

    @pytest.mark.parametrize("missing_field", MANDATORY_FIELDS)
    def test_missing_field_reason_reported(self, missing_field: str) -> None:
        normalized = _full_normalized_state()
        params = dict(normalized.parameters)
        params.pop(missing_field, None)
        ns = NormalizedState(
            parameters=params,
            parameter_status={k: v for k, v in normalized.parameter_status.items() if k != missing_field},
        )
        state = GovernedSessionState(normalized=ns)

        result = check_inquiry_admissibility(state)
        reasons_str = " ".join(result.blocking_reasons)
        assert missing_field in reasons_str

    def test_empty_normalized_state_blocks_all(self) -> None:
        state = GovernedSessionState()
        result = check_inquiry_admissibility(state)
        assert result.admissible is False
        # All 5 mandatory fields must be mentioned
        reasons_str = " ".join(result.blocking_reasons)
        for field_name in MANDATORY_FIELDS:
            assert field_name in reasons_str

    def test_blocking_reasons_never_empty_when_not_admissible(self) -> None:
        state = GovernedSessionState()
        result = check_inquiry_admissibility(state)
        assert not result.admissible
        assert len(result.blocking_reasons) > 0


# ---------------------------------------------------------------------------
# 3. "assumed" status for critical field → admissible=False
# ---------------------------------------------------------------------------

class TestAssumedStatusBlocking:
    def test_assumed_pressure_blocks(self) -> None:
        normalized = _full_normalized_state()
        status = dict(normalized.parameter_status)
        status["pressure_max_bar"] = "assumed"
        ns = NormalizedState(
            parameters=normalized.parameters,
            parameter_status=status,
        )
        state = GovernedSessionState(normalized=ns)

        result = check_inquiry_admissibility(state)
        assert result.admissible is False

    def test_assumed_pressure_reason_reported(self) -> None:
        normalized = _full_normalized_state()
        status = dict(normalized.parameter_status)
        status["pressure_max_bar"] = "assumed"
        ns = NormalizedState(
            parameters=normalized.parameters,
            parameter_status=status,
        )
        state = GovernedSessionState(normalized=ns)

        result = check_inquiry_admissibility(state)
        reasons_str = " ".join(result.blocking_reasons)
        assert "assumed" in reasons_str
        assert "pressure_max_bar" in reasons_str

    def test_assumed_temperature_blocks(self) -> None:
        normalized = _full_normalized_state()
        status = dict(normalized.parameter_status)
        status["temperature_max_c"] = "assumed"
        ns = NormalizedState(
            parameters=normalized.parameters,
            parameter_status=status,
        )
        state = GovernedSessionState(normalized=ns)

        result = check_inquiry_admissibility(state)
        assert result.admissible is False

    def test_assumed_medium_blocks(self) -> None:
        normalized = _full_normalized_state()
        status = dict(normalized.parameter_status)
        status["medium"] = "assumed"
        ns = NormalizedState(
            parameters=normalized.parameters,
            parameter_status=status,
        )
        state = GovernedSessionState(normalized=ns)

        result = check_inquiry_admissibility(state)
        assert result.admissible is False

    @pytest.mark.parametrize("non_blocking_status", ["observed", "derived", "stale"])
    def test_non_assumed_status_does_not_block(self, non_blocking_status: str) -> None:
        normalized = _full_normalized_state()
        status = dict(normalized.parameter_status)
        status["pressure_max_bar"] = non_blocking_status
        ns = NormalizedState(
            parameters=normalized.parameters,
            parameter_status=status,
        )
        state = GovernedSessionState(normalized=ns)

        result = check_inquiry_admissibility(state)
        # Only "assumed" should block
        reasons_str = " ".join(result.blocking_reasons)
        assert "assumed_status" not in reasons_str


# ---------------------------------------------------------------------------
# 4. critical_review blocking_findings → admissible=False
# ---------------------------------------------------------------------------

class TestCriticalReviewBlocking:
    def test_blocking_finding_blocks(self) -> None:
        rfq = RfqState(blocking_findings=["release_status_not_inquiry_ready"])
        state = GovernedSessionState(
            normalized=_full_normalized_state(),
            rfq=rfq,
        )

        result = check_inquiry_admissibility(state)
        assert result.admissible is False

    def test_blocking_finding_reason_reported(self) -> None:
        rfq = RfqState(blocking_findings=["release_status_not_inquiry_ready"])
        state = GovernedSessionState(
            normalized=_full_normalized_state(),
            rfq=rfq,
        )

        result = check_inquiry_admissibility(state)
        reasons_str = " ".join(result.blocking_reasons)
        assert "critical_review_blocking" in reasons_str
        assert "release_status_not_inquiry_ready" in reasons_str

    def test_multiple_findings_all_reported(self) -> None:
        rfq = RfqState(
            blocking_findings=["finding_a", "finding_b", "finding_c"]
        )
        state = GovernedSessionState(
            normalized=_full_normalized_state(),
            rfq=rfq,
        )

        result = check_inquiry_admissibility(state)
        assert not result.admissible
        reasons_str = " ".join(result.blocking_reasons)
        for finding in ("finding_a", "finding_b", "finding_c"):
            assert finding in reasons_str

    def test_empty_blocking_findings_does_not_block(self) -> None:
        rfq = RfqState(blocking_findings=[])
        state = GovernedSessionState(
            normalized=_full_normalized_state(),
            rfq=rfq,
        )

        result = check_inquiry_admissibility(state)
        assert result.admissible is True


# ---------------------------------------------------------------------------
# 5. Invariants
# ---------------------------------------------------------------------------

class TestInvariants:
    def test_admissible_false_never_empty_reasons(self) -> None:
        """blocking_reasons must never be empty when admissible=False."""
        # missing field case
        state = GovernedSessionState()
        result = check_inquiry_admissibility(state)
        assert not result.admissible
        assert len(result.blocking_reasons) > 0

    def test_admissible_true_implies_empty_reasons(self) -> None:
        """admissible=True must always have empty blocking_reasons."""
        state = _full_state()
        result = check_inquiry_admissibility(state)
        assert result.admissible is True
        assert result.blocking_reasons == ()

    def test_basis_hash_is_str_on_failure(self) -> None:
        state = GovernedSessionState()
        result = check_inquiry_admissibility(state)
        assert isinstance(result.basis_hash, str)

    def test_combined_violations_all_reported(self) -> None:
        """Missing field + assumed pressure + critical finding → all reasons present."""
        normalized = _full_normalized_state()
        # Remove medium
        params = {k: v for k, v in normalized.parameters.items() if k != "medium"}
        # Mark pressure as assumed
        status = dict(normalized.parameter_status)
        status["pressure_max_bar"] = "assumed"
        ns = NormalizedState(parameters=params, parameter_status=status)
        rfq = RfqState(blocking_findings=["unknowns_release_blocking"])
        state = GovernedSessionState(normalized=ns, rfq=rfq)

        result = check_inquiry_admissibility(state)
        assert not result.admissible
        reasons_str = " ".join(result.blocking_reasons)
        assert "medium" in reasons_str
        assert "assumed" in reasons_str
        assert "pressure_max_bar" in reasons_str
        assert "unknowns_release_blocking" in reasons_str

    def test_deterministic_same_state_same_result(self) -> None:
        """Same state → identical result every time (no randomness)."""
        state = _full_state()
        results = [check_inquiry_admissibility(state) for _ in range(5)]
        assert all(r.admissible == results[0].admissible for r in results)
        assert all(r.basis_hash == results[0].basis_hash for r in results)
        assert all(r.blocking_reasons == results[0].blocking_reasons for r in results)

    def test_result_is_frozen(self) -> None:
        """AdmissibilityResult is a frozen dataclass — immutable after creation."""
        result = AdmissibilityResult(admissible=True, blocking_reasons=(), basis_hash="abc123")
        with pytest.raises((AttributeError, TypeError)):
            result.admissible = False  # type: ignore[misc]
