from langchain_core.tools import tool
from src.evidence.models import Claim, ClaimType
from typing import List, Optional

@tool("submit_claim")
def submit_claim(
    claim_type: ClaimType,
    statement: str,
    confidence: float,
    source_fact_ids: List[str] = []
) -> str:
    """
    Übergibt eine strukturierte fachliche Erkenntnis (Claim) an den SealingAIState.
    Dies ist der einzige Weg für das LLM, den technischen Zustand des Systems zu beeinflussen.
    Validiert die Eingaben gegen das Engineering-Modell (Strict Tooling).
    """
    # Instanziierung löst Pydantic-Validierung aus
    claim = Claim(
        claim_type=claim_type,
        statement=statement,
        confidence=confidence,
        source_fact_ids=source_fact_ids
    )
    
    # Bestätigung an das LLM (Phase C3 Meilenstein)
    return f"Claim empfangen: [{claim.claim_type.value}] {claim.statement} (Confidence: {claim.confidence})"
