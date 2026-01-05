# backend/app/langgraph_v2/tools/parameter_tools.py
"""Tools for managing technical parameters in LangGraph state."""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from langgraph.prebuilt import InjectedState

if TYPE_CHECKING:
    from app.langgraph_v2.state import SealAIState

logger = logging.getLogger(__name__)


def set_parameters(
    # Core
    pressure_bar: Optional[float] = None,
    temperature_C: Optional[float] = None,
    shaft_diameter: Optional[float] = None,
    speed_rpm: Optional[float] = None,
    medium: Optional[str] = None,
    
    # Shaft
    nominal_diameter: Optional[float] = None,
    tolerance: Optional[float] = None,
    hardness: Optional[str] = None,
    surface: Optional[str] = None,
    roughness_ra: Optional[float] = None,
    lead: Optional[str] = None,
    lead_pitch: Optional[str] = None,
    runout: Optional[float] = None,
    eccentricity: Optional[str] = None,

    # Housing
    housing_diameter: Optional[float] = None,
    bore_diameter: Optional[float] = None,
    housing_tolerance: Optional[float] = None,
    housing_surface: Optional[str] = None,
    housing_material: Optional[str] = None,
    axial_plate_axial: Optional[float] = None,
    
    # Operating Conditions
    pressure_min: Optional[float] = None,
    pressure_max: Optional[float] = None,
    temp_min: Optional[float] = None,
    temp_max: Optional[float] = None,
    speed_linear: Optional[float] = None,
    dynamic_runout: Optional[float] = None,
    mounting_offset: Optional[float] = None,

    # Misc
    contamination: Optional[str] = None,
    lifespan: Optional[str] = None,
    application_type: Optional[str] = None,
    food_grade: Optional[str] = None,

    # Injected
    state: "InjectedState[SealAIState]" = None,
) -> dict:
    """Set technical parameters for seal recommendation.
    
    Use this tool when the user provides or updates ANY technical parameters.
    Even single values (e.g. "diameter is 50") should be updated via this tool.
    
    Args:
        pressure_bar: Operating pressure in bar
        temperature_C: Operating temperature in Celsius
        shaft_diameter: Shaft diameter in mm (d1)
        speed_rpm: Rotational speed in RPM
        medium: Sealed medium name
        nominal_diameter: Nominal bore diameter (mm)
        tolerance: Shaft tolerance (mm)
        hardness: Shaft hardness (e.g. 55 HRC)
        surface: Shaft material/surface
        roughness_ra: Shaft roughness Ra
        lead: Shaft lead type
        lead_pitch: Lead pitch
        runout: Shaft runout
        eccentricity: Shaft eccentricity
        housing_diameter: Housing diameter (D)
        bore_diameter: Bore diameter
        housing_tolerance: Housing tolerance
        housing_surface: Housing surface quality
        housing_material: Housing material
        axial_plate_axial: Axial space
        pressure_min: Minimum pressure
        pressure_max: Maximum pressure
        temp_min: Minimum temperature
        temp_max: Maximum temperature
        speed_linear: Linear speed (m/s)
        dynamic_runout: Dynamic runout
        mounting_offset: Mounting offset
        contamination: Contamination type
        lifespan: Target lifespan
        application_type: Application type (e.g. Pump)
        food_grade: Food grade requirement (fda, etc.)
        state: Injected current graph state
    """
    # Get current parameters from state
    current_params = {}
    current_provenance = {}
    if state and hasattr(state, "parameters"):
        current_params = state.parameters.as_dict() if hasattr(state.parameters, "as_dict") else dict(state.parameters)
        current_provenance = getattr(state, "parameter_provenance", {}) or {}
    
    # Update with new values (only non-None values)
    updates = {}
    locals_ = locals()
    ignore_keys = ["state", "current_params", "updates", "locals_"]
    
    for key, value in locals_.items():
        if key not in ignore_keys and value is not None:
            if key == "medium" and isinstance(value, str):
                updates[key] = value.lower()
            else:
                updates[key] = value

    # Merge with current parameters respecting user provenance.
    from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance
    merged_params, merged_provenance = apply_parameter_patch_with_provenance(
        current_params,
        updates,
        current_provenance,
        source="llm",
    )
    
    logger.info(
        "set_parameters_tool_called",
        updates=updates,
        merged_params=merged_params,
    )
    
    # Return TechnicalParameters object
    from app.langgraph_v2.state import TechnicalParameters
    # Ensure ignore extra fields if any mismatch, but TechnicalParameters allows extra via config if set.
    # But since we updated TechnicalParameters, it should be fine.
    return {
        "parameters": TechnicalParameters(**merged_params),
        "parameter_provenance": merged_provenance,
    }

__all__ = ["set_parameters"]
