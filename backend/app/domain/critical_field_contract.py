"""Shared v0.7 critical field contract.

This module is intentionally dependency-light so durable services can enforce
the contract without importing agent/LangGraph code.
"""
from __future__ import annotations


CORE_CONTEXT_FIELDS: frozenset[str] = frozenset(
    {
        "asset_type",
        "application",
        "seal_location",
        "motion_type",
        "medium",
        "medium_name",
        "seal_type",
        "sealing_type",
        "requested_seal_type",
    }
)

OPERATING_CONDITION_FIELDS: frozenset[str] = frozenset(
    {
        "temperature_min",
        "temperature_max",
        "temperature_c",
        "temperature_profile",
        "pressure_nominal",
        "pressure_peak",
        "pressure_bar",
        "pressure_system_bar",
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "ambiguous_pressure_bar",
        "pressure_profile",
        "speed_rpm",
        "rpm",
        "speed",
        "duty_cycle",
        "start_stop_frequency",
        "lubrication",
        "lubrication_condition",
        "contamination",
        "contamination_condition",
        "particles_present",
        "abrasive_content",
    }
)

GEOMETRY_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_diameter",
        "shaft_diameter_mm",
        "housing_bore",
        "housing_bore_mm",
        "installation_width",
        "installation_width_mm",
        "geometry",
        "geometry_context",
        "geometry_space",
        "installation_space_summary",
        "available_space",
        "tolerance_gap",
        "radial_gap_mm",
        "clearance_gap_mm",
        "shaft_runout",
        "runout",
        "runout_mm",
        "runout_um",
        "dynamic_runout",
        "dynamic_runout_mm",
        "eccentricity",
        "eccentricity_mm",
        "axial_movement_mm",
        "misalignment",
    }
)

SURFACE_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_material",
        "surface_finish",
        "counterface_surface",
        "counterface_surface_condition",
        "shaft_surface",
        "surface_roughness",
        "surface_roughness_ra_um",
        "surface_roughness_rz_um",
        "shaft_roughness_ra_um",
        "roughness",
        "shaft_hardness",
        "shaft_hardness_hrc",
        "surface_hardness_hrc",
        "hardness",
        "hardness_shore_a",
    }
)

MATERIAL_IDENTITY_FIELDS: frozenset[str] = frozenset(
    {
        "material",
        "material_identity",
        "material_or_compound",
        "compound",
        "compound_family_hint",
        "candidate_materials",
        "gasket_material",
        "shaft_material",
    }
)

REQUIREMENT_FIELDS: frozenset[str] = frozenset(
    {
        "sealing_function",
        "primary_function",
        "leakage_target",
        "leakage_requirement",
        "safety_context",
        "atex_relevance",
        "food_contact",
        "pharma_contact",
        "certification_requirement",
        "verification_criteria",
        "lifetime_target",
        "target_lifetime_hours",
        "target_lifetime_cycles",
        "mounting_path",
        "installation_context",
    }
)

CRITICAL_CASE_FIELDS: frozenset[str] = frozenset(
    CORE_CONTEXT_FIELDS
    | OPERATING_CONDITION_FIELDS
    | GEOMETRY_FIELDS
    | SURFACE_FIELDS
    | MATERIAL_IDENTITY_FIELDS
    | REQUIREMENT_FIELDS
)

TEMPERATURE_FIELDS: frozenset[str] = frozenset(
    {"temperature_min", "temperature_max", "temperature_c", "temperature_profile"}
)
PRESSURE_FIELDS: frozenset[str] = frozenset(
    {
        "pressure_nominal",
        "pressure_peak",
        "pressure_bar",
        "pressure_system_bar",
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "ambiguous_pressure_bar",
        "pressure_profile",
    }
)
RPM_FIELDS: frozenset[str] = frozenset({"speed_rpm", "rpm", "speed"})
LENGTH_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_diameter",
        "shaft_diameter_mm",
        "housing_bore",
        "housing_bore_mm",
        "installation_width",
        "installation_width_mm",
    }
)
RUNOUT_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_runout",
        "runout",
        "runout_mm",
        "runout_um",
        "dynamic_runout",
        "dynamic_runout_mm",
        "eccentricity",
        "eccentricity_mm",
        "axial_movement_mm",
        "misalignment",
    }
)
ROUGHNESS_FIELDS: frozenset[str] = frozenset(
    {
        "surface_roughness_ra_um",
        "surface_roughness_rz_um",
        "shaft_roughness_ra_um",
    }
)
HARDNESS_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_hardness_hrc",
        "surface_hardness_hrc",
    }
)
MM_FIELDS: frozenset[str] = frozenset(LENGTH_FIELDS | RUNOUT_FIELDS)


def is_critical_case_field(field_name: str) -> bool:
    normalized = str(field_name or "").strip()
    return normalized in CRITICAL_CASE_FIELDS


def is_critical_technical_field(field_name: str) -> bool:
    normalized = str(field_name or "").strip()
    return normalized in (
        TEMPERATURE_FIELDS
        | PRESSURE_FIELDS
        | RPM_FIELDS
        | MM_FIELDS
        | ROUGHNESS_FIELDS
        | HARDNESS_FIELDS
    )
