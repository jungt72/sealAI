from __future__ import annotations

from typing import Any, Iterable, List


def truncate_history_for_prompt(system_prompt: str, history: Iterable[Any], max_chars: int = 4000) -> List[Any]:
    keep: List[Any] = []
    remaining = max(max_chars - len(system_prompt or ""), 0)
    for message in reversed(list(history)):
        text = (getattr(message, "content", None) or getattr(message, "text", None) or "")
        if len(text) > remaining and keep:
            break
        keep.append(message)
        remaining -= len(text)
    keep.reverse()
    return keep


__all__ = ["truncate_history_for_prompt"]
