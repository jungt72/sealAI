from __future__ import annotations
import os

path = '/home/thorsten/sealai/backend/app/langgraph_v2/utils/threading.py'
new_content = """from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

_CURRENT_TENANT_ID: ContextVar[Optional[str]] = ContextVar("langgraph_v2_tenant_id", default=None)


def set_current_tenant_id(tenant_id: Optional[str]) -> ContextVar.Token:
    return _CURRENT_TENANT_ID.set(tenant_id)


def reset_current_tenant_id(token: ContextVar.Token) -> None:
    _CURRENT_TENANT_ID.reset(token)


def get_current_tenant_id() -> Optional[str]:
    return _CURRENT_TENANT_ID.get()


def normalize_chat_id(chat_id: str) -> str:
    try:
        # Ensure it's a valid UUID
        # Input might have whitespace
        chat_id = chat_id.strip()
        return str(uuid.UUID(chat_id))
    except ValueError:
        # Fallback or re-raise? Given this is strict backend, raise.
        raise ValueError(f"Invalid chat_id: {chat_id}")


def stable_thread_key(user_sub: str, conversation_id: str, tenant_id: str | None = None) -> str:
    \"\"\"
    Stable key for checkpoints/memory scoped to tenant + user + conversation.
    
    If tenant_id is explicitly provided, it is used.
    If not, it falls back to the context variable _CURRENT_TENANT_ID.
    If neither is present, it returns the legacy format ({user_sub}:{conversation_id}) or raises
    ValueError depending on strictness (here we fall back for safety during migration).
    \"\"\"
    if tenant_id:
        return f"{tenant_id}:{user_sub}:{conversation_id}"
    
    ctx_tenant = get_current_tenant_id()
    if ctx_tenant:
        return f"{ctx_tenant}:{user_sub}:{conversation_id}"

    # Legacy fallback
    return f"{user_sub}:{conversation_id}"


def resolve_checkpoint_thread_id(*, tenant_id: str | None, user_id: str, chat_id: str) -> str:
    \"\"\"
    Single Source of Truth for resolving the thread_id used in checkpoints.
    
    Args:
        tenant_id: Canonical tenant ID (never from raw input)
        user_id: Canonical user ID (never 'legacy' user ID unless intended)
        chat_id: Raw chat_id from request
        
    Returns:
        The valid checkpoint thread key.
    \"\"\"
    normalized_chat_id = normalize_chat_id(chat_id)
    return stable_thread_key(
        user_sub=user_id,
        conversation_id=normalized_chat_id,
        tenant_id=tenant_id
    )


__all__ = [
    "stable_thread_key",
    "resolve_checkpoint_thread_id",
    "set_current_tenant_id",
    "reset_current_tenant_id",
    "get_current_tenant_id",
]
"""

with open(path, 'w') as f:
    f.write(new_content)
print("Updated threading.py with complete content")
