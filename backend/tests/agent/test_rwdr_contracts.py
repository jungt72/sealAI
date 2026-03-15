from app.agent.agent.state import SealingAIState
from app.agent.case_state import build_default_sealing_requirement_spec
from app.agent.domain.rwdr import (
    RWDRSelectorConfig,
    RWDRSelectorDerivedDTO,
    RWDRSelectorInputDTO,
    RWDRSelectorOutputDTO,
    build_default_rwdr_selector_config,
)
from pydantic import ValidationError


def test_rwdr_input_valid_minimal_stage1_contract():
    payload = RWDRSelectorInputDTO(
        motion_type="single_direction_rotation",
        shaft_diameter_mm=40.0,
        max_speed_rpm=3000.0,
        pressure_profile="light_pressure_upto_0_5_bar",
        inner_lip_medium_scenario="splash_oil",
        maintenance_mode="used_shaft",
        confidence={"pressure_profile": "known", "available_width_mm": "estimated"},
    )

    assert payload.motion_type == "single_direction_rotation"
    assert payload.confidence["pressure_profile"] == "known"


def test_rwdr_input_rejects_missing_required_fields():
    try:
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="light_pressure_upto_0_5_bar",
            maintenance_mode="used_shaft",
        )
    except ValidationError as exc:
        assert "inner_lip_medium_scenario" in str(exc)
    else:
        raise AssertionError("ValidationError expected for missing required RWDR input field")


def test_rwdr_input_rejects_unknown_confidence_field_key():
    try:
        RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=40.0,
            max_speed_rpm=3000.0,
            pressure_profile="light_pressure_upto_0_5_bar",
            inner_lip_medium_scenario="splash_oil",
            maintenance_mode="used_shaft",
            confidence={"unsupported_field": "known"},
        )
    except ValidationError as exc:
        assert "unsupported_field" in str(exc)
    else:
        raise AssertionError("ValidationError expected for unsupported confidence field")


def test_rwdr_output_structure_is_typed_and_extensible():
    output = RWDRSelectorOutputDTO(
        type_class="rwdr_with_dust_lip",
        modifiers=["installation_sleeve_required"],
        warnings=["installation_path_damage_risk"],
        review_flags=["review_due_to_geometry"],
        hard_stop=None,
        reasoning=["External contamination requires an exclusion upgrade."],
    )

    assert output.type_class == "rwdr_with_dust_lip"
    assert output.modifiers == ["installation_sleeve_required"]


def test_rwdr_config_backbone_defaults_are_available():
    config = build_default_rwdr_selector_config()

    assert config.config_version == "rwdr_selector_v1_1"
    assert config.surface_speed_limits["standard_rwdr"].max_mps == 12.0
    assert config.surface_speed_classification.reference_type_class == "standard_rwdr"
    assert config.surface_speed_classification.medium_ratio == 0.66
    assert config.pressure_limits["pressure_profile_rwdr"].max_bar == 10.0
    assert config.geometry_min_widths["heavy_duty_or_cassette_review"].min_width_mm == 12.0
    assert config.uncertainty.required_known_fields == (
        "motion_type",
        "shaft_diameter_mm",
        "max_speed_rpm",
        "maintenance_mode",
    )
    assert config.uncertainty.review_fields == (
        "pressure_profile",
        "external_contamination_class",
        "medium_level_relative_to_seal",
    )
    assert config.uncertainty.max_critical_unknowns_for_auto_release == 1
    assert config.uncertainty.min_confidence_score_for_auto_release == 0.75
    assert config.uncertainty.estimated_weight == 0.5
    assert config.uncertainty.conservative_review_type_class == "engineering_review_required"
    assert config.contamination["mud_high_pressure_abrasive"].heavy_duty_candidate is True
    assert config.review_triggers.water_with_pressure_requires_review is True
    assert config.review_triggers.heavy_duty_without_width_requires_review is True


def test_rwdr_config_schema_rejects_missing_review_triggers():
    defaults = build_default_rwdr_selector_config().model_dump()
    defaults.pop("review_triggers")

    try:
        RWDRSelectorConfig.model_validate(defaults)
    except ValidationError as exc:
        assert "review_triggers" in str(exc)
    else:
        raise AssertionError("ValidationError expected when review_triggers are missing")


def test_rwdr_state_can_hold_optional_contracts_without_breaking_layers():
    config = build_default_rwdr_selector_config()
    state: SealingAIState = {
        "observed": {"observed_inputs": [], "raw_parameters": {}},
        "normalized": {"identity_records": {}, "normalized_parameters": {}},
        "asserted": {
            "medium_profile": {},
            "machine_profile": {},
            "installation_profile": {},
            "operating_conditions": {},
            "sealing_requirement_spec": build_default_sealing_requirement_spec(
                analysis_cycle_id="cycle-1",
                state_revision=1,
            ),
        },
        "governance": {
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "scope_of_validity": [],
            "assumptions_active": [],
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        },
        "cycle": {
            "analysis_cycle_id": "cycle-1",
            "snapshot_parent_revision": 0,
            "superseded_by_cycle": None,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
            "state_revision": 1,
        },
        "selection": {
            "selection_status": "not_started",
            "candidates": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "winner_candidate_id": None,
            "recommendation_artifact": None,
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
        },
        "rwdr": {
            "input": RWDRSelectorInputDTO(
                motion_type="single_direction_rotation",
                shaft_diameter_mm=40.0,
                max_speed_rpm=3000.0,
                pressure_profile="light_pressure_upto_0_5_bar",
                inner_lip_medium_scenario="splash_oil",
                maintenance_mode="used_shaft",
            ),
            "derived": RWDRSelectorDerivedDTO(
                surface_speed_mps=6.28,
                surface_speed_class="medium",
                tribology_risk_level="medium",
                pressure_risk_level="medium",
                exclusion_level="medium",
                geometry_fit_status="fit",
                confidence_score=0.8,
                critical_unknown_count=0,
            ),
            "output": RWDRSelectorOutputDTO(
                type_class="rwdr_with_dust_lip",
                modifiers=["installation_sleeve_required"],
                warnings=[],
                review_flags=[],
                hard_stop=None,
                reasoning=["Typed RWDR contract can be attached to sealing_state."],
            ),
            "config": config,
            "config_version": config.config_version,
        },
    }

    assert state["cycle"]["state_revision"] == 1
    assert state["rwdr"]["derived"].surface_speed_class == "medium"
    assert state["rwdr"]["config"].review_triggers.cumulative_uncertainty_requires_review is True
