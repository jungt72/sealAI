from langchain_core.tools import tool
from app.services.rag.rag_orchestrator import hybrid_retrieve
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _format_hit(hit: dict, max_chars: int = 480) -> str:
    metadata = hit.get("metadata") or {}
    
    # SUPPORT BOTH V1/V2 KEYS
    doc_id = metadata.get("doc_id") or metadata.get("document_id") or "unknown"
    section = metadata.get("section") or metadata.get("section_title") or "Abschnitt unbekannt"
    source = metadata.get("source_uri") or hit.get("source") or metadata.get("url") or ""
    
    # Score key might be 'score' (V2) or 'vector_score' (V1)
    score = float(hit.get("score") or hit.get("fused_score") or 0.0)
    
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
    is_privileged: bool = False,
) -> str:
    """
    Tool f??r Agentic RAG: liefert Top-k-contexts aus Qdrant.
    """
    import sys
    print(f"[RAG_DEBUG] Tool called: query='{query}', category='{category}', tenant='{tenant}'", file=sys.stderr, flush=True)
    
    if not tenant:
        logger.error("RAG Tool: missing tenant_id")
        raise ValueError("missing tenant_id for RAG retrieval")
    
    filters = {}
    if category:
        domain_map = {
            "materials": "material",
            "norms": "standard", 
            "troubleshooting": "failure"
        }
        filters["domain"] = domain_map.get(category, category)
        logger.info(f"RAG Tool: mapped category '{category}' to filter {filters}")

    try:
        results, metrics = hybrid_retrieve(
            query=query,
            k=k,
            metadata_filters=filters,
            use_rerank=True,
            tenant=tenant,
            return_metrics=True,
        )
        logger.info(f"RAG Tool: retrieved {len(results)} results")
    except Exception as exc:
        logger.error("RAG retrieval failed: %s", exc)
        return f"Fehler beim Abrufen der Wissensdatenbank: {exc}"
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
