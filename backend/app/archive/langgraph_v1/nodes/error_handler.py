from __future__ import annotations

import logging
from typing import Any, Dict

from app.langgraph.state import SealAIState
from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)

def error_handler_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    Graceful error handling with user-friendly message.
    Ensures consistent UX even during system failures.
    """
    error = state.get("error", "")
    logger.error(f"error_handler invoked: {error}")
    
    friendly_message = (
        "Entschuldigung, es gab ein technisches Problem bei der Verarbeitung Ihrer Anfrage. "
        "Bitte versuchen Sie es erneut oder kontaktieren Sie unseren Support unter support@sealai.de."
    )
    
    return {
        "slots": {"final_answer": friendly_message},
        "error": str(error),
        "error_handled": True
    }


__all__ = ["error_handler_node"]
