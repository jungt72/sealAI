from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def build_scope_id(*, tenant_id: str, user_id: str | None) -> str:
    """
    Constructs a consistent scope ID for data isolation.
    Format: "{tenant_id}:{user_id}" to ensure strict tenant prefixing.
    
    If user_id is missing, returns just tenant_id (optional feature), 
    but for SSE we usually need user specificity.
    Strictly forbids empty tenant_id.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for scope construction")
    
    # Ensure tenant_id is first!
    if user_id:
        return f"{tenant_id}:{user_id}"
    return tenant_id
