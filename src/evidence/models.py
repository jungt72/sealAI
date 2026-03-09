from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

class ClaimType(str, Enum):
    """
    Blueprint v1.2 / v1.3 — Claim Governance Taxonomy.
    Definiert die Autorität und Herkunft einer fachlichen Aussage.
    """
    FACT_OBSERVED = "fact_observed"       # Direkte Nutzerbeobachtung
    FACT_LOOKUP = "fact_lookup"           # Aus autoritativer Quelle (KB/Norm)
    FACT_INFERRED = "fact_inferred"       # Logisch abgeleitet (Reasoning)
    HEURISTIC_HINT = "heuristic_hint"     # Musterbasiert, nicht autoritativ
    EXPERT_PATTERN = "expert_pattern"     # Domänenexperten-Heuristik
    MANUFACTURER_LIMIT = "manufacturer_limit" # Herstellerspezifische Grenze

class Claim(BaseModel):
    """
    Strukturierter Claim für die Übergabe von Erkenntnissen an den SealingAIState.
    Validiert die vom LLM gelieferten Daten gegen das Engineering-Modell.
    """
    claim_type: ClaimType = Field(..., description="Die Kategorie der fachlichen Aussage.")
    statement: str = Field(..., min_length=5, description="Die eigentliche fachliche Erkenntnis.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Konfidenzlevel der Aussage (0.0 - 1.0).")
    source_fact_ids: List[str] = Field(default_factory=list, description="IDs der Fakten, auf denen dieser Claim basiert.")

    model_config = ConfigDict(
        extra="forbid",
        frozen=True
    )
