from __future__ import annotations

from app.api.v1.projections.case_workspace import project_case_workspace
from app.domain.case_type import CaseType


def _workspace_state(*, system: dict | None = None, profile: dict | None = None) -> dict:
    return {
        "conversation": {"thread_id": "case-type-projection"},
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


def test_projection_maps_legacy_rfq_without_old_field_loss() -> None:
    projection = project_case_workspace(
        _workspace_state(system={"request_type": "new_design"})
    )

    assert projection.case_type is CaseType.new_rfq
    assert projection.request_type == "new_design"
    assert projection.cockpit_view.request_type == "new_design"
    assert projection.cockpit_view.routing_metadata.routing["case_type"] == "new_rfq"
    assert (
        projection.cockpit_view.routing_metadata.routing["case_type_event"]
        == "CaseTypeMappedFromLegacyRouting"
    )


def test_projection_maps_legacy_rca_request_to_failure_analysis() -> None:
    projection = project_case_workspace(
        _workspace_state(system={"request_type": "rca_failure_analysis"})
    )

    assert projection.case_type is CaseType.failure_analysis
    assert projection.request_type == "rca_failure_analysis"


def test_projection_maps_legacy_retrofit_to_replacement_reorder() -> None:
    projection = project_case_workspace(
        _workspace_state(system={"request_type": "retrofit"})
    )

    assert projection.case_type is CaseType.replacement_reorder
    assert projection.request_type == "retrofit"


def test_projection_maps_routing_conversation_intent_before_legacy_request_type() -> None:
    projection = project_case_workspace(
        _workspace_state(
            system={
                "request_type": "new_design",
                "routing": {"conversation_intent": "manufacturer_matching"},
            }
        )
    )

    assert projection.case_type is CaseType.manufacturer_matching
    assert projection.request_type == "new_design"
    assert (
        projection.cockpit_view.routing_metadata.routing["case_type"]
        == "manufacturer_matching"
    )


def test_projection_exposes_no_case_when_routing_says_no_real_case() -> None:
    projection = project_case_workspace(
        _workspace_state(system={"routing": {"conversation_intent": "small_talk"}})
    )

    assert projection.case_type is CaseType.no_case
    assert (
        projection.cockpit_view.routing_metadata.routing["case_type_event"]
        == "CaseTypeRemainsUnassigned"
    )


def test_projection_keeps_unknown_for_ambiguous_legacy_request_and_path() -> None:
    projection = project_case_workspace(
        _workspace_state(
            system={"request_type": "validation_check"},
            profile={
                "movement_type": "rotary",
                "installation": "Radialwellendichtring",
            },
        )
    )

    assert projection.case_type is CaseType.unknown
    assert projection.request_type == "validation_check"
    assert projection.engineering_path == "rwdr"
