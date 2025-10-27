from __future__ import annotations

"""In-memory checkpoint stub compatible with the simplified LangGraph."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class MemorySaver:
    """Persist last seen state snapshot for debugging purposes."""

    # MIGRATION: Phase 1 - Placeholder checkpointer
    latest_state: Dict[str, Any] = field(default_factory=dict)

    def put(self, key: str, value: Dict[str, Any]) -> None:
        self.latest_state = {"key": key, "value": value}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if self.latest_state.get("key") == key:
            return self.latest_state.get("value")
        return None


__all__ = ["MemorySaver"]
