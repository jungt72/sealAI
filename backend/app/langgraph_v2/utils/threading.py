from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_CURRENT_TENANT_ID: ContextVar[Optional[str]] = ContextVar("langgraph_v2_tenant_id", default=None)


def set_current_tenant_id(tenant_id: Optional[str]) -> ContextVar.Token:
    return _CURRENT_TENANT_ID.set(tenant_id)


def reset_current_tenant_id(token: ContextVar.Token) -> None:
    _CURRENT_TENANT_ID.reset(token)


def get_current_tenant_id() -> Optional[str]:
    return _CURRENT_TENANT_ID.get()


def stable_thread_key(user_sub: str, conversation_id: str) -> str:
    """Stable key for checkpoints/memory scoped to user + conversation."""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise ValueError("missing tenant_id for stable_thread_key")
    return f"{tenant_id}:{user_sub}:{conversation_id}"


__all__ = [
    "stable_thread_key",
    "set_current_tenant_id",
    "reset_current_tenant_id",
    "get_current_tenant_id",
]
