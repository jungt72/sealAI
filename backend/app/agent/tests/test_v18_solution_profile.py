"""V1.8 §6.4 SolutionProfile foundation (P2-K1): the second envelope bundle
validates per the blueprint example, reuses the requirement-profile mechanics,
and is an additive, round-trip-safe case-state slice (default empty)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.state.models import (
    GovernedSessionState,
    SolutionField,
    SolutionProfile,
)

# The verbatim §6.4 blueprint example.
BLUEPRINT_EXAMPLE = {
    "solution_id": "sol_01",
    "label": "Angebot Hersteller A, Pos. 1",
    "state": "selected",
    "fields": [
        {
            "field": "material",
            "value": "FKM",
            "status": "confirmed",
            "origin": "datasheet_extracted",
            "source_doc": "doc_17",
            "source_page": 2,
        },
        {
            "field": "temp_max_continuous_c",
            "value": 150,
            "status": "confirmed",
            "origin": "datasheet_extracted",
            "source_doc": "doc_17",
            "source_page": 2,
        },
        {
            "field": "dry_run_capable",
            "value": False,
            "status": "pending_confirmation",
            "origin": "manufacturer_response",
        },
    ],
}


def test_blueprint_6_4_example_validates_and_round_trips() -> None:
    profile = SolutionProfile.model_validate(BLUEPRINT_EXAMPLE)
    assert profile.solution_id == "sol_01"
    assert profile.state == "selected"
    assert len(profile.fields) == 3
    # datasheet origin carries the mandatory doc + page
    material = profile.fields[0]
    assert material.origin == "datasheet_extracted"
    assert (material.source_doc, material.source_page) == ("doc_17", 2)
    # manufacturer_response origin is accepted; no source doc required
    dry_run = profile.fields[2]
    assert dry_run.origin == "manufacturer_response"
    assert dry_run.status == "pending_confirmation"
    # round-trips byte-for-byte through (de)serialization
    assert SolutionProfile.model_validate(profile.model_dump()) == profile


def test_solution_field_defaults_match_ingestion_intent() -> None:
    f = SolutionField(field="v_max")
    assert f.status == "pending_confirmation"  # candidates start unconfirmed
    assert f.origin == "datasheet_extracted"
    assert f.source_doc is None and f.source_page is None


def test_solution_field_rejects_unknown_origin() -> None:
    with pytest.raises(ValidationError):
        SolutionField(field="x", origin="hearsay")


def test_solution_state_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        SolutionProfile(solution_id="s", state="recommended")  # ranking not allowed


def test_case_state_slice_is_additive_and_defaults_empty() -> None:
    state = GovernedSessionState()
    assert state.solution_profiles == []
    # unchanged inquiry-half default


def test_case_state_carries_multiple_profiles_for_comparison() -> None:
    # Multiple profiles = technical comparison, never a ranking/recommendation.
    state = GovernedSessionState(
        solution_profiles=[
            SolutionProfile(solution_id="sol_a", label="A", state="offer"),
            SolutionProfile(solution_id="sol_b", label="B", state="offer"),
        ]
    )
    restored = GovernedSessionState.model_validate(state.model_dump())
    assert [p.solution_id for p in restored.solution_profiles] == ["sol_a", "sol_b"]
