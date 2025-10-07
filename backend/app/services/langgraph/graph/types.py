from __future__ import annotations

from typing import Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage
from app.services.langgraph.graph.consult.state import ConsultState


class SupervisorState(TypedDict, total=False):
    messages: List[BaseMessage]
    intent: Literal["consult", "chitchat"]
    query_type: Literal["simple", "complex"]
    phase: Optional[str]
    route: Optional[str]
    source: Optional[str]
    intent_seed: Optional[str]
    intent_candidate: Optional[str]
    intent_final: Optional[str]
    confidence: Optional[float]
    fallback: Optional[bool]
    next_node: Optional[str]
    suggestions: Optional[List[Dict[str, str]]]
    last_agent: Optional[str]
    chat_id: Optional[str]
    user_id: Optional[str]
    feature_flag_state: Optional[bool]


class MaiDxoState(SupervisorState, ConsultState, total=False):
    """Vereint Supervisor- und Consult-Attribute für den MAI-DXO-Graphen."""


__all__ = ["SupervisorState", "MaiDxoState"]
