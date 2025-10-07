"""Utility helpers for chat endpoints."""
from __future__ import annotations

from functools import lru_cache

try:
    from app.services.langgraph.prompt_registry import get_agent_prompt
except Exception:  # pragma: no cover - fallback when prompt registry unavailable
    get_agent_prompt = None  # type: ignore[assignment]

_DEFAULT_PROMPT = (
    "Du bist SealAI, ein technischer Fachberater. "
    "Antworte präzise, nachvollziehbar und auf Deutsch."
)


@lru_cache(maxsize=1)
def ensure_system_prompt() -> str:
    """Return the supervisor system prompt, falling back to a static default."""
    if get_agent_prompt is None:
        return _DEFAULT_PROMPT
    try:
        prompt = get_agent_prompt("supervisor", context={})
        return prompt.strip() or _DEFAULT_PROMPT
    except Exception:  # pragma: no cover - keep endpoint robust
        return _DEFAULT_PROMPT


__all__ = ["ensure_system_prompt"]
