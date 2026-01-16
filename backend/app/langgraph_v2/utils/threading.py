from __future__ import annotations
from app.services.chat.validation import normalize_chat_id


def stable_thread_key(user_sub: str, conversation_id: str, tenant_id: str | None = None) -> str:
    """
    Stable key for checkpoints/memory scoped to tenant + user + conversation.

    Backwards compatible:
      - if tenant_id is None -> "{user_sub}:{conversation_id}" (legacy)
      - if tenant_id provided -> "{tenant_id}:{user_sub}:{conversation_id}"
    """
    if tenant_id:
        return f"{tenant_id}:{user_sub}:{conversation_id}"
    return f"{user_sub}:{conversation_id}"


def resolve_checkpoint_thread_id(*, tenant_id: str | None, user_id: str, chat_id: str) -> str:
    """
    Single Source of Truth for resolving the thread_id used in checkpoints.
    
    Args:
        tenant_id: Canonical tenant ID (never from raw input)
        user_id: Canonical user ID (never 'legacy' user ID unless intended)
        chat_id: Raw chat_id from request
        
    Returns:
        The valid checkpoint thread key.
    """
    normalized_chat_id = normalize_chat_id(chat_id)
    return stable_thread_key(
        user_sub=user_id,
        conversation_id=normalized_chat_id,
        tenant_id=tenant_id
    )


__all__ = ["stable_thread_key", "resolve_checkpoint_thread_id"]
