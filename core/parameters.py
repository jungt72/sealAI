from __future__ import annotations
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel, Field
from .enums import ExtractionCertainty

V = TypeVar("V", int, float, str, bool)


class ExtractedParameter(BaseModel, Generic[V]):
    """
    Wraps every Layer-1 field. Carries provenance, not just a value.
    The LLM fills raw_text + parsed_value + certainty.
    The orchestrator (not the LLM) decides confirmation status.
    """
    raw_text: Optional[str] = None
    parsed_value: Optional[V] = None
    unit: Optional[str] = None
    certainty: ExtractionCertainty = ExtractionCertainty.AMBIGUOUS
    confirmed: bool = False

    @property
    def is_calculable(self) -> bool:
        """Can deterministic engine use this value?"""
        if self.parsed_value is None:
            return False
        if self.certainty == ExtractionCertainty.AMBIGUOUS:
            return False
        if self.certainty == ExtractionCertainty.INFERRED_FROM_CONTEXT and not self.confirmed:
            return False
        return True


class RawInputState(BaseModel):
    """
    LAYER 1 – The ONLY state object the LLM is allowed to write to.
    All fields are Optional: a case starts empty and fills progressively.
    """
    medium: Optional[ExtractedParameter[str]] = None
    temperature_celsius: Optional[ExtractedParameter[float]] = None
    pressure_bar: Optional[ExtractedParameter[float]] = None
    shaft_diameter_mm: Optional[ExtractedParameter[float]] = None
    speed_rpm: Optional[ExtractedParameter[float]] = None
    installation_type: Optional[ExtractedParameter[str]] = None
    seal_type: Optional[ExtractedParameter[str]] = None
    rotation_direction: Optional[ExtractedParameter[str]] = None
    surface_roughness_um: Optional[ExtractedParameter[float]] = None
    duty_cycle: Optional[ExtractedParameter[str]] = None

    # Extend as domain requires. Every field MUST be ExtractedParameter.
    # Adding a plain float/str here is an architecture violation.

    model_config = {"extra": "forbid"}  # Reject any field not defined here
