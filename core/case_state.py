from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from .parameters import RawInputState
from .deterministic_state import DeterministicState
from .enums import VerbindlichkeitsStufe


class ConversationTurn(BaseModel):
    role: str                    # "user" | "assistant" | "system"
    content: str
    timestamp: datetime


class CaseMetadata(BaseModel):
    case_id: str
    user_id: Optional[str] = None
    schema_version: str = "1.0.0"    # Increment on ANY model change
    engine_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = 0                 # Optimistic locking counter


class CaseState(BaseModel):
    """
    The complete case. Two namespaces, hard boundary between them.

    - 'inputs' (L1):  Written by LLM extraction → whitelist guard → Pydantic validation
    - 'derived' (L2-L4): Written ONLY by engine/ functions. Immutable object, replaced wholesale.
    - 'conversation': Append-only log of turns.
    - 'meta': Case identity, schema version, optimistic lock version.
    - 'verbindlichkeit': Computed from state completeness, never set by LLM.
    """
    meta: CaseMetadata
    inputs: RawInputState = RawInputState()
    derived: DeterministicState = DeterministicState()
    conversation: List[ConversationTurn] = []
    verbindlichkeit: VerbindlichkeitsStufe = VerbindlichkeitsStufe.KNOWLEDGE
