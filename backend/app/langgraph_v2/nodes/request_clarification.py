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
    verification_error_obj = getattr(state.system, "verification_error", None)
    generic_error_obj = getattr(state.system, "error", None)
    error_obj = verification_error_obj if isinstance(verification_error_obj, dict) else generic_error_obj

    unverified = []
    if isinstance(error_obj, dict):
        unverified = error_obj.get("unverified_values", []) or []
    
    clarification = (
        "⚠️ **Hinweis zur Datenqualität**\n\n"
        "Ich habe eine Antwort generiert, konnte aber folgende Werte "
        "nicht in den verfügbaren Quellen verifizieren:\n\n"
    )
    
    for val in unverified:
        if isinstance(val, dict):
            formatted_value = val.get("formatted") or str(val.get("value") or val)
        else:
            formatted_value = str(val)
        clarification += f"- **{formatted_value}**\n"
    
    clarification += (
        "\n**Empfehlung:**\n"
        "Bitte überprüfen Sie diese Werte in den Original-Datenblättern "
        "oder kontaktieren Sie den Hersteller für verifizierte Angaben.\n\n"
        "Möchten Sie die Suche mit zusätzlichen Informationen wiederholen?"
    )
    
    log.warning(
        "clarification_requested",
        unverified_count=len(unverified),
        tenant_id=state.system.tenant_id
    )
    
    return {
               "requires_user_input": True,
               "verification_status": "FAILED_REQUIRES_CLARIFICATION",
               "system": {
                   "final_answer": clarification,
               },
               "reasoning": {
                   "last_node": "request_clarification_node",
               },
           }
