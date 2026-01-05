from langchain_core.tools import tool
from app.services.rag.rag_orchestrator import hybrid_retrieve
from typing import Optional
import logging

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
) -> str:
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
    filters = {"tenant_id": tenant}
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
        return f"Fehler beim Abrufen der Wissensdatenbank: {exc}"

    retrieval_meta = dict(metrics or {})
    retrieval_meta["tenant_id"] = tenant
    if category:
        retrieval_meta["category"] = category

    if not results:
        return {
            "context": "Keine relevanten Informationen in der Wissensdatenbank gefunden.",
            "retrieval_meta": retrieval_meta,
        }

    output = ["**Gefundene Informationen aus der Wissensdatenbank:**"]
    for hit in results:
        output.append(_format_hit(hit))

    return {
        "context": "\n".join(output),
        "retrieval_meta": retrieval_meta,
    }


__all__ = ["search_knowledge_base"]
