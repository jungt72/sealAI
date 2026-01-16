from __future__ import annotations

import logging
import os
from typing import Any, Optional

from langchain_core.tools import tool

from app.services.rag.rag_orchestrator import hybrid_retrieve
from app.services.rag.rag_safety import sanitize_rag_context

logger = logging.getLogger(__name__)


def _format_hit(hit: dict, max_chars: int = 480) -> str:
    metadata = hit.get("metadata") or {}
    doc_id = metadata.get("document_id") or metadata.get("document_title") or "unknown"
    section = metadata.get("section_title") or metadata.get("chunk_title") or "Abschnitt unbekannt"
    source = metadata.get("url") or metadata.get("source") or ""
    score = float(hit.get("fused_score") or hit.get("vector_score") or 0.0)
    text = (hit.get("text") or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    source_line = f"Quelle: {source}\n" if isinstance(source, str) and source.strip() else ""
    return (
        f"- Dokument: **{doc_id}** | Abschnitt: *{section}* | Score: {score:.2f}\n"
        f"{text}\n"
        f"{source_line}"
    )


@tool
def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    k: int = 5,
    tenant: Optional[str] = None,
) -> dict[str, Any]:
    """
    Tool für Agentic RAG: liefert Top-k-contexts aus Qdrant, inklusive Metadata.

    Args:
        query: Suchanfrage (z.B. "Eigenschaften von NBR bei 150°C")
        category: Optionaler Filter (materials, norms, troubleshooting)
        k: Trefferanzahl (default 5)
        tenant: Optionaler Tenant (wird als Payload-Filter genutzt)
    """
    if not tenant:
        raise ValueError("missing tenant_id for RAG retrieval")

    filters: dict[str, Any] = {"tenant_id": tenant}
    if category:
        filters["category"] = category

    try:
        results, metrics = hybrid_retrieve(
            query=query,
            k=k,
            metadata_filters=filters,
            use_rerank=True,
            tenant=tenant,
            return_metrics=True,
        )
    except Exception as exc:
        logger.error("RAG retrieval failed: %s", exc)
        return {
            "context": f"Fehler beim Abrufen der Wissensdatenbank: {exc}",
            "retrieval_meta": {"tenant_id": tenant, "category": category, "error": str(exc)},
        }

    retrieval_meta = dict(metrics or {})
    retrieval_meta["tenant_id"] = tenant
    if category:
        retrieval_meta["category"] = category

    if not results:
        return {
            "context": "Keine relevanten Informationen in der Wissensdatenbank gefunden.",
            "retrieval_meta": retrieval_meta,
        }

    max_sources_raw = os.getenv("RAG_MAX_SOURCES", "12")
    try:
        max_sources = int(max_sources_raw)
    except (TypeError, ValueError):
        max_sources = 12

    results_for_context = results[:max_sources] if max_sources > 0 else results

    output = ["**Gefundene Informationen aus der Wissensdatenbank:**"]
    for hit in results_for_context:
        output.append(_format_hit(hit))

    context_text = "\n".join(output)
    sanitized_text, normalized_sources, safety = sanitize_rag_context(
        context_text,
        retrieval_meta.get("sources"),
        max_sources=max_sources,
    )
    retrieval_meta["safety"] = safety
    if normalized_sources is not None:
        retrieval_meta["sources"] = normalized_sources

    return {
        "context": sanitized_text,
        "retrieval_meta": retrieval_meta,
    }


__all__ = ["search_knowledge_base"]
