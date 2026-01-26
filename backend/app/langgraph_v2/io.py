
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Any, Dict

class ParameterProfile(BaseModel):
    """
    Simulated replacement for legacy ParameterProfile.
    Stores parameter analysis results.
    """
    profile_name: Optional[str] = None
    completeness: float = 0.0
    missing_critical: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")

class CoverageAnalysis(BaseModel):
    """
    Simulated replacement for legacy CoverageAnalysis.
    """
    score: float = 0.0
    missing_params: List[str] = Field(default_factory=list)
    covered_params: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")

class AskMissingRequest(BaseModel):
    """
    Simulated replacement for legacy AskMissingRequest.
    """
    questions: List[str] = Field(default_factory=list)
    intro_text: Optional[str] = None
    model_config = ConfigDict(extra="allow")
