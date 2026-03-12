from pathlib import Path

from app.agent.agent.rwdr_orchestration import (
    evaluate_rwdr_flow,
    merge_rwdr_patch,
    required_stage_2_fields,
    run_rwdr_orchestration,
)
from app.agent.agent.rwdr_patch_parser import parse_rwdr_patch_for_field
from app.agent.agent.sync import sync_working_profile_to_state
from app.agent.cli import create_initial_state
from app.agent.domain.rwdr import RWDRSelectorInputDTO, RWDRSelectorInputPatchDTO


def test_stage_1_incomplete_reports_missing_fields_and_skips_decision():
    sealing_state = create_initial_state()
    sealing_state["rwdr"] = {
        "flow": {
            "active": True,
            "collected_fields": {
                "motion_type": "single_direction_rotation",
                "shaft_diameter_mm": 40.0,
            },
        }
    }

    rwdr_state = evaluate_rwdr_flow(sealing_state)

    assert rwdr_state["flow"]["stage"] == "stage_1"
    assert rwdr_state["flow"]["ready_for_decision"] is False
    assert "max_speed_rpm" in rwdr_state["flow"]["missing_fields"]
    assert "output" not in rwdr_state


def test_stage_2_requires_width_for_heavy_contamination_and_medium_level_for_vertical_oil_bath():
    heavy_fields = required_stage_2_fields(
        {
            "motion_type": "single_direction_rotation",
            "inner_lip_medium_scenario": "oil_bath",
            "external_contamination_class": "mud_high_pressure_abrasive",
            "vertical_shaft_flag": True,
        }
    )
    light_fields = required_stage_2_fields(
        {
            "motion_type": "single_direction_rotation",
            "inner_lip_medium_scenario": "grease",
            "external_contamination_class": "clean_room_dust",
            "vertical_shaft_flag": False,
        }
    )

    assert "available_width_mm" in heavy_fields
    assert "medium_level_relative_to_seal" in heavy_fields
    assert "installation_over_edges_flag" in heavy_fields
    assert "available_width_mm" not in light_fields
    assert "medium_level_relative_to_seal" not in light_fields


def test_complete_rwdr_flow_executes_core_and_decision_and_stores_output():
    sealing_state = create_initial_state()
    rwdr_input = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=35.0,
        max_speed_rpm=1000.0,
        pressure_profile="pressureless_vented",
        inner_lip_medium_scenario="oil_bath",
        maintenance_mode="new_shaft",
        external_contamination_class="clean_room_dust",
        installation_over_edges_flag=False,
        vertical_shaft_flag=False,
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
    sealing_state["rwdr"] = {
        "flow": {"active": True, "collected_fields": rwdr_input.model_dump(exclude_none=True)},
        "input": rwdr_input,
    }

    new_sealing_state, reply = run_rwdr_orchestration(sealing_state)
    rwdr_state = new_sealing_state["rwdr"]

    assert rwdr_state["flow"]["stage"] == "stage_3"
    assert rwdr_state["flow"]["decision_executed"] is True
    assert rwdr_state["derived"].surface_speed_class == "low"
    assert rwdr_state["output"].type_class == "standard_rwdr"
    assert "RWDR preselection ready" in reply.content


def test_hard_stop_and_review_are_structurally_propagated():
    hard_stop_state = create_initial_state()
    hard_stop_state["rwdr"] = {
        "flow": {
            "active": True,
            "collected_fields": {
                "motion_type": "linear_stroke",
                "shaft_diameter_mm": 20.0,
                "max_speed_rpm": 100.0,
                "pressure_profile": "pressureless_vented",
                "inner_lip_medium_scenario": "oil_bath",
                "maintenance_mode": "new_shaft",
            },
        }
    }
    review_state = create_initial_state()
    review_state["rwdr"] = {
        "flow": {
            "active": True,
            "collected_fields": {
                "motion_type": "single_direction_rotation",
                "shaft_diameter_mm": 40.0,
                "max_speed_rpm": 1200.0,
                "pressure_profile": "constant_pressure_above_0_5_bar",
                "inner_lip_medium_scenario": "water_or_aqueous",
                "maintenance_mode": "new_shaft",
                "external_contamination_class": "clean_room_dust",
                "installation_over_edges_flag": False,
                "confidence": {
                    "motion_type": "known",
                    "shaft_diameter_mm": "known",
                    "max_speed_rpm": "known",
                    "maintenance_mode": "known",
                    "pressure_profile": "known",
                    "external_contamination_class": "known",
                    "medium_level_relative_to_seal": "known",
                },
            },
        }
    }

    hard_stop_result, _ = run_rwdr_orchestration(hard_stop_state)
    review_result, _ = run_rwdr_orchestration(review_state)

    assert hard_stop_result["rwdr"]["output"].hard_stop == "hard_stop_linear_motion_not_supported"
    assert review_result["rwdr"]["output"].type_class == "engineering_review_required"
    assert "review_water_with_pressure" in review_result["rwdr"]["output"].review_flags


def test_sync_projects_rwdr_read_model_without_domain_logic():
    state = {
        "working_profile": {},
        "sealing_state": create_initial_state(),
    }
    state["sealing_state"]["rwdr"] = {
        "flow": {
            "active": True,
            "stage": "stage_2",
            "missing_fields": ["available_width_mm"],
            "ready_for_decision": False,
            "decision_executed": False,
        }
    }

    updated_state = sync_working_profile_to_state(state)

    assert updated_state["working_profile"]["rwdr"]["stage"] == "stage_2"
    assert updated_state["working_profile"]["rwdr"]["missing_fields"] == ["available_width_mm"]


def test_sync_handles_empty_rwdr_state_without_crashing_or_leaving_stale_projection():
    state = {
        "working_profile": {"rwdr": {"stage": "stage_2"}},
        "sealing_state": create_initial_state(),
    }

    updated_state = sync_working_profile_to_state(state)

    assert "rwdr" not in updated_state["working_profile"]


def test_sync_projects_partial_rwdr_state_without_output_or_draft():
    state = {
        "working_profile": {},
        "sealing_state": create_initial_state(),
    }
    state["sealing_state"]["rwdr"] = {
        "flow": {
            "active": True,
            "stage": "stage_1",
            "missing_fields": ["max_speed_rpm"],
            "next_field": "max_speed_rpm",
        }
    }

    updated_state = sync_working_profile_to_state(state)

    assert updated_state["working_profile"]["rwdr"]["stage"] == "stage_1"
    assert updated_state["working_profile"]["rwdr"]["draft"] is None
    assert updated_state["working_profile"]["rwdr"]["output"] is None


def test_partial_stage_1_accumulates_across_turns_and_reduces_missing_fields():
    sealing_state = create_initial_state()

    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
        ),
    )
    first_state = evaluate_rwdr_flow(sealing_state)
    first_missing_fields = list(first_state["flow"]["missing_fields"])

    assert first_state["flow"]["stage"] == "stage_1"
    assert "max_speed_rpm" in first_state["flow"]["missing_fields"]

    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            max_speed_rpm=3000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
        ),
    )
    second_state = evaluate_rwdr_flow(sealing_state)

    assert second_state["flow"]["stage"] == "stage_2"
    assert len(second_state["flow"]["missing_fields"]) < len(first_missing_fields)


def test_partial_stage_2_accumulates_width_after_heavy_contamination_trigger():
    sealing_state = create_initial_state()
    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=1000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            external_contamination_class="mud_high_pressure_abrasive",
            installation_over_edges_flag=False,
            vertical_shaft_flag=False,
            confidence={
                "motion_type": "known",
                "shaft_diameter_mm": "known",
                "max_speed_rpm": "known",
                "maintenance_mode": "known",
                "pressure_profile": "known",
                "external_contamination_class": "known",
                "medium_level_relative_to_seal": "known",
            },
        ),
    )

    pending_state = evaluate_rwdr_flow(sealing_state)
    assert pending_state["flow"]["stage"] == "stage_2"
    assert pending_state["flow"]["missing_fields"] == ["available_width_mm"]

    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            available_width_mm=14.0,
        ),
    )
    ready_state = evaluate_rwdr_flow(sealing_state)

    assert ready_state["flow"]["stage"] == "stage_3"
    assert ready_state["output"].type_class == "heavy_duty_or_cassette_review"


def test_confidence_merge_preserves_existing_entries_and_updates_fieldwise():
    sealing_state = create_initial_state()
    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            motion_type="single_direction_rotation",
            confidence={"motion_type": "known", "pressure_profile": "estimated"},
        ),
    )
    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            pressure_profile="pressureless_vented",
            confidence={"pressure_profile": "known", "max_speed_rpm": "estimated"},
        ),
    )

    rwdr_state = sealing_state["rwdr"]

    assert rwdr_state["draft"].confidence["motion_type"] == "known"
    assert rwdr_state["draft"].confidence["pressure_profile"] == "known"
    assert rwdr_state["draft"].confidence["max_speed_rpm"] == "estimated"


def test_repeated_patch_only_overwrites_explicitly_set_fields():
    sealing_state = create_initial_state()
    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            motion_type="single_direction_rotation",
            max_speed_rpm=1800.0,
            confidence={"motion_type": "known", "max_speed_rpm": "known"},
        ),
    )

    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            maintenance_mode="new_shaft",
            confidence={"maintenance_mode": "known"},
        ),
    )

    draft = sealing_state["rwdr"]["draft"]

    assert draft.motion_type == "single_direction_rotation"
    assert draft.max_speed_rpm == 1800.0
    assert draft.maintenance_mode == "new_shaft"
    assert draft.confidence["motion_type"] == "known"
    assert draft.confidence["max_speed_rpm"] == "known"
    assert draft.confidence["maintenance_mode"] == "known"


def test_re_evaluation_recomputes_output_after_relevant_patch():
    sealing_state = create_initial_state()
    merge_rwdr_patch(
        sealing_state,
        rwdr_input=RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=35.0,
            max_speed_rpm=1000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            external_contamination_class="clean_room_dust",
            installation_over_edges_flag=False,
            vertical_shaft_flag=False,
            confidence={
                "motion_type": "known",
                "shaft_diameter_mm": "known",
                "max_speed_rpm": "known",
                "maintenance_mode": "known",
                "pressure_profile": "known",
                "external_contamination_class": "known",
                "medium_level_relative_to_seal": "known",
            },
        ),
    )
    baseline_state = evaluate_rwdr_flow(sealing_state)
    assert baseline_state["output"].type_class == "standard_rwdr"

    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            external_contamination_class="splash_water_or_outdoor_dust",
            confidence={"external_contamination_class": "known"},
        ),
    )
    reevaluated_state = evaluate_rwdr_flow(sealing_state)

    assert reevaluated_state["output"].type_class == "rwdr_with_dust_lip"
    assert reevaluated_state["flow"]["decision_executed"] is True


def test_controlled_field_intake_parses_max_speed_from_simple_answer():
    patch = parse_rwdr_patch_for_field("max_speed_rpm", "3000 U/min")

    assert patch is not None
    assert patch.max_speed_rpm == 3000.0
    assert patch.confidence["max_speed_rpm"] == "known"


def test_controlled_field_intake_parses_maintenance_mode_from_simple_answer():
    patch = parse_rwdr_patch_for_field("maintenance_mode", "gebrauchte Welle")

    assert patch is not None
    assert patch.maintenance_mode == "used_shaft"
    assert patch.confidence["maintenance_mode"] == "known"


def test_controlled_field_intake_rejects_unknown_answer():
    patch = parse_rwdr_patch_for_field("max_speed_rpm", "weiss nicht")

    assert patch is None


def test_run_rwdr_orchestration_accepts_simple_patch_and_advances_stage():
    sealing_state = create_initial_state()
    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
        ),
    )
    pending_state = evaluate_rwdr_flow(sealing_state)

    assert pending_state["flow"]["next_field"] == "max_speed_rpm"

    advanced_state, reply = run_rwdr_orchestration(sealing_state, latest_user_message="3000 U/min")

    assert advanced_state["rwdr"]["draft"].max_speed_rpm == 3000.0
    assert advanced_state["rwdr"]["flow"]["stage"] == "stage_2"
    assert "RWDR field accepted: max_speed_rpm" in reply.content


def test_run_rwdr_orchestration_keeps_field_open_when_answer_is_unclear():
    sealing_state = create_initial_state()
    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
        ),
    )
    pending_state = evaluate_rwdr_flow(sealing_state)
    assert pending_state["flow"]["next_field"] == "max_speed_rpm"

    advanced_state, reply = run_rwdr_orchestration(sealing_state, latest_user_message="weiss nicht")

    assert "max_speed_rpm" in advanced_state["rwdr"]["flow"]["missing_fields"]
    assert advanced_state["rwdr"]["draft"].max_speed_rpm is None
    assert "could not be safely structured" in reply.content


def test_final_transition_runs_existing_core_decision_after_last_patch():
    sealing_state = create_initial_state()
    merge_rwdr_patch(
        sealing_state,
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=35.0,
            max_speed_rpm=1000.0,
            pressure_profile="pressureless_vented",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            external_contamination_class="clean_room_dust",
            vertical_shaft_flag=False,
            confidence={
                "motion_type": "known",
                "shaft_diameter_mm": "known",
                "max_speed_rpm": "known",
                "maintenance_mode": "known",
                "pressure_profile": "known",
                "external_contamination_class": "known",
                "medium_level_relative_to_seal": "known",
            },
        ),
    )
    pending_state = evaluate_rwdr_flow(sealing_state)
    assert pending_state["flow"]["next_field"] == "installation_over_edges_flag"

    final_state, reply = run_rwdr_orchestration(sealing_state, latest_user_message="nein")

    assert final_state["rwdr"]["flow"]["stage"] == "stage_3"
    assert final_state["rwdr"]["output"].type_class == "standard_rwdr"
    assert "RWDR preselection ready" in reply.content


def test_sync_projects_stage_3_review_and_hard_stop_outputs():
    review_state = {"working_profile": {}, "sealing_state": create_initial_state()}
    review_state["sealing_state"]["rwdr"] = {
        "flow": {
            "active": True,
            "stage": "stage_3",
            "missing_fields": [],
            "ready_for_decision": True,
            "decision_executed": True,
        },
        "output": {
            "type_class": "engineering_review_required",
            "review_flags": ["review_water_with_pressure"],
            "warnings": [],
            "modifiers": [],
            "hard_stop": None,
            "reasoning": ["Review path."],
        },
    }
    hard_stop_state = {"working_profile": {}, "sealing_state": create_initial_state()}
    hard_stop_state["sealing_state"]["rwdr"] = {
        "flow": {
            "active": True,
            "stage": "stage_3",
            "missing_fields": [],
            "ready_for_decision": True,
            "decision_executed": True,
        },
        "output": {
            "type_class": "rwdr_not_suitable",
            "review_flags": [],
            "warnings": [],
            "modifiers": [],
            "hard_stop": "hard_stop_linear_motion_not_supported",
            "reasoning": ["Hard stop path."],
        },
    }

    synced_review = sync_working_profile_to_state(review_state)
    synced_hard_stop = sync_working_profile_to_state(hard_stop_state)

    assert synced_review["working_profile"]["rwdr"]["output"]["type_class"] == "engineering_review_required"
    assert synced_review["working_profile"]["rwdr"]["output"]["review_flags"] == ["review_water_with_pressure"]
    assert synced_hard_stop["working_profile"]["rwdr"]["output"]["hard_stop"] == "hard_stop_linear_motion_not_supported"


def test_rwdr_runtime_documentation_exists():
    doc_path = Path("/home/thorsten/sealai/konzept/rwdr_selector_runtime_implementation.md")

    assert doc_path.exists()
