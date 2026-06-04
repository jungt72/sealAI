from __future__ import annotations

from app.api.v1.projections.case_workspace import project_case_workspace
from app.domain.seal_type import SealFamily, SealType


def _workspace_state(
    *, system: dict | None = None, profile: dict | None = None
) -> dict:
    return {
        "conversation": {"thread_id": "seal-application-profile"},
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


def test_projection_defaults_to_unknown_when_no_seal_text_is_available() -> None:
    projection = project_case_workspace(_workspace_state())

    assert projection.seal_application_profile.seal_type is SealType.unknown_seal
    assert projection.seal_application_profile.seal_family is SealFamily.unknown
    assert projection.seal_application_profile.seal_type_confidence == 0.1
    assert projection.seal_application_profile.type_specific_missing_hints == []


def test_radial_shaft_profile_includes_pressure_speed_surface_hints() -> None:
    projection = project_case_workspace(
        _workspace_state(profile={"sealing_type": "Wellendichtring"})
    )

    profile = projection.seal_application_profile
    assert profile.seal_type is SealType.radial_shaft_seal
    assert profile.seal_family is SealFamily.rotary_shaft
    assert "speed_rpm" in profile.type_specific_missing_hints
    assert "pressure_or_pressure_difference" in profile.type_specific_missing_hints
    assert "shaft_surface" in profile.type_specific_missing_hints


def test_flat_gasket_profile_includes_flange_material_bolt_load_hints() -> None:
    projection = project_case_workspace(
        _workspace_state(profile={"sealing_type": "Flachdichtung"})
    )

    profile = projection.seal_application_profile
    assert profile.seal_type is SealType.flat_gasket
    assert profile.seal_family is SealFamily.flat_gasket
    assert "flange_standard" in profile.type_specific_missing_hints
    assert "gasket_material" in profile.type_specific_missing_hints
    assert "bolt_load_or_torque" in profile.type_specific_missing_hints


def test_hydraulic_profile_includes_pressure_fluid_groove_hints() -> None:
    projection = project_case_workspace(
        _workspace_state(
            profile={
                "sealing_type": "Stangendichtung",
                "application_context": "Hydraulikzylinder",
            }
        )
    )

    profile = projection.seal_application_profile
    assert profile.seal_type is SealType.hydraulic_rod_seal
    assert profile.seal_family is SealFamily.hydraulic
    assert "pressure" in profile.type_specific_missing_hints
    assert "hydraulic_fluid" in profile.type_specific_missing_hints
    assert "groove_dimensions" in profile.type_specific_missing_hints


def test_raw_user_text_can_seed_seal_type_profile_when_structured_field_missing() -> (
    None
):
    projection = project_case_workspace(
        _workspace_state(
            system={
                "medium_capture": {
                    "primary_raw_text": "Hydraulik-Stangendichtung an einem Zylinder, 160 bar, HLP 46"
                }
            },
            profile={"pressure_bar": 160, "medium": "HLP 46"},
        )
    )

    profile = projection.seal_application_profile
    assert profile.seal_type is SealType.hydraulic_rod_seal
    assert profile.seal_family is SealFamily.hydraulic
    assert "rod_or_piston_diameter" in profile.type_specific_missing_hints
    assert "pressure_peaks" in profile.type_specific_missing_hints


def test_parameters_snapshot_exposes_type_specific_fields_for_ui_entry_roundtrip() -> (
    None
):
    projection = project_case_workspace(
        _workspace_state(
            profile={
                "sealing_type": "Hydraulik-Stangendichtung",
                "pressure_bar": 160,
                "pressure_peaks": 250,
                "hydraulic_fluid": "HLP 46",
                "rod_or_piston_diameter": 40,
                "single_or_double_acting": "doppeltwirkend",
            }
        )
    )

    assert projection.parameters["pressure_peaks"] == 250
    assert projection.parameters["hydraulic_fluid"] == "HLP 46"
    assert projection.parameters["rod_or_piston_diameter"] == 40
    assert projection.parameters["single_or_double_acting"] == "doppeltwirkend"


def test_mechanical_seal_profile_includes_flush_barrier_solids_hints() -> None:
    projection = project_case_workspace(
        _workspace_state(profile={"sealing_type": "Gleitringdichtung"})
    )

    profile = projection.seal_application_profile
    assert profile.seal_type is SealType.mechanical_seal
    assert profile.seal_family is SealFamily.mechanical_face
    assert "flush_or_barrier_fluid" in profile.type_specific_missing_hints
    assert "solids_or_gas_content" in profile.type_specific_missing_hints


def test_application_profile_is_read_only_additive_to_legacy_projection_fields() -> (
    None
):
    projection = project_case_workspace(
        _workspace_state(
            system={"request_type": "new_design"},
            profile={
                "sealing_type": "O-Ring",
                "movement_type": "static",
                "application_context": "housing_sealing",
                "standard_refs": ["ISO 3601"],
            },
        )
    )

    assert projection.request_type == "new_design"
    assert projection.engineering_path == "static"
    assert projection.seal_application_profile.seal_type is SealType.o_ring
    assert projection.seal_application_profile.motion_type == "static"
    assert projection.seal_application_profile.application_domain == "housing_sealing"
    assert projection.seal_application_profile.standard_refs == ["ISO 3601"]


def test_explicit_profile_text_sets_projection_seal_type() -> None:
    projection = project_case_workspace(
        _workspace_state(
            system={"routing": {"engineering_path": "rwdr"}},
            profile={"sealing_type": "Gleitringdichtung"},
        )
    )

    profile = projection.seal_application_profile
    assert profile.seal_type is SealType.mechanical_seal
    assert profile.ambiguous is False
    assert profile.candidate_types == [SealType.mechanical_seal]
