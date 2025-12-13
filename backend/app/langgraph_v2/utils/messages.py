"""Message utilities for LangGraph v2."""

from __future__ import annotations

from typing import List

from langchain_core.messages import BaseMessage, HumanMessage


def latest_user_text(messages: List[BaseMessage] | None) -> str:
    """
    Return the latest human message content as plain text.

    Keeps any structured content (list/dict) flattened into a string so nodes
    can safely consume it for prompting or routing.
    """
    if not messages:
        return ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = getattr(msg, "content", "") or ""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: List[str] = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        parts.append(str(part.get("text", "")))
                    else:
                        parts.append(str(part))
                return "".join(parts)
            return str(content)
    return ""


__all__ = ["latest_user_text"]
