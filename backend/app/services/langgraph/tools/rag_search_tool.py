# backend/app/services/langgraph/tools/rag_search_tool.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
from langchain_core.tools import tool
from ...rag.rag_orchestrator import hybrid_retrieve

class RagSearchInput(TypedDict, total=False):
    query: str
    tenant: Optional[str]
    k: int
    filters: Dict[str, Any]

@tool("rag_search", return_direct=False)
def rag_search_tool(query: str, tenant: Optional[str] = None, k: int = 6, **filters: Any) -> List[Dict[str, Any]]:
    """Hybrid Retrieval (Qdrant + BM25 + Rerank). Returns top-k docs with metadata and fused scores."""
    docs = hybrid_retrieve(query=query, tenant=tenant, k=k, metadata_filters=filters or None, use_rerank=True)
    return docs
