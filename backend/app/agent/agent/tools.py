from langchain_core.tools import tool
from app.agent.evidence.models import Claim, ClaimType
from typing import List, Optional

@tool("submit_claim")
def submit_claim(
    claim_type: ClaimType,
    statement: str,
    is_inferred: bool = False,
    is_range: bool = False,
    source_fact_ids: List[str] = [],
) -> str:
    """
    Übergibt eine strukturierte fachliche Erkenntnis (Claim) an den SealingAIState.
    Dies ist der einzige Weg für das LLM, den technischen Zustand des Systems zu beeinflussen.
    Validiert die Eingaben gegen das Engineering-Modell (Strict Tooling).

    is_inferred: True wenn dieser Wert aus dem Kontext abgeleitet wurde (nicht explizit genannt).
    is_range: True wenn der Nutzer einen Bereich statt eines einzelnen Wertes angegeben hat.
    """
    # Instanziierung löst Pydantic-Validierung aus
    claim = Claim(
        claim_type=claim_type,
        statement=statement,
        is_inferred=is_inferred,
        is_range=is_range,
        source_fact_ids=source_fact_ids,
    )

    # Bestätigung an das LLM
    return f"Claim empfangen: [{claim.claim_type.value}] {claim.statement} (Certainty: {claim.certainty.value})"
