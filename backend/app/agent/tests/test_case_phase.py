from __future__ import annotations

import pytest

from app.domain.case_phase import AUTHORITY_CASE_PHASES, derive_case_phase


@pytest.mark.parametrize("phase", sorted(AUTHORITY_CASE_PHASES))
def test_authority_case_phase_is_preserved(phase: str) -> None:
    assert derive_case_phase(phase=phase) == phase


def test_duplicate_identical_authority_signals_are_preserved() -> None:
    assert (
        derive_case_phase(
            phase="clarification",
            authority_values=["clarification", None, ""],
        )
        == "clarification"
    )


@pytest.mark.parametrize("phase", [None, "", "   "])
def test_empty_case_phase_returns_none(phase: object) -> None:
    assert derive_case_phase(phase=phase) is None


@pytest.mark.parametrize("phase", ["final", "analysis", "rfq_ready", "matching "])
def test_unknown_explicit_case_phase_returns_none(phase: str) -> None:
    assert derive_case_phase(phase=phase) is None


def test_mixed_authority_values_return_none() -> None:
    assert derive_case_phase(authority_values=["clarification", "matching"]) is None


def test_unknown_mixed_with_authority_value_returns_none() -> None:
    assert derive_case_phase(authority_values=["matching", "final"]) is None


@pytest.mark.parametrize(
    "signals",
    [
        {"gov_class": "A"},
        {"rfq_ready": True},
        {"matching_status": "matched_primary_candidate"},
        {"last_route": "GOVERNED"},
        {"analysis_cycle": 3},
        {"conversation_phase": "matching"},
    ],
)
def test_neighbouring_signals_do_not_derive_case_phase(signals: dict[str, object]) -> None:
    assert derive_case_phase(**signals) is None
