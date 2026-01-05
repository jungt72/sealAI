"""Strict Pydantic IO models shared across LangGraph components (v1 shim)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ParameterProfile(BaseModel):
    """Defines required/optional technical parameters for a seal configuration."""

    required: List[str] = Field(default_factory=list)
    optional: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CoverageAnalysis(BaseModel):
    """Lightweight coverage summary for the current technical parameter set."""

    coverage_score: float
    missing_params: List[str] = Field(default_factory=list)
    high_impact_gaps: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AskMissingRequest(BaseModel):
    """Request payload instructing the frontend to collect missing inputs."""

    missing_fields: List[str] = Field(default_factory=list)
    question: str
    suggested_format: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class PreflightInput(BaseModel):
    """Incoming data for preflight/coverage analysis."""

    parameters: Dict[str, Any] = Field(default_factory=dict)
    parameter_profile: Optional[ParameterProfile] = None

    model_config = ConfigDict(extra="forbid")


class PreflightOutput(BaseModel):
    """Result of a preflight coverage analysis."""

    coverage: CoverageAnalysis
    ask_missing: Optional[AskMissingRequest] = None

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ParameterProfile",
    "CoverageAnalysis",
    "AskMissingRequest",
    "PreflightInput",
    "PreflightOutput",
]
