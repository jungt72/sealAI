from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, Optional, List

class BasePromptContext(BaseModel):
    """
    Base context for all prompts. 
    Enforces strict typing for variables passed to Jinja2.
    """
    model_config = ConfigDict(extra='forbid') # Fail fast on extra args too

    # Base fields as per spec
    trace_id: str = Field(..., description="Traceability ID for the prompt rendering")
    session_id: str = Field(..., description="Session ID")
    language: str = Field(default="de", description="Language code")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

class GreetingContext(BasePromptContext):
    """
    Context for the Greeting Node.
    """
    is_first_visit: bool = Field(..., description="True if this is the user's first interaction")
    formality_score: int = Field(default=5, ge=1, le=10, description="Formality level (1-10)")
    
    # Optional: organization name if used in template (implied from previous attempts)
    organization_name: str = "SealAI"

from typing import List

class CollaborativeExtractionContext(BasePromptContext):
    """Context for Collaborative Extraction (Confirm Gate)."""
    missing_params_grouped: str = Field(..., description="Grouped missing parameters")
    known_params_summary: str = Field(..., description="Summary of known parameters")
    questions_asked_count: int = Field(default=0, description="Number of questions asked so far")

class EmpathicConcernContext(BasePromptContext):
    """Context for Empathic Concern (Safety/Guardrail)."""
    critical_issues: List[Dict[str, Any]] = Field(..., description="List of critical issues")
    urgency_level: str = Field(..., description="Urgency level (e.g. 'critical', 'high')")
    application_type: str = Field(..., description="Application type (e.g. 'hydrogen')")
