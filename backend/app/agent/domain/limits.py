from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.agent.domain.parameters import PhysicalParameter

class OperatingLimit(BaseModel):
    """
    Repräsentiert eine Betriebs- oder Materialgrenze (Phase H2).
    Wird typischerweise in der Basis-Einheit (bar, C) definiert.
    """
    min_value: Optional[float] = Field(default=None, description="Untergrenze (inklusive).")
    max_value: Optional[float] = Field(default=None, description="Obergrenze (inklusive).")
    unit: str = Field(..., description="Die Einheit der Grenze (sollte bar oder C sein).")

    model_config = ConfigDict(extra="forbid", frozen=True)

    def is_within_limits(self, param: PhysicalParameter) -> bool:
        """
        Prüft, ob ein gegebener Parameter innerhalb dieser Grenzen liegt.
        Konvertiert den Parameter automatisch in die Basis-Einheit.
        """
        val = param.to_base_unit()
        
        # Prüfung der Untergrenze
        if self.min_value is not None:
            if val < self.min_value:
                return False
                
        # Prüfung der Obergrenze
        if self.max_value is not None:
            if val > self.max_value:
                return False
                
        return True
