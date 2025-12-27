from __future__ import annotations

import logging
from typing import Any, Dict

from app.langgraph.state import SealAIState
from app.langgraph.types import interrupt
from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)

def human_escalation_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    HITL (Human-in-the-Loop) process: pauses for human approval if needed.
    Triggers interrupt for critical risk scenarios.
    """
    slots = state.get("slots") or {}
    calc_risk = str(slots.get("calc_risk_level", "")).upper()
    
    # Trigger HITL for CRITICAL_FAILURE_RISK
    if calc_risk == "CRITICAL_FAILURE_RISK":
        logger.warning(f"HITL triggered for critical risk: {calc_risk}")
        interrupt({
            "prompt": "Diese Empfehlung betrifft kritische Sicherheitsanforderungen. Bitte prüfen Sie die Angaben manuell.",
            "reason": "high_risk",
            "risk_level": calc_risk,
            "data": slots
        })
        return {"slots": {"hitl_status": "PENDING", "hitl_required": True}}
    
    # No HITL needed for SAFE or WARNING levels
    logger.info(f"HITL not required for risk level: {calc_risk}")
    return {"slots": {"hitl_status": "APPROVED", "hitl_required": False}}


__all__ = ["human_escalation_node"]
