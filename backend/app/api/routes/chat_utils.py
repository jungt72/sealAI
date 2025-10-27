"""Utility helpers for chat endpoints."""
from __future__ import annotations

from functools import lru_cache

_DEFAULT_PROMPT = (
    "Du bist SealAI, ein technischer Fachberater. "
    "Antworte präzise, nachvollziehbar und auf Deutsch."
)


@lru_cache(maxsize=1)
def ensure_system_prompt() -> str:
    """Return the legacy system prompt used before the LangGraph rollout."""
    return _DEFAULT_PROMPT


__all__ = ["ensure_system_prompt"]
