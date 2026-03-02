from __future__ import annotations

from typing import Any, Optional
from app.langgraph_v2.state.sealai_state import SealAIState, LiveCalcTile

class AnswerSubgraphState(SealAIState):
    """Explicit state for the answer subgraph to ensure isolation and field availability.
    
    Inherits from SealAIState but explicitly lists critical fields to ensure 
    they are correctly mapped and available during subgraph execution.
    """
    # Deterministic calculation state
    live_calc_tile: LiveCalcTile = LiveCalcTile()
    
    # Structured engineering context
    working_profile: Optional[Any] = None
