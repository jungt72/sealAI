from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class RatingEnum(str, Enum):
    A = "A"  # Empfohlen
    B = "B"  # Bedingt
    C = "C"  # Ausschluss
    U = "U"  # Unknown

class ChemicalCompatibility(BaseModel):
    material_id: str
    medium_id: str
    rating: RatingEnum
    t_max_continuous_c: Optional[float] = None
    t_max_short_c: Optional[float] = None
    conditions: List[str] = Field(default_factory=list)
    failure_modes: List[str] = Field(default_factory=list)
    evidence_source: Optional[str] = None
    tenant_override: Optional[str] = None

class ChemicalKnowledgeBase(BaseModel):
    entries: List[ChemicalCompatibility]
