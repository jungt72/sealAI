from __future__ import annotations

import logging
from typing import Any, Dict

from app.langgraph.state import SealAIState
from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)

GREETINGS_MAP = {
    "hallo": "Hallo! Wie kann ich Ihnen bei Ihrer Dichtungsfrage helfen?",
    "hi": "Hi! Ich bin hier, um Sie bei technischen Fragen zu unterstützen.",
    "hey": "Hey! Was möchten Sie wissen?",
    "guten tag": "Guten Tag! Wie kann ich Ihnen weiterhelfen?",
    "guten morgen": "Guten Morgen! Was kann ich für Sie tun?",
    "servus": "Servus! Wie kann ich helfen?",
}

def smalltalk_agent_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    """Handles greetings and simple conversation with minimal latency."""
    user_query = str(state.get("slots", {}).get("user_query", "")).strip().lower()
    
    if not user_query:
        return {}
    
    # Pattern matching for common greetings
    for key, response in GREETINGS_MAP.items():
        if key in user_query:
            return {"slots": {"final_answer": response}}
    
    # Fallback: send to LLM triage if not recognized
    logger.info(f"smalltalk_agent: no match for '{user_query}', routing to LLM")
    return {"routing": {"needs_llm_triage": True}}


__all__ = ["smalltalk_agent_node"]
