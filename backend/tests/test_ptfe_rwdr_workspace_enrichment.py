from __future__ import annotations

from app.api.v1.projections.case_workspace import project_case_workspace


def _workspace_state(profile: dict) -> dict:
    return {
        "conversation": {"thread_id": "case-ptfe-1", "turn_count": 1},
        "working_profile": {
            "engineering_profile": profile,
            "extracted_params": profile,
            "completeness": {"coverage_score": 0.5, "missing_critical_parameters": []},
        },
        "reasoning": {"phase": "clarification", "state_revision": 1},
        "system": {
            "governance_metadata": {
                "release_status": "manufacturer_validation_required"
            },
            "rfq_admissibility": {"status": "preliminary"},
            "answer_contract": {"release_status": "manufacturer_validation_required"},
            "medium_capture": {"primary_raw_text": profile.get("medium")},
            "medium_classification": {},
            "medium_context": {},
            "evidence_state": {},
            "matching_state": {},
            "rfq_state": {},
            "manufacturer_state": {},
        },
    }


def test_ptfe_rwdr_workspace_enrichment_runs_cascade_and_advisories() -> None:
    projection = project_case_workspace(
        _workspace_state(
            {
                "engineering_path": "rwdr",
                "sealing_type": "PTFE-RWDR",
                "sealing_material_family": "ptfe_glass_filled",
                "medium": "HLP46",
                "application_context": "Hydraulik Getriebe",
                "shaft_diameter_mm": 50,
                "speed_rpm": 1500,
                "pressure_bar": 5,
                "temperature_c": 120,
                "radial_force_n_per_mm": 2,
                "contact_width_mm": 0.5,
                "extrusion_gap_mm": 0.1,
                "expected_service_duration_years": 2,
                "quantity_requested": 1,
                "shaft_surface_finish_ra_um": 1.0,
                "shaft_hardness_hrc": 40,
                "machining_method": "hard_turned",
            }
        )
    )

    assert projection.engineering_path == "rwdr"
    assert projection.technical_derivations
    derivation = projection.technical_derivations[0]
    assert derivation.calc_type == "rwdr"
    assert derivation.status == "ok"
    assert derivation.v_surface_m_s and derivation.v_surface_m_s > 0
    assert derivation.pv_value_mpa_m_s and derivation.pv_value_mpa_m_s > 0
    assert derivation.dn_value == 75000
    assert any("ptfe_rwdr.circumferential_speed" in note for note in derivation.notes)
    assert any(
        "Application pattern candidate: hydraulic_gearbox_standard" in note
        for note in derivation.notes
    )
    assert any("shaft_requirements_concern" in note for note in derivation.notes)
    assert any(
        check.calc_id == "rwdr_circumferential_speed" and check.status == "ok"
        for check in projection.cockpit_view.checks
    )
    assert projection.medium_context.status == "recognized"
    assert (
        projection.partner_matching.data_source == "ptfe_rwdr_deterministic_projection"
    )
    assert (
        "manufacturer_capability_data_required"
        in projection.partner_matching.blocking_reasons
    )
    assert (
        "small_quantity_requires_accepts_single_pieces_claim"
        in projection.partner_matching.blocking_reasons
    )


def test_non_ptfe_rwdr_keeps_existing_rwdr_calculation_source() -> None:
    projection = project_case_workspace(
        _workspace_state(
            {
                "engineering_path": "rwdr",
                "sealing_type": "Radialwellendichtring",
                "medium": "Oel",
                "movement_type": "rotary",
                "shaft_diameter_mm": 50,
                "speed_rpm": 1500,
            }
        )
    )

    assert projection.engineering_path == "rwdr"
    assert projection.technical_derivations == []
    assert projection.partner_matching.data_source == "candidate_derived"


def test_non_ptfe_static_workspace_is_not_enriched_as_rwdr() -> None:
    projection = project_case_workspace(
        _workspace_state(
            {
                "engineering_path": "static",
                "sealing_type": "Flachdichtung",
                "medium": "Wasser",
            }
        )
    )

    assert projection.engineering_path == "static"
    assert projection.technical_derivations == []
    assert projection.partner_matching.data_source == "candidate_derived"
