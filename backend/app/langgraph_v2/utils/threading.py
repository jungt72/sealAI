from __future__ import annotations


def stable_thread_key(user_sub: str, conversation_id: str) -> str:
    """Stable key for checkpoints/memory scoped to user + conversation."""
    return f"{user_sub}:{conversation_id}"


__all__ = ["stable_thread_key"]
