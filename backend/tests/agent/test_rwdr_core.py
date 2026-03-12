from app.agent.domain.rwdr import RWDRSelectorInputDTO, build_default_rwdr_selector_config
from app.agent.domain.rwdr_core import (
    calculate_surface_speed,
    classify_contamination,
    derive_rwdr_core,
    evaluate_confidence,
    evaluate_geometry,
    evaluate_installation,
    evaluate_maintenance,
    evaluate_pressure_tribology,
)


def test_surface_speed_calculates_and_classifies_from_config():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=3000.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
    )

    surface_speed_mps, surface_speed_class = calculate_surface_speed(
        rwdr_input,
        build_default_rwdr_selector_config(),
    )

    assert surface_speed_mps == 6.283
    assert surface_speed_class == "medium"


def test_pressure_tribology_flags_water_plus_pressure_review():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=1200.0,
        pressure_profile="constant_pressure_above_0_5_bar",
        inner_lip_medium_scenario="water_or_aqueous",
        maintenance_mode="new_shaft",
    )

    result = evaluate_pressure_tribology(
        rwdr_input,
        surface_speed_class="low",
        config=build_default_rwdr_selector_config(),
    )

    assert result["pressure_profile_required_flag"] is True
    assert result["review_due_to_water_pressure"] is True
    assert result["tribology_risk_level"] == "critical"


def test_pressure_tribology_flags_dry_run_high_speed_review():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=80.0,
        max_speed_rpm=2600.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="dry_run_or_air",
        maintenance_mode="new_shaft",
    )

    result = evaluate_pressure_tribology(
        rwdr_input,
        surface_speed_class="high",
        config=build_default_rwdr_selector_config(),
    )

    assert result["ptfe_candidate_flag"] is True
    assert result["review_due_to_dry_run_high_speed"] is True
    assert result["tribology_risk_level"] == "critical"


def test_geometry_handles_fit_tight_not_fit_and_unknown():
    config = build_default_rwdr_selector_config()

    fit_result = evaluate_geometry(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            available_width_mm=12.0,
        ),
        config,
    )
    tight_result = evaluate_geometry(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            available_width_mm=7.5,
        ),
        config,
    )
    not_fit_result = evaluate_geometry(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            available_width_mm=5.0,
        ),
        config,
    )
    unknown_result = evaluate_geometry(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
        ),
        config,
    )

    assert fit_result["geometry_fit_status"] == "fit"
    assert tight_result["geometry_fit_status"] == "tight"
    assert not_fit_result["geometry_fit_status"] == "not_fit"
    assert not_fit_result["review_due_to_geometry"] is True
    assert unknown_result["geometry_fit_status"] == "unknown"


def test_contamination_maps_clean_and_heavy_scenarios():
    config = build_default_rwdr_selector_config()

    clean_result = classify_contamination(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            external_contamination_class="clean_room_dust",
        ),
        config,
    )
    heavy_result = classify_contamination(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            external_contamination_class="mud_high_pressure_abrasive",
        ),
        config,
    )

    assert clean_result["exclusion_level"] == "none"
    assert heavy_result["exclusion_level"] == "heavy"
    assert heavy_result["heavy_duty_candidate_flag"] is True


def test_maintenance_flags_used_shaft_only():
    used_result = evaluate_maintenance(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="used_shaft",
        )
    )
    new_result = evaluate_maintenance(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
        )
    )

    assert used_result["repair_sleeve_flag"] is True
    assert used_result["lip_offset_check_flag"] is True
    assert new_result["repair_sleeve_flag"] is False


def test_installation_flags_over_edges_as_risk():
    result = evaluate_installation(
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            installation_over_edges_flag=True,
        )
    )

    assert result["installation_sleeve_required_flag"] is True
    assert result["sensitive_profiles_restricted_flag"] is True


def test_confidence_engine_counts_unknowns_and_blocks_auto_release():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=3000.0,
        pressure_profile="unknown",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="used_shaft",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "estimated",
            "maintenance_mode": "known",
            "pressure_profile": "unknown",
            "external_contamination_class": "unknown",
            "medium_level_relative_to_seal": "estimated",
        },
    )

    result = evaluate_confidence(rwdr_input, build_default_rwdr_selector_config())

    assert result["critical_unknown_count"] == 2
    assert result["confidence_score"] == 0.571
    assert result["review_due_to_uncertainty"] is True
    assert result["auto_release_allowed_flag"] is False


def test_derive_rwdr_core_aggregates_required_derived_state():
    derived = derive_rwdr_core(
        RWDRSelectorInputDTO(
            motion_type="reversing_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="light_pressure_upto_0_5_bar",
            inner_lip_medium_scenario="splash_oil",
            maintenance_mode="used_shaft",
            external_contamination_class="splash_water_or_outdoor_dust",
            available_width_mm=8.0,
            installation_over_edges_flag=True,
            confidence={
                "motion_type": "known",
                "shaft_diameter_mm": "known",
                "max_speed_rpm": "known",
                "maintenance_mode": "known",
                "pressure_profile": "known",
                "external_contamination_class": "known",
                "medium_level_relative_to_seal": "estimated",
            },
        )
    )

    assert derived.surface_speed_mps == 6.283
    assert derived.surface_speed_class == "medium"
    assert derived.exclusion_level == "medium"
    assert derived.geometry_fit_status == "tight"
    assert derived.repair_sleeve_flag is True
    assert derived.installation_sleeve_required_flag is True
    assert derived.reverse_rotation_requires_directionless_profile is True
