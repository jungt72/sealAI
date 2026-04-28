"""Shared v0.7 critical field contract.

This module is intentionally dependency-light so durable services can enforce
the contract without importing agent/LangGraph code.
"""
from __future__ import annotations


CRITICAL_CASE_FIELDS: frozenset[str] = frozenset(
    {
        "asset_type",
        "seal_location",
        "motion_type",
        "medium_name",
        "temperature_min",
        "temperature_max",
        "temperature_c",
        "pressure_nominal",
        "pressure_peak",
        "pressure_bar",
        "speed_rpm",
        "rpm",
        "shaft_diameter",
        "shaft_diameter_mm",
        "housing_bore",
        "housing_bore_mm",
        "installation_width",
        "installation_width_mm",
        "shaft_material",
        "surface_finish",
        "food_contact",
        "atex_relevance",
    }
)

TEMPERATURE_FIELDS: frozenset[str] = frozenset(
    {"temperature_min", "temperature_max", "temperature_c"}
)
PRESSURE_FIELDS: frozenset[str] = frozenset(
    {"pressure_nominal", "pressure_peak", "pressure_bar"}
)
RPM_FIELDS: frozenset[str] = frozenset({"speed_rpm", "rpm"})
MM_FIELDS: frozenset[str] = frozenset(
    {
        "shaft_diameter",
        "shaft_diameter_mm",
        "housing_bore",
        "housing_bore_mm",
        "installation_width",
        "installation_width_mm",
    }
)


def is_critical_case_field(field_name: str) -> bool:
    return str(field_name or "").strip() in CRITICAL_CASE_FIELDS


def is_critical_technical_field(field_name: str) -> bool:
    normalized = str(field_name or "").strip()
    return normalized in TEMPERATURE_FIELDS | PRESSURE_FIELDS | RPM_FIELDS | MM_FIELDS
