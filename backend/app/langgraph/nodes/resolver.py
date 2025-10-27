# MIGRATION: Phase-2 - Resolver (regel-basierter Fan-in)

from langgraph.types import Send
from ..state import SealAIState

CONFIDENCE_THRESHOLD = 0.7

async def resolver(state: SealAIState) -> Send:
    routing = state.get("routing", {})
    confidence = routing.get("confidence", 0.0)
    
    # Regel: Wenn confidence < threshold, debate
    if confidence < CONFIDENCE_THRESHOLD:
        # Send zu debate_subgraph (noch nicht implementiert, placeholder)
        return Send("debate_subgraph", state)
    else:
        # Go to exit
        return Send("exit_response", state)
