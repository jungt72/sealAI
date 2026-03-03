from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MaterialPhysicalProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str = Field(
        ...,
        description="Canonical ID (e.g., NBR_70, FKM_80, PTFE_G25).",
    )

    # Tribology Limits
    pv_limit_warning: float = Field(
        2.0,
        description="PV warning limit in MPa*m/s.",
    )
    pv_limit_critical: float = Field(
        3.0,
        description="PV critical limit in MPa*m/s.",
    )
    v_surface_max: float = Field(
        ...,
        description="Maximum permitted surface speed in m/s.",
    )

    # Thermal Limits
    temp_min: float = Field(
        ...,
        description="Minimum application temperature in degC.",
    )
    temp_max: float = Field(
        ...,
        description="Maximum application temperature in degC.",
    )
    thermal_expansion_coeff: float = Field(
        1.2e-4,
        description="Linear thermal expansion coefficient alpha [1/K].",
    )

    # Mechanical / Extrusion
    hardness_shore_a: Optional[float] = Field(
        None,
        description="Typical Shore A hardness of the compound.",
    )
    modulus_100: Optional[float] = Field(
        None,
        description="E-modulus at 100% elongation in MPa for extrusion resistance.",
    )
    gap_pressure_matrix: Dict[float, float] = Field(
        default_factory=lambda: {100.0: 0.2, 200.0: 0.1, 350.0: 0.05},
        description="Mapping pressure [bar] -> maximum extrusion gap [mm].",
    )

    # Application Specific Fallbacks
    is_standard_elastomer: bool = Field(
        True,
        description="Indicates whether the profile is a standard elastomer baseline.",
    )
    requires_spring: bool = Field(
        False,
        description="Whether spring energization is required (e.g., PTFE in cryogenic service).",
    )


class MaterialKnowledgeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: List[MaterialPhysicalProfile] = Field(
        default_factory=list,
        description="List of material physical profiles.",
    )
