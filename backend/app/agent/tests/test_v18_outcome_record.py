"""V1.8 §6.5 Outcome-Record foundation (the moat): the blueprint example
validates, the case-state slice is additive and round-trip-safe, and an outcome
is an observation (suspected_cause is a hypothesis), never a release."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.state.models import GovernedSessionState, OutcomeRecord

# The verbatim §6.5 blueprint example.
BLUEPRINT_EXAMPLE = {
    "case_id": "case_1",
    "tenant_id": "tenant_1",
    "position_id": "pos_1",
    "solution_ref": "sol_01",
    "installed_at": "2026-03-02",
    "runtime_hours_estimate": 2100,
    "event": "incident",
    "outcome_pattern": "lip_hardening_thermal",
    "suspected_cause": "temp_peaks_above_continuous_limit",
    "evidence_refs": ["photo_88"],
    "confidence": "medium",
}


def test_blueprint_6_5_example_validates_and_round_trips() -> None:
    record = OutcomeRecord.model_validate(BLUEPRINT_EXAMPLE)
    assert record.event == "incident"
    assert record.solution_ref == "sol_01"
    assert record.outcome_pattern == "lip_hardening_thermal"
    assert record.suspected_cause == "temp_peaks_above_continuous_limit"  # hypothesis
    assert record.evidence_refs == ["photo_88"]
    assert OutcomeRecord.model_validate(record.model_dump()) == record


def test_outcome_record_defaults() -> None:
    record = OutcomeRecord()
    assert record.event == "incident"
    assert record.position_id == "pos_1"  # §6.6 positions[] vorsorge
    assert record.confidence == "medium"
    assert record.solution_ref is None


def test_outcome_record_rejects_unknown_event_and_confidence() -> None:
    with pytest.raises(ValidationError):
        OutcomeRecord(event="exploded")
    with pytest.raises(ValidationError):
        OutcomeRecord(confidence="certain")  # no certainty — only low/medium/high


def test_case_slice_is_additive_and_defaults_empty() -> None:
    assert GovernedSessionState().outcome_records == []


def test_case_carries_multiple_outcomes_across_positions() -> None:
    state = GovernedSessionState(
        outcome_records=[
            OutcomeRecord(position_id="pos_1", event="installed"),
            OutcomeRecord(position_id="pos_2", event="incident"),
        ]
    )
    restored = GovernedSessionState.model_validate(state.model_dump())
    assert [(r.position_id, r.event) for r in restored.outcome_records] == [
        ("pos_1", "installed"),
        ("pos_2", "incident"),
    ]
