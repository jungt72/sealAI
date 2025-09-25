# backend/app/services/langgraph/graph/consult/nodes/rag.py
"""
RAG-Node: holt Hybrid-Treffer (Qdrant + Redis BM25), baut kompakten
Kontext-String und legt beides in den State (retrieved_docs/docs, context) ab.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import structlog

from .....rag import rag_orchestrator as ro  # relativer Import

log = structlog.get_logger(__name__)


def _extract_query(state: Dict[str, Any]) -> str:
    return (
        state.get("query")
        or state.get("question")
        or state.get("user_input")
        or state.get("input")
        or ""
    )


def _extract_tenant(state: Dict[str, Any]) -> Optional[str]:
    ctx = state.get("context") or {}
    return state.get("tenant") or (ctx.get("tenant") if isinstance(ctx, dict) else None)


def _context_from_docs(docs: List[Dict[str, Any]], max_chars: int = 1200) -> str:
    """Kompakter Textkontext für Prompting (inkl. Quelle)."""
    if not docs:
        return ""
    parts: List[str] = []
    for d in docs[:6]:
        t = (d.get("text") or "").strip()
        if not t:
            continue
        src = d.get("source") or (d.get("metadata") or {}).get("source")
        if src:
            t = f"{t}\n[source: {src}]"
        parts.append(t)
    ctx = "\n\n".join(parts)
    return ctx[:max_chars]


def run_rag_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Eingänge (optional):
      - query/question/user_input/input
      - tenant bzw. context.tenant
      - rag_filters, rag_k, rag_rerank
    Ausgänge:
      - retrieved_docs/docs: List[Dict[str, Any]]
      - context: str
    """
    query = _extract_query(state)
    tenant = _extract_tenant(state)
    filters = state.get("rag_filters") or None
    k = int(state.get("rag_k") or ro.FINAL_K)
    use_rerank = bool(state.get("rag_rerank", True))

    if not query.strip():
        return {**state, "retrieved_docs": [], "docs": [], "context": "", "phase": "rag"}

    docs = ro.hybrid_retrieve(
        query=query,
        tenant=tenant,
        k=k,
        metadata_filters=filters,
        use_rerank=use_rerank,
    )

    context = state.get("context")
    if not isinstance(context, str) or not context.strip():
        context = _context_from_docs(docs)

    out = {
        **state,
        "retrieved_docs": docs,
        "docs": docs,              # Alias für nachfolgende Nodes
        "context": context,
        "phase": "rag",
    }
    try:
        log.info("[rag_node] retrieved", n=len(docs), tenant=tenant or "-", ctx_len=len(context or ""))
    except Exception:
        pass
    return out


__all__ = ["run_rag_node"]
