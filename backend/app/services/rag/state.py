"""RAG-layer state models for SealAI v4.4.0 flange/gasket engineering workflows."""

from __future__ import annotations

import operator
import re
import time
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Helpers reused from the legacy v2 state shape.
# ---------------------------------------------------------------------------

_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _coerce_float(value: Any, field_name: str) -> Any:
    """Coerce string values to float, handling German comma notation."""
    if value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        normalized = trimmed.replace(",", ".")
        match = _NUMBER_PATTERN.search(normalized)
        if not match:
            raise ValueError(f"{field_name} must be a number (e.g. 10 or 10.5)")
        return float(match.group(0))
    return value


# ---------------------------------------------------------------------------
# Valid ASME flange classes
# ---------------------------------------------------------------------------

_VALID_FLANGE_CLASSES = frozenset({150, 300, 600, 900, 1500, 2500})


# ---------------------------------------------------------------------------
# Conflict model
# ---------------------------------------------------------------------------


ConflictSeverity = Literal["BLOCKER", "WARNING", "NOTE"]


class ConflictRecord(BaseModel):
    """Deterministic chemistry/mechanics conflict raised by guard rules."""

    rule_id: str
    severity: ConflictSeverity
    title: str
    condition: str
    reason: str
    recommendation: Optional[str] = None
    handled: bool = False
    resolved: bool = False

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# WorkingProfile
# ---------------------------------------------------------------------------


class WorkingProfile(BaseModel):
    """Canonical engineering profile (single source of truth for supervisor/agents)."""

    # v8 mandatory profile metadata
    knowledge_coverage: str = Field(default="LIMITED")
    safety_flags: List[str] = Field(default_factory=list)
    calc_results: Dict[str, Any] = Field(default_factory=dict)

    # Core technical fields (legacy + v8)
    medium: Optional[str] = None
    medium_detail: Optional[str] = None
    medium_type: Optional[str] = None
    medium_viscosity: Optional[str] = None
    medium_additives: Optional[str] = None
    medium_solid_content: Optional[str] = None
    medium_food_grade: Optional[str] = None
    medium_elastomer_notes: Optional[str] = None
    pressure_bar: Optional[float] = None
    pressure_max_bar: Optional[float] = None
    pressure_min_bar: Optional[float] = None
    pressure_max: Optional[float] = None
    pressure_min: Optional[float] = None
    p_max: Optional[float] = None
    p_min: Optional[float] = None
    pressure_spike_factor: Optional[float] = None
    temperature_c: Optional[float] = None
    temperature_C: Optional[float] = None
    temperature_max_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    temperature_max: Optional[float] = None
    temperature_min: Optional[float] = None
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    temp_range: Optional[tuple[float, float]] = None
    T_medium_min: Optional[float] = None
    T_medium_max: Optional[float] = None
    T_ambient_min: Optional[float] = None
    T_ambient_max: Optional[float] = None
    dynamic_type: Optional[str] = None

    # Flange / bolting / compliance
    flange_standard: Optional[str] = None
    flange_dn: Optional[int] = None
    flange_pn: Optional[int] = None
    flange_class: Optional[int] = None
    bolt_count: Optional[int] = None
    bolt_size: Optional[str] = None
    cyclic_load: bool = False
    emission_class: Optional[str] = None
    industry_sector: Optional[str] = None

    # Geometry / mechanics
    shaft_diameter: Optional[float] = None
    housing_diameter: Optional[float] = None
    housing_bore: Optional[float] = None
    piston_diameter: Optional[float] = None
    bore_diameter: Optional[float] = None
    rod_diameter: Optional[float] = None
    diameter: Optional[float] = None
    shaft_d1: Optional[float] = None
    shaft_d1_mm: Optional[float] = None
    d1: Optional[float] = None
    d_shaft_nominal: Optional[float] = None
    d_bore_nominal: Optional[float] = None
    inner_diameter_mm: Optional[float] = None
    outer_diameter_mm: Optional[float] = None
    nominal_diameter: Optional[float] = None
    tolerance: Optional[float] = None
    shaft_tolerance: Optional[float] = None
    housing_tolerance: Optional[float] = None
    shaft_hardness: Optional[str] = None
    surface_hardness_hrc: Optional[float] = None
    hrc_value: Optional[float] = None
    hardness: Optional[str] = None
    shaft_material: Optional[str] = None
    housing_material: Optional[str] = None
    shaft_Ra: Optional[float] = None
    shaft_Rz: Optional[float] = None
    shaft_lead: Optional[str] = None
    shaft_runout: Optional[str] = None
    shaft_chamfer: Optional[str] = None
    housing_surface_roughness: Optional[str] = None
    housing_axial_space: Optional[float] = None
    housing_surface: Optional[str] = None
    axial_plate_axial: Optional[float] = None
    roughness_ra: Optional[float] = None
    lead: Optional[str] = None
    lead_pitch: Optional[str] = None
    runout: Optional[float] = None
    dynamic_runout: Optional[float] = None
    eccentricity: Optional[str] = None
    mounting_offset: Optional[float] = None
    speed_rpm: Optional[float] = None
    speed_linear: Optional[float] = None
    rpm: Optional[float] = None
    n: Optional[float] = None
    n_min: Optional[float] = None
    n_max: Optional[float] = None
    v_max: Optional[float] = None

    # Sealing/material selection context
    material: Optional[str] = None
    seal_material: Optional[str] = None
    elastomer_material: Optional[str] = None
    spring_material: Optional[str] = None
    outer_case_type: Optional[str] = None
    lip_config: Optional[str] = None
    dust_lip: Optional[str] = None
    helix_direction: Optional[str] = None
    seal_type: Optional[str] = None
    product_name: Optional[str] = None
    standard_reference: Optional[str] = None
    application_type: Optional[str] = None

    # Operating environment
    misalignment: Optional[str] = None
    vibration_level: Optional[str] = None
    contamination_level: Optional[str] = None
    contamination: Optional[str] = None
    fluid_contamination_iso: Optional[str] = None
    aed_required: Optional[bool] = None
    compound_aed_certified: Optional[bool] = None
    dp_dt_bar_per_s: Optional[float] = None
    side_load_kn: Optional[float] = None
    cycle_rate_hz: Optional[float] = None
    extrusion_gap_mm: Optional[float] = None
    clearance_gap_mm: Optional[float] = None
    IP_requirement: Optional[str] = None
    water_exposure: Optional[str] = None
    chemicals_outside: Optional[str] = None
    target_lifetime: Optional[str] = None
    lifespan: Optional[str] = None
    max_leakage: Optional[str] = None
    max_friction_torque: Optional[str] = None
    safety_factors: Optional[str] = None
    install_method: Optional[str] = None
    access_level: Optional[str] = None
    expected_service_interval: Optional[str] = None
    food_grade: Optional[str] = None

    # Deterministic termination/safety fields
    candidate_materials: List[str] = Field(default_factory=list)
    active_hypothesis: Optional[str] = None
    knowledge_coverage_check: Dict[str, Any] = Field(default_factory=dict)
    risk_mitigated: bool = True
    conflicts_detected: List[ConflictRecord] = Field(default_factory=list)
    evidence_bundle_key: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "pressure_bar",
        "pressure_max_bar",
        "pressure_min_bar",
        "pressure_max",
        "pressure_min",
        "p_max",
        "p_min",
        mode="before",
    )
    @classmethod
    def _coerce_pressure(cls, value: Any, info: Any) -> Any:
        return _coerce_float(value, info.field_name)

    @field_validator(
        "temperature_c",
        "temperature_C",
        "temperature_max_c",
        "temperature_min_c",
        "temperature_max",
        "temperature_min",
        "temp_max",
        "temp_min",
        "T_medium_min",
        "T_medium_max",
        "T_ambient_min",
        "T_ambient_max",
        mode="before",
    )
    @classmethod
    def _coerce_temperature(cls, value: Any, info: Any) -> Any:
        return _coerce_float(value, info.field_name)

    @field_validator(
        "shaft_diameter",
        "housing_diameter",
        "housing_bore",
        "piston_diameter",
        "bore_diameter",
        "rod_diameter",
        "diameter",
        "shaft_d1",
        "shaft_d1_mm",
        "d1",
        "d_shaft_nominal",
        "d_bore_nominal",
        "inner_diameter_mm",
        "outer_diameter_mm",
        "nominal_diameter",
        "tolerance",
        "shaft_tolerance",
        "housing_tolerance",
        "shaft_Ra",
        "shaft_Rz",
        "housing_axial_space",
        "axial_plate_axial",
        "roughness_ra",
        "runout",
        "dynamic_runout",
        "mounting_offset",
        "speed_rpm",
        "speed_linear",
        "rpm",
        "n",
        "n_min",
        "n_max",
        "v_max",
        "dp_dt_bar_per_s",
        "side_load_kn",
        "cycle_rate_hz",
        "extrusion_gap_mm",
        "clearance_gap_mm",
        "surface_hardness_hrc",
        "hrc_value",
        mode="before",
    )
    @classmethod
    def _coerce_numeric_fields(cls, value: Any, info: Any) -> Any:
        return _coerce_float(value, info.field_name)

    @field_validator("temp_range", mode="before")
    @classmethod
    def _coerce_temp_range(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (list, tuple)) and len(value) == 2:
            low = _coerce_float(value[0], "temp_range[0]")
            high = _coerce_float(value[1], "temp_range[1]")
            if low is None or high is None:
                return None
            return (float(low), float(high))
        return value

    @field_validator("knowledge_coverage", mode="before")
    @classmethod
    def _normalize_knowledge_coverage(cls, value: Any) -> str:
        normalized = str(value or "LIMITED").strip().upper()
        if normalized not in {"FULL", "PARTIAL", "LIMITED"}:
            return "LIMITED"
        return normalized

    @field_validator(
        "pressure_bar",
        "pressure_max_bar",
        "pressure_min_bar",
        "pressure_max",
        "pressure_min",
        "p_max",
        "p_min",
    )
    @classmethod
    def _pressure_non_negative(cls, value: Optional[float], info: Any) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError(f"{info.field_name} must be >= 0, got {value}")
        return value

    @field_validator(
        "temperature_c",
        "temperature_C",
        "temperature_max_c",
        "temperature_min_c",
        "temperature_max",
        "temperature_min",
        "temp_max",
        "temp_min",
        "T_medium_min",
        "T_medium_max",
        "T_ambient_min",
        "T_ambient_max",
    )
    @classmethod
    def _temperature_above_absolute_zero(cls, value: Optional[float], info: Any) -> Optional[float]:
        if value is not None and value < -273.15:
            raise ValueError(f"{info.field_name} must be >= -273.15 °C, got {value}")
        return value

    @field_validator("flange_dn", "flange_pn")
    @classmethod
    def _positive_int(cls, value: Optional[int], info: Any) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValueError(f"{info.field_name} must be > 0, got {value}")
        return value

    @field_validator("flange_class")
    @classmethod
    def _valid_flange_class(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value not in _VALID_FLANGE_CLASSES:
            raise ValueError(f"flange_class must be one of {sorted(_VALID_FLANGE_CLASSES)}, got {value}")
        return value

    @field_validator("bolt_count")
    @classmethod
    def _bolt_count_positive_even(cls, value: Optional[int]) -> Optional[int]:
        if value is not None:
            if value <= 0:
                raise ValueError(f"bolt_count must be > 0, got {value}")
            if value % 2 != 0:
                raise ValueError(f"bolt_count must be even, got {value}")
        return value

    @model_validator(mode="after")
    def _check_min_max_consistency(self) -> "WorkingProfile":
        if (
            self.pressure_min_bar is not None
            and self.pressure_max_bar is not None
            and self.pressure_min_bar > self.pressure_max_bar
        ):
            raise ValueError(
                f"pressure_min_bar ({self.pressure_min_bar}) must be <= pressure_max_bar ({self.pressure_max_bar})"
            )
        if self.pressure_min is not None and self.pressure_max is not None and self.pressure_min > self.pressure_max:
            raise ValueError(f"pressure_min ({self.pressure_min}) must be <= pressure_max ({self.pressure_max})")
        if (
            self.temperature_min_c is not None
            and self.temperature_max_c is not None
            and self.temperature_min_c > self.temperature_max_c
        ):
            raise ValueError(
                f"temperature_min_c ({self.temperature_min_c}) must be <= temperature_max_c ({self.temperature_max_c})"
            )
        if self.temp_min is not None and self.temp_max is not None and self.temp_min > self.temp_max:
            raise ValueError(f"temp_min ({self.temp_min}) must be <= temp_max ({self.temp_max})")
        if self.temp_range is not None and self.temp_range[0] > self.temp_range[1]:
            raise ValueError(f"temp_range min ({self.temp_range[0]}) must be <= max ({self.temp_range[1]})")
        return self

    _PROFILE_FIELDS: frozenset[str] = frozenset(
        {
            "medium",
            "medium_detail",
            "pressure_max_bar",
            "pressure_min_bar",
            "temperature_max_c",
            "temperature_min_c",
            "flange_standard",
            "flange_dn",
            "flange_pn",
            "flange_class",
            "bolt_count",
            "bolt_size",
            "cyclic_load",
            "emission_class",
            "industry_sector",
        }
    )

    def as_dict(self) -> Dict[str, Any]:
        """Return non-null fields while hiding v8 reducer metadata by default."""
        payload = self.model_dump(exclude_none=True, exclude_defaults=True)
        if payload and "cyclic_load" not in payload and self.cyclic_load is False:
            payload["cyclic_load"] = False
        # Keep compatibility payload focused on technical content.
        payload.pop("knowledge_coverage", None)
        payload.pop("safety_flags", None)
        payload.pop("calc_results", None)
        return payload

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __len__(self) -> int:
        """Treat an untouched profile as empty (for truthy checks in graph logic)."""
        return len(self.model_dump(exclude_unset=True, exclude_none=True))

    def coverage_ratio(self) -> float:
        """Fraction of key engineering fields that are filled."""
        total = len(self._PROFILE_FIELDS)
        filled = 0
        for name in self._PROFILE_FIELDS:
            value = getattr(self, name, None)
            if isinstance(value, (list, dict, tuple)):
                if value:
                    filled += 1
                continue
            if value is not None and value is not False:
                filled += 1
        return filled / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# ErrorInfo
# ---------------------------------------------------------------------------


class ErrorInfo(BaseModel):
    """Structured error object for graph node failures."""

    code: str
    message: str
    node: Optional[str] = None
    recoverable: bool = True
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# RAGState (TypedDict with operator.add reducers)
# ---------------------------------------------------------------------------


class RAGState(TypedDict, total=False):
    """TypedDict-based graph state for RAG workflows with list reducers."""

    # Accumulated lists (operator.add = append-on-update)
    messages: Annotated[list, operator.add]
    sources: Annotated[list, operator.add]
    sealing_type_results: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]

    # Scalar fields (last-write-wins)
    calculation_result: Optional[dict]
    error_state: Optional[ErrorInfo]
    session_id: Optional[str]
    tenant_id: Optional[str]
    profile: Optional[WorkingProfile]


__all__ = [
    "ConflictSeverity",
    "ConflictRecord",
    "WorkingProfile",
    "ErrorInfo",
    "RAGState",
]
