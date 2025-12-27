from __future__ import annotations

import logging
from typing import Any, Dict

from app.langgraph.state import SealAIState
from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)

# TODO: Replace with actual partner database query
PRODUCT_DATABASE = {
    "PTFE": "Empfehlung: Dichtungsring PTFE-ABC-123 von SKF (Temperaturbereich -200°C bis +260°C)",
    "EPDM": "Empfehlung: O-Ring EPDM-DEF-456 von Freudenberg (Mediumbeständig, -40°C bis +130°C)",
    "FKM": "Empfehlung: Viton® FKM-Dichtung GHI-789 von Trelleborg (Chemikalienbeständig, -20°C bis +200°C)",
    "NBR": "Empfehlung: NBR O-Ring JKL-012 von Parker (Ölbeständig, -30°C bis +100°C)",
}

def product_recommender_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    """
    Recommends specific products from partner database based on final material selection.
    This is the actionable output step that transitions from recommendation to procurement.
    """
    slots = state.get("slots") or {}
    final_material = str(slots.get("final_material", "")).upper()
    
    if not final_material:
        logger.warning("product_recommender: no final_material found in state")
        recommendation = "Für eine konkrete Produktempfehlung benötigen wir die Materialauswahl."
        return {"slots": {"recommended_product": recommendation}}
    
    # Query product database (placeholder logic)
    recommendation = PRODUCT_DATABASE.get(final_material)
    
    if not recommendation:
        logger.info(f"product_recommender: no product found for material '{final_material}'")
        recommendation = (
            f"Für das Material {final_material} empfehlen wir, sich direkt an unseren Vertrieb zu wenden "
            "für eine maßgeschneiderte Produktempfehlung."
        )
    
    return {"slots": {"recommended_product": recommendation}}


__all__ = ["product_recommender_node"]
