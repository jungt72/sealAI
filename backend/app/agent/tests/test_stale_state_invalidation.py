from __future__ import annotations

from app.agent.state.models import (
    ActionReadinessState,
    DecisionState,
    DerivedState,
    GovernedSessionState,
    RequirementClass,
)
from app.agent.state.reducers import invalidate_downstream


def _state() -> GovernedSessionState:
    return GovernedSessionState(
        derived=DerivedState(
            pv_value=1.23,
            velocity=4.56,
            material_suitability={"result": "ok"},
            applicable_norms=["ISO 21049"],
            field_status={
                "pv_value": "derived",
                "velocity": "derived",
                "material_suitability": "derived",
                "applicable_norms": "derived",
                "requirement_class": "derived",
            },
        ),
        decision=DecisionState(
            requirement_class=RequirementClass(class_id="PTFE10", description="demo"),
            preselection={"candidate": "demo"},
            field_status={
                "preselection": "derived",
                "requirement_class": "derived",
            },
        ),
        action_readiness=ActionReadinessState(
            pdf_ready=True,
            pdf_url="https://example.invalid/demo.pdf",
            inquiry_sent=True,
        ),
    )


def test_rpm_invalidation_marks_real_downstream_fields_stale() -> None:
    state = _state()

    result = invalidate_downstream("rpm", state)

    assert result.derived.field_status["pv_value"] == "stale"
    assert result.derived.field_status["velocity"] == "stale"
    assert result.derived.field_status["material_suitability"] == "stale"
    assert result.derived.applicable_norms == ["ISO 21049"]
    assert result.decision.preselection is None
    assert result.action_readiness.pdf_ready is False
    assert result.action_readiness.pdf_url is None


def test_medium_invalidation_marks_requirement_class_and_norms_stale() -> None:
    state = _state()

    result = invalidate_downstream("medium", state)

    assert result.derived.field_status["material_suitability"] == "stale"
    assert result.derived.field_status["applicable_norms"] == "stale"
    assert result.derived.field_status["requirement_class"] == "stale"
    assert result.decision.field_status["requirement_class"] == "stale"
    assert result.decision.preselection is None
    assert result.action_readiness.pdf_ready is False
    assert result.action_readiness.pdf_url is None
    assert result.action_readiness.inquiry_sent is True


def test_unmapped_field_leaves_state_unchanged_and_is_repeatable() -> None:
    state = _state()

    first = invalidate_downstream("unknown_field", state)
    second = invalidate_downstream("unknown_field", state)

    assert first == state
    assert second == state
