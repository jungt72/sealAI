from __future__ import annotations

import math

from app.agent.domain.rwdr import (
    RWDRSelectorConfig,
    RWDRSelectorDerivedDTO,
    RWDRSelectorInputDTO,
    build_default_rwdr_selector_config,
)


def calculate_surface_speed(
    rwdr_input: RWDRSelectorInputDTO,
    config: RWDRSelectorConfig,
) -> tuple[float, str]:
    surface_speed_mps = (math.pi * rwdr_input.shaft_diameter_mm * rwdr_input.max_speed_rpm) / 60000.0
    classification = config.surface_speed_classification
    max_speed = config.surface_speed_limits[classification.reference_type_class].max_mps
    low_limit = max_speed * classification.low_ratio
    medium_limit = max_speed * classification.medium_ratio

    if surface_speed_mps > max_speed:
        surface_speed_class = "over_limit"
    elif surface_speed_mps > medium_limit:
        surface_speed_class = "high"
    elif surface_speed_mps > low_limit:
        surface_speed_class = "medium"
    else:
        surface_speed_class = "low"

    return round(surface_speed_mps, 3), surface_speed_class


def evaluate_pressure_tribology(
    rwdr_input: RWDRSelectorInputDTO,
    surface_speed_class: str,
    config: RWDRSelectorConfig,
) -> dict[str, bool | str]:
    pressure_risk_level = "low"
    tribology_risk_level = "low"
    review_due_to_water_pressure = False
    review_due_to_dry_run_high_speed = False
    ptfe_candidate_flag = False
    pressure_profile_required_flag = False
    reverse_rotation_requires_directionless_profile = rwdr_input.motion_type == "reversing_rotation"

    standard_pressure_limit = config.pressure_limits["standard_rwdr"].max_bar
    pressure_profile = rwdr_input.pressure_profile

    if pressure_profile in {"constant_pressure_above_0_5_bar", "pulsating_pressure"}:
        pressure_profile_required_flag = True
        pressure_risk_level = "high" if pressure_profile == "constant_pressure_above_0_5_bar" else "critical"
    elif pressure_profile == "vacuum":
        pressure_risk_level = "medium"
    elif pressure_profile == "unknown":
        pressure_risk_level = "unknown"
    elif standard_pressure_limit > 0 and pressure_profile == "light_pressure_upto_0_5_bar":
        pressure_risk_level = "medium"

    if rwdr_input.inner_lip_medium_scenario == "water_or_aqueous":
        tribology_risk_level = "high"
        ptfe_candidate_flag = True
        if pressure_profile in {"constant_pressure_above_0_5_bar", "pulsating_pressure"}:
            review_due_to_water_pressure = config.review_triggers.water_with_pressure_requires_review
            tribology_risk_level = "critical"
    elif rwdr_input.inner_lip_medium_scenario == "dry_run_or_air":
        tribology_risk_level = "high"
        ptfe_candidate_flag = True
        if surface_speed_class in {"high", "over_limit"}:
            review_due_to_dry_run_high_speed = config.review_triggers.dry_run_high_speed_requires_review
            tribology_risk_level = "critical"
    elif rwdr_input.inner_lip_medium_scenario == "grease":
        tribology_risk_level = "medium"

    return {
        "tribology_risk_level": tribology_risk_level,
        "pressure_risk_level": pressure_risk_level,
        "ptfe_candidate_flag": ptfe_candidate_flag,
        "pressure_profile_required_flag": pressure_profile_required_flag,
        "review_due_to_water_pressure": review_due_to_water_pressure,
        "review_due_to_dry_run_high_speed": review_due_to_dry_run_high_speed,
        "reverse_rotation_requires_directionless_profile": reverse_rotation_requires_directionless_profile,
    }


def evaluate_geometry(
    rwdr_input: RWDRSelectorInputDTO,
    config: RWDRSelectorConfig,
) -> dict[str, bool | str]:
    if rwdr_input.available_width_mm is None:
        return {"geometry_fit_status": "unknown", "review_due_to_geometry": False}

    width = rwdr_input.available_width_mm
    standard_width = config.geometry_min_widths["standard_rwdr"].min_width_mm
    heavy_width = config.geometry_min_widths["heavy_duty_or_cassette_review"].min_width_mm

    if width >= heavy_width:
        return {"geometry_fit_status": "fit", "review_due_to_geometry": False}
    if width >= standard_width:
        return {"geometry_fit_status": "tight", "review_due_to_geometry": False}
    return {"geometry_fit_status": "not_fit", "review_due_to_geometry": True}


def classify_contamination(
    rwdr_input: RWDRSelectorInputDTO,
    config: RWDRSelectorConfig,
) -> dict[str, bool | str]:
    contamination_class = rwdr_input.external_contamination_class or "unknown"
    contamination = config.contamination[contamination_class]
    return {
        "exclusion_level": contamination.exclusion_level,
        "dust_lip_required_flag": contamination.dust_lip_required,
        "heavy_duty_candidate_flag": contamination.heavy_duty_candidate,
        "additional_exclusion_required_flag": contamination.additional_exclusion_required,
    }


def evaluate_maintenance(rwdr_input: RWDRSelectorInputDTO) -> dict[str, bool]:
    used_shaft = rwdr_input.maintenance_mode == "used_shaft"
    return {
        "repair_sleeve_flag": used_shaft,
        "lip_offset_check_flag": used_shaft,
    }


def evaluate_installation(rwdr_input: RWDRSelectorInputDTO) -> dict[str, bool]:
    over_edges = rwdr_input.installation_over_edges_flag is True
    return {
        "installation_sleeve_required_flag": over_edges,
        "sensitive_profiles_restricted_flag": over_edges,
    }


def evaluate_confidence(
    rwdr_input: RWDRSelectorInputDTO,
    config: RWDRSelectorConfig,
) -> dict[str, bool | float | int]:
    rules = config.uncertainty
    relevant_fields = tuple(dict.fromkeys((*rules.required_known_fields, *rules.review_fields)))
    status_to_weight = {
        "known": rules.known_weight,
        "estimated": rules.estimated_weight,
        "unknown": rules.unknown_weight,
    }

    scores: list[float] = []
    critical_unknown_count = 0
    estimated_critical_count = 0

    for field_name in relevant_fields:
        status = rwdr_input.confidence.get(field_name, "unknown")
        scores.append(status_to_weight[status])
        if status == "unknown":
            critical_unknown_count += 1
        elif status == "estimated":
            estimated_critical_count += 1

    confidence_score = round(sum(scores) / len(scores), 3) if scores else 1.0
    review_due_to_uncertainty = (
        critical_unknown_count > rules.max_critical_unknowns_for_auto_release
        or estimated_critical_count > rules.max_estimated_critical_fields_for_auto_release
        or confidence_score < rules.min_confidence_score_for_auto_release
    )
    auto_release_allowed_flag = not review_due_to_uncertainty

    return {
        "confidence_score": confidence_score,
        "critical_unknown_count": critical_unknown_count,
        "review_due_to_uncertainty": review_due_to_uncertainty,
        "auto_release_allowed_flag": auto_release_allowed_flag,
    }


def derive_rwdr_core(
    rwdr_input: RWDRSelectorInputDTO,
    config: RWDRSelectorConfig | None = None,
) -> RWDRSelectorDerivedDTO:
    active_config = config or build_default_rwdr_selector_config()
    surface_speed_mps, surface_speed_class = calculate_surface_speed(rwdr_input, active_config)
    derived_payload: dict[str, object] = {
        "surface_speed_mps": surface_speed_mps,
        "surface_speed_class": surface_speed_class,
    }
    derived_payload.update(evaluate_pressure_tribology(rwdr_input, surface_speed_class, active_config))
    derived_payload.update(evaluate_geometry(rwdr_input, active_config))
    derived_payload.update(classify_contamination(rwdr_input, active_config))
    derived_payload.update(evaluate_maintenance(rwdr_input))
    derived_payload.update(evaluate_installation(rwdr_input))
    derived_payload.update(evaluate_confidence(rwdr_input, active_config))
    return RWDRSelectorDerivedDTO.model_validate(derived_payload)
