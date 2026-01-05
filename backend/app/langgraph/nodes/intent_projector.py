# MIGRATION: Phase-2 - Intent Projector

from ..state import SealAIState

async def intent_projector(state: SealAIState) -> dict:
    # Dummy: Set routing basierend auf Query
    user_query = state["slots"].get("user_query", "").lower()
    if "material" in user_query:
        domains = ["material"]
        primary = "material"
        confidence = 0.9
    else:
        domains = ["material"]  # Default
        primary = "material"
        confidence = 0.5
    routing = {
        "domains": domains,
        "primary_domain": primary,
        "confidence": confidence,
        "coverage": state["slots"].get("coverage", 0.0)
    }
    return {"routing": routing}