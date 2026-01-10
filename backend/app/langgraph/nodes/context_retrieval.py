from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import SystemMessage

from app.langgraph.state import SealAIState

logger = logging.getLogger(__name__)

hybrid_retrieve = None


def context_retrieval(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    user_query = str(slots.get("user_query") or "").strip()
    if not user_query or hybrid_retrieve is None:
        return {}
    meta = state.get("meta") or {}
    tenant = meta.get("user_id") or slots.get("tenant_id")
    if not tenant:
        logger.warning("context_retrieval_missing_tenant")
        slots["rag_status"] = "empty"
        return {"slots": slots}
    try:
        documents = hybrid_retrieve(query=user_query, tenant=tenant)
    except TypeError:
        logger.warning("context_retrieval_tenant_unsupported")
        slots["rag_status"] = "empty"
        return {"slots": slots}
    if not documents:
        slots["rag_status"] = "empty"
        return {"slots": slots}
    lines = []
    for idx, doc in enumerate(documents, start=1):
        text = str(doc.get("text") or "").strip()
        source = str(doc.get("source") or "").strip()
        header = f"[{idx}]"
        if source:
            header += f" Quelle: {source}"
        lines.append(f"{header}\n{text}")
    message = SystemMessage(content="Kontextwissen (RAG):\n" + "\n\n".join(lines), id="msg-rag-context")
    slots["rag_status"] = "success"
    return {"messages": [message], "slots": slots}


__all__ = ["context_retrieval", "hybrid_retrieve"]
