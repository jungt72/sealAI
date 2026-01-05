"""State logging helpers for LangGraph v2."""
from __future__ import annotations

import logging
from typing import Any, List

from langchain_core.messages import BaseMessage

state_logger = logging.getLogger("langgraph_v2.state")


def _flatten_message_content(message: Any) -> str | None:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                text_value = chunk.get("text") or chunk.get("content")
                if isinstance(text_value, str):
                    parts.append(text_value)
                else:
                    parts.append(str(text_value))
            else:
                parts.append(str(chunk))
        return "".join(parts).strip()
    if isinstance(content, dict):
        text_value = content.get("text") or content.get("content")
        if isinstance(text_value, str):
            return text_value.strip()
        return str(content).strip()
    if content is None:
        return None
    return str(content).strip()


def _collect_messages(state: Any) -> List[BaseMessage | Any]:
    if isinstance(state, dict):
        raw = state.get("messages")
    else:
        raw = getattr(state, "messages", None)
    if isinstance(raw, list):
        return list(raw)
    return []


def log_state_debug(node_name: str, state: Any) -> None:
    """Robustes Logging fuer Node-Start, ohne UnboundLocalError."""
    try:
        thread_id = getattr(state, "thread_id", None)
        user_id = getattr(state, "user_id", None)

        # Falls der State als dict durchgereicht wurde, ggf. thread_id/user_id aus config holen
        if isinstance(state, dict):
            config = state.get("config") or {}
            thread_id = thread_id or config.get("thread_id")
            user_id = user_id or config.get("user_id")

        messages = _collect_messages(state)
        messages_count = len(messages) if isinstance(messages, list) else None
        coverage_score = getattr(state, "coverage_score", None)
        recommendation_ready = getattr(state, "recommendation_ready", None)
        recommendation_go = getattr(state, "recommendation_go", None)

        last_user = None
        for msg in reversed(messages):
            role = getattr(msg, "type", None) or getattr(msg, "role", None)
            if role in ("human", "user"):
                candidate = _flatten_message_content(msg)
                if candidate:
                    last_user = candidate[:200]
                    break

        state_logger.info(
            "langgraph_v2_node_start node=%s thread_id=%s user_id=%s "
            "messages_count=%s coverage_score=%s ready=%s go=%s last_user=%r",
            node_name,
            thread_id,
            user_id,
            messages_count,
            coverage_score,
            recommendation_ready,
            recommendation_go,
            last_user,
        )
    except Exception:
        state_logger.exception("Failed to log LangGraph v2 state for node %s", node_name)
