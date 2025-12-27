from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SealRenderRequest(BaseModel):
    script_path: str = Field(..., min_length=1, description="Relative path inside /app/freecad/scripts")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parametrization passed into the script template")


class SealRenderResponse(BaseModel):
    job_id: str
    script: str
    stdout: str
    stderr: str
    outputs: List[str]
