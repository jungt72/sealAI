"""Message utilities for LangGraph v2."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def flatten_message_content(content: Any) -> str:
    """Flatten structured message content into plain text."""
    if isinstance(content, BaseMessage):
        return flatten_message_content(getattr(content, "content", ""))
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            text = flatten_message_content(part)
            if text:
                parts.append(text)
        return " ".join(parts).strip()
    if isinstance(content, dict):
        for key in ("text", "content", "message", "value"):
            if key in content:
                text = flatten_message_content(content.get(key))
                if text:
                    return text
        return str(content)
    return str(content)


def coerce_message_to_base(message: Any) -> Optional[BaseMessage]:
    """Best-effort conversion of unknown message payloads to BaseMessage."""
    if isinstance(message, BaseMessage):
        content_text = flatten_message_content(getattr(message, "content", ""))
        if isinstance(message, SystemMessage):
            return SystemMessage(content=content_text)
        if isinstance(message, HumanMessage):
            return HumanMessage(content=content_text)
        if isinstance(message, AIMessage):
            return AIMessage(content=content_text)
        role = str(getattr(message, "type", "") or "").strip().lower()
        if role in {"human", "user"}:
            return HumanMessage(content=content_text)
        if role in {"ai", "assistant"}:
            return AIMessage(content=content_text)
        if role == "system":
            return SystemMessage(content=content_text)
        return None

    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "").strip().lower()
        content_text = flatten_message_content(message.get("content"))
        if not content_text and "text" in message:
            content_text = flatten_message_content(message.get("text"))
        if role in {"human", "user"}:
            return HumanMessage(content=content_text)
        if role in {"ai", "assistant"}:
            return AIMessage(content=content_text)
        if role == "system":
            return SystemMessage(content=content_text)
    return None


def sanitize_message_history(messages: Iterable[Any] | None, *, include_system: bool = True) -> List[BaseMessage]:
    """Normalize mixed/raw message history into BaseMessage objects with plain-text content."""
    if not messages:
        return []
    sanitized: List[BaseMessage] = []
    for message in messages:
        coerced = coerce_message_to_base(message)
        if coerced is None:
            continue
        if not include_system and isinstance(coerced, SystemMessage):
            continue
        sanitized.append(coerced)
    return sanitized


def latest_user_text(messages: Iterable[Any] | None) -> str:
    """
    Return the latest human message content as plain text.

    Keeps any structured content (list/dict) flattened into a string so nodes
    can safely consume it for prompting or routing.
    """
    if not messages:
        return ""
    for msg in reversed(list(messages)):
        coerced = coerce_message_to_base(msg)
        if isinstance(coerced, HumanMessage):
            return flatten_message_content(getattr(coerced, "content", ""))
    return ""


__all__ = [
    "coerce_message_to_base",
    "flatten_message_content",
    "latest_user_text",
    "sanitize_message_history",
]
