from __future__ import annotations

import logging
from typing import Optional, Any, Dict, List

from langchain_core.tools import tool

from app.services.rag.rag_orchestrator import hybrid_retrieve

logger = logging.getLogger(__name__)


def _category_to_domain(category: str | None) -> str | None:
    value = str(category or "").strip().lower()
    if not value:
        return None
    mapping = {
        "materials": "material",
        "material": "material",
        "norms": "norms",
        "lifetime": "lifetime",
        "troubleshooting": "troubleshooting",
    }
    return mapping.get(value, value)


def _extract_hit_text(hit: dict) -> str:
    if not isinstance(hit, dict):
        return ""
    payload = hit.get("payload") or {}
    metadata = hit.get("metadata") or {}
    text = (
        hit.get("text")
        or hit.get("page_content")
        or payload.get("page_content")
        or metadata.get("page_content")
        or payload.get("text")
        or metadata.get("text")
        or ""
    )
    return str(text or "")


def _format_hit(hit: dict, max_chars: int = 480) -> str:
    metadata = hit.get("metadata") or {}
    doc_id = metadata.get("document_id") or metadata.get("document_title") or "unknown"
    section = metadata.get("section_title") or metadata.get("chunk_title") or "Abschnitt unbekannt"

    # Prefer explicit url/source, else filename, else empty
    source = (
        metadata.get("url")
        or metadata.get("source")
        or metadata.get("filename")
        or ""
    )

    score = float(hit.get("fused_score") or hit.get("vector_score") or 0.0)

    text = _extract_hit_text(hit).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "..."

    source_line = f"Quelle: {source}\n" if isinstance(source, str) and source.strip() else ""
    return (
        f"- Dokument: **{doc_id}** | Abschnitt: *{section}* | Score: {score:.2f}\n"
        f"{text}\n"
        f"{source_line}"
    )


def _dedupe_hits(hits: List[dict]) -> List[dict]:
    """Deduplicate by (document_id, chunk_index) if available, else by text hash."""
    seen: set[tuple[Any, Any]] = set()
    out: List[dict] = []
    for h in hits or []:
        md = h.get("metadata") or {}
        key = (md.get("document_id"), md.get("chunk_index"))
        if key == (None, None):
            key = (md.get("sha256"), (h.get("text") or "")[:64])
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


@tool
def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    k: int = 5,
    tenant: Optional[str] = None,
    tenant_id: Optional[str] = None,  # alias
    is_privileged: bool = False,
    can_read_private: Optional[bool] = None,
    is_admin: Optional[bool] = None,
) -> dict:
    """
    Tool für Agentic RAG: liefert Top-k-contexts aus Qdrant, inklusive Metadata.

    Args:
        query: Suchanfrage (z.B. "Eigenschaften von NBR bei 150°C")
        category: Optionaler Filter (materials, norms, troubleshooting)
        k: Trefferanzahl (default 5)
        tenant: Optionaler Tenant (wird als Payload-Filter genutzt)
        tenant_id: Alias für tenant (Kompatibilität zum restlichen Code/State)
        is_privileged: Legacy-Flag (True erlaubt private Treffer).
        can_read_private: explizites Admin-Flag für private Treffer.
        is_admin: Alias für can_read_private.
    """
    # Accept both tenant and tenant_id, prefer explicit tenant_id if provided
    effective_tenant = (tenant_id or tenant)
    if not effective_tenant:
        raise ValueError("missing tenant_id for RAG retrieval")

    effective_can_read_private = (
        bool(is_admin)
        if is_admin is not None
        else bool(can_read_private)
        if can_read_private is not None
        else bool(is_privileged)
    )

    # Qdrant payload layout in your system:
    #   payload.metadata.tenant_id
    #   payload.metadata.visibility  (NOT top-level visibility)
    filters: Dict[str, Any] = {}
    domain = _category_to_domain(category)
    if domain:
        filters["metadata.domain"] = domain

    # IMPORTANT: filter on metadata.visibility (your payload stores it there)
    if not effective_can_read_private:
        filters["metadata.visibility"] = "public"

    results: List[dict] = []
    metrics: Dict[str, Any] = {}

    try:
        # Primary retrieval (correct filter)
        out = hybrid_retrieve(
            query=query,
            k=k,
            metadata_filters=filters,
            use_rerank=True,
            tenant=effective_tenant,
            return_metrics=True,
        )
        results, metrics = out  # type: ignore[misc]
    except Exception as exc:
        logger.exception("RAG retrieval failed (primary): %s", exc)
        return {
            "context": f"Fehler beim Abrufen der Wissensdatenbank: {exc}",
            "retrieval_meta": {
                "tenant_id": effective_tenant,
                "retrieval_attempted": True,
                "retrieval_error": str(exc),
                "error": str(exc),
            },
        }

    # Backward-compat fallback:
    # If older points still have top-level "visibility" (rare in your case), try again.
    # This keeps the tool resilient if payload schema changes over time.
    if (not effective_can_read_private) and (not results):
        fallback_filters = dict(filters)
        fallback_filters.pop("metadata.visibility", None)
        fallback_filters["visibility"] = "public"
        try:
            out2 = hybrid_retrieve(
                query=query,
                k=k,
                metadata_filters=fallback_filters,
                use_rerank=True,
                tenant=effective_tenant,
                return_metrics=True,
            )
            results2, metrics2 = out2  # type: ignore[misc]
            if results2:
                results = results2
                metrics = metrics2 or metrics
        except Exception as exc:
            logger.debug("RAG fallback retrieval skipped/failed: %s", exc)

    results = _dedupe_hits(results)

    retrieval_meta = dict(metrics or {})
    retrieval_meta["tenant_id"] = effective_tenant
    if category:
        retrieval_meta["category"] = category
    if domain:
        retrieval_meta["domain"] = domain
    retrieval_meta["is_privileged"] = bool(effective_can_read_private)

    if not results:
        return {
            "context": "Keine relevanten Informationen in der Wissensdatenbank gefunden.",
            "retrieval_meta": retrieval_meta,
        }

    output = ["**Gefundene Informationen aus der Wissensdatenbank:**"]
    for hit in results[:k]:
        output.append(_format_hit(hit))

    return {
        "context": "\n".join(output),
        "retrieval_meta": retrieval_meta,
    }


__all__ = ["search_knowledge_base"]
