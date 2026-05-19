from __future__ import annotations

from app.api.v1.projections.case_workspace import project_case_workspace
from app.domain.source_validation import SourceType, ValidationStatus


def _workspace_state(*, system: dict | None = None, profile: dict | None = None) -> dict:
    return {
        "conversation": {"thread_id": "source-validation-projection"},
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


def test_workspace_projection_exposes_source_and_validation_for_cockpit_fields() -> None:
    state = _workspace_state(
        profile={
            "medium": "Salzwasser",
            "temperature_c": 40.0,
            "pressure_at_seal_bar": 5.0,
        },
        system={
            "request_type": "new_design",
        },
    )
    state["reasoning"] = {
        "phase": "clarification",
        "state_revision": 1,
        "parameter_provenance": {"pressure_at_seal_bar": "user_override"},
        "parameter_confidence": {"pressure_at_seal_bar": "confirmed"},
    }
    projection = project_case_workspace(
        state
    )

    operating_geometry = next(
        section
        for section in projection.cockpit_view.sections
        if section.section_id == "operating_geometry"
    )
    pressure_property = next(
        prop for prop in operating_geometry.properties if prop.key == "pressure_nominal"
    )

    assert pressure_property.origin == "user_override"
    assert pressure_property.confidence == "confirmed"
    assert pressure_property.source_type is SourceType.user_stated
    assert pressure_property.validation_status is ValidationStatus.validated
    assert pressure_property.is_confirmed is True


def test_workspace_projection_keeps_old_projection_fields_present() -> None:
    projection = project_case_workspace(
        _workspace_state(
            profile={
                "medium": "Oel",
                "temperature_c": 80,
                "pressure_bar": 3,
            },
            system={"request_type": "new_design"},
        )
    )

    assert projection.case_type.value == "new_rfq"
    assert projection.parameters["medium"] == "Oel"
    assert projection.decision_understanding.case_summary
    assert projection.rfq_status.release_status == "precheck_only"


def test_workspace_projection_marks_missing_field_source_validation_unknown() -> None:
    projection = project_case_workspace(
        _workspace_state(
            profile={"medium": "Wasser"},
            system={"request_type": "new_design"},
        )
    )

    medium_environment = next(
        section
        for section in projection.cockpit_view.sections
        if section.section_id == "medium_environment"
    )
    temperature_property = next(
        prop for prop in medium_environment.properties if prop.key == "temperature_max"
    )

    assert temperature_property.value is None
    assert temperature_property.origin == "missing"
    assert temperature_property.source_type is SourceType.unknown
    assert temperature_property.validation_status is ValidationStatus.unknown


def test_technical_derivations_expose_deterministic_calculation_metadata() -> None:
    projection = project_case_workspace(
        _workspace_state(
            profile={"shaft_diameter_mm": 50, "speed_rpm": 1500, "pressure_bar": 4},
            system={"request_type": "new_design"},
        )
    )

    derivation = projection.technical_derivations[0]

    assert derivation.source_type is SourceType.deterministic_calculation
    assert derivation.validation_status is ValidationStatus.calculated
