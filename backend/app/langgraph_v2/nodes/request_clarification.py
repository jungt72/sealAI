"""
Fordert User-Klarstellung bei Verification-Failures an.
"""
from app.langgraph_v2.state.sealai_state import SealAIState
import structlog

log = structlog.get_logger(__name__)

async def request_clarification_node(state: SealAIState) -> dict:
    """
    Informiert User über unverified values und bietet Optionen.
    """
    error = state.get("verification_error", {})
    unverified = error.get("unverified_values", [])
    
    clarification = (
        "⚠️ **Hinweis zur Datenqualität**\n\n"
        "Ich habe eine Antwort generiert, konnte aber folgende Werte "
        "nicht in den verfügbaren Quellen verifizieren:\n\n"
    )
    
    for val in unverified:
        clarification += f"- **{val['formatted']}**\n"
    
    clarification += (
        "\n**Empfehlung:**\n"
        "Bitte überprüfen Sie diese Werte in den Original-Datenblättern "
        "oder kontaktieren Sie den Hersteller für verifizierte Angaben.\n\n"
        "Möchten Sie die Suche mit zusätzlichen Informationen wiederholen?"
    )
    
    log.warning(
        "clarification_requested",
        unverified_count=len(unverified),
        tenant_id=state.get("tenant_id")
    )
    
    return {
        "final_answer": clarification,
        "requires_user_input": True,
        "verification_status": "FAILED_REQUIRES_CLARIFICATION",
        "last_node": "request_clarification_node"
    }
