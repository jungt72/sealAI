from pydantic import BaseModel, Field
from datetime import datetime

class FormData(BaseModel):
    shaft_diameter: float = Field(..., description="Wellen-Ø in mm")
    housing_diameter: float = Field(..., description="Gehäuse-Ø in mm")

class FormResult(BaseModel):
    id: str
    username: str
    radial_clearance: float
    tolerance_fit: str
    result_text: str
    created_at: datetime

    class Config:
        from_attributes = True
