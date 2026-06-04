from __future__ import annotations

from app.api.v1.projections.case_workspace import project_case_workspace
from app.domain.case_type import CaseType


def _workspace_state(
    *, system: dict | None = None, profile: dict | None = None
) -> dict:
    return {
        "conversation": {"thread_id": "needs-analysis-projection"},
        "working_profile": {
            "engineering_profile": profile or {},
            "completeness": {"coverage_score": 0.0, "missing_critical_parameters": []},
        },
        "reasoning": {"phase": "clarification", "state_revision": 1},
        "system": {
            "governance_metadata": {"release_status": "precheck_only"},
            "rfq_admissibility": {
                "release_status": "precheck_only",
                "status": "precheck_only",
            },
            "matching_state": {},
            "rfq_state": {},
            "manufacturer_state": {},
            **(system or {}),
        },
    }


def test_projection_exposes_needs_current_state_nbq_and_score_without_old_field_breakage() -> (
    None
):
    projection = project_case_workspace(
        _workspace_state(
            system={"request_type": "new_design"},
            profile={
                "sealing_type": "Wellendichtring",
                "medium": "Oel",
                "temperature_c": 80,
            },
        )
    )

    assert projection.case_type is CaseType.new_rfq
    assert projection.decision_understanding.case_summary
    assert projection.needs_analysis.primary_need == (
        "prepare_manufacturer_review_ready_rfq_basis"
    )
    assert projection.current_state_analysis.seal_type_status == "known_not_confirmed"
    assert "medium" in projection.current_state_analysis.known_fields
    assert "temperature" in projection.current_state_analysis.known_fields
    assert projection.next_best_questions
    assert projection.next_best_questions[0].focus_key in {
        "pressure_or_pressure_difference",
        "speed",
    }
    assert projection.next_best_questions[0].reason
    assert projection.completeness_score.missing_critical_count >= 1
    assert projection.decision_understanding.needs_analysis == projection.needs_analysis
    assert (
        projection.decision_understanding.current_state_analysis
        == projection.current_state_analysis
    )
    assert (
        projection.decision_understanding.next_best_questions
        == projection.next_best_questions
    )
    assert (
        projection.decision_understanding.completeness_score
        == projection.completeness_score
    )


def test_projection_no_case_small_talk_has_no_engineering_question() -> None:
    projection = project_case_workspace(
        _workspace_state(system={"routing": {"conversation_intent": "small_talk"}})
    )

    assert projection.case_type is CaseType.no_case
    assert projection.next_best_questions == []
    assert projection.needs_analysis.primary_need == "no_engineering_case"
