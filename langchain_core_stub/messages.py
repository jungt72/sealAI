from __future__ import annotations

"""Lightweight message classes compatible with tests."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class BaseMessage:
    content: Any
    role: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"content": self.content, "role": self.role}


@dataclass
class HumanMessage(BaseMessage):
    role: str = "user"


@dataclass
class AIMessage(BaseMessage):
    role: str = "assistant"


@dataclass
class SystemMessage(BaseMessage):
    role: str = "system"


__all__ = ["BaseMessage", "HumanMessage", "AIMessage", "SystemMessage"]
