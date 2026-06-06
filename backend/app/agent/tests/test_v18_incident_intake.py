"""V1.8 §5.3 / AC14: incident at the installed part → Soll-Ist → Outcome-Event.

The suspected_cause is a hypothesis from the worst requirement-vs-limit mismatch,
never a verdict; no mismatch → no fabricated cause.
"""

from __future__ import annotations

from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernedSessionState,
    SolutionField,
    SolutionProfile,
)
from app.services.incident_intake import build_incident_outcome


def _claim(field: str, value: object, status: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, status=status)


def _sol(**limits: object) -> SolutionProfile:
    return SolutionProfile(
        solution_id="sol_01",
        state="installed",
        fields=[
            SolutionField(
                field=k,
                value=v,
                origin="datasheet_extracted",
                source_doc="doc_17",
                source_page=2,
            )
            for k, v in limits.items()
        ],
    )


def _state(assertions, solution=None) -> GovernedSessionState:
    return GovernedSessionState(
        asserted=AssertedState(assertions=assertions),
        solution_profiles=[solution] if solution else [],
    )


def test_thermal_overrun_yields_thermal_pattern_and_hypothesis() -> None:
    # operating temp 180 °C above the datasheet 150 °C continuous limit
    state = _state(
        {"temperature_max_c": _claim("temperature_max_c", 180)},
        _sol(temp_max_continuous_c=150),
    )
    rec = build_incident_outcome(
        state, case_id="c1", tenant_id="t1", evidence_refs=["photo_88"]
    )
    assert rec.event == "incident"
    assert rec.solution_ref == "sol_01"
    assert rec.outcome_pattern == "lip_hardening_thermal"
    assert rec.suspected_cause == "operating_temperature_above_continuous_limit"
    assert (
        rec.confidence == "high"
    )  # clear critical Soll-Ist signal (still a hypothesis)
    assert rec.evidence_refs == ["photo_88"]


def test_dry_running_incident_pattern() -> None:
    state = _state(
        {"dry_running_required": _claim("dry_running_required", True)},
        _sol(dry_run_capable=False),
    )
    rec = build_incident_outcome(state, tenant_id="t1")
    assert rec.outcome_pattern == "dry_running_track"
    assert rec.suspected_cause == "dry_running_not_supported"
    assert rec.confidence == "high"


def test_no_mismatch_emits_outcome_without_fabricated_cause() -> None:
    # within all limits → incident recorded, but no pattern/cause invented
    state = _state(
        {"temperature_max_c": _claim("temperature_max_c", 100)},
        _sol(temp_max_continuous_c=150),
    )
    rec = build_incident_outcome(state, tenant_id="t1")
    assert rec.event == "incident"
    assert rec.outcome_pattern is None
    assert rec.suspected_cause is None
    assert rec.confidence == "low"


def test_no_solution_still_records_incident_low_confidence() -> None:
    state = _state({"temperature_max_c": _claim("temperature_max_c", 180)})
    rec = build_incident_outcome(state, tenant_id="t1")
    assert rec.event == "incident"
    assert rec.solution_ref is None
    assert rec.confidence == "low"  # nothing to compare against — no cause


def test_passthrough_context_fields() -> None:
    state = _state(
        {"temperature_max_c": _claim("temperature_max_c", 180)},
        _sol(temp_max_continuous_c=150),
    )
    rec = build_incident_outcome(
        state,
        tenant_id="t1",
        position_id="pos_2",
        installed_at="2026-03-02",
        runtime_hours_estimate=2100,
    )
    assert rec.position_id == "pos_2"
    assert rec.installed_at == "2026-03-02"
    assert rec.runtime_hours_estimate == 2100
