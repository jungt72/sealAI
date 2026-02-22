"""RAG-layer state models for SealAI v4.4.0 flange/gasket engineering workflows."""

from __future__ import annotations

import operator
import re
import time
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Helpers (reused pattern from langgraph_v2/state/sealai_state.py)
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
# WorkingProfile
# ---------------------------------------------------------------------------


class WorkingProfile(BaseModel):
    """Engineering working profile for flange/gasket seal applications."""

    # Medium
    medium: Optional[str] = None
    medium_detail: Optional[str] = None

    # Pressure (bar)
    pressure_max_bar: Optional[float] = None
    pressure_min_bar: Optional[float] = None

    # Temperature (°C)
    temperature_max_c: Optional[float] = None
    temperature_min_c: Optional[float] = None

    # Flange specification
    flange_standard: Optional[str] = None
    flange_dn: Optional[int] = None
    flange_pn: Optional[int] = None
    flange_class: Optional[int] = None

    # Bolting
    bolt_count: Optional[int] = None
    bolt_size: Optional[str] = None

    # Operating conditions
    cyclic_load: bool = False

    # Compliance
    emission_class: Optional[str] = None

    # Context
    industry_sector: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    # -- Field validators (string → float coercion) --

    @field_validator("pressure_max_bar", "pressure_min_bar", mode="before")
    @classmethod
    def _coerce_pressure(cls, value: Any, info: Any) -> Any:
        return _coerce_float(value, info.field_name)

    @field_validator("temperature_max_c", "temperature_min_c", mode="before")
    @classmethod
    def _coerce_temperature(cls, value: Any, info: Any) -> Any:
        return _coerce_float(value, info.field_name)

    # -- Individual field constraints --

    @field_validator("pressure_max_bar", "pressure_min_bar")
    @classmethod
    def _pressure_non_negative(cls, value: Optional[float], info: Any) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError(f"{info.field_name} must be >= 0, got {value}")
        return value

    @field_validator("temperature_max_c", "temperature_min_c")
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
            raise ValueError(
                f"flange_class must be one of {sorted(_VALID_FLANGE_CLASSES)}, got {value}"
            )
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

    # -- Cross-field consistency (model-level) --

    @model_validator(mode="after")
    def _check_min_max_consistency(self) -> WorkingProfile:
        if (
            self.pressure_min_bar is not None
            and self.pressure_max_bar is not None
            and self.pressure_min_bar > self.pressure_max_bar
        ):
            raise ValueError(
                f"pressure_min_bar ({self.pressure_min_bar}) must be "
                f"<= pressure_max_bar ({self.pressure_max_bar})"
            )
        if (
            self.temperature_min_c is not None
            and self.temperature_max_c is not None
            and self.temperature_min_c > self.temperature_max_c
        ):
            raise ValueError(
                f"temperature_min_c ({self.temperature_min_c}) must be "
                f"<= temperature_max_c ({self.temperature_max_c})"
            )
        return self

    # -- Helpers --

    _PROFILE_FIELDS: frozenset[str] = frozenset({
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
    })

    def as_dict(self) -> Dict[str, Any]:
        """Return non-None fields as dict."""
        return self.model_dump(exclude_none=True)

    def coverage_ratio(self) -> float:
        """Fraction of profile fields that are filled (non-None, non-default)."""
        total = len(self._PROFILE_FIELDS)
        filled = 0
        for name in self._PROFILE_FIELDS:
            value = getattr(self, name, None)
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
    "WorkingProfile",
    "ErrorInfo",
    "RAGState",
]
