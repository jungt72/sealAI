from app.agent.domain.rwdr import RWDRSelectorInputDTO
from app.agent.domain.rwdr_core import derive_rwdr_core
from app.agent.domain.rwdr_decision import decide_rwdr_output


def test_linear_motion_produces_hard_stop_and_unsuitable_type():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="linear_stroke",
        shaft_diameter_mm=20.0,
        max_speed_rpm=100.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.hard_stop == "hard_stop_linear_motion_not_supported"
    assert output.type_class == "rwdr_not_suitable"
    assert any("Linear motion" in line for line in output.reasoning)


def test_surface_speed_over_limit_produces_hard_stop():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=100.0,
        max_speed_rpm=5000.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.hard_stop == "hard_stop_surface_speed_over_limit"
    assert output.type_class == "rwdr_not_suitable"


def test_water_plus_pressure_escalates_to_engineering_review():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=1200.0,
        pressure_profile="constant_pressure_above_0_5_bar",
        inner_lip_medium_scenario="water_or_aqueous",
        maintenance_mode="new_shaft",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.type_class == "engineering_review_required"
    assert output.review_flags == ["review_water_with_pressure"]
    assert output.hard_stop is None


def test_dry_run_high_speed_escalates_to_engineering_review():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=80.0,
        max_speed_rpm=2600.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="dry_run_or_air",
        maintenance_mode="new_shaft",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.type_class == "engineering_review_required"
    assert "review_dry_run_high_speed" in output.review_flags


def test_heavy_duty_without_width_escalates_to_review_and_modifier():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=1000.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
        external_contamination_class="mud_high_pressure_abrasive",
        available_width_mm=5.0,
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.type_class == "engineering_review_required"
    assert "review_heavy_duty_without_width" in output.review_flags
    assert "additional_exclusion_protection_check" in output.modifiers


def test_uncertainty_review_blocks_standard_release():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=3000.0,
        pressure_profile="unknown",
        inner_lip_medium_scenario="splash_oil",
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

    output = decide_rwdr_output(rwdr_input)

    assert output.type_class == "engineering_review_required"
    assert "review_due_to_uncertainty" in output.review_flags


def test_reversing_rotation_adds_warning_and_modifier():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="reversing_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=1200.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert "reverse_rotation_requires_directionless_profile" in output.modifiers
    assert "reverse_rotation_disallows_directional_helix" in output.warnings


def test_used_shaft_adds_repair_modifier():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=1200.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="used_shaft",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert "repair_sleeve_or_lip_offset_check" in output.modifiers


def test_installation_over_edges_adds_warning_and_modifier():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=1200.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
        installation_over_edges_flag=True,
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert "installation_sleeve_required" in output.modifiers
    assert "installation_path_damage_risk" in output.warnings


def test_simple_standard_case_selects_standard_rwdr():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=35.0,
        max_speed_rpm=1000.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
        external_contamination_class="clean_room_dust",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.type_class == "standard_rwdr"
    assert output.review_flags == []
    assert output.hard_stop is None


def test_outdoor_dust_selects_rwdr_with_dust_lip():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=35.0,
        max_speed_rpm=1000.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
        external_contamination_class="splash_water_or_outdoor_dust",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.type_class == "rwdr_with_dust_lip"


def test_pressure_profile_selects_pressure_profile_rwdr_without_higher_blocker():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=35.0,
        max_speed_rpm=1000.0,
        pressure_profile="constant_pressure_above_0_5_bar",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
        external_contamination_class="clean_room_dust",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.type_class == "pressure_profile_rwdr"


def test_ptfe_path_selects_ptfe_candidate_without_review_blocker():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=35.0,
        max_speed_rpm=1000.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="water_or_aqueous",
        maintenance_mode="new_shaft",
        external_contamination_class="clean_room_dust",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    output = decide_rwdr_output(rwdr_input)

    assert output.type_class == "ptfe_profile_review"
    assert output.review_flags == []


def test_vertical_oil_bath_conflict_escalates_to_review():
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=35.0,
        max_speed_rpm=1000.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
        vertical_shaft_flag=True,
        medium_level_relative_to_seal="above",
        confidence={
            "motion_type": "known",
            "shaft_diameter_mm": "known",
            "max_speed_rpm": "known",
            "maintenance_mode": "known",
            "pressure_profile": "known",
            "external_contamination_class": "known",
            "medium_level_relative_to_seal": "known",
        },
    )

    derived = derive_rwdr_core(rwdr_input)
    output = decide_rwdr_output(rwdr_input, derived=derived)

    assert output.type_class == "engineering_review_required"
    assert "review_vertical_layout_conflict" in output.review_flags
    assert "vertical_layout_requires_level_review" in output.warnings
