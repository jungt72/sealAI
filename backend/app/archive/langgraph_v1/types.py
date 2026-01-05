"""Basic compatibility helpers for LangGraph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class InterruptSignal(Exception):
    """Raised to indicate that graph execution should pause for human input."""

    payload: Dict[str, Any]

    def __str__(self) -> str:  # pragma: no cover - human readable info
        return f"LangGraph interrupt: {self.payload!r}"


def interrupt(payload: Dict[str, Any]) -> None:
    """Signal an interrupt by raising an exception with the provided payload."""

    raise InterruptSignal(payload)


__all__ = ["interrupt", "InterruptSignal"]

