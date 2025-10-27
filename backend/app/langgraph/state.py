# MIGRATION: Phase-2 - State-Definitionen (messages-first, TypedDict für 0.6.10)

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import add_messages

class ContextRef(TypedDict, total=False):
    kind: str  # "rag" or "tool"
    id: str
    meta: Optional[Dict[str, Any]]

class Routing(TypedDict, total=False):
    domains: List[str]
    primary_domain: Optional[str]
    confidence: float
    coverage: float

class MetaInfo(TypedDict, total=False):
    thread_id: str
    user_id: str
    trace_id: str

class SealAIState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    slots: Dict[str, Any]
    routing: Routing
    context_refs: List[ContextRef]
    meta: MetaInfo


def new_user_message(content: str, *, user_id: str, msg_id: str) -> HumanMessage:
    return HumanMessage(content=content, id=msg_id, name=user_id)


def new_assistant_message(content: str, *, msg_id: str) -> AIMessage:
    return AIMessage(content=content, id=msg_id)

# Validation function for slots (keine großen Artefakte)
def validate_slots(slots: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in slots.items():
        if isinstance(value, (str, dict, list)) and len(str(value)) > 1000:
            raise ValueError(f"Slot {key} too large")
    return slots

# No custom update method needed; use built-in Partial-Updates in LangGraph
