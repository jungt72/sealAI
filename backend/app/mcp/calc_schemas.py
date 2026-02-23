"""Pydantic I/O schemas for the MCP gasket calculation engine.

These models enforce typed, validated inputs and outputs for the
deterministic calculation tool (R1: no LLM computes).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CalcInput(BaseModel):
    """Input parameters for gasket calculation."""

    pressure_max_bar: float = Field(..., ge=0, description="Max operating pressure in bar")
    temperature_max_c: float = Field(..., ge=-273.15, description="Max operating temperature in C")
    flange_standard: Optional[str] = None
    flange_dn: Optional[int] = Field(default=None, gt=0)
    flange_pn: Optional[int] = Field(default=None, gt=0)
    flange_class: Optional[int] = None
    bolt_count: Optional[int] = Field(default=None, gt=0)
    bolt_size: Optional[str] = None
    medium: Optional[str] = None
    cyclic_load: bool = False

    model_config = ConfigDict(extra="forbid")

    @field_validator("flange_class")
    @classmethod
    def _valid_flange_class(cls, value: Optional[int]) -> Optional[int]:
        valid = {150, 300, 600, 900, 1500, 2500}
        if value is not None and value not in valid:
            raise ValueError(f"flange_class must be one of {sorted(valid)}, got {value}")
        return value

    @field_validator("bolt_count")
    @classmethod
    def _bolt_count_even(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value % 2 != 0:
            raise ValueError(f"bolt_count must be even, got {value}")
        return value


class CalcOutput(BaseModel):
    """Output of the gasket calculation engine."""

    gasket_inner_d_mm: float
    gasket_outer_d_mm: float
    bolt_circle_d_mm: Optional[float] = None
    required_gasket_stress_mpa: float
    available_bolt_load_kn: Optional[float] = None
    safety_factor: float
    temperature_margin_c: float
    pressure_margin_bar: float
    is_critical_application: bool
    notes: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


__all__ = ["CalcInput", "CalcOutput"]
