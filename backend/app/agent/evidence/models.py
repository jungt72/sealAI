from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

from app.agent.hardening.enums import ExtractionCertainty
from app.agent.hardening.extraction import classify_certainty


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

    The LLM reports structural facts (is_inferred, is_range) about how it obtained
    the value.  ExtractionCertainty is then assigned deterministically by
    classify_certainty() — never self-assessed by the LLM.
    """
    claim_type: ClaimType = Field(..., description="Die Kategorie der fachlichen Aussage.")
    statement: str = Field(..., min_length=5, description="Die eigentliche fachliche Erkenntnis.")
    is_inferred: bool = Field(
        default=False,
        description="True if this value was derived from context rather than explicitly stated by the user.",
    )
    is_range: bool = Field(
        default=False,
        description="True if the user provided a range rather than a single value.",
    )
    source_fact_ids: List[str] = Field(
        default_factory=list,
        description="IDs der Fakten, auf denen dieser Claim basiert.",
    )

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    @property
    def certainty(self) -> ExtractionCertainty:
        """
        Derived ExtractionCertainty — NEVER LLM self-assessed.
        Structurally derived from is_inferred and is_range flags.
        """
        return classify_certainty(
            raw_text=self.statement,
            parsed_value=self.statement,  # non-None: a statement is always present
            is_range=self.is_range,
            is_inferred=self.is_inferred,
        )
