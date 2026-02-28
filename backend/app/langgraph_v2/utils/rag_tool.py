from langchain_core.tools import tool
from app.services.rag.rag_orchestrator import hybrid_retrieve
from typing import Optional
import logging
from app.mcp.knowledge_tool import query_deterministic_norms

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
    material: Optional[str] = None,
    temp: Optional[float] = None,
    pressure: Optional[float] = None,
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

    if category == "norms" and material and temp is not None and pressure is not None:
        try:
            deterministic_payload = query_deterministic_norms(
                material=material,
                temp=float(temp),
                pressure=float(pressure),
                tenant_id=tenant,
            )
        except Exception as exc:
            logger.error("Deterministic norms query failed: %s", exc)
            return f"Fehler beim deterministischen Normabgleich: {exc}"

        matches = deterministic_payload.get("matches") if isinstance(deterministic_payload, dict) else {}
        din_rows = (matches or {}).get("din_norms") or []
        material_rows = (matches or {}).get("material_limits") or []

        lines = ["**Deterministischer Normabgleich (PostgreSQL/Range-SQL):**"]
        if din_rows:
            lines.append("DIN-Normen:")
            for row in din_rows[:5]:
                lines.append(
                    f"- {row.get('norm_code')} | "
                    f"T={row.get('temperature_min_c')}..{row.get('temperature_max_c')} °C | "
                    f"P={row.get('pressure_min_bar')}..{row.get('pressure_max_bar')} bar | "
                    f"Version {row.get('version')} (ab {row.get('effective_date')})"
                )
        if material_rows:
            lines.append("Materialgrenzen:")
            for row in material_rows[:5]:
                lines.append(
                    f"- {row.get('limit_kind')}: {row.get('min_value')}..{row.get('max_value')} "
                    f"{row.get('unit') or ''} | Version {row.get('version')} (ab {row.get('effective_date')})"
                )
        if not din_rows and not material_rows:
            lines.append("Keine deterministischen Treffer fuer die angegebene Material-/Temperatur-/Druck-Kombination.")
        return "\n".join(lines)

    filters = {"tenant_id": tenant}
    if category:
        filters["category"] = category

    try:
        retrieved = hybrid_retrieve(
            query=query,
            k=k,
            metadata_filters=filters,
            use_rerank=True,
            tenant=tenant,
            return_metrics=True,
        )
        if isinstance(retrieved, tuple) and len(retrieved) == 2:
            results, metrics = retrieved
        else:
            results, metrics = retrieved, {}
    except Exception as exc:
        logger.error("RAG retrieval failed: %s", exc)
        return f"Fehler beim Abrufen der Wissensdatenbank: {exc}"

    retrieval_meta = dict(metrics or {})
    retrieval_meta["tenant_id"] = tenant
    if category:
        retrieval_meta["category"] = category

    if not results:
        return "Keine relevanten Informationen in der Wissensdatenbank gefunden."

    output = ["**Gefundene Informationen aus der Wissensdatenbank:**"]
    for hit in results:
        output.append(_format_hit(hit))

    return "\n".join(output)


__all__ = ["search_knowledge_base"]
