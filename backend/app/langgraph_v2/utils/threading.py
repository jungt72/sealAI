from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

_CURRENT_TENANT_ID: ContextVar[Optional[str]] = ContextVar("langgraph_v2_tenant_id", default=None)
_CHAT_ID_NAMESPACE = uuid.UUID("8a6c7c31-8e4b-4f6f-9a1d-7c8b9f0f2a5b")


def set_current_tenant_id(tenant_id: Optional[str]) -> ContextVar.Token:
    return _CURRENT_TENANT_ID.set(tenant_id)


def reset_current_tenant_id(token: ContextVar.Token) -> None:
    _CURRENT_TENANT_ID.reset(token)


def get_current_tenant_id() -> Optional[str]:
    return _CURRENT_TENANT_ID.get()


def normalize_chat_id(*, chat_id: str, tenant_id: str | None, user_id: str) -> str:
    """
    Normalizes chat_id to a standard UUID string.
    Handles 'thread-' prefix if present (legacy frontend behavior).
    Non-UUID values are deterministically mapped to UUIDv5 scoped to tenant+user+chat_id.
    """
    if not tenant_id:
        raise ValueError("missing tenant_id for normalize_chat_id")

    chat_id = (chat_id or "").strip()

    if chat_id.startswith("thread-"):
        chat_id = chat_id[7:]

    try:
        return str(uuid.UUID(chat_id))
    except ValueError:
        scoped_name = f"{tenant_id}:{user_id}:{chat_id}"
        return str(uuid.uuid5(_CHAT_ID_NAMESPACE, scoped_name))


def stable_thread_key(user_sub: str, conversation_id: str, tenant_id: str | None = None) -> str:
    """
    Stable key for checkpoints/memory scoped to tenant + user + conversation.
    """
    if not tenant_id:
        raise ValueError("missing tenant_id for stable_thread_key")

    return f"{tenant_id}:{user_sub}:{conversation_id}"


def resolve_checkpoint_thread_id(*, tenant_id: str | None, user_id: str, chat_id: str) -> str:
    """
    Single Source of Truth for resolving the thread_id used in checkpoints.

    Idempotent behavior:
    - If chat_id is already a stable thread key in the form "{tenant_id}:{user_id}:{uuid}",
      return it unchanged (prevents double-wrapping on confirm/go paths).

    Args:
        tenant_id: Canonical tenant ID (never from raw input)
        user_id: Canonical user ID (never 'legacy' user ID unless intended)
        chat_id: Raw chat_id from request OR an already-resolved stable thread key

    Returns:
        The valid checkpoint thread key.
    """
    if not tenant_id:
        raise ValueError("missing tenant_id for resolve_checkpoint_thread_id")

    chat_id = (chat_id or "").strip()

    # Idempotency guard: already a stable thread key?
    prefix = f"{tenant_id}:{user_id}:"
    if chat_id.startswith(prefix):
        tail = chat_id[len(prefix) :]
        try:
            # tail must be a UUID (the normalized conversation_id)
            uuid.UUID(tail)
            return chat_id
        except Exception:
            # Not a valid stable key tail -> fall through and normalize
            pass

    normalized_chat_id = normalize_chat_id(
        chat_id=chat_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    return stable_thread_key(
        user_sub=user_id,
        conversation_id=normalized_chat_id,
        tenant_id=tenant_id,
    )


__all__ = [
    "stable_thread_key",
    "resolve_checkpoint_thread_id",
    "set_current_tenant_id",
    "reset_current_tenant_id",
    "get_current_tenant_id",
]
