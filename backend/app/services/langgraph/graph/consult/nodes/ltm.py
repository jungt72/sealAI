from __future__ import annotations

from typing import Any, Dict, List, Optional

from ....tools import long_term_memory as ltm


def _extract_query(state: Dict[str, Any]) -> str:
    q = (state.get("query") or state.get("question") or state.get("input") or "").strip()
    if q:
        return q
    # fallback: last human text from messages
    msgs = state.get("messages") or []
    for m in reversed(msgs):
        role = (getattr(m, "type", "") or getattr(m, "role", "") or "").lower()
        content = getattr(m, "content", "")
        if isinstance(m, dict):
            role = (m.get("type") or m.get("role") or "").lower()
            content = m.get("content")
        if role in ("human", "user") and isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def ltm_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Augment state.context with user-specific LTM context from Qdrant.

    Inputs:
      - query (preferred) or last user message
      - user_id, chat_id (optional for filtering)
    Outputs:
      - context: concatenated LTM context + existing context
      - ltm_hits: optional raw hits for debugging/inspection
    """
    query = _extract_query(state)
    if not query:
        return {**state, "phase": "ltm"}

    user_id = state.get("user_id") or None
    chat_id = state.get("chat_id") or None

    ctx, hits = ltm.ltm_query(query, user=user_id, chat_id=chat_id, top_k=5, strategy="mmr")

    existing_ctx = state.get("context") or ""
    if isinstance(existing_ctx, dict):
        existing_ctx = ""
    if not isinstance(existing_ctx, str):
        existing_ctx = ""

    new_ctx_parts: List[str] = []
    if ctx:
        new_ctx_parts.append(ctx)
    if existing_ctx:
        new_ctx_parts.append(existing_ctx)
    merged_ctx = "\n\n".join([p for p in new_ctx_parts if p])

    out = {**state, "phase": "ltm"}
    if merged_ctx:
        out["context"] = merged_ctx
    # keep raw hits for optional downstream use
    out["ltm_hits"] = hits
    return out


__all__ = ["ltm_node"]

