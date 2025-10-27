from dataclasses import dataclass
from typing import Any
"""Local LangGraph compatibility layer."""

from .constants import END
from .graph import StateGraph, add_messages
from .tool_node import ToolNode

__all__ = ["StateGraph", "add_messages", "END", "ToolNode", "Send"]

@dataclass
class Send:
    node: str
    arg: Any = None

    def __repr__(self):
        return f"Send({self.node!r}, {self.arg!r})"

@dataclass
class Send:
    node: str
    arg: Any = None

    def __repr__(self):
        return f"Send({self.node!r}, {self.arg!r})"
