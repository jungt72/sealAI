from langchain_core.tools import tool
from app.services.rag.rag_orchestrator import hybrid_retrieve
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _format_hit(hit: dict, max_chars: int = 480) -> str:
    metadata = hit.get("metadata") or {}
    doc_id = metadata.get("document_id") or metadata.get("document_title") or "unknown"
    section = metadata.get("section_title") or metadata.get("chunk_title") or "Abschnitt unbekannt"
    source = metadata.get("url") or metadata.get("source") or "intern"
    score = float(hit.get("fused_score") or hit.get("vector_score") or 0.0)
    text = (hit.get("text") or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return (
        f"- Dokument: **{doc_id}** | Abschnitt: *{section}* | Score: {score:.2f}\n"
        f"{text}\n"
        f"Quelle: {source}\n"
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
    filters = {"category": category} if category else {}
    if tenant:
        filters["tenant_id"] = tenant
    if not filters:
        filters = None

    try:
        results = hybrid_retrieve(
            query=query,
            k=k,
            metadata_filters=filters,
            use_rerank=True,
            tenant=tenant,
        )
    except Exception as exc:
        logger.error("RAG retrieval failed: %s", exc)
        return f"Fehler beim Abrufen der Wissensdatenbank: {exc}"

    if not results:
        return "Keine relevanten Informationen in der Wissensdatenbank gefunden."

    output = ["**Gefundene Informationen aus der Wissensdatenbank:**"]
    for hit in results:
        output.append(_format_hit(hit))

    return "\n".join(output)


__all__ = ["search_knowledge_base"]
