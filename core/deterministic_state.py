from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel
from .engine_result import EngineResult


class CalculationResults(BaseModel):
    """LAYER 2 – Deterministic calculations. LLM has ZERO write access."""
    circumferential_speed_ms: Optional[EngineResult[float]] = None
    pv_value: Optional[EngineResult[float]] = None
    groove_depth_check: Optional[EngineResult[bool]] = None


class EngineeringSignals(BaseModel):
    """LAYER 3 – Classified signals derived from L1 + L2. LLM has ZERO write access."""
    speed_class: Optional[EngineResult[str]] = None
    temperature_class: Optional[EngineResult[str]] = None
    pressure_class: Optional[EngineResult[str]] = None
    media_compatibility_group: Optional[EngineResult[str]] = None
    boundary_warnings: List[str] = []
    contradictions: List[str] = []


class QualificationResults(BaseModel):
    """LAYER 4 – Rule engine output. LLM has ZERO write access."""
    material_shortlist: Optional[EngineResult[List[str]]] = None
    rwdr_type_class: Optional[EngineResult[str]] = None
    hard_stops: List[str] = []
    review_flags: List[str] = []
    qualification_level: Optional[str] = "not_started"
    rfq_admissible: bool = False


class DeterministicState(BaseModel):
    """
    Combined L2 + L3 + L4. This object is the 'protected zone'.
    It is NEVER deserialized from LLM output.
    It is ONLY written to by functions in sealai/engine/.
    """
    calculations: CalculationResults = CalculationResults()
    signals: EngineeringSignals = EngineeringSignals()
    qualification: QualificationResults = QualificationResults()

    model_config = {"frozen": True}
    # frozen=True makes this immutable after creation.
    # Engine functions create NEW instances, they don't mutate.
    # This prevents accidental in-place mutation from any caller.
