from __future__ import annotations

from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

RWDRConfidenceStatus = Literal["known", "estimated", "unknown"]
RWDRConfidenceField = Literal[
    "motion_type",
    "shaft_diameter_mm",
    "max_speed_rpm",
    "pressure_profile",
    "inner_lip_medium_scenario",
    "maintenance_mode",
    "external_contamination_class",
    "available_width_mm",
    "installation_over_edges_flag",
    "vertical_shaft_flag",
    "medium_level_relative_to_seal",
]
RWDRMotionType = Literal[
    "single_direction_rotation",
    "reversing_rotation",
    "small_angle_oscillation",
    "linear_stroke",
]
RWDRPressureProfile = Literal[
    "pressureless_vented",
    "light_pressure_upto_0_5_bar",
    "constant_pressure_above_0_5_bar",
    "pulsating_pressure",
    "vacuum",
    "unknown",
]
RWDRInnerLipMediumScenario = Literal[
    "oil_bath",
    "splash_oil",
    "grease",
    "water_or_aqueous",
    "dry_run_or_air",
]
RWDRMaintenanceMode = Literal["new_shaft", "used_shaft"]
RWDRExternalContaminationClass = Literal[
    "clean_room_dust",
    "splash_water_or_outdoor_dust",
    "mud_high_pressure_abrasive",
    "unknown",
]
RWDRMediumLevelRelativeToSeal = Literal["above", "below", "at_level", "unknown"]
RWDRSurfaceSpeedClass = Literal["low", "medium", "high", "over_limit", "unknown"]
RWDRRiskLevel = Literal["low", "medium", "high", "critical", "unknown"]
RWDRExclusionLevel = Literal["none", "light", "medium", "heavy", "unknown"]
RWDRGeometryFitStatus = Literal["fit", "tight", "not_fit", "unknown"]
RWDRTypeClass = Literal[
    "standard_rwdr",
    "rwdr_with_dust_lip",
    "pressure_profile_rwdr",
    "heavy_duty_or_cassette_review",
    "ptfe_profile_review",
    "rwdr_not_suitable",
    "engineering_review_required",
]
RWDRModifier = Literal[
    "repair_sleeve_or_lip_offset_check",
    "installation_sleeve_required",
    "reverse_rotation_requires_directionless_profile",
    "additional_exclusion_protection_check",
    "axial_retention_check",
]
RWDRWarning = Literal[
    "reverse_rotation_disallows_directional_helix",
    "installation_path_damage_risk",
    "vertical_layout_requires_level_review",
]
RWDRReviewFlag = Literal[
    "review_dry_run_high_speed",
    "review_water_with_pressure",
    "review_heavy_duty_without_width",
    "review_due_to_uncertainty",
    "review_due_to_geometry",
    "review_vertical_layout_conflict",
]
RWDRHardStop = Literal[
    "hard_stop_linear_motion_not_supported",
    "hard_stop_surface_speed_over_limit",
]


class RWDRSelectorInputDTO(BaseModel):
    motion_type: RWDRMotionType
    shaft_diameter_mm: float = Field(..., gt=0)
    max_speed_rpm: float = Field(..., ge=0)
    pressure_profile: RWDRPressureProfile
    inner_lip_medium_scenario: RWDRInnerLipMediumScenario
    maintenance_mode: RWDRMaintenanceMode
    external_contamination_class: Optional[RWDRExternalContaminationClass] = None
    available_width_mm: Optional[float] = Field(default=None, gt=0)
    installation_over_edges_flag: Optional[bool] = None
    vertical_shaft_flag: Optional[bool] = None
    medium_level_relative_to_seal: Optional[RWDRMediumLevelRelativeToSeal] = None
    confidence: Dict[RWDRConfidenceField, RWDRConfidenceStatus] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RWDRSelectorInputPatchDTO(BaseModel):
    motion_type: Optional[RWDRMotionType] = None
    shaft_diameter_mm: Optional[float] = Field(default=None, gt=0)
    max_speed_rpm: Optional[float] = Field(default=None, ge=0)
    pressure_profile: Optional[RWDRPressureProfile] = None
    inner_lip_medium_scenario: Optional[RWDRInnerLipMediumScenario] = None
    maintenance_mode: Optional[RWDRMaintenanceMode] = None
    external_contamination_class: Optional[RWDRExternalContaminationClass] = None
    available_width_mm: Optional[float] = Field(default=None, gt=0)
    installation_over_edges_flag: Optional[bool] = None
    vertical_shaft_flag: Optional[bool] = None
    medium_level_relative_to_seal: Optional[RWDRMediumLevelRelativeToSeal] = None
    confidence: Dict[RWDRConfidenceField, RWDRConfidenceStatus] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RWDRSelectorDerivedDTO(BaseModel):
    surface_speed_mps: Optional[float] = None
    surface_speed_class: RWDRSurfaceSpeedClass = "unknown"
    tribology_risk_level: RWDRRiskLevel = "unknown"
    pressure_risk_level: RWDRRiskLevel = "unknown"
    exclusion_level: RWDRExclusionLevel = "unknown"
    geometry_fit_status: RWDRGeometryFitStatus = "unknown"
    ptfe_candidate_flag: bool = False
    pressure_profile_required_flag: bool = False
    dust_lip_required_flag: bool = False
    heavy_duty_candidate_flag: bool = False
    additional_exclusion_required_flag: bool = False
    repair_sleeve_flag: bool = False
    lip_offset_check_flag: bool = False
    installation_sleeve_required_flag: bool = False
    sensitive_profiles_restricted_flag: bool = False
    review_due_to_water_pressure: bool = False
    review_due_to_dry_run_high_speed: bool = False
    review_due_to_geometry: bool = False
    review_due_to_uncertainty: bool = False
    reverse_rotation_requires_directionless_profile: bool = False
    auto_release_allowed_flag: bool = False
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    critical_unknown_count: int = Field(..., ge=0)

    model_config = ConfigDict(extra="forbid")


class RWDRSelectorOutputDTO(BaseModel):
    type_class: Optional[RWDRTypeClass] = None
    modifiers: List[RWDRModifier] = Field(default_factory=list)
    warnings: List[RWDRWarning] = Field(default_factory=list)
    review_flags: List[RWDRReviewFlag] = Field(default_factory=list)
    hard_stop: Optional[RWDRHardStop] = None
    reasoning: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RWDRSurfaceSpeedRule(BaseModel):
    max_mps: float = Field(..., gt=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RWDRPressureRule(BaseModel):
    max_bar: float = Field(..., ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RWDRGeometryRule(BaseModel):
    min_width_mm: float = Field(..., gt=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RWDRUncertaintyRules(BaseModel):
    required_known_fields: Tuple[RWDRConfidenceField, ...] = Field(default_factory=tuple)
    review_fields: Tuple[RWDRConfidenceField, ...] = Field(default_factory=tuple)
    max_critical_unknowns_for_auto_release: int = Field(..., ge=0)
    max_estimated_critical_fields_for_auto_release: int = Field(..., ge=0)
    min_confidence_score_for_auto_release: float = Field(..., ge=0.0, le=1.0)
    known_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    estimated_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    unknown_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    conservative_review_type_class: RWDRTypeClass = "engineering_review_required"

    model_config = ConfigDict(extra="forbid", frozen=True)


class RWDRSurfaceSpeedClassRules(BaseModel):
    reference_type_class: RWDRTypeClass = "standard_rwdr"
    low_ratio: float = Field(..., gt=0.0, lt=1.0)
    medium_ratio: float = Field(..., gt=0.0, lt=1.0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RWDRContaminationRule(BaseModel):
    exclusion_level: RWDRExclusionLevel
    dust_lip_required: bool = False
    heavy_duty_candidate: bool = False
    additional_exclusion_required: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)


class RWDRCoreReviewTriggers(BaseModel):
    water_with_pressure_requires_review: bool = True
    dry_run_high_speed_requires_review: bool = True
    heavy_duty_without_width_requires_review: bool = True
    cumulative_uncertainty_requires_review: bool = True
    vertical_above_medium_oil_bath_conflict_requires_review: bool = True
    reversing_disallows_directional_helix: bool = True

    model_config = ConfigDict(extra="forbid", frozen=True)


class RWDRSelectorConfig(BaseModel):
    config_version: str = "rwdr_selector_v1_1"
    surface_speed_limits: Dict[RWDRTypeClass, RWDRSurfaceSpeedRule]
    surface_speed_classification: RWDRSurfaceSpeedClassRules
    pressure_limits: Dict[RWDRTypeClass, RWDRPressureRule]
    geometry_min_widths: Dict[RWDRTypeClass, RWDRGeometryRule]
    uncertainty: RWDRUncertaintyRules
    contamination: Dict[RWDRExternalContaminationClass, RWDRContaminationRule]
    review_triggers: RWDRCoreReviewTriggers

    model_config = ConfigDict(extra="forbid", frozen=True)


def build_default_rwdr_selector_config() -> RWDRSelectorConfig:
    return RWDRSelectorConfig(
        surface_speed_limits={
            "standard_rwdr": RWDRSurfaceSpeedRule(max_mps=12.0),
            "rwdr_with_dust_lip": RWDRSurfaceSpeedRule(max_mps=10.0),
            "pressure_profile_rwdr": RWDRSurfaceSpeedRule(max_mps=8.0),
            "heavy_duty_or_cassette_review": RWDRSurfaceSpeedRule(max_mps=8.0),
            "ptfe_profile_review": RWDRSurfaceSpeedRule(max_mps=25.0),
            "rwdr_not_suitable": RWDRSurfaceSpeedRule(max_mps=0.1),
            "engineering_review_required": RWDRSurfaceSpeedRule(max_mps=25.0),
        },
        surface_speed_classification=RWDRSurfaceSpeedClassRules(
            reference_type_class="standard_rwdr",
            low_ratio=0.33,
            medium_ratio=0.66,
        ),
        pressure_limits={
            "standard_rwdr": RWDRPressureRule(max_bar=0.5),
            "rwdr_with_dust_lip": RWDRPressureRule(max_bar=0.5),
            "pressure_profile_rwdr": RWDRPressureRule(max_bar=10.0),
            "heavy_duty_or_cassette_review": RWDRPressureRule(max_bar=5.0),
            "ptfe_profile_review": RWDRPressureRule(max_bar=10.0),
            "rwdr_not_suitable": RWDRPressureRule(max_bar=0.0),
            "engineering_review_required": RWDRPressureRule(max_bar=10.0),
        },
        geometry_min_widths={
            "standard_rwdr": RWDRGeometryRule(min_width_mm=7.0),
            "rwdr_with_dust_lip": RWDRGeometryRule(min_width_mm=8.0),
            "pressure_profile_rwdr": RWDRGeometryRule(min_width_mm=10.0),
            "heavy_duty_or_cassette_review": RWDRGeometryRule(min_width_mm=12.0),
            "ptfe_profile_review": RWDRGeometryRule(min_width_mm=8.0),
            "rwdr_not_suitable": RWDRGeometryRule(min_width_mm=1.0),
            "engineering_review_required": RWDRGeometryRule(min_width_mm=7.0),
        },
        uncertainty=RWDRUncertaintyRules(
            required_known_fields=(
                "motion_type",
                "shaft_diameter_mm",
                "max_speed_rpm",
                "maintenance_mode",
            ),
            review_fields=(
                "pressure_profile",
                "external_contamination_class",
                "medium_level_relative_to_seal",
            ),
            max_critical_unknowns_for_auto_release=1,
            max_estimated_critical_fields_for_auto_release=1,
            min_confidence_score_for_auto_release=0.75,
            known_weight=1.0,
            estimated_weight=0.5,
            unknown_weight=0.0,
        ),
        contamination={
            "clean_room_dust": RWDRContaminationRule(exclusion_level="none"),
            "splash_water_or_outdoor_dust": RWDRContaminationRule(
                exclusion_level="medium",
                dust_lip_required=True,
            ),
            "mud_high_pressure_abrasive": RWDRContaminationRule(
                exclusion_level="heavy",
                heavy_duty_candidate=True,
                additional_exclusion_required=True,
            ),
            "unknown": RWDRContaminationRule(
                exclusion_level="unknown",
                additional_exclusion_required=True,
            ),
        },
        review_triggers=RWDRCoreReviewTriggers(),
    )
