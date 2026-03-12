from __future__ import annotations

from app.agent.domain.rwdr import (
    RWDRSelectorConfig,
    RWDRSelectorDerivedDTO,
    RWDRSelectorInputDTO,
    RWDRSelectorOutputDTO,
    build_default_rwdr_selector_config,
)
from app.agent.domain.rwdr_core import derive_rwdr_core


def _has_vertical_medium_conflict(
    rwdr_input: RWDRSelectorInputDTO,
    config: RWDRSelectorConfig,
) -> bool:
    return (
        config.review_triggers.vertical_above_medium_oil_bath_conflict_requires_review
        and rwdr_input.vertical_shaft_flag is True
        and rwdr_input.medium_level_relative_to_seal == "above"
        and rwdr_input.inner_lip_medium_scenario == "oil_bath"
    )


def _build_modifiers(
    rwdr_input: RWDRSelectorInputDTO,
    derived: RWDRSelectorDerivedDTO,
) -> list[str]:
    modifiers: list[str] = []
    if derived.repair_sleeve_flag or derived.lip_offset_check_flag:
        modifiers.append("repair_sleeve_or_lip_offset_check")
    if derived.installation_sleeve_required_flag:
        modifiers.append("installation_sleeve_required")
    if derived.reverse_rotation_requires_directionless_profile:
        modifiers.append("reverse_rotation_requires_directionless_profile")
    if derived.additional_exclusion_required_flag and derived.geometry_fit_status == "not_fit":
        modifiers.append("additional_exclusion_protection_check")
    elif derived.additional_exclusion_required_flag and rwdr_input.external_contamination_class == "unknown":
        modifiers.append("additional_exclusion_protection_check")
    return modifiers


def _build_warnings(
    rwdr_input: RWDRSelectorInputDTO,
    derived: RWDRSelectorDerivedDTO,
    vertical_conflict: bool,
) -> list[str]:
    warnings: list[str] = []
    if derived.reverse_rotation_requires_directionless_profile:
        warnings.append("reverse_rotation_disallows_directional_helix")
    if derived.installation_sleeve_required_flag:
        warnings.append("installation_path_damage_risk")
    if vertical_conflict or rwdr_input.vertical_shaft_flag is True:
        warnings.append("vertical_layout_requires_level_review")
    return warnings


def _build_review_flags(
    derived: RWDRSelectorDerivedDTO,
    vertical_conflict: bool,
) -> list[str]:
    review_flags: list[str] = []
    if derived.review_due_to_water_pressure:
        review_flags.append("review_water_with_pressure")
    if derived.review_due_to_dry_run_high_speed:
        review_flags.append("review_dry_run_high_speed")
    if derived.heavy_duty_candidate_flag and derived.geometry_fit_status == "not_fit":
        review_flags.append("review_heavy_duty_without_width")
    if derived.review_due_to_uncertainty:
        review_flags.append("review_due_to_uncertainty")
    if derived.review_due_to_geometry:
        review_flags.append("review_due_to_geometry")
    if vertical_conflict:
        review_flags.append("review_vertical_layout_conflict")
    return review_flags


def _build_hard_stop(
    rwdr_input: RWDRSelectorInputDTO,
    derived: RWDRSelectorDerivedDTO,
) -> str | None:
    if rwdr_input.motion_type == "linear_stroke":
        return "hard_stop_linear_motion_not_supported"
    if derived.surface_speed_class == "over_limit":
        return "hard_stop_surface_speed_over_limit"
    return None


def _decide_type_class(
    derived: RWDRSelectorDerivedDTO,
    review_flags: list[str],
    hard_stop: str | None,
    config: RWDRSelectorConfig,
) -> str:
    if hard_stop is not None:
        return "rwdr_not_suitable"
    if review_flags:
        return config.uncertainty.conservative_review_type_class
    if derived.heavy_duty_candidate_flag and derived.geometry_fit_status in {"fit", "tight"}:
        return "heavy_duty_or_cassette_review"
    if derived.ptfe_candidate_flag:
        return "ptfe_profile_review"
    if derived.pressure_profile_required_flag:
        return "pressure_profile_rwdr"
    if derived.dust_lip_required_flag:
        return "rwdr_with_dust_lip"
    return "standard_rwdr"


def _build_reasoning(
    rwdr_input: RWDRSelectorInputDTO,
    derived: RWDRSelectorDerivedDTO,
    type_class: str,
    hard_stop: str | None,
    review_flags: list[str],
) -> list[str]:
    reasoning: list[str] = []

    if hard_stop == "hard_stop_linear_motion_not_supported":
        reasoning.append("Linear motion is outside the admissible RWDR operating principle.")
    elif hard_stop == "hard_stop_surface_speed_over_limit":
        reasoning.append("Calculated surface speed exceeds the configured admissible RWDR contact limit.")

    if "review_water_with_pressure" in review_flags:
        reasoning.append("Water or aqueous medium combined with pressure requires deterministic engineering review.")
    if "review_dry_run_high_speed" in review_flags:
        reasoning.append("Dry-run operation combined with high surface speed is escalated to review.")
    if "review_heavy_duty_without_width" in review_flags:
        reasoning.append("Heavy-duty exclusion demand is present but available width is below the configured minimum.")
    if "review_due_to_uncertainty" in review_flags:
        reasoning.append("Confidence thresholds block automatic release because critical unknowns remain active.")
    if "review_vertical_layout_conflict" in review_flags:
        reasoning.append("Vertical shaft with seal above medium level conflicts with a persistent oil-bath assumption.")

    if type_class == "standard_rwdr":
        reasoning.append("Oil or grease lubrication, low pressure burden and clean external conditions allow a standard RWDR preselection.")
    elif type_class == "rwdr_with_dust_lip":
        reasoning.append("External contamination requires an exclusion upgrade to a dust-lip profile.")
    elif type_class == "pressure_profile_rwdr":
        reasoning.append("Pressure profile exceeds the standard RWDR envelope and requires a pressure-capable profile.")
    elif type_class == "heavy_duty_or_cassette_review":
        reasoning.append("Heavy external contamination justifies a heavy-duty or cassette-oriented preselection.")
    elif type_class == "ptfe_profile_review":
        reasoning.append("Tribology signals indicate a PTFE-oriented profile should be considered before standard elastomer designs.")
    elif type_class == "engineering_review_required" and not review_flags:
        reasoning.append("Conservative review fallback remains active under the current rule configuration.")

    if derived.repair_sleeve_flag and rwdr_input.maintenance_mode == "used_shaft":
        reasoning.append("Used shaft maintenance activates repair sleeve or lip offset preparation.")
    if derived.installation_sleeve_required_flag:
        reasoning.append("Installation over edges or threads requires a protective installation sleeve.")
    if derived.reverse_rotation_requires_directionless_profile:
        reasoning.append("Reversing rotation blocks directional helix concepts and requires a directionless design.")

    return reasoning


def decide_rwdr_output(
    rwdr_input: RWDRSelectorInputDTO,
    derived: RWDRSelectorDerivedDTO | None = None,
    config: RWDRSelectorConfig | None = None,
) -> RWDRSelectorOutputDTO:
    active_config = config or build_default_rwdr_selector_config()
    active_derived = derived or derive_rwdr_core(rwdr_input, active_config)
    vertical_conflict = _has_vertical_medium_conflict(rwdr_input, active_config)
    hard_stop = _build_hard_stop(rwdr_input, active_derived)
    review_flags = _build_review_flags(active_derived, vertical_conflict)
    modifiers = _build_modifiers(rwdr_input, active_derived)
    warnings = _build_warnings(rwdr_input, active_derived, vertical_conflict)
    type_class = _decide_type_class(active_derived, review_flags, hard_stop, active_config)
    reasoning = _build_reasoning(rwdr_input, active_derived, type_class, hard_stop, review_flags)

    return RWDRSelectorOutputDTO(
        type_class=type_class,
        modifiers=modifiers,
        warnings=warnings,
        review_flags=review_flags,
        hard_stop=hard_stop,
        reasoning=reasoning,
    )
