"""V1.8 §6.2/§6.3 additive schema headroom (P1-H): new status/origin values and
the typed lifecycle status are accepted; existing defaults are unchanged."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.state.models import CaseField, CaseLifecycleState


def test_casefield_accepts_v18_origin_and_status_headroom() -> None:
    f = CaseField(
        field_name="material",
        value="FKM",
        status="pending_confirmation",
        provenance="datasheet_extracted",
    )
    assert f.status == "pending_confirmation"
    assert f.provenance == "datasheet_extracted"

    out = CaseField(
        field_name="outcome", status="rag_supported_note", provenance="outcome_observation"
    )
    assert out.provenance == "outcome_observation"


def test_casefield_defaults_unchanged() -> None:
    f = CaseField(field_name="speed_rpm")
    assert f.status == "unknown"
    assert f.provenance == "missing"
    assert f.confirmation_required is True


def test_lifecycle_status_defaults_to_inquiry_half() -> None:
    state = CaseLifecycleState()
    assert state.status == "inquiring"
    assert state.phase is None  # backward-compatible field retained


@pytest.mark.parametrize(
    "status",
    ["rfq_sent", "solution_selected", "installed", "in_operation", "incident", "closed"],
)
def test_lifecycle_status_accepts_all_v18_states(status: str) -> None:
    state = CaseLifecycleState(status=status)
    assert state.status == status
    # round-trips through serialization (snapshot-safe)
    assert CaseLifecycleState.model_validate(state.model_dump()).status == status


def test_lifecycle_status_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        CaseLifecycleState(status="teleporting")
